"""The guard reviews agent-drafted decisions inside a Relate transaction."""

from __future__ import annotations

import shutil

import pytest

from precedent import guard
from precedent.api import Precedent
from precedent.indexer import extract_corpus


@pytest.fixture()
def rw(built, tmp_path):
    """A writable copy of the fixture store (guard tests commit)."""
    dst = tmp_path / "w.rl"
    shutil.copy(built[3], dst)
    shutil.copy(built[3].with_suffix(".lsa.npz"), dst.with_suffix(".lsa.npz"))
    api = Precedent(dst, read_only=False)
    yield api
    api.close()


def test_dry_run_on_a_read_only_store_forks_instead_of_touching_it(built):
    api = Precedent(built[3])  # read-only
    try:
        before = api.corpus()["decisions"]
        out = guard.propose(api, {"title": "Drop LRU", "treats": [{"target": "ADR-0002", "kind": "SUPERSEDES", "clauses": [1]}]})
        assert out["simulated_in"] == "fork" and not out["committed"]
        assert out["standing_changes"][0]["decision"] == "ADR-0002" and out["standing_changes"][0]["after"] == "partial"
        assert api.corpus()["decisions"] == before  # original untouched
        with pytest.raises(PermissionError):
            guard.propose(api, {"title": "x"}, commit=True)
    finally:
        api.close()


def test_citing_an_out_of_force_clause_is_rejected_with_a_fix(rw):
    out = guard.propose(rw, {"title": "Use batched fsync", "cites": [{"target": "ADR-0003"}]})
    assert out["verdict"] == "rejected"
    e = out["errors"][0]
    assert e["code"] == "cites-out-of-force" and "ADR-0005" in e["fix"]


def test_overruling_something_others_rely_on_needs_acknowledgement(rw):
    draft = {"title": "Group commit", "treats": [{"target": "ADR-0001", "kind": "SUPERSEDES", "clauses": [2], "reason": "batch the fsync"}]}
    out = guard.propose(rw, draft)
    assert out["verdict"] == "rejected"
    assert out["errors"][0]["code"] == "impact-unacknowledged"
    assert {d["id"] for d in out["dependents"]} >= {"ADR-0002", "ADR-0007"}

    ok = guard.propose(rw, {**draft, "acknowledge_impact": True})
    assert ok["verdict"] == "dry-run ok" and not ok["committed"]
    change = next(c for c in ok["standing_changes"] if c["decision"] == "ADR-0001")
    assert (change["before"], change["after"], change["out_clauses_after"]) == ("in_force", "partial", [2])
    # dry run really rolled back
    assert rw.status("ADR-0001")["standing"] == "in_force"
    assert rw.store.one("MATCH (d:Decision) RETURN count(d) AS n")["n"] == 7


def test_unknown_ids_and_clauses_are_explained(rw):
    out = guard.propose(rw, {"title": "x", "treats": [{"target": "ADR-0999"}, {"target": "ADR-0001", "clauses": [9]}]})
    codes = {e["code"] for e in out["errors"]}
    assert codes == {"unknown-target", "unknown-clause"}
    assert all(e["fix"] for e in out["errors"])


def test_commit_records_the_decision_and_updates_standing(rw):
    out = guard.propose(
        rw,
        {"title": "Group commit", "treats": [{"target": "ADR-0001", "kind": "SUPERSEDES", "clauses": [2], "reason": "batch the fsync"}], "acknowledge_impact": True},
        commit=True,
    )
    assert out["committed"] and out["id"] == "ADR-0008"
    s = rw.status("ADR-0001")
    assert s["standing"] == "partial" and s["controlled_by"] == ["ADR-0008"] and s["out_clauses"] == [2]
    assert rw.status("ADR-0008")["declared"] == "proposed"


def test_rendered_markdown_round_trips_through_the_extractor(rw, repo, tmp_path):
    draft = {"title": "Group commit", "body": "Batch the fsync.", "treats": [{"target": "ADR-0001", "kind": "SUPERSEDES", "clauses": [2], "reason": "batch the fsync"}],
             "cites": [{"target": "ADR-0002", "clauses": [1]}], "acknowledge_impact": True}
    out = guard.propose(rw, draft)
    clone = tmp_path / "clone"
    shutil.copytree(repo, clone)
    (clone / "docs" / "adr" / "0008-group-commit.md").write_text(out["markdown"], encoding="utf-8")
    corpus = extract_corpus(clone)
    sup = [t for t in corpus.treatments if t.actor == "ADR-0008" and t.kind == "SUPERSEDES"]
    assert len(sup) == 1 and sup[0].target == "ADR-0001" and sup[0].target_clauses == (2,)
    assert any(c.src == "ADR-0008" and c.dst == "ADR-0002" and c.dst_clauses == (1,) for c in corpus.citations)
