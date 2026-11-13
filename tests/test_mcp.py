"""Drive the MCP server in-process (same code path as stdio, no subprocess)."""

from __future__ import annotations

import asyncio
import json

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from precedent.api import Precedent
from precedent.mcp_server import build_server


@pytest.fixture(scope="module")
def server(built):
    api = Precedent(built[3])
    yield build_server(api)
    api.close()


def call(server, name, **args):
    try:
        res = asyncio.run(server.call_tool(name, args))
    except ToolError as e:  # explainable, client-visible error
        return True, str(e)
    return res.is_error, json.loads(res.content[0].text)


def test_tools_are_listed_with_read_only_hints(server):
    tools = asyncio.run(server.list_tools())
    names = {t.name for t in tools}
    assert {"preflight", "decision_status", "search_decisions", "explain_link", "cite_check", "graph_schema", "query_graph", "propose_decision"} <= names
    ro = {t.name: t.annotations.read_only_hint for t in tools}
    assert ro["preflight"] is True and ro["propose_decision"] is False


def test_preflight_flags_stale_decisions(server):
    err, out = call(server, "preflight", task="fsync policy for commits")
    assert not err
    cards = {c["id"]: c for c in out["decisions"]}
    assert cards["ADR-0003"]["standing"] == "out" and "ADR-0005" in cards


def test_preflight_needs_input_and_says_how(server):
    err, msg = call(server, "preflight")
    assert err and "task" in msg


def test_decision_status_unknown_id_is_explained(server):
    err, msg = call(server, "decision_status", decision="ADR-0999")
    assert err and "search_decisions" in msg


def test_query_graph_is_read_only_and_capped(server):
    err, out = call(server, "query_graph", cypher="MATCH (d:Decision) RETURN d.id AS id ORDER BY id", max_rows=3)
    assert not err and out["truncated"] and out["row_count"] == 3
    err, msg = call(server, "query_graph", cypher="MATCH (d:Decision) DETACH DELETE d")
    assert err and "read-only" in msg


def test_propose_commit_refused_on_read_only_server(server):
    err, msg = call(server, "propose_decision", title="x", commit=True)
    assert err and "--writable" in msg
    err, out = call(server, "propose_decision", title="Drop LRU", treats=[{"target": "ADR-0002", "kind": "SUPERSEDES", "clauses": [1]}])
    assert not err and out["verdict"] == "dry-run ok" and out["simulated_in"] == "fork"
