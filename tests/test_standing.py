from __future__ import annotations

from precedent import standing
from precedent.model import Clause, Decision, Treatment


def D(i: int, status="accepted", date=None, clauses=0) -> Decision:
    return Decision(f"ADR-{i:04d}", i, f"d{i}", f"{i}.md", status, status, date,
                    clauses=[Clause(n, f"c{n}", "") for n in range(1, clauses + 1)])


def T(actor: int, target: int, kind="SUPERSEDES", clauses=(), whole=False) -> Treatment:
    return Treatment(f"ADR-{actor:04d}", f"ADR-{target:04d}", kind, tuple(clauses), "evidence", "test", 0.9, f"ADR-{actor:04d}", (), whole)


def decisions(*ds: Decision) -> dict[str, Decision]:
    return {d.id: d for d in ds}


def test_unattacked_decisions_are_in_force():
    rep = standing.compute(decisions(D(1), D(2)), [])
    assert rep.counts() == {"in_force": 2}


def test_clause_level_supersession_is_partial():
    rep = standing.compute(decisions(D(1, clauses=3), D(2)), [T(2, 1, clauses=[2])])
    s = rep["ADR-0001"]
    assert s.state == "partial" and s.out_clauses == [2] and s.controlling == ["ADR-0002"]


def test_whole_supersession_is_out():
    rep = standing.compute(decisions(D(1, clauses=2), D(2)), [T(2, 1, whole=True)])
    assert rep["ADR-0001"].state == "out"


def test_unspecified_partial_does_not_guess_a_clause():
    rep = standing.compute(decisions(D(1, clauses=2), D(2)), [T(2, 1)])
    s = rep["ADR-0001"]
    assert s.state == "partial" and s.out_clauses == [] and s.unspecified_part_out


def test_reversal_of_a_reversal_restores_the_original():
    # 1 is superseded by 2, but 2 is itself reversed by 3  =>  1 is good law again
    rep = standing.compute(decisions(D(1), D(2), D(3)), [T(2, 1, whole=True), T(3, 2, "REVERSES", whole=True)])
    assert rep["ADR-0002"].state == "out"
    assert rep["ADR-0001"].state == "in_force" and rep["ADR-0001"].restored
    assert ("ADR-0002", "ADR-0001", "SUPERSEDES", ()) not in rep.effective  # the dead attack did not take effect


def test_chain_of_three_alternates():
    rep = standing.compute(decisions(D(1), D(2), D(3), D(4)),
                           [T(2, 1, whole=True), T(3, 2, whole=True), T(4, 3, whole=True)])
    assert [rep[f"ADR-000{i}"].state for i in (1, 2, 3, 4)] == ["out", "in_force", "out", "in_force"]


def test_mutual_supersession_is_contested_not_resolved_arbitrarily():
    rep = standing.compute(decisions(D(1), D(2)), [T(2, 1, whole=True), T(1, 2, whole=True)])
    assert rep["ADR-0001"].state == rep["ADR-0002"].state == "contested"


def test_attacker_only_partly_defeated_is_still_alive():
    # 2 attacks 1; 3 only attacks clause 1 of 2 -> 2 keeps clause 2 and therefore its force
    rep = standing.compute(decisions(D(1), D(2, clauses=2), D(3)), [T(2, 1, whole=True), T(3, 2, clauses=[1])])
    assert rep["ADR-0001"].state == "out"
    assert rep["ADR-0002"].state == "partial"


def test_rejected_decisions_cannot_supersede():
    rep = standing.compute(decisions(D(1), D(2, status="rejected")), [T(2, 1, whole=True)])
    assert rep["ADR-0001"].state == "in_force"


def test_temporal_anomaly_is_ignored_and_reported():
    ds = decisions(D(1, date="2026-05-01"), D(2, date="2026-01-01"))
    rep = standing.compute(ds, [T(2, 1, whole=True)])
    assert rep["ADR-0001"].state == "in_force" and len(rep.anomalies) == 1


def test_non_negative_treatments_never_take_anything_out():
    rep = standing.compute(decisions(D(1, clauses=2), D(2)), [T(2, 1, "AMENDS", clauses=[1])])
    assert rep["ADR-0001"].state == "in_force"


def test_fixture_corpus(built):
    _corpus, report, _stats, _out = built
    assert report["ADR-0001"].state == "in_force" and report["ADR-0001"].restored  # ADR-0003 was reversed by ADR-0005
    assert report["ADR-0003"].state == "out"
    assert report["ADR-0004"].state == "out"
    assert report["ADR-0006"].state == "in_force"
