#!/usr/bin/env python3
"""Reproduce every number quoted in docs/evaluation.md.

    uv run python scripts/evaluate.py --repo /path/to/relate --store data/relate-adr.rl

`--repo` must be a checkout of the corpus at the commit stored in the graph (the script checks).
Nothing here calls a model or the network.
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import time
from collections import Counter
from pathlib import Path

from precedent import standing
from precedent.api import Precedent
from precedent.indexer import extract_corpus
from precedent.model import NEGATIVE_KINDS


def chain_depth(treatments, effective_only: set | None = None) -> int:
    """Longest chain A overrules B overrules C ... among negative treatments (cycles are cut)."""
    edges: dict[str, set[str]] = {}
    for t in treatments:
        if t.kind in NEGATIVE_KINDS:
            edges.setdefault(t.actor, set()).add(t.target)
    best: dict[str, int] = {}

    def depth(n: str, seen: frozenset[str]) -> int:
        if n in best:
            return best[n]
        d = 0
        for m in edges.get(n, ()):
            if m not in seen:
                d = max(d, 1 + depth(m, seen | {n}))
        best[n] = d
        return d

    return max((depth(n, frozenset()) for n in edges), default=0)


def timeit(fn, n: int) -> dict[str, float]:
    xs = []
    for i in range(n):
        t0 = time.perf_counter()
        fn(i)
        xs.append((time.perf_counter() - t0) * 1000)
    xs.sort()
    return {"p50_ms": round(statistics.median(xs), 2), "p95_ms": round(xs[int(0.95 * (len(xs) - 1))], 2), "n": n}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path, required=True)
    ap.add_argument("--store", type=Path, default=Path("data/relate-adr.rl"))
    ap.add_argument("--rename", action="append", default=["cypherlite=relate"])
    args = ap.parse_args()

    api = Precedent(args.store)
    info = api.corpus()
    head = subprocess.run(["git", "-C", str(args.repo), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    if info["commit"] != head:
        print(f"WARNING: store was built from {info['commit'][:7]} but --repo is at {head[:7]}")

    t0 = time.perf_counter()
    corpus = extract_corpus(args.repo, renames=dict(r.split("=", 1) for r in args.rename))
    report = standing.compute(corpus.decisions, corpus.treatments)
    extract_s = time.perf_counter() - t0

    neg = [t for t in corpus.treatments if t.kind in NEGATIVE_KINDS]
    declared = Counter((corpus.decisions[d].status, s.state) for d, s in report.standing.items())
    non = [d for d, s in report.standing.items() if s.state != "in_force"]
    still_open = [d for d in non if corpus.decisions[d].status in ("accepted", "proposed", "unknown")]
    dated = [t for t in corpus.treatments if corpus.decisions[t.actor].date and corpus.decisions[t.target].date]

    # --- exposure: how often would a flat top-5 hand an agent a decision that is partly/wholly out of force?
    titles = [(d.id, d.title) for d in corpus.decisions.values()]
    exposed = hits = stale_hits = 0
    for did, title in titles:
        rows = api.store.run(
            "CALL db.index.fulltext.queryNodes('decision_text', $q) YIELD node, score RETURN node.id AS id, node.standing AS standing ORDER BY score DESC LIMIT 6",
            {"q": " ".join(w for w in title.replace("`", " ").split() if w.isalnum())[:200]})
        top = [r for r in rows if r["id"] != did][:5]
        hits += len(top)
        bad = [r for r in top if r["standing"] != "in_force"]
        stale_hits += len(bad)
        exposed += 1 if bad else 0

    pf = api.preflight("add support for creating and switching between multiple databases", k=5)
    sample_ids = [d for d, _ in titles][:200]
    out = {
        "corpus": {k: info[k] for k in ("name", "commit", "decisions", "clauses", "citations")},
        "extraction": {
            "treatments": len(corpus.treatments), "by_kind": dict(Counter(t.kind for t in corpus.treatments)),
            "by_rule": dict(Counter(t.rule for t in corpus.treatments)), "negative": len(neg),
            "negative_scope": dict(Counter(t.scope for t in neg)), "extract_and_standing_seconds": round(extract_s, 2),
        },
        "standing": {
            "counts": report.counts(), "not_in_force": len(non), "not_in_force_pct": round(100 * len(non) / len(corpus.decisions), 1),
            "still_declared_accepted_or_proposed": len(still_open),
            "declared_vs_computed": {f"{a}->{b}": n for (a, b), n in sorted(declared.items())},
            "restored": sum(1 for s in report.standing.values() if s.restored), "contested": report.counts().get("contested", 0),
            "temporal_anomalies": len(report.anomalies), "dated_treatments": len(dated), "longest_overruling_chain": chain_depth(corpus.treatments),
        },
        "paths": {
            "mentions": len({p.path for p in corpus.paths}), "exist_now": len({p.path for p in corpus.paths if p.exists}),
            "resolved_after_rename": len({p.path for p in corpus.paths if not p.exists and p.current}),
        },
        "exposure_of_flat_retrieval": {
            "queries": len(titles), "top5_hits": hits, "hits_partly_or_wholly_out_of_force": stale_hits,
            "hit_share_pct": round(100 * stale_hits / max(1, hits), 1), "queries_with_at_least_one_such_hit": exposed,
            "query_share_pct": round(100 * exposed / len(titles), 1),
        },
        "preflight_example": {"decisions": [c["id"] for c in pf["decisions"]], "tokens": pf["tokens"], "warnings": len(pf["warnings"])},
        "latency": {
            "status": timeit(lambda i: api.status(sample_ids[i % len(sample_ids)]), 200),
            "search": timeit(lambda i: api.search(titles[i % len(titles)][1], 8), 200),
            "preflight": timeit(lambda i: api.preflight(titles[i % len(titles)][1], k=5), 100),
        },
        "store_bytes": args.store.stat().st_size,
    }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
