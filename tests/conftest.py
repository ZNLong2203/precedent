"""Shared fixtures: a tiny but adversarial decision-record repo."""

from __future__ import annotations

from pathlib import Path

import pytest

ADRS = {
    "0001-use-wal.md": """# ADR-0001: Use a write-ahead log

- **Status**: Accepted
- **Date**: 2026-01-01

## Context

We need durability for `src/store/wal.rs`.

## Decision

1. **Append-only log.** Every write is appended to `src/store/wal.rs` before it is acknowledged.
2. **Fsync on every commit.** Each commit calls fsync.
3. **Checkpoint nightly.** A checkpoint is written every night.

## Consequences

Slower writes, safe crashes.

## Later references

- ADR-0003 supersedes Decision 2's fsync policy. Decisions 1 and 3 stand.
""",
    "0002-cache.md": """# ADR-0002: Page cache

- **Status**: Accepted
- **Date**: 2026-01-05

## Context

Builds on ADR-0001 §1 and the log in `src/store/wal.rs`.

## Decision

1. **LRU cache.** Pages are cached with LRU eviction, per ADR-0001 §2.

## Consequences

Faster reads.
""",
    "0003-relax-fsync.md": """# ADR-0003: Relax the fsync policy

- **Status**: Accepted
- **Date**: 2026-02-01

## Context

Fsync on every commit is too slow for bulk loads.

## Decision

This ADR supersedes ADR-0001 Decision 2: fsync is batched every 100 ms.

## Consequences

A crash can lose 100 ms of writes.

## Later references

- ADR-0005 reverses this ADR; the batched fsync is withdrawn.
""",
    "0004-bolt.md": """# ADR-0004: Bolt v1

Status: Superseded by ADR-0006
Date: 2026-02-10

## Context

We need a wire protocol.

## Decision

1. **Bolt v1.** Use Bolt v1.

## Consequences

None.
""",
    "0005-revert-fsync.md": """# ADR-0005: Restore per-commit fsync

- **Status**: Accepted
- **Date**: 2026-03-01

## Context

Batched fsync lost acknowledged data.

## Decision

This ADR reverses ADR-0003. Per-commit fsync is back.

## Consequences

Bulk loads use `everysecond` durability instead.
""",
    "0006-bolt-v2.md": """# ADR-0006: Bolt v2

- **Status**: Accepted
- **Date**: 2026-03-05

## Context

Bolt v1 is obsolete.

## Decision

Supersedes ADR-0004.

## Consequences

Clients upgrade.
""",
    "0007-cache-ttl.md": """# ADR-0007: Cache TTL

- **Status**: Accepted
- **Date**: 2026-03-10

## Context

ADR-0002 caches pages forever.

## Decision

1. **Add a TTL.** Cached pages expire.

## Consequences

ADR-0001 §2 (fsync per commit) is why we rely on `src/store/wal.rs` here.
""",
}


@pytest.fixture(scope="session")
def repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("repo")
    adr = root / "docs" / "adr"
    adr.mkdir(parents=True)
    for name, body in ADRS.items():
        (adr / name).write_text(body, encoding="utf-8")
    (root / "src" / "store").mkdir(parents=True)
    (root / "src" / "store" / "wal.rs").write_text("// wal\n")
    return root


@pytest.fixture(scope="session")
def built(repo: Path, tmp_path_factory: pytest.TempPathFactory):
    from precedent.indexer import index

    out = tmp_path_factory.mktemp("store") / "fixture.rl"
    corpus, report, stats = index(repo, out, name="fixture", lsa_path=out.with_suffix(".lsa.npz"))
    return corpus, report, stats, out
