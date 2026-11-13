"""Parse a directory of markdown decision records (ADR style) into :class:`Decision` objects.

The parser is deliberately forgiving: records in the wild disagree about headings,
status syntax and numbering.  It understands

* ``- **Status**: Accepted`` / ``Status: Accepted`` / a ``## Status`` section,
* the usual ``## Context / Decision / Consequences / Alternatives considered`` sections,
* a ``## Later references`` section (decisions that touched this one afterwards),
* numbered clauses inside ``## Decision`` (``1. **Title.** text`` or ``### 1. Title``).
"""

from __future__ import annotations

import re
from pathlib import Path

from .model import Clause, Decision, Unit

ADR_REF = re.compile(r"\bADR[- ](\d{1,4})\b", re.IGNORECASE)
LINK_REF = re.compile(r"\]\((?:\./|\.\./adr/)?(\d{4})-[\w.\-]+\.md")
FIELD = re.compile(r"^-\s+\*\*([A-Za-z][A-Za-z ]*?)\*\*:\s*(.*)$")
PLAIN_STATUS = re.compile(r"^Status:\s*(.+)$", re.MULTILINE)
DATE = re.compile(r"(\d{4}-\d{2}-\d{2})")
H2 = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
CLAUSE_LINE = re.compile(r"^(\d{1,2})\.\s+(.*)$")
CLAUSE_HEADING = re.compile(r"^#{3,4}\s+(\d{1,2})[.)]?\s+(.*)$")
LIST_ITEM = re.compile(r"^\s{0,3}(?:[-*+]|\d{1,2}[.)])\s+")

SECTION_ALIASES = {
    "context": "context",
    "decision": "decision",
    "consequences": "consequences",
    "alternatives considered": "alternatives",
    "alternatives": "alternatives",
    "later references": "later",
    "status": "status",
}


def adr_id(num: int) -> str:
    return f"ADR-{num:04d}"


def normalise_status(raw: str | None) -> str:
    if not raw:
        return "unknown"
    s = raw.strip().lower()
    if s.startswith("superseded in part") or "superseded in part" in s:
        return "superseded_in_part"
    if s.startswith("superseded"):
        return "superseded"
    if s.startswith(("accepted", "approved", "adopted")):
        return "accepted"
    if s.startswith(("proposed", "draft")):
        return "proposed"
    if s.startswith(("rejected", "declined")):
        return "rejected"
    if s.startswith(("deprecated", "withdrawn", "obsolete")):
        return "withdrawn"
    return "unknown"


def refs_in(text: str) -> list[int]:
    """All decision numbers referenced in ``text`` (``ADR-0116`` or a link to ``0116-x.md``)."""
    found = [int(m) for m in ADR_REF.findall(text)] + [int(m) for m in LINK_REF.findall(text)]
    seen: dict[int, None] = {}
    for n in found:
        seen.setdefault(n, None)
    return list(seen)


def _split_sections(text: str) -> tuple[str, dict[str, str]]:
    """Return (header block, {normalised section name: body})."""
    matches = list(H2.finditer(text))
    if not matches:
        return text, {}
    header = text[: matches[0].start()]
    sections: dict[str, str] = {}
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        name = SECTION_ALIASES.get(m.group(1).strip().lower(), "other")
        body = text[m.end() : end].strip("\n")
        sections[name] = (sections[name] + "\n\n" + body) if name in sections else body
    return header, sections


def _header_fields(header: str) -> dict[str, str]:
    """``- **Key**: value`` lines (with indented continuation lines) from the header block."""
    fields: dict[str, str] = {}
    current: str | None = None
    for line in header.splitlines():
        m = FIELD.match(line)
        if m:
            current = m.group(1).strip().lower()
            fields[current] = m.group(2).strip()
        elif current and line.startswith("  ") and line.strip():
            fields[current] += " " + line.strip()
        elif not line.strip():
            current = None
        else:
            current = None
    return fields


def _title(text: str, num: int) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            t = line[2:].strip()
            t = re.sub(r"^(?:ADR[- ]?)?0*%d\s*[:.\-–—]?\s*" % num, "", t, flags=re.IGNORECASE)
            return t.strip() or line[2:].strip()
    return f"Decision {num}"


