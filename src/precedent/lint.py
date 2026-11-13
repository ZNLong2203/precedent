"""``cite-check``: structural findings a graph makes cheap and prose makes invisible.

Each finding is a dict ``{category, severity, decisions, message, evidence?}`` so it can be printed,
posted as a PR comment, or handed to an agent as a to-do list.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from .api import STATE_WORD, Precedent, _ranges
from .model import NEGATIVE_KINDS

NEG = "|".join(NEGATIVE_KINDS)

CATEGORIES = {
    "stale-status": "Declared Accepted/Proposed, but later decisions took clauses out of force",
    "reliance-on-superseded": "A decision written after a supersession still relies on the superseded clause",
    "proposed-but-relied-on": "Status says Proposed, yet several accepted decisions build on it",
    "ghost-path": "A decision in force points at a file or directory that no longer exists",
    "uncited-similar": "Two live decisions are near-duplicates but never cite each other",
    "temporal-anomaly": "A treatment whose actor is dated before its target (renumbering? typo?)",
    "contested": "Mutually conflicting treatments that need a human ruling",
    "low-confidence": "Negative treatments inferred with low confidence - worth a glance",
}


def _later(src: dict[str, Any], ctrl: dict[str, Any]) -> bool:
    if src.get("date") and ctrl.get("date"):
        return src["date"] > ctrl["date"]
    return src["num"] > ctrl["num"]


def run(p: Precedent, *, categories: list[str] | None = None, limit: int = 12) -> dict[str, Any]:
    want = set(categories or CATEGORIES)
    store = p.store
    info = {r["id"]: r for r in store.run(
        "MATCH (d:Decision) RETURN d.id AS id, d.num AS num, d.date AS date, d.title AS title, d.status AS declared, "
        "d.status_raw AS declared_raw, d.standing AS standing, d.out_clauses AS out_clauses, d.controlled_by AS controlled_by")}
    findings: list[dict[str, Any]] = []

    if "stale-status" in want:
        for d in info.values():
            if d["standing"] in ("partial", "out") and d["declared"] in ("accepted", "proposed", "unknown"):
                where = _ranges(d["out_clauses"] or []) or "a part"
                findings.append({
                    "category": "stale-status", "severity": "warn", "decisions": [d["id"]],
                    "message": f"{d['id']} says '{d['declared_raw'] or d['declared']}' but {where} is out of force ({', '.join(d['controlled_by'] or [])}): {STATE_WORD[d['standing']].lower()}.",
                })

    if "reliance-on-superseded" in want:
        rows = store.run(
            "MATCH (s:Decision)-[c:CITES]->(d:Decision) WHERE c.section IN ['decision', 'consequences'] AND size(c.clauses) > 0 "
            "AND any(n IN c.clauses WHERE n IN d.out_clauses) "
            "RETURN s.id AS src, d.id AS dst, [n IN c.clauses WHERE n IN d.out_clauses] AS stale, c.evidence AS evidence")
        for r in rows:
            ctrl = [info[c] for c in info[r["dst"]]["controlled_by"] or [] if c in info]
            if r["src"] in (info[r["dst"]]["controlled_by"] or []) or not ctrl:
                continue
            if all(_later(info[r["src"]], c) for c in ctrl):
                findings.append({
                    "category": "reliance-on-superseded", "severity": "warn", "decisions": [r["src"], r["dst"]],
                    "message": f"{r['src']} (after {', '.join(c['id'] for c in ctrl)}) still relies on {r['dst']} {_ranges(r['stale'])}, which is out of force.",
                    "evidence": r["evidence"],
                })

    if "proposed-but-relied-on" in want:
        rows = store.run(
            "MATCH (s:Decision)-[c:CITES]->(d:Decision {status: 'proposed'}) WHERE c.section IN ['decision', 'consequences'] "
            "WITH d, collect(DISTINCT s.id) AS citers WHERE size(citers) >= 3 RETURN d.id AS id, citers ORDER BY size(citers) DESC")
        for r in rows:
            findings.append({
                "category": "proposed-but-relied-on", "severity": "info", "decisions": [r["id"]],
                "message": f"{r['id']} is still 'Proposed' but {len(r['citers'])} decisions build on it (e.g. {', '.join(r['citers'][:3])}) - de facto accepted?",
            })

    if "ghost-path" in want:
        rows = store.run(
            "MATCH (d:Decision)-[r:REFERS_TO]->(p:CodePath {exists: false}) WHERE p.current IS NULL AND d.standing <> 'out' "
            "AND r.section IN ['decision', 'consequences'] RETURN d.id AS id, collect(p.path) AS gone ORDER BY size(collect(p.path)) DESC")
        for r in rows:
            findings.append({
                "category": "ghost-path", "severity": "info", "decisions": [r["id"]],
                "message": f"{r['id']} points at {len(r['gone'])} path(s) that no longer exist: {', '.join(r['gone'][:3])}{' …' if len(r['gone']) > 3 else ''}",
            })

    if "uncited-similar" in want:
        rows = store.run(
            "MATCH (a:Decision)-[s:SIMILAR {cited: false}]->(b:Decision) WHERE s.score >= 0.8 AND a.num < b.num "
            "AND a.standing <> 'out' AND b.standing <> 'out' RETURN a.id AS a, b.id AS b, s.score AS score ORDER BY s.score DESC")
        for r in rows:
            findings.append({
                "category": "uncited-similar", "severity": "info", "decisions": [r["a"], r["b"]],
                "message": f"{r['a']} and {r['b']} are {r['score']:.0%} similar but neither cites the other - duplicate or conflict?",
            })

    if "temporal-anomaly" in want:
        rows = store.run(
            f"MATCH (a:Decision)-[t:{NEG}]->(b:Decision) WHERE a.date IS NOT NULL AND b.date IS NOT NULL AND a.date < b.date "
            "RETURN a.id AS actor, a.date AS adate, type(t) AS kind, b.id AS target, b.date AS bdate")
        for r in rows:
            findings.append({
                "category": "temporal-anomaly", "severity": "warn", "decisions": [r["actor"], r["target"]],
                "message": f"{r['actor']} ({r['adate']}) {r['kind'].lower()} {r['target']} ({r['bdate']}) but is dated earlier; the treatment was ignored.",
            })

    if "contested" in want:
        for d in info.values():
            if d["standing"] == "contested":
                findings.append({"category": "contested", "severity": "warn", "decisions": [d["id"]],
                                 "message": f"{d['id']} is the subject of mutually conflicting treatments."})

    if "low-confidence" in want:
        rows = store.run(
            f"MATCH (a:Decision)-[t:{NEG} {{effective: true}}]->(b:Decision) WHERE t.confidence < 0.7 "
            "RETURN a.id AS actor, type(t) AS kind, b.id AS target, t.confidence AS conf, t.evidence AS evidence ORDER BY t.confidence")
        for r in rows:
            findings.append({
                "category": "low-confidence", "severity": "info", "decisions": [r["actor"], r["target"]],
                "message": f"{r['actor']} {r['kind'].lower()} {r['target']} was inferred with confidence {r['conf']:.2f}.",
                "evidence": r["evidence"],
            })

    by_cat: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for f in findings:
        by_cat[f["category"]].append(f)
    summary = {c: len(by_cat.get(c, [])) for c in CATEGORIES if c in want}
    shown = [f for c in CATEGORIES if c in want for f in by_cat.get(c, [])[:limit]]
    return {"summary": summary, "total": len(findings), "shown": len(shown), "findings": shown, "categories": {c: CATEGORIES[c] for c in summary}}
