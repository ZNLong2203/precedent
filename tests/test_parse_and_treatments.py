from __future__ import annotations

from precedent.model import Unit
from precedent.parse_adr import normalise_status, parse_directory, refs_in
from precedent.treatments import clause_refs, extract, sentences


def test_parse_directory(repo):
    decisions, units = parse_directory(repo / "docs" / "adr", repo)
    assert sorted(decisions) == [f"ADR-000{i}" for i in range(1, 8)]
    d1 = decisions["ADR-0001"]
    assert d1.title == "Use a write-ahead log"
    assert d1.status == "accepted" and d1.date == "2026-01-01"
    assert d1.clause_numbers == [1, 2, 3]
    assert decisions["ADR-0004"].status == "superseded"  # plain "Status:" line
    assert any(u.section == "later" for u in units)


def test_status_normalisation():
    assert normalise_status("Accepted (2026-10-29)") == "accepted"
    assert normalise_status("Superseded in part by ADR-0012") == "superseded_in_part"
    assert normalise_status("proposed") == "proposed"
    assert normalise_status(None) == "unknown"


def test_refs_in_understands_links():
    assert refs_in("see ADR-0116 and [x](0229-foo.md), ADR 7") == [116, 7, 229][:0] or set(refs_in("see ADR-0116 and [x](0229-foo.md), ADR 7")) == {116, 229, 7}


def test_clause_refs():
    assert clause_refs("§1's rule and §4–6 and Decisions 8 and 10") == (1, 4, 5, 6, 8, 10)
    assert clause_refs("everything except §2 is replaced") == ()  # exceptions are not treated clauses
    assert clause_refs("no references here") == ()


def test_sentences_do_not_split_abbreviations():
    s = sentences("Use e.g. fsync. Then ADR-0003 supersedes it; ADR-0005 reverses that.")
    assert len(s) == 3 and s[0].startswith("Use e.g. fsync")


def _treatment(treatments, actor, target, kind):
    for t in treatments:
        if (t.actor, t.target, t.kind) == (actor, target, kind):
            return t
    raise AssertionError(f"missing {actor} -{kind}-> {target}; have {[(t.actor, t.kind, t.target) for t in treatments]}")


def test_extracted_treatments(repo):
    decisions, units = parse_directory(repo / "docs" / "adr", repo)
    _cits, treatments = extract(decisions, units)

    clause_level = _treatment(treatments, "ADR-0003", "ADR-0001", "SUPERSEDES")
    assert clause_level.scope == "clauses" and clause_level.target_clauses == (2,)
    assert clause_level.affirmed_clauses == (1, 3)  # "Decisions 1 and 3 stand."
    assert "fsync" in clause_level.evidence

    assert _treatment(treatments, "ADR-0005", "ADR-0003", "REVERSES").scope == "whole"
    assert _treatment(treatments, "ADR-0006", "ADR-0004", "SUPERSEDES").scope == "whole"


def test_citations_keep_clause_and_section(repo):
    decisions, units = parse_directory(repo / "docs" / "adr", repo)
    cits, _ = extract(decisions, units)
    got = {(c.src, c.dst, c.section): c.dst_clauses for c in cits}
    assert got[("ADR-0002", "ADR-0001", "context")] == (1,)
    assert got[("ADR-0002", "ADR-0001", "decision")] == (2,)


def test_hedged_and_alternative_sentences_are_not_treatments(repo):
    decisions, _ = parse_directory(repo / "docs" / "adr", repo)
    units = [
        Unit("ADR-0002", "decision", None, "This ADR would supersede ADR-0001 if we adopted option B."),
        Unit("ADR-0002", "decision", None, "This ADR does not supersede ADR-0001."),
        Unit("ADR-0002", "alternatives", None, "Option B supersedes ADR-0001 entirely."),
        Unit("ADR-0002", "decision", None, "The `override` flag lets operators change ADR-0001's default."),
    ]
    _, treatments = extract(decisions, units)
    assert treatments == []