def _parse_clauses(decision_body: str) -> list[Clause]:
    """Numbered top-level clauses of the Decision section (1, 2, 3 ... strictly increasing)."""
    lines = decision_body.splitlines()
    starts: list[tuple[int, int, str]] = []  # (line index, n, first-line text)
    last = 0
    in_fence = False
    for i, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        if in_fence:
            continue
        m = CLAUSE_LINE.match(line) or CLAUSE_HEADING.match(line)
        if m and int(m.group(1)) == last + 1:
            last = int(m.group(1))
            starts.append((i, last, m.group(2).strip()))
    clauses: list[Clause] = []
    for k, (i, n, first) in enumerate(starts):
        end = starts[k + 1][0] if k + 1 < len(starts) else len(lines)
        body = "\n".join([first, *lines[i + 1 : end]]).strip()
        bold = re.match(r"\*\*(.+?)\*\*", first)
        if bold:
            title = bold.group(1).strip().rstrip(".")
        else:
            title = re.sub(r"[*`#]", "", first).strip()
            title = " ".join(title.split()[:10])
        clauses.append(Clause(n=n, title=title, text=body))
    return clauses


def _units(decision: str, section: str, body: str, clauses: list[Clause] | None = None) -> list[Unit]:
    """Split a section body into paragraph / list-item units, remembering the clause they sit in."""
    units: list[Unit] = []
    clause_no: int | None = None
    clause_starts = {c.text.splitlines()[0].strip(): c.n for c in clauses or []}
    buf: list[str] = []
    in_fence = False

    def flush() -> None:
        text = " ".join(" ".join(buf).split())
        if text:
            units.append(Unit(decision, section, clause_no, text))
        buf.clear()

    for line in body.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            flush()
            continue
        if in_fence:
            continue
        stripped = line.strip()
        if not stripped:
            flush()
            continue
        if section == "decision":
            m = CLAUSE_LINE.match(line) or CLAUSE_HEADING.match(line)
            if m and m.group(2).strip() in clause_starts:
                flush()
                clause_no = clause_starts[m.group(2).strip()]
        if LIST_ITEM.match(line) or stripped.startswith("#"):
            flush()
        buf.append(re.sub(r"^\s{0,3}(?:[-*+]|\d{1,2}[.)])\s+", "", stripped) if LIST_ITEM.match(line) else stripped)
    flush()
    return units


def parse_decision(path: Path, repo_rel: str) -> tuple[Decision, list[Unit]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    m = re.match(r"(\d{3,4})-", path.name)
    if not m:
        raise ValueError(f"not a numbered decision record: {path.name}")
    num = int(m.group(1))
    did = adr_id(num)

    header, sections = _split_sections(text)
    fields = _header_fields(header)

    status_raw = fields.get("status")
    if status_raw is None:
        pm = PLAIN_STATUS.search(header) or PLAIN_STATUS.search(text[:2500])
        status_raw = pm.group(1).strip() if pm else None
    if status_raw is None and sections.get("status"):
        status_raw = next((ln.strip() for ln in sections["status"].splitlines() if ln.strip()), None)

    date = None
    if fields.get("date"):
        dm = DATE.search(fields["date"])
        date = dm.group(1) if dm else None
    if date is None and status_raw:
        dm = DATE.search(status_raw)
        date = dm.group(1) if dm else None

    clauses = _parse_clauses(sections.get("decision", ""))
    decision = Decision(
        id=did,
        num=num,
        title=_title(text, num),
        path=repo_rel,
        status_raw=status_raw,
        status=normalise_status(status_raw),
        date=date,
        sections=sections,
        clauses=clauses,
        text=text,
    )

    units: list[Unit] = []
    # Header fields that carry relations are treated as units of their own.
    for key, value in fields.items():
        if key in {"later references", "amended", "amends", "supersedes", "superseded by", "related"}:
            sec = "later" if key == "later references" else "header"
            units.append(Unit(did, sec, None, f"{key.title()}: {value}"))
    if status_raw:
        units.append(Unit(did, "status", None, f"Status: {status_raw}"))
    for name in ("context", "decision", "consequences", "alternatives", "later", "other"):
        body = sections.get(name)
        if body:
            units.extend(_units(did, name, body, clauses if name == "decision" else None))
    return decision, units


def parse_directory(adr_dir: Path, repo_root: Path) -> tuple[dict[str, Decision], list[Unit]]:
    decisions: dict[str, Decision] = {}
    units: list[Unit] = []
    for path in sorted(adr_dir.glob("*.md")):
        if not re.match(r"\d{3,4}-", path.name):
            continue
        rel = path.relative_to(repo_root).as_posix()
        decision, us = parse_decision(path, rel)
        decisions[decision.id] = decision
        units.extend(us)
    return decisions, units
