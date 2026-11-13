"""MCP server: Precedent's tools for AI agents, backed by an embedded Relate store.

Relate itself ships an MCP surface with three generic tools (``get_schema``, ``read_cypher``,
``write_cypher``).  This server sits one level higher: *intent-level* tools that return
good-law-aware, token-budgeted, provenance-carrying answers, so an agent does not have to write
Cypher to learn which decisions it must respect.  The store is opened in-process - no Relate server,
no ports.  ``query_graph`` is the read-only escape hatch for everything else.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from . import guard
from . import lint as lint_mod
from .api import Precedent

INSTRUCTIONS = """\
Precedent tells you which architecture decisions (ADRs/RFCs) are still good law.
Decision records are immutable, so later decisions quietly supersede, reverse or withdraw parts of
earlier ones; the old text still says "Accepted".  Never act on a decision's text alone.

Workflow:
1. Before changing code or designing something, call `preflight` with the task and/or the file paths.
   Treat `live_clauses` as binding, and follow the decision named in `stale_clauses[].by` instead of
   the stale text.
2. Use `decision_status` to inspect one decision (clause-level standing + the quoted evidence).
3. If your change should overrule an earlier decision, do NOT edit it: call `propose_decision`
   (dry run by default). It reports which decisions change standing and who relies on what you are
   overruling. Fix every error (each has a `fix`) before resubmitting; commit only when asked.
4. `query_graph` runs read-only Cypher for anything else (see `graph_schema`).
"""

WRITE_WORDS = re.compile(r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|FOREACH|LOAD\s+CSV|CALL\s*\{)\b|\bCALL\s+(?:db|dbms|apoc)\.(?!index\.fulltext)", re.IGNORECASE)

SCHEMA_DOC = """\
Nodes
  (:Decision {id 'ADR-0116', num, title, status (declared), status_raw, date, standing ('in_force'|'partial'|'out'|'contested'),
              out_clauses [int], controlled_by [id], n_clauses, gist, text, path})
  (:Clause {key 'ADR-0116#4', decision, n, title, text, standing ('in_force'|'out'), defeated_by [id]})
  (:CodePath {path, exists, current})      # `current` = where a historical path lives today
  (:Corpus {name, source_url, commit, license})
Relationships
  (a:Decision)-[:CITES {section, clauses [int], evidence}]->(b:Decision)
  (a:Decision)-[:SUPERSEDES|REVERSES|WITHDRAWS|AMENDS|REINSTATES|AFFIRMS {scope 'whole'|'clauses'|'partial', clauses [int],
        evidence, rule, confidence, effective: bool}]->(b:Decision)      # a treats b; `effective` = the treatment took effect
  (d:Decision)-[:HAS_CLAUSE]->(:Clause)
  (d:Decision)-[:REFERS_TO {section}]->(:CodePath)
  (a:Decision)-[:SIMILAR {score, cited}]->(b:Decision)
Indexes: fulltext `decision_text`, `clause_text`; vector `decision_vec`.
Examples
  MATCH (a:Decision)-[t:SUPERSEDES {effective: true}]->(d:Decision {id: 'ADR-0116'}) RETURN a.id, t.clauses, t.evidence
  MATCH (d:Decision) WHERE d.standing = 'partial' AND d.status = 'accepted' RETURN d.id, d.title, d.out_clauses LIMIT 20
  MATCH p = shortestPath((a:Decision {id:'ADR-0116'})-[:CITES|SUPERSEDES|REVERSES*..6]-(b:Decision {id:'ADR-0472'})) RETURN [n IN nodes(p) | n.id]
