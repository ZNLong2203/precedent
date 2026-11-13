#!/usr/bin/env python3
"""Prove that `precedent fix-status` is safe on a real corpus.

    uv run python scripts/verify_headers.py --repo /path/to/relate --store data/relate-adr.rl

Steps (nothing here calls a model or the network):
  1. work on a throw-away copy of the checkout's records,
  2. compute standing for the untouched records,
  3. apply every suggested header edit to the copy,
  4. recompute standing from the edited records and compare, decision by decision,
  5. count how many headers still disagree with the computed standing.

Safe means: the diff applies, no decision changes standing, and no stale header is left.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from precedent import headers, standing
from precedent.api import Precedent
from precedent.indexer import extract_corpus
from precedent.model import NEGATIVE_KINDS


def snapshot(repo: Path, renames: dict[str, str]):
    corpus = extract_corpus(repo, renames=renames)
    report = standing.compute(corpus.decisions, corpus.treatments)
    return corpus, {d: (s.state, tuple(s.out_clauses), tuple(sorted(s.controlling))) for d, s in report.standing.items()}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path, required=True)
    ap.add_argument("--store", type=Path, default=Path("data/relate-adr.rl"))
    ap.add_argument("--rename", action="append", default=["cypherlite=relate"])
    args = ap.parse_args()
    renames = dict(r.split("=", 1) for r in args.rename)

    api = Precedent(args.store)
    plan = headers.suggest(api)
    diff = headers.render_diff(api, plan["fixes"])

    work = Path(tempfile.mkdtemp(prefix="precedent-headers-"))
    try:
        shutil.copytree(args.repo / "docs", work / "docs")
        subprocess.run(["git", "init", "-q"], cwd=work, check=True)
        check = subprocess.run(["git", "apply", "--check", "-"], input=diff, text=True, cwd=work, capture_output=True)
        before_corpus, before = snapshot(work, renames)
        result = headers.apply(plan["fixes"], work)
        after_corpus, after = snapshot(work, renames)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    pairs = lambda c: {(t.actor, t.target) for t in c.treatments if t.kind in NEGATIVE_KINDS}  # noqa: E731
    lost, gained = pairs(before_corpus) - pairs(after_corpus), pairs(after_corpus) - pairs(before_corpus)
    changed = {d: (before[d], after[d]) for d in before if before[d] != after.get(d)}
    still_stale = [d for d, dec in after_corpus.decisions.items() if after[d][0] != "in_force" and dec.status in headers.OPEN_STATUSES]
    out = {
        "stale_headers_before": sum(1 for d, dec in before_corpus.decisions.items() if before[d][0] != "in_force" and dec.status in headers.OPEN_STATUSES),
        "suggested": len(plan["fixes"]), "needs_a_human": len(plan["manual"]),
        "git_apply_check": "ok" if check.returncode == 0 else check.stderr.strip()[:300],
        "applied": {k: len(v) for k, v in result.items()},
        "decisions_whose_standing_changed": len(changed),
        "examples_of_change": {d: {"before": b, "after": a} for d, (b, a) in list(changed.items())[:3]},
        "stale_headers_after": len(still_stale),
        "treatments_before_after": [len(before_corpus.treatments), len(after_corpus.treatments)],
        "overruling_pairs_lost": sorted(lost), "overruling_pairs_gained": sorted(gained),
    }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
