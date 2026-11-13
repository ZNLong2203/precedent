"""Find repository paths mentioned in decision records and check them against the real tree."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from .model import PathRef, Unit

_EXTS = (
    "rs", "py", "md", "toml", "sh", "go", "java", "swift", "js", "ts", "tsx", "c", "h", "cpp", "cypher",
    "yml", "yaml", "json", "txt", "lock", "wasm", "ipynb", "html", "css", "mjs", "cjs", "kt", "rb", "cs",
)
# A backticked token that looks like a path: has a slash and a known extension, or ends with "/".
_TOKEN = re.compile(r"`([^`\s]{3,200})`")
_LINE_SUFFIX = re.compile(r"(?::\d+(?:-\d+)?|::[\w:<>]+|#L\d+(?:-L\d+)?)$")
_SECTION_RANK = {"decision": 0, "consequences": 1, "later": 2, "context": 3, "other": 4, "header": 5, "status": 6, "alternatives": 7}


def normalise(token: str) -> str | None:
    t = token.strip()
    if t.startswith(("http://", "https://", "git@", "$", "-", "~/")) or "://" in t:
        return None
    t = _LINE_SUFFIX.sub("", t)
    t = t.removeprefix("./").rstrip(",.;:)")
    if "/" not in t or any(ch in t for ch in "<>{}*|=()"):
        return None
    if t.endswith("/"):
        return t if re.fullmatch(r"[\w.\-@+/]+", t) and t.count("/") >= 1 else None
    if not re.fullmatch(r"[\w.\-@+/]+", t):
        return None
    ext = t.rsplit(".", 1)[-1].lower() if "." in t.rsplit("/", 1)[-1] else ""
    return t if ext in _EXTS else None


def tracked_files(repo: Path) -> set[str] | None:
    """Files in the repository (``git ls-files`` when possible, otherwise a directory walk)."""
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "ls-files"], capture_output=True, text=True, check=True, timeout=60
        ).stdout
        files = {line for line in out.splitlines() if line}
        if files:
            return files
    except (OSError, subprocess.SubprocessError):
        pass
    if repo.is_dir():
        return {p.relative_to(repo).as_posix() for p in repo.rglob("*") if p.is_file() and ".git" not in p.parts}
    return None


def exists_in(path: str, files: set[str], dirs: set[str]) -> bool:
    if path.endswith("/"):
        return path.rstrip("/") in dirs
    return path in files


def resolve_current(path: str, files: set[str], dirs: set[str], renames: dict[str, str], index: dict[str, list[str]]) -> str | None:
    """Where does a (possibly historical) path live today?

    1. the path itself, 2. after applying ``renames`` (``{"old-name": "new-name"}``),
    3. a *unique* tracked file that ends with the longest matching tail of the path.
    """
    if exists_in(path, files, dirs):
        return path
    renamed = path
    for old, new in renames.items():
        renamed = renamed.replace(old, new)
    if renamed != path and exists_in(renamed, files, dirs):
        return renamed
    if renamed.endswith("/"):
        return None
    comps = renamed.split("/")
    for k in range(len(comps), 1, -1):
        tail = "/".join(comps[-k:])
        hits = [f for f in index.get(comps[-1], []) if f == tail or f.endswith("/" + tail)]
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            return None  # ambiguous: refuse to guess
    return None


def extract_paths(units: list[Unit], files: set[str] | None, renames: dict[str, str] | None = None) -> list[PathRef]:
    """One :class:`PathRef` per (decision, path), keeping the most authoritative section."""
    renames = renames or {}
    index: dict[str, list[str]] = {}
    for f in files or ():
        index.setdefault(f.rsplit("/", 1)[-1], []).append(f)
    dirs: set[str] = set()
    if files:
        for f in files:
            parts = f.split("/")
            for i in range(1, len(parts)):
                dirs.add("/".join(parts[:i]))
    best: dict[tuple[str, str], str] = {}
    for u in units:
        for m in _TOKEN.finditer(u.text):
            p = normalise(m.group(1))
            if not p:
                continue
            key = (u.decision, p)
            if key not in best or _SECTION_RANK.get(u.section, 9) < _SECTION_RANK.get(best[key], 9):
                best[key] = u.section
    out: list[PathRef] = []
    for (d, p), sec in sorted(best.items()):
        if files is None:
            out.append(PathRef(d, p, sec, None, None))
            continue
        out.append(PathRef(d, p, sec, exists_in(p, files, dirs), resolve_current(p, files, dirs, renames, index)))
    return out
