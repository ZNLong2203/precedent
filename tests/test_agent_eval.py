"""The agent experiment's own plumbing: parsing model answers and the paired test (no model is called)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("agent_eval", Path(__file__).resolve().parents[1] / "scripts" / "agent_eval.py")
agent_eval = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(agent_eval)  # type: ignore[union-attr]


@pytest.mark.parametrize(
    "answer",
    [
        '[{"task_id": "T01", "relies_on": []}]',
        '```json\n[{"task_id": "T01", "relies_on": []}]\n```',
        'Here is my answer:\n[{"task_id": "T01", "relies_on": []}]\nHope that helps.',
    ],
)
def test_the_json_array_is_found_in_a_fenced_or_chatty_answer(answer):
    assert agent_eval._array(answer) == [{"task_id": "T01", "relies_on": []}]


def test_sign_test_matches_exact_binomial_values():
    assert agent_eval.sign_test_p(0, 0) == 1.0
    assert agent_eval.sign_test_p(5, 5) == 1.0
    assert agent_eval.sign_test_p(8, 0) == pytest.approx(2 / 256)
    assert agent_eval.sign_test_p(0, 8) == agent_eval.sign_test_p(8, 0)
    assert agent_eval.sign_test_p(1, 7) == pytest.approx(2 * (1 + 8) / 256)


def test_sections_split_header_from_the_decision_and_cap_the_length():
    text = "# ADR-1: T\n\nStatus: Accepted\n\n## Context\n\nwhy\n\n## Decision\n\n" + "1. **A.** " + "x" * 5000 + "\n\n## Consequences\n\nz\n"
    head, decision = agent_eval.sections(text)
    assert head.startswith("# ADR-1: T") and "Context" not in head
    assert decision.startswith("1. **A.**") and len(decision) == agent_eval.DOC_CAP


def test_every_task_names_a_decision_with_a_dead_and_a_live_clause():
    store = pytest.importorskip("precedent.api")
    api = store.Precedent("data/relate-adr.rl")
    try:
        for t in json.loads(Path("data/agent-eval/tasks.json").read_text()):
            standings = {r["s"] for r in api.store.run("MATCH (:Decision {id: $i})-[:HAS_CLAUSE]->(c:Clause) RETURN c.standing AS s", {"i": t["decision"]})}
            assert standings == {"in_force", "out"}, t["id"]
    finally:
        api.close()
