"""Export the store for the browser explorer (``docs/``).

The explorer loads this JSON into **Relate compiled to WebAssembly** and then answers every question
with Cypher in the tab - the data below is exactly what the `.rl` file holds (minus the long texts).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from . import __version__
from .api import Precedent
from .model import TREATMENT_KINDS

_FENCE = re.compile(r"```.*?```", re.DOTALL)


def clause_body(text: str, limit: int = 520) -> str:
    """The clause as running prose for the explorer: no code fences, list markers or links, no leading title."""
    t = _FENCE.sub(" … ", text or "")
    t = "\n".join(ln for ln in t.splitlines() if not ln.lstrip().startswith("|"))  # markdown tables
    t = re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", t, flags=re.MULTILINE)
    t = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", t)
    t = " ".join(t.split())
    t = re.sub(r"^\*\*[^*]+\*\*\s*", "", t)  # the title is shown as the heading
    if len(t) <= limit:
        return t
    cut = t[:limit]
    return cut[: max(cut.rfind(". "), cut.rfind(" "))].rstrip(" ,;:") + " …"


def export(api: Precedent, out_dir: Path) -> dict[str, int]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    s = api.store
    corpus = api.corpus()

    clause_titles: dict[str, list[str]] = {}
    clauses = s.run("MATCH (c:Clause) RETURN c.key AS key, c.decision AS decision, c.n AS n, c.title AS title, c.text AS text, c.standing AS standing, c.defeated_by AS defeated_by ORDER BY c.decision, c.n")
    for c in clauses:
        clause_titles.setdefault(c["decision"], []).append(c["title"])
        c["body"] = clause_body(c.pop("text"))

    decisions = []
    for d in s.run(
        "MATCH (d:Decision) RETURN d.id AS id, d.num AS num, d.title AS title, d.status AS status, d.status_raw AS status_raw, d.date AS date, "
        "d.standing AS standing, d.out_clauses AS out_clauses, d.controlled_by AS controlled_by, d.attackers AS attackers, d.restored AS restored, "
        "d.n_clauses AS n_clauses, d.gist AS gist, d.path AS path, d.embedding AS emb ORDER BY d.num"
    ):
        emb = d.pop("emb")
        d["emb"] = [round(float(x), 3) for x in emb.values] if emb is not None else None
        d["text"] = " ".join([d["title"] or "", d["gist"] or "", *clause_titles.get(d["id"], [])])
        decisions.append(d)

    cites = s.run(
        "MATCH (a:Decision)-[c:CITES]->(b:Decision) WHERE c.section IN ['decision', 'consequences', 'later'] "
        "RETURN a.id AS src, b.id AS dst, c.section AS section, c.clauses AS clauses")
    treatments = s.run(
        f"MATCH (a:Decision)-[t:{'|'.join(TREATMENT_KINDS)}]->(b:Decision) "
        "RETURN type(t) AS kind, a.id AS actor, b.id AS target, t.scope AS scope, t.clauses AS clauses, t.evidence AS evidence, "
        "t.confidence AS confidence, t.rule AS rule, t.effective AS effective ORDER BY b.num, a.num")
    paths = s.run(
        "MATCH (d:Decision)-[r:REFERS_TO]->(p:CodePath) WHERE r.section IN ['decision', 'consequences'] "
        "RETURN d.id AS decision, p.path AS path, p.exists AS exists, p.current AS current")

    doc: dict[str, Any] = {
        "meta": {
            "name": corpus.get("name"), "source_url": corpus.get("source_url"), "commit": corpus.get("commit"), "license": corpus.get("license"),
            "standing": corpus["standing"], "decisions": corpus["decisions"], "generated_by": f"precedent {__version__}",
            "embedding_dim": len(next((d["emb"] for d in decisions if d["emb"]), [])),
        },
        "decisions": decisions, "clauses": clauses, "cites": cites, "treatments": treatments, "paths": paths,
    }
    (out_dir / "graph.json").write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return {"decisions": len(decisions), "edges": len(cites) + len(treatments), "bytes": (out_dir / "graph.json").stat().st_size}
