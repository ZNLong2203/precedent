"""Before you write a decision: which clauses does the draft overlap?"""

from __future__ import annotations

import asyncio
import json

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from precedent import overlaps
from precedent.api import Precedent
from precedent.mcp_server import build_server

DRAFT = "Batch the fsync every 100 ms for bulk loads instead of calling fsync on every commit"


@pytest.fixture(scope="module")
def api(built):
    a = Precedent(built[3])
    yield a
    a.close()


def test_the_clause_a_draft_would_change_is_flagged_as_still_binding(api):
    out = overlaps.find_overlaps(api, DRAFT)
    top = out["candidates"][0]
    assert top["id"] == "ADR-0001" and top["overlaps_live"] == [2] and top["overlaps_dead"] == []
    assert out["treats_template"] == [{"target": "ADR-0001", "kind": "SUPERSEDES", "clauses": [2], "reason": ""}]
    assert "declare it in `treats`" in top["read"]


def test_a_decision_that_was_already_overruled_points_to_its_replacement(api):
    ids = {c["id"]: c for c in overlaps.find_overlaps(api, DRAFT)["candidates"]}
    stale = ids["ADR-0003"]  # relaxed fsync, reversed by ADR-0005
    assert stale["standing"] == "out" and "ADR-0005" in stale["read"]


def test_files_alone_are_enough(api):
    out = overlaps.find_overlaps(api, "", ["src/store/wal.rs"])
    assert {"ADR-0001", "ADR-0002"} <= {c["id"] for c in out["candidates"]}


def test_nothing_to_go_on_is_an_error(api):
    with pytest.raises(ValueError):
        overlaps.find_overlaps(api, "  ", [])


def test_unrelated_text_does_not_invent_overlaps(api):
    out = overlaps.find_overlaps(api, "zebra giraffe savannah migration")
    assert out["treats_template"] == [] and all(not c["overlaps_live"] for c in out["candidates"])


def test_it_is_a_read_only_mcp_tool(built):
    api = Precedent(built[3])
    try:
        server = build_server(api)
        tool = next(t for t in asyncio.run(server.list_tools()) if t.name == "find_overlaps")
        assert tool.annotations.read_only_hint is True
        res = asyncio.run(server.call_tool("find_overlaps", {"draft": DRAFT}))
        assert json.loads(res.content[0].text)["candidates"][0]["id"] == "ADR-0001"
        with pytest.raises(ToolError):
            asyncio.run(server.call_tool("find_overlaps", {}))
    finally:
        api.close()
