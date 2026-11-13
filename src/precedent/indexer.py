"""End-to-end indexing: decision records on disk -> a persistent Relate store."""

from __future__ import annotations

import subprocess
from pathlib import Path

from . import graph, standing
from .model import Corpus
from .parse_adr import parse_directory
from .paths import extract_paths, tracked_files
from .treatments import extract


def git_commit(repo: Path) -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=True, timeout=20
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def extract_corpus(
    repo: Path,
    adr_dir: str = "docs/adr",
    *,
    name: str | None = None,
    source_url: str = "",
    license_id: str = "",
    commit: str | None = None,
    renames: dict[str, str] | None = None,
) -> Corpus:
    repo = Path(repo).resolve()
    decisions, units = parse_directory(repo / adr_dir, repo)
    if not decisions:
        raise SystemExit(f"no numbered decision records (NNNN-*.md) found in {repo / adr_dir}")
    citations, treatments = extract(decisions, units)
    paths = extract_paths(units, tracked_files(repo), renames)
    return Corpus(
        name=name or repo.name,
        source_url=source_url,
        commit=commit or git_commit(repo),
        license=license_id,
        decisions=decisions,
        citations=citations,
        treatments=treatments,
        paths=paths,
    )


def index(
    repo: Path,
    out: Path,
    adr_dir: str = "docs/adr",
    *,
    name: str | None = None,
    source_url: str = "",
    license_id: str = "",
    commit: str | None = None,
    lsa_path: Path | None = None,
    renames: dict[str, str] | None = None,
) -> tuple[Corpus, standing.Report, dict[str, int]]:
    corpus = extract_corpus(repo, adr_dir, name=name, source_url=source_url, license_id=license_id, commit=commit, renames=renames)
    report = standing.compute(corpus.decisions, corpus.treatments)
    stats = graph.build(corpus, report, Path(out), lsa_path=lsa_path)
    return corpus, report, stats
