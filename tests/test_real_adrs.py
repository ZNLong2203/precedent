"""Regression tests on real decision records (a hand-read subset of relatedb/relate docs/adr)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from precedent import standing
from precedent.indexer import extract_corpus

FIXTURES = Path(__file__).parent / "fixtures" / "relate-adr"
GOLD = Path(__file__).parent.parent / "data" / "gold" / "negative_treatments_audit.jsonl"


@pytest.fixture(scope="module")
def corpus(tmp_path_factory):
    root = tmp_path_factory.mktemp("relate")
    (root / "docs" / "adr").mkdir(parents=True)
    for f in FIXTURES.glob("0*.md"):
        (root / "docs" / "adr" / f.name).write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
    return extract_corpus(root, commit="fixture")


def edge(corpus, actor, target, kind):
    return [t for t in corpus.treatments if (t.actor, t.target, t.kind) == (actor, target, kind)]


def test_clause_level_supersession_is_extracted_exactly(corpus):
    assert {t.target_clauses for t in edge(corpus, "ADR-0229", "ADR-0116", "SUPERSEDES")} == {(1, 4, 5, 7, 10)}
    assert {t.target_clauses for t in edge(corpus, "ADR-0276", "ADR-0116", "SUPERSEDES")} == {(8,)}
    assert {t.target_clauses for t in edge(corpus, "ADR-0487", "ADR-0364", "SUPERSEDES")} >= {(1, 2, 5, 6)}
    assert {t.target_clauses for t in edge(corpus, "ADR-0585", "ADR-0068", "SUPERSEDES")} >= {(6, 7)}


def test_formal_status_lines_become_whole_and_partial_supersession(corpus):
    assert any(t.scope == "whole" for t in edge(corpus, "ADR-0013", "ADR-0011", "SUPERSEDES"))
    assert any(t.rule == "status-in-part" for t in edge(corpus, "ADR-0012", "ADR-0004", "SUPERSEDES"))


@pytest.mark.parametrize(
    ("actor", "target", "kind"),
    [
        ("ADR-0115", "ADR-0069", "SUPERSEDES"),  # "the atomic self-replace ... are unchanged"
        ("ADR-0091", "ADR-0074", "WITHDRAWS"),  # "quarantining **retired** catalog pages"
        ("ADR-0492", "ADR-0307", "SUPERSEDES"),  # "the Storage text it replaces"
        ("ADR-0319", "ADR-0110", "SUPERSEDES"),  # "ADR-0110 stays ... nothing is superseded"
    ],
)
def test_known_false_positives_stay_fixed(corpus, actor, target, kind):
    assert edge(corpus, actor, target, kind) == []


def test_standing_of_the_headline_decision(corpus):
    rep = standing.compute(corpus.decisions, corpus.treatments)
    s = rep["ADR-0116"]
    assert s.state == "partial" and s.out_clauses == [1, 4, 5, 7, 8, 9, 10]  # §2, §3 and §6 remain good law
    assert s.controlling == ["ADR-0229", "ADR-0276", "ADR-0307"]
    assert rep["ADR-0011"].state == "out"
    assert not rep.anomalies


def test_every_correct_gold_edge_inside_the_fixtures_is_still_found(corpus):
    ids = set(corpus.decisions)
    missing = []
    for line in GOLD.read_text(encoding="utf-8").splitlines():
        g = json.loads(line)
        if g["label"] != "correct" or g["actor"] not in ids or g["target"] not in ids:
            continue
        if not any(t.kind == g["kind"] and t.target_clauses == tuple(g["clauses"]) for t in edge(corpus, g["actor"], g["target"], g["kind"])):
            missing.append((g["actor"], g["target"], g["kind"], g["clauses"]))
    assert not missing, f"gold edges no longer extracted: {missing}"
