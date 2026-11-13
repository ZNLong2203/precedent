"""Integration tests against a real Relate store (single `.rl` file)."""

from __future__ import annotations

import pytest

from precedent.api import Precedent, canonical_id
from precedent.graph import Store


@pytest.fixture(scope="module")
def p(built):
    api = Precedent(built[3])
    yield api
    api.close()


def test_store_is_a_single_file_with_expected_counts(built):
    _corpus, _report, stats, out = built
    assert out.is_file() and out.suffix == ".rl"
    assert stats["decisions"] == 7 and stats["clauses"] == 6


def test_persisted_indexes_and_constraints(built):
    with Store(built[3], read_only=True) as s:
        kinds = {r["type"] for r in s.run("SHOW INDEXES YIELD type RETURN type")}
        assert {"FULLTEXT", "VECTOR"} <= kinds


def test_canonical_id():
    assert canonical_id("116") == "ADR-0116" == canonical_id("adr 116") == canonical_id("ADR-0116")
    with pytest.raises(ValueError):
        canonical_id("nonsense")


def test_status_verdicts(p):
    one = p.status("ADR-0001")
    assert one["standing"] == "in_force" and one["restored"]
    assert "restored" in one["verdict"]
    assert [t["actor"] for t in one["treated_by"] if t["kind"] == "SUPERSEDES"] == ["ADR-0003"]
    three = p.status("3")
    assert three["standing"] == "out" and three["controlled_by"] == ["ADR-0005"]
    assert "Follow ADR-0005" in three["verdict"]
    with pytest.raises(KeyError):
        p.status("ADR-0999")


def test_declared_vs_computed_mismatch(p):
    # ADR-0003 is declared Accepted but was reversed by ADR-0005
    assert "computed out of force" in p.status("ADR-0003")["declared_vs_computed"]
    assert p.status("ADR-0002")["declared_vs_computed"] is None


def test_search_is_hybrid_and_finds_the_fsync_decision(p):
    hits = p.search("batch fsync every 100 ms", k=3)
    assert hits and hits[0]["id"] in {"ADR-0003", "ADR-0001"}
    assert {"fulltext"} <= set(hits[0]["matched_by"])


def test_preflight_by_path_returns_governing_decisions(p):
    out = p.preflight(paths=["src/store/wal.rs"], budget_tokens=2000, k=5)
    ids = [c["id"] for c in out["decisions"]]
    assert "ADR-0001" in ids and "ADR-0002" in ids
    assert out["tokens"] > 0


def test_preflight_pulls_in_the_controlling_authority_of_stale_decisions(p):
    out = p.preflight(task="fsync policy for commits", k=6)
    cards = {c["id"]: c for c in out["decisions"]}
    # the reversed relaxation is shown as out of force, and the reversal is pulled in
    assert cards["ADR-0003"]["standing"] == "out"
    assert "ADR-0005" in cards
    assert any("ADR-0003" in w for w in out["warnings"])


def test_explain_finds_the_shortest_path(p):
    e = p.explain("ADR-0001", "ADR-0005")
    assert e["connected"] and e["length"] == 2
    assert [d["id"] for d in e["decisions"]] == ["ADR-0001", "ADR-0003", "ADR-0005"]


def test_second_opener_is_refused_with_a_clear_error(built, tmp_path):
    import shutil

    from precedent.graph import StoreLocked

    copy = tmp_path / "copy.rl"
    shutil.copy(built[3], copy)
    writer = Store(copy)
    try:
        with pytest.raises(StoreLocked):
            Store(copy, read_only=True)
    finally:
        writer.close()
    with Store(copy, read_only=True) as reader, Store(copy, read_only=True) as reader2:  # many readers are fine
        assert reader.one("MATCH (d:Decision) RETURN count(d) AS n")["n"] == reader2.one("MATCH (d:Decision) RETURN count(d) AS n")["n"]
