#!/usr/bin/env python3
"""How well does `find_overlaps` find what a draft really overrules?  (no model, no network)

    uv run python scripts/evaluate_overlaps.py --store data/relate-adr.rl

Ground truth comes from the corpus itself: every decision that took *named clauses* of an earlier
decision out of force is a known case.  Its own text is the "draft" (with every ADR number, §-reference
and link removed so the answer is not handed over), and we ask:

  * is the overruled decision among the top 5 / 8 / 10 candidates?
  * of its overruled clauses, how many does the finder flag as overlapping?
  * how selective is it: what share of that decision's clauses does it flag?  (Flagging everything
    would have perfect recall and be useless, so recall is reported next to selectivity.)

Thresholds are tuned on the even-numbered cases and reported on the odd-numbered ones.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from precedent import overlaps as ov
from precedent.api import Precedent

REF = re.compile(r"\[[^\]]*\]\([^)]*\)|\bADR[- ]?\d{1,4}\b|§\s*\d+(?:\s*[–-]\s*\d+)?|\bDecisions?\s+\d+(?:\s*(?:,|and|–|-)\s*\d+)*|\b0\d{3}\b", re.IGNORECASE)


def draft_of(text: str) -> str:
    m = re.search(r"^##\s+Decision\s*$(.*?)(?=^##\s|\Z)", text, re.MULTILINE | re.DOTALL)
    body = m.group(1) if m else text
    return " ".join(REF.sub(" ", body).split())[:1500]


def cases(api: Precedent) -> list[dict]:
    rows = api.store.run(
        "MATCH (a:Decision)-[t:SUPERSEDES|REVERSES|WITHDRAWS {effective: true}]->(b:Decision) WHERE size(t.clauses) > 0 "
        "RETURN a.id AS actor, a.text AS text, b.id AS target, collect(t.clauses) AS cl")
    by: dict[tuple[str, str], dict] = {}
    for r in sorted(rows, key=lambda r: (r["actor"], r["target"])):
        c = by.setdefault((r["actor"], r["target"]), {"actor": r["actor"], "target": r["target"], "draft": draft_of(r["text"]), "clauses": set()})
        c["clauses"] |= {n for lst in r["cl"] for n in lst}
    return [c for c in by.values() if len(c["draft"]) > 120]


def run(api: Precedent, items: list[dict], n_clauses: dict[str, int]) -> dict:
    hit1 = hit5 = hit8 = hit10 = 0
    recall, share, flagged_any = [], [], 0
    for c in items:
        res = ov.find_overlaps(api, c["draft"], limit=10)["candidates"]
        ids = [x["id"] for x in res]
        hit5 += c["target"] in ids[:5]
        hit8 += c["target"] in ids[:8]
        hit10 += c["target"] in ids
        hit1 += ids[:1] == [c["target"]]
        if c["target"] in ids:
            rec = res[ids.index(c["target"])]
            flagged = set(rec["overlaps_live"]) | set(rec["overlaps_dead"])
            recall.append(len(flagged & c["clauses"]) / len(c["clauses"]))
            share.append(len(flagged) / max(1, n_clauses[c["target"]]))
            flagged_any += bool(flagged)
    n = len(items)
    return {
        "cases": n, "target_is_first_pct": round(100 * hit1 / n, 1), "target_in_top5_pct": round(100 * hit5 / n, 1),
        "target_in_top8_pct": round(100 * hit8 / n, 1), "target_in_top10_pct": round(100 * hit10 / n, 1),
        "clause_recall_when_found_pct": round(100 * sum(recall) / max(1, len(recall)), 1),
        "share_of_clauses_flagged_pct": round(100 * sum(share) / max(1, len(share)), 1),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", type=Path, default=Path("data/relate-adr.rl"))
    ap.add_argument("--no-sweep", action="store_true", help="evaluate the shipped thresholds only")
    args = ap.parse_args()
    api = Precedent(args.store)
    items = cases(api)
    n_clauses = {r["id"]: r["n"] for r in api.store.run("MATCH (d:Decision) RETURN d.id AS id, d.n_clauses AS n")}
    tune, test = items[0::2], items[1::2]
    out: dict = {"thresholds": {"STRONG": ov.STRONG, "RELATIVE": ov.RELATIVE}}
    if not args.no_sweep:
        sweep = []
        for strong in (0.30, 0.35, 0.40, 0.45, 0.50):
            for rel in (0.6, 0.7, 0.8, 0.9):
                ov.STRONG, ov.RELATIVE = strong, rel
                r = run(api, tune, n_clauses)
                sweep.append({"STRONG": strong, "RELATIVE": rel, **{k: r[k] for k in ("clause_recall_when_found_pct", "share_of_clauses_flagged_pct")}})
        out["tuning_sweep_even_cases"] = sweep
        ov.STRONG, ov.RELATIVE = out["thresholds"]["STRONG"], out["thresholds"]["RELATIVE"]
    out["held_out_odd_cases"] = run(api, test, n_clauses)
    out["all_cases"] = run(api, items, n_clauses)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
