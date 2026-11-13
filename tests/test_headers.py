"""Status-header patches: a stale 'Accepted' becomes what later decisions made of it, without changing any verdict."""

from __future__ import annotations

import shutil
import subprocess

import pytest

from precedent import headers, standing
from precedent import lint as lint_mod
from precedent.api import Precedent
from precedent.indexer import extract_corpus, index


@pytest.fixture(scope="module")
def api(built):
    a = Precedent(built[3])
    yield a
    a.close()


def test_the_only_stale_header_is_found_with_its_evidence(api):
    plan = headers.suggest(api)
    assert plan["manual"] == [] and [f["id"] for f in plan["fixes"]] == ["ADR-0003"]
    fx = plan["fixes"][0]
    assert (fx["old_status"], fx["new_status"], fx["kind"]) == ("Accepted", "Superseded by ADR-0005", "field")
    assert fx["evidence"][0]["by"] == "ADR-0005" and "reverses ADR-0003" in fx["evidence"][0]["quote"]


def test_the_diff_applies_with_git(api, repo, tmp_path):
    diff = headers.render_diff(api, headers.suggest(api)["fixes"])
    assert "+- **Status**: Superseded by ADR-0005" in diff and "--- a/docs/adr/0003-relax-fsync.md" in diff
    work = tmp_path / "w"
    shutil.copytree(repo, work)
    subprocess.run(["git", "init", "-q"], cwd=work, check=True)
    subprocess.run(["git", "apply", "-"], input=diff, text=True, cwd=work, check=True)
    assert "- **Status**: Superseded by ADR-0005" in (work / "docs/adr/0003-relax-fsync.md").read_text()


def test_patching_is_idempotent_for_standing_and_clears_the_lint(api, repo, tmp_path):
    work = tmp_path / "w"
    shutil.copytree(repo, work)
    before = standing.compute(*[getattr(extract_corpus(work), k) for k in ("decisions", "treatments")])
    res = headers.apply(headers.suggest(api)["fixes"], work)
    assert res == {"patched": ["ADR-0003"], "missing_file": [], "drifted": []}
    corpus = extract_corpus(work)
    after = standing.compute(corpus.decisions, corpus.treatments)
    assert {d: (s.state, s.out_clauses) for d, s in before.standing.items()} == {d: (s.state, s.out_clauses) for d, s in after.standing.items()}

    out = tmp_path / "patched.rl"
    index(work, out, name="patched", lsa_path=out.with_suffix(".lsa.npz"))
    p = Precedent(out)
    try:
        assert not lint_mod.run(p, categories=["stale-status"])["findings"]
        assert headers.suggest(p) == {"fixes": [], "manual": []}
    finally:
        p.close()


def test_a_record_that_changed_since_indexing_is_left_alone(api, repo, tmp_path):
    work = tmp_path / "w"
    shutil.copytree(repo, work)
    f = work / "docs/adr/0003-relax-fsync.md"
    f.write_text(f.read_text().replace("- **Status**: Accepted", "- **Status**: Proposed"))
    res = headers.apply(headers.suggest(api)["fixes"], work)
    assert res["drifted"] == ["ADR-0003"] and "Proposed" in f.read_text()


@pytest.mark.parametrize(
    ("text", "kind", "old"),
    [
        ("# 1. T\n\n- **Status**: Accepted\n- **Date**: 2026-01-01\n\n## Context\n", "field", "Accepted"),
        ("# 1. T\n\n- **Status**: Accepted, pending\n  the board's review\n- **Date**: x\n\n## Context\n", "field", "Accepted, pending the board's review"),
        ("# ADR-1: T\n\nStatus: Proposed\nDate: 2026-01-01\n\n## Context\n", "plain", "Proposed"),
        ("# 1. T\n\n## Status\n\nAccepted\n\n## Context\n", "section", "Accepted"),
    ],
)
def test_the_status_line_is_found_in_every_style_the_parser_reads(text, kind, old):
    loc = headers.locate(text)
    assert loc and (loc["kind"], loc["old"]) == (kind, old)


def test_line_endings_and_continuation_lines_survive_patching():
    text = "# 1. T\r\n\r\n- **Status**: Accepted, pending\r\n  review\r\n- **Date**: x\r\n\r\n## Context\r\n"
    fx = {"old_status": "Accepted, pending review", "new_status": "Superseded in part by ADR-0002 (§1)"}
    assert headers.patched(text, fx) == "# 1. T\r\n\r\n- **Status**: Superseded in part by ADR-0002 (§1)\r\n- **Date**: x\r\n\r\n## Context\r\n"
    assert headers.patched(text.replace("pending", "other"), fx) is None


def test_declaration_wording_follows_the_corpus_convention():
    assert headers.declaration("out", ["ADR-0013", "ADR-0028"], {}) == "Superseded by ADR-0013, ADR-0028"
    assert headers.declaration("partial", ["ADR-0229", "ADR-0276"], {"ADR-0229": [1, 4, 5], "ADR-0276": [8]}) == "Superseded in part by ADR-0229 (§1, §4–5), ADR-0276 (§8)"
    assert headers.declaration("partial", ["ADR-0050"], {}) == "Superseded in part by ADR-0050"
