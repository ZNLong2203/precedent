"""Status-header patches: make the *declared* status say what later decisions did to the record.

Decision records are never edited, so a record keeps saying ``Status: Accepted`` long after a later
decision took clauses out of force.  That is exactly what ``cite-check`` flags as ``stale-status``.
This module turns every such finding into a one-line edit in the corpus's own convention (the
Relate ADRs already use ``Superseded in part by ADR-0012``), so a maintainer can review a diff
instead of a report.

Nothing here guesses: the new line names only decisions the graph says control the record, with
the clause numbers they took out of force, and every suggestion carries the quoted sentence it
came from.  The result is *idempotent*: re-indexing the patched records produces the same
standing for every decision (checked by ``scripts/verify_headers.py``).
"""

from __future__ import annotations

import difflib
import re
from pathlib import Path
from typing import Any

from .api import Precedent, _ranges
from .parse_adr import H2

OPEN_STATUSES = ("accepted", "proposed", "unknown")
REVIEW_BELOW = 0.8  # a suggestion resting on a weaker edge than this is marked for a closer look

_FIELD = re.compile(r"^(-\s+\*\*Status\*\*:\s*)(.*)$", re.IGNORECASE)
_PLAIN = re.compile(r"^(Status:\s*)(.*)$", re.IGNORECASE)
_SECTION = re.compile(r"^##\s+Status\s*$", re.IGNORECASE)


def _body(line: str) -> str:
    return line.rstrip("\r\n")


def locate(text: str) -> dict[str, Any] | None:
    """Find the status line the parser would read: ``- **Status**:`` in the header block,
    else a plain ``Status:`` line, else the first line under ``## Status``.

    Returns ``{index, end, kind, prefix, old}``: lines ``index:end`` hold the old value (a field may
    continue on indented lines), ``prefix`` is what precedes the value on the first line.
    """
    lines = text.splitlines(keepends=True)
    m = H2.search(text)
    header_end = text[: m.start()].count("\n") if m else len(lines)
    for i, line in enumerate(lines[:header_end]):
        f = _FIELD.match(_body(line))
        if f:
            j = i + 1
            while j < len(lines) and lines[j].startswith("  ") and lines[j].strip():
                j += 1
            old = " ".join([f.group(2).strip(), *[x.strip() for x in lines[i + 1 : j]]]).strip()
            return {"index": i, "end": j, "kind": "field", "prefix": f.group(1), "old": old}
    for i, line in enumerate(lines):
        p = _PLAIN.match(_body(line))
        if p:
            return {"index": i, "end": i + 1, "kind": "plain", "prefix": p.group(1), "old": p.group(2).strip()}
    for i, line in enumerate(lines):
        if _SECTION.match(_body(line)):
            for j in range(i + 1, len(lines)):
                if lines[j].strip():
                    return {"index": j, "end": j + 1, "kind": "section", "prefix": "", "old": _body(lines[j]).strip()}
    return None


def declaration(standing: str, controllers: list[str], by_clause: dict[str, list[int]]) -> str:
    """The new status value, in the wording the corpus already uses."""
    if standing == "out":
        return "Superseded by " + ", ".join(controllers)
    parts = [f"{b} ({_ranges(by_clause[b])})" if by_clause.get(b) else b for b in controllers]
    return "Superseded in part by " + ", ".join(parts)


def suggest(api: Precedent) -> dict[str, list[dict[str, Any]]]:
    """Every decision whose header still says Accepted/Proposed/unknown although later decisions
    overruled it, with the line that would replace it.  ``fixes`` can be patched; ``manual`` needs a
    human (a contested record, or no status line to edit)."""
    rows = api.store.run(
        "MATCH (d:Decision) WHERE d.standing <> 'in_force' AND d.status IN $open "
        "RETURN d.id AS id, d.num AS num, d.title AS title, d.path AS path, d.status_raw AS declared, d.standing AS standing, "
        "d.out_clauses AS out_clauses, d.controlled_by AS controlled_by, d.text AS text ORDER BY num",
        {"open": list(OPEN_STATUSES)},
    )
    fixes: list[dict[str, Any]] = []
    manual: list[dict[str, Any]] = []
    for d in rows:
        base = {"id": d["id"], "title": d["title"], "path": d["path"], "standing": d["standing"], "declared": d["declared"]}
        if d["standing"] == "contested":
            manual.append({**base, "reason": "contested: later decisions overrule each other, so the status needs a human ruling"})
            continue
        ctrl_ids = sorted(d["controlled_by"] or [])
        if not ctrl_ids:
            manual.append({**base, "reason": "no controlling decision recorded"})
            continue
        by_clause = api._controller_clauses(d["id"])
        loc = locate(d["text"] or "")
        if loc is None:
            manual.append({**base, "reason": "the record has no status line to edit"})
            continue
        ev = api.store.run(
            "MATCH (a:Decision)-[t:SUPERSEDES|REVERSES|WITHDRAWS {effective: true}]->(:Decision {id: $id}) "
            "RETURN a.id AS by, type(t) AS treatment, t.clauses AS clauses, t.confidence AS confidence, t.evidence AS quote ORDER BY a.num, t.confidence DESC",
            {"id": d["id"]},
        )
        fixes.append({
            **base, "new_status": declaration(d["standing"], ctrl_ids, by_clause), "old_status": loc["old"], "line": loc["index"] + 1,
            "kind": loc["kind"], "min_confidence": (conf := min((e["confidence"] for e in ev), default=None)), "evidence": ev[:4],
            "review": conf is None or conf < REVIEW_BELOW,
        })
    return {"fixes": fixes, "manual": manual}


def patched(text: str, fix: dict[str, Any]) -> str | None:
    """``text`` with the status value replaced, or None if the line is no longer where the graph saw it."""
    loc = locate(text)
    if loc is None or loc["old"] != fix["old_status"]:
        return None
    lines = text.splitlines(keepends=True)
    eol = lines[loc["index"]][len(_body(lines[loc["index"]])) :] or "\n"
    lines[loc["index"] : loc["end"]] = [f"{loc['prefix']}{fix['new_status']}{eol}"]
    return "".join(lines)


def render_diff(api: Precedent, fixes: list[dict[str, Any]]) -> str:
    """One unified diff for all fixes, relative to the corpus root, ready for ``git apply``."""
    out: list[str] = []
    for fx in fixes:
        text = api.store.one("MATCH (d:Decision {id: $id}) RETURN d.text AS t", {"id": fx["id"]})["t"]
        new = patched(text, fx)
        if new is None:
            continue
        out.extend(difflib.unified_diff(text.splitlines(keepends=True), new.splitlines(keepends=True), f"a/{fx['path']}", f"b/{fx['path']}"))
    return "".join(out)


def apply(fixes: list[dict[str, Any]], repo: Path) -> dict[str, Any]:
    """Edit the records in a checkout in place.  A record whose status line changed since the store
    was built is left alone and reported, never overwritten."""
    done, missing, drifted = [], [], []
    for fx in fixes:
        f = Path(repo) / fx["path"]
        if not f.is_file():
            missing.append(fx["id"])
            continue
        with f.open(encoding="utf-8", newline="") as fh:  # keep the file's own line endings
            text = fh.read()
        new = patched(text, fx)
        if new is None:
            drifted.append(fx["id"])
            continue
        with f.open("w", encoding="utf-8", newline="") as fh:
            fh.write(new)
        done.append(fx["id"])
    return {"patched": done, "missing_file": missing, "drifted": drifted}
