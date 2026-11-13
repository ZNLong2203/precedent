#!/usr/bin/env python3
"""Render real CLI output to SVG for the README (rich's recording console; nothing is mocked)."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from rich.console import Console

import precedent.cli as cli

STORE = Path("data/relate-adr.rl")
OUT = Path("docs/img")


def record(title: str, name: str, fn) -> None:
    cli.console = Console(record=True, width=100, force_terminal=True, color_system="truecolor", highlight=False)
    fn()
    cli.console.save_svg(str(OUT / f"{name}.svg"), title=title)
    print("wrote", OUT / f"{name}.svg")


def main(only: list[str] | None = None) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    want = set(only or [])

    def rec(title: str, name: str, fn) -> None:
        if not want or name in want:
            record(title, name, fn)

    rec("precedent demo", "demo", lambda: cli.demo(store=STORE))
    rec("precedent status ADR-0116", "status", lambda: cli.status("ADR-0116", store=STORE, as_json=False))
    rec(
        "precedent preflight",
        "preflight",
        lambda: cli.preflight("add support for creating and switching between multiple databases", [], 1500, 4, STORE, False),
    )
    rec(
        "precedent overlaps",
        "overlaps",
        lambda: cli.overlaps("Allow creating and dropping additional databases at runtime instead of the three fixed namespaces", None, [], 3, STORE, False),
    )
    rec("precedent fix-status", "fix-status", lambda: cli.fix_status(False, None, False, 6, STORE, False))
    spec = {
        "title": "Allow CREATE DATABASE for tenant isolation",
        "body": "Each tenant gets its own database inside one store.",
        "treats": [{"target": "ADR-0116", "kind": "SUPERSEDES", "clauses": [3], "reason": "USE can now route to tenant databases"}],
        "cites": [{"target": "ADR-0229", "clauses": [1]}],
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(spec, f)
    rec("precedent propose (dry run)", "propose", lambda: cli.propose(f.name, False, STORE, False))
    rec("precedent cite-check", "cite-check", lambda: cli.cite_check([], 2, STORE, False, False))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
