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


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    record("precedent demo", "demo", lambda: cli.demo(store=STORE))
    record("precedent status ADR-0116", "status", lambda: cli.status("ADR-0116", store=STORE, as_json=False))
    record(
        "precedent preflight",
        "preflight",
        lambda: cli.preflight("add support for creating and switching between multiple databases", [], 1500, 4, STORE, False),
    )
    spec = {
        "title": "Allow CREATE DATABASE for tenant isolation",
        "body": "Each tenant gets its own database inside one store.",
        "treats": [{"target": "ADR-0116", "kind": "SUPERSEDES", "clauses": [3], "reason": "USE can now route to tenant databases"}],
        "cites": [{"target": "ADR-0229", "clauses": [1]}],
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(spec, f)
    record("precedent propose (dry run)", "propose", lambda: cli.propose(f.name, False, STORE, False))
    record("precedent cite-check", "cite-check", lambda: cli.cite_check([], 2, STORE, False, False))


if __name__ == "__main__":
    sys.exit(main())
