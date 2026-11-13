"""The Relate-backed graph: schema, loader and a small ``Store`` wrapper.

Graph model (all of it lives in one ``.rl`` file)::

    (:Corpus)                      where the records came from (repo, commit, license)
    (:Decision)-[:HAS_CLAUSE]->(:Clause)
    (:Decision)-[:CITES {section, clauses, evidence}]->(:Decision)
    (:Decision)-[:SUPERSEDES|REVERSES|WITHDRAWS|AMENDS|REINSTATES|AFFIRMS
                 {scope, clauses, evidence, rule, confidence, effective}]->(:Decision)
    (:Decision)-[:REFERS_TO {section}]->(:CodePath {exists})
    (:Decision)-[:SIMILAR {score, cited}]->(:Decision)        # offline LSA neighbours

``standing`` / ``out_clauses`` / ``controlled_by`` on Decision and Clause are *derived* by
:mod:`precedent.standing` and written back, so plain Cypher can answer "what is still good law?".
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import relate

from . import standing as st
from .lsa import LSA
from .model import NEGATIVE_KINDS, TREATMENT_KINDS, Clause, Corpus, Decision, Treatment

TEXT_CAP = 60_000
CLAUSE_CAP = 8_000


class Store:
    """Thin wrapper over a Relate connection with dict rows and a transaction helper."""

    def __init__(self, path: str | os.PathLike[str], *, read_only: bool = False):
        self.path = str(path)
        self.read_only = read_only
        try:
            self.db = relate.connect(self.path, read_only=read_only)
        except relate.OperationalError as e:  # pragma: no cover - environment dependent
            if "locked" in str(e).lower():
                raise StoreLocked(self.path) from e
            raise

    def run(self, cypher: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        return [dict(r) for r in self.db.execute(cypher, params or {})]

    def one(self, cypher: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
        rows = self.run(cypher, params)
        return rows[0] if rows else None

    @contextlib.contextmanager
    def transaction(self, *, rollback: bool = False) -> Iterator[Store]:
        """Explicit transaction; ``rollback=True`` always rolls back (what-if / dry run)."""
        self.db.autocommit = False
        try:
            yield self
            if rollback:
                self.db.rollback()
            else:
                self.db.commit()
        except BaseException:
            self.db.rollback()
            raise
        finally:
            self.db.autocommit = True

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self.db.close()

    def __enter__(self) -> Store:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


class StoreLocked(RuntimeError):
    """Another process holds the store open for writing (Relate is single-writer)."""

    def __init__(self, path: str):
        super().__init__(
            f"{path} is locked by another process. Relate allows one writer at a time; "
            "stop the MCP server / other CLI that is writing, or open with read_only=True."
        )


SCHEMA = [
    "CREATE CONSTRAINT decision_id IF NOT EXISTS FOR (d:Decision) REQUIRE d.id IS UNIQUE",
    "CREATE CONSTRAINT clause_key IF NOT EXISTS FOR (c:Clause) REQUIRE c.key IS UNIQUE",
    "CREATE CONSTRAINT path_unique IF NOT EXISTS FOR (p:CodePath) REQUIRE p.path IS UNIQUE",
    "CREATE FULLTEXT INDEX decision_text IF NOT EXISTS FOR (d:Decision) ON EACH [d.title, d.search_text]",
    "CREATE FULLTEXT INDEX clause_text IF NOT EXISTS FOR (c:Clause) ON EACH [c.title, c.text]",
]


def vector_index_ddl(dim: int) -> str:
    return (
        "CREATE VECTOR INDEX decision_vec IF NOT EXISTS FOR (d:Decision) ON (d.embedding) "
        f"OPTIONS {{indexConfig: {{`vector.dimensions`: {dim}, `vector.similarity_function`: 'cosine'}}}}"
    )


def _gist(d: Decision, limit: int = 300) -> str:
    body = d.sections.get("decision", "") or d.sections.get("context", "")
    text = " ".join(body.replace("*", "").replace("`", "").split())
    if len(text) <= limit:
        return text
    cut = text[:limit]
    return cut[: cut.rfind(" ")] + "…" if " " in cut else cut + "…"


def search_text(d: Decision, decision_cap: int = 4000, context_cap: int = 1500) -> str:
    """What the decision-level full-text index sees: title + Decision + the start of Context.

    The full record stays in ``text`` for display; clause-level text is indexed separately, so deep
    content is still found - and decision-level queries stay fast (BM25 cost grows with indexed bytes).
    """
    return "\n".join([d.title, d.sections.get("decision", "")[:decision_cap], d.sections.get("context", "")[:context_cap]])


def _embedding_text(d: Decision) -> str:
    parts = [d.title, d.title, d.sections.get("decision", ""), d.sections.get("context", "")]
    return "\n".join(p for p in parts if p)


def build(
    corpus: Corpus,
    report: st.Report,
    out: Path,
    *,
    lsa_path: Path | None = None,
    neighbours: int = 5,
    min_similarity: float = 0.45,
) -> dict[str, int]:
    """Create ``out`` (a single ``.rl`` file) from an extracted corpus. Returns row counts."""
    out = Path(out)
    if out.exists():
        out.unlink()
    out.parent.mkdir(parents=True, exist_ok=True)

    decisions = list(corpus.decisions.values())
    lsa = LSA.fit([_embedding_text(d) for d in decisions])
    vectors = lsa.transform([_embedding_text(d) for d in decisions])
    if lsa_path:
        lsa.save(lsa_path)

    store = Store(out)
    try:
        for stmt in SCHEMA:
            store.run(stmt)
        store.run(vector_index_ddl(lsa.dim))

        store.run(
            "CREATE (:Corpus {name: $name, source_url: $url, commit: $commit, license: $license, "
            "embedding: 'lsa', embedding_dim: $dim})",
            {"name": corpus.name, "url": corpus.source_url, "commit": corpus.commit, "license": corpus.license, "dim": lsa.dim},
        )

        rows = []
        for d, vec in zip(decisions, vectors, strict=True):
            s = report[d.id]
            rows.append(
                {
                    "id": d.id, "num": d.num, "title": d.title, "path": d.path,
                    "status": d.status, "status_raw": d.status_raw, "date": d.date,
                    "text": d.text[:TEXT_CAP], "search_text": search_text(d), "gist": _gist(d), "n_clauses": len(d.clauses),
                    "standing": s.state, "out_clauses": s.out_clauses, "partial_unspecified": s.unspecified_part_out,
                    "controlled_by": s.controlling, "attackers": s.attackers, "restored": s.restored,
                    "emb": [float(x) for x in vec],
                }
            )
        for i in range(0, len(rows), 200):
            store.run(
                "UNWIND $rows AS r CREATE (d:Decision {id: r.id, num: r.num, title: r.title, path: r.path, "
                "status: r.status, status_raw: r.status_raw, date: r.date, text: r.text, search_text: r.search_text, gist: r.gist, "
                "n_clauses: r.n_clauses, standing: r.standing, out_clauses: r.out_clauses, "
                "partial_unspecified: r.partial_unspecified, controlled_by: r.controlled_by, "
                "attackers: r.attackers, restored: r.restored, embedding: vector(r.emb, $dim, FLOAT32)})",
                {"rows": rows[i : i + 200], "dim": lsa.dim},
            )

        clause_rows = []
        for d in decisions:
            s = report[d.id]
            for c in d.clauses:
                out_c = c.n in s.out_clauses
                clause_rows.append(
                    {
                        "key": f"{d.id}#{c.n}", "decision": d.id, "n": c.n, "title": c.title,
                        "text": c.text[:CLAUSE_CAP], "standing": "out" if out_c else "in_force",
                        "defeated_by": s.defeated_by.get(c.n, []),
                    }
                )
        for i in range(0, len(clause_rows), 400):
            store.run(
                "UNWIND $rows AS r MATCH (d:Decision {id: r.decision}) "
                "CREATE (d)-[:HAS_CLAUSE]->(:Clause {key: r.key, decision: r.decision, n: r.n, title: r.title, "
                "text: r.text, standing: r.standing, defeated_by: r.defeated_by})",
                {"rows": clause_rows[i : i + 400]},
            )

        cite_rows = [
            {"src": c.src, "dst": c.dst, "section": c.section, "src_clause": c.src_clause,
             "clauses": list(c.dst_clauses), "evidence": c.evidence}
            for c in corpus.citations
        ]
        for i in range(0, len(cite_rows), 500):
            store.run(
                "UNWIND $rows AS r MATCH (a:Decision {id: r.src}), (b:Decision {id: r.dst}) "
                "CREATE (a)-[:CITES {section: r.section, src_clause: r.src_clause, clauses: r.clauses, evidence: r.evidence}]->(b)",
                {"rows": cite_rows[i : i + 500]},
            )

        for kind in TREATMENT_KINDS:
            trows = [
                {"actor": t.actor, "target": t.target, "scope": t.scope, "clauses": list(t.target_clauses),
                 "evidence": t.evidence, "rule": t.rule, "confidence": t.confidence,
                 "affirmed": list(t.affirmed_clauses), "reported_in": t.reported_in,
                 "effective": st.treatment_key(t) in report.effective}
                for t in corpus.treatments if t.kind == kind
            ]
            if trows:
                store.run(
                    "UNWIND $rows AS r MATCH (a:Decision {id: r.actor}), (b:Decision {id: r.target}) "
                    f"CREATE (a)-[:{kind} {{scope: r.scope, clauses: r.clauses, evidence: r.evidence, rule: r.rule, "
                    "confidence: r.confidence, affirmed: r.affirmed, reported_in: r.reported_in, effective: r.effective}]->(b)",
                    {"rows": trows},
                )

        paths = sorted({(p.path, p.exists, p.current) for p in corpus.paths}, key=lambda x: x[0])
        store.run(
            "UNWIND $rows AS r CREATE (:CodePath {path: r.path, exists: r.exists, current: r.current})",
            {"rows": [{"path": p, "exists": e, "current": c} for p, e, c in paths]},
        )
        store.run(
            "UNWIND $rows AS r MATCH (d:Decision {id: r.decision}), (p:CodePath {path: r.path}) "
            "CREATE (d)-[:REFERS_TO {section: r.section}]->(p)",
            {"rows": [{"decision": p.decision, "path": p.path, "section": p.section} for p in corpus.paths]},
        )

        # Offline nearest neighbours: "these two decisions talk about the same thing".
        sims = vectors @ vectors.T
        cited = {(c.src, c.dst) for c in corpus.citations} | {(c.dst, c.src) for c in corpus.citations}
        sim_rows = []
        ids = [d.id for d in decisions]
        for i, a in enumerate(ids):
            order = np.argsort(-sims[i])
            n = 0
            for j in order:
                if j == i:
                    continue
                score = float(sims[i, j])
                if score < min_similarity or n >= neighbours:
                    break
                sim_rows.append({"a": a, "b": ids[j], "score": round(score, 4), "cited": (a, ids[j]) in cited})
                n += 1
        for i in range(0, len(sim_rows), 500):
            store.run(
                "UNWIND $rows AS r MATCH (a:Decision {id: r.a}), (b:Decision {id: r.b}) "
                "CREATE (a)-[:SIMILAR {score: r.score, cited: r.cited}]->(b)",
                {"rows": sim_rows[i : i + 500]},
            )
        stats = {
            "decisions": len(decisions), "clauses": len(clause_rows), "citations": len(cite_rows),
            "treatments": len(corpus.treatments), "code_paths": len(paths), "similar": len(sim_rows),
        }
    finally:
        store.close()
    return stats


# --------------------------------------------------------------------------- read the model back
def load_model(store: Store) -> tuple[dict[str, Decision], list[Treatment]]:
    """Rebuild the minimal model (ids, clause numbers, dates, treatments) from the graph.

    Reads *the current transaction state*, so a what-if that has written but not committed is
    visible to :func:`precedent.standing.compute`.
    """
    decisions: dict[str, Decision] = {}
    for r in store.run(
        "MATCH (d:Decision) OPTIONAL MATCH (d)-[:HAS_CLAUSE]->(c:Clause) "
        "RETURN d.id AS id, d.num AS num, d.title AS title, d.status AS status, d.date AS date, d.path AS path, collect(c.n) AS ns"
    ):
        decisions[r["id"]] = Decision(
            id=r["id"], num=r["num"], title=r["title"], path=r["path"] or "", status_raw=None,
            status=r["status"] or "unknown", date=r["date"],
            clauses=[Clause(n, f"clause {n}", "") for n in sorted(x for x in r["ns"] if x is not None)],
        )
    treatments: list[Treatment] = []
    for r in store.run(
        f"MATCH (a:Decision)-[t:{'|'.join(TREATMENT_KINDS)}]->(b:Decision) "
        "RETURN a.id AS actor, b.id AS target, type(t) AS kind, t.scope AS scope, t.clauses AS clauses, t.evidence AS evidence, "
        "t.rule AS rule, t.confidence AS confidence, t.affirmed AS affirmed, t.reported_in AS reported_in"
    ):
        treatments.append(
            Treatment(r["actor"], r["target"], r["kind"], tuple(r["clauses"] or ()), r["evidence"] or "", r["rule"] or "",
                      r["confidence"] or 0.0, r["reported_in"] or r["actor"], tuple(r["affirmed"] or ()), r["scope"] == "whole")
        )
    return decisions, treatments


def write_back(store: Store, decisions: dict[str, Decision], report: st.Report, only: set[str] | None = None) -> None:
    """Persist derived standing (Decision/Clause properties and the ``effective`` flag on treatments)."""
    rows = []
    clause_rows = []
    for did, d in decisions.items():
        if only is not None and did not in only:
            continue
        s = report[did]
        rows.append({"id": did, "standing": s.state, "out": s.out_clauses, "unspec": s.unspecified_part_out,
                     "by": s.controlling, "attackers": s.attackers, "restored": s.restored})
        for c in d.clauses:
            clause_rows.append({"key": f"{did}#{c.n}", "standing": "out" if c.n in s.out_clauses else "in_force", "by": s.defeated_by.get(c.n, [])})
    store.run(
        "UNWIND $rows AS r MATCH (d:Decision {id: r.id}) SET d.standing = r.standing, d.out_clauses = r.out, "
        "d.partial_unspecified = r.unspec, d.controlled_by = r.by, d.attackers = r.attackers, d.restored = r.restored", {"rows": rows})
    if clause_rows:
        store.run("UNWIND $rows AS r MATCH (c:Clause {key: r.key}) SET c.standing = r.standing, c.defeated_by = r.by", {"rows": clause_rows})
    # effective flags: recompute for every negative treatment
    for kind in NEGATIVE_KINDS:
        eff = [
            {"actor": t.actor, "target": t.target, "clauses": list(t.target_clauses), "effective": st.treatment_key(t) in report.effective}
            for t in report.treatments if t.kind == kind
        ]
        if eff:
            store.run(
                f"UNWIND $rows AS r MATCH (a:Decision {{id: r.actor}})-[t:{kind}]->(b:Decision {{id: r.target}}) "
                "WHERE t.clauses = r.clauses SET t.effective = r.effective", {"rows": eff})