"""

READ = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)
WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False)


def build_server(api: Precedent, *, writable: bool = False) -> MCPServer:
    """Create the MCP server around an open :class:`Precedent`.

    Relate connections are *thread-affine* (DB-API ``threadsafety = 1``), so every tool is a
    coroutine: it runs on the event-loop thread, which is the thread that opened the store.  The
    queries are millisecond-scale and never ``await``, so calls are naturally serialised.
    """
    server = MCPServer("precedent", instructions=INSTRUCTIONS)

    @server.tool(annotations=READ)
    async def preflight(task: str = "", paths: list[str] | None = None, budget_tokens: int = 1800, limit: int = 6) -> dict[str, Any]:
        """Which decisions must you respect before doing `task` / touching `paths`? Returns good-law-aware
        cards: live clauses are binding; stale clauses name the decision that replaced them."""
        if not task.strip() and not paths:
            raise ToolError("give a `task` and/or `paths` (e.g. task='add multi-database support', paths=['relate/relate-storage/src/wal.rs'])")
        return api.preflight(task, paths or [], budget_tokens=max(300, min(budget_tokens, 8000)), k=max(1, min(limit, 12)))

    @server.tool(annotations=READ)
    async def decision_status(decision: str) -> dict[str, Any]:
        """Is this decision still good law? Clause-level standing, who treated it and the quoted evidence, who relies on it."""
        try:
            return api.status(decision)
        except (KeyError, ValueError) as e:
            raise ToolError(f"{e.args[0]}; use `search_decisions` to find the id") from e

    @server.tool(annotations=READ)
    async def search_decisions(query: str, limit: int = 8) -> dict[str, Any]:
        """Hybrid search (BM25 + clause BM25 + vector) over decisions; each hit carries its standing."""
        return {"results": api.search(query, max(1, min(limit, 25)))}

    @server.tool(annotations=READ)
    async def explain_link(a: str, b: str) -> dict[str, Any]:
        """Shortest path of citations/treatments between two decisions - why are they related?"""
        try:
            return api.explain(a, b)
        except ValueError as e:
            raise ToolError(str(e)) from e

    @server.tool(annotations=READ)
    async def cite_check(categories: list[str] | None = None, limit: int = 8) -> dict[str, Any]:
        """Structural findings: stale statuses, reliance on superseded clauses, ghost paths, near-duplicates..."""
        return lint_mod.run(api, categories=categories, limit=max(1, min(limit, 30)))

    @server.tool(annotations=READ)
    async def graph_schema() -> dict[str, str]:
        """The graph model and example Cypher for `query_graph`."""
        return {"schema": SCHEMA_DOC}

    @server.tool(annotations=READ)
    async def query_graph(cypher: str, parameters: dict[str, Any] | None = None, max_rows: int = 50) -> dict[str, Any]:
        """Run a READ-ONLY Cypher query. Rows are capped; a capped result says so in `truncated`."""
        if WRITE_WORDS.search(cypher):
            raise ToolError("query_graph is read-only. To add a decision use `propose_decision`; to inspect schema see `graph_schema`.")
        cap = max(1, min(max_rows, 200))
        try:
            if api.store.read_only:
                rows = api.store.run(cypher, parameters or {})
            else:  # writable store: still guarantee nothing can stick
                with api.store.transaction(rollback=True):
                    rows = api.store.run(cypher, parameters or {})
        except Exception as e:  # surface the engine's explainable error verbatim
            raise ToolError(f"Cypher failed: {e}. See `graph_schema` for labels and properties.") from e
        return {"rows": rows[:cap], "row_count": min(len(rows), cap), "truncated": len(rows) > cap}

    @server.tool(annotations=WRITE)
    async def propose_decision(
        title: str,
        body: str = "",
        context: str = "",
        treats: list[dict[str, Any]] | None = None,
        cites: list[dict[str, Any]] | None = None,
        governs: list[str] | None = None,
        acknowledge_impact: bool = False,
        commit: bool = False,
    ) -> dict[str, Any]:
        """Review a draft decision against the graph before it lands (dry run unless commit=true).
        `treats`: [{target:'ADR-0116', kind:'SUPERSEDES'|'REVERSES'|'WITHDRAWS'|'AMENDS', clauses:[1,4], reason:'...'}].
        `cites`: [{target:'ADR-0276', clauses:[1]}]. Returns errors (each with a `fix`), warnings, which decisions
        change standing, who relies on what you overrule, and the ADR markdown to save."""
        if commit and not writable:
            raise ToolError("this server was started read-only; the review can only run as a dry run. Restart with `precedent mcp --writable` to commit.")
        spec = {"title": title, "body": body, "context": context, "treats": treats or [], "cites": cites or [], "governs": governs or [], "acknowledge_impact": acknowledge_impact}
        try:
            return guard.propose(api, spec, commit=commit)
        except (guard.ProposalError, ValueError, KeyError) as e:
            raise ToolError(str(e)) from e

    return server


def serve(store: Path, *, writable: bool = False) -> None:
    api = Precedent(store, read_only=not writable)
    try:
        build_server(api, writable=writable).run("stdio")
    finally:
        api.close()
