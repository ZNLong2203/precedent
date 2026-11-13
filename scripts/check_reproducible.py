#!/usr/bin/env python3
"""Rebuild the store from the pinned corpus into a temp file and compare its content with the committed one.

    make data-check   (or: uv run python scripts/check_reproducible.py --repo .cache/relate)

Byte-for-byte equality of a `.rl` file is not expected; the *content* (counts, standing, every treatment
edge and its evidence) must be identical, which proves the build is deterministic.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from precedent.api import Precedent
from precedent.indexer import index


def fingerprint(store: Path) -> dict:
    api = Precedent(store)
    try:
        s = api.store
        return {
            "counts": api.corpus(),
            "standing": s.run("MATCH (d:Decision) RETURN d.id AS id, d.standing AS st, d.out_clauses AS out, d.controlled_by AS by ORDER BY id"),
            "treatments": s.run(
                "MATCH (a:Decision)-[t:SUPERSEDES|REVERSES|WITHDRAWS|AMENDS|REINSTATES|AFFIRMS]->(b:Decision) "
                "RETURN a.id AS a, type(t) AS k, b.id AS b, t.clauses AS c, t.scope AS sc, t.evidence AS ev, t.effective AS eff ORDER BY a, k, b, c"),
        }
    finally:
        api.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path, required=True)
    ap.add_argument("--store", type=Path, default=Path("data/relate-adr.rl"))
    args = ap.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "rebuilt.rl"
        index(args.repo, out, name="relatedb/relate", source_url="https://github.com/relatedb/relate", license_id="Apache-2.0",
              lsa_path=out.with_suffix(".lsa.npz"), renames={"cypherlite": "relate"})
        a, b = fingerprint(args.store), fingerprint(out)
    for key in a:
        if a[key] != b[key]:
            print(f"MISMATCH in {key}")
            return 1
    print(f"reproducible: {a['counts']['decisions']} decisions, {len(a['treatments'])} treatments identical")
    return 0


if __name__ == "__main__":
    sys.exit(main())
