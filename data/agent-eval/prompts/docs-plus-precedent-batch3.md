You are a coding agent in a repository that keeps architecture decision records (ADRs). Below are 6 independent tasks.
For each task you get context retrieved for it. Decide which numbered decision clauses your plan for the task must
respect or build on (ADR number and clause number), at most 8, most important first. Use only the context in this
file: do not read any other file, search the repository or run commands.

Answer with a single JSON array, one object per task, in this exact shape and nothing else:

[{"task_id": "T01", "relies_on": [{"adr": "ADR-0046", "clause": 2}], "note": "one sentence on your plan"}]

Use `"clause": null` for a decision that has no numbered clauses.


==================== TASK T16 ====================
Task: Add a query-latency benchmark suite based on the LDBC workload, with plan golden files.

Context retrieved for this task: the decision records of the repository, as written.

--- ADR-0243 ---
# ADR-0243: Query-latency suite from the graph-benchmark-ldbc workload

> Renamed from ADR-0226: the number collided with
> docs/adr/0226-* on main (both were taken by parallel PRs). The
> decision is unchanged; references were updated in the same change.

Status: Accepted

Date: 2026-10-13

## Decision
1. **New crate `testing/cypherlite-query-latency`** (R4: `testing/*` may
   depend on any workspace package). The first workload is `gbl`, under
   `workloads/gbl/`:
   - `queries/q01.cypher` … `q30.cypher`: upstream's Neo4j query text,
     verbatim, each after a `// qN: <docstring>` line that is not sent.
   - `expected-sf1.json`: upstream's 30 answers and order sensitivity.
   - `expected-sf0.1.json`: the 30 answers at SF0.1, produced **once** by
     a reference Neo4j lane (Neo4j in Docker,
     upstream's schema, the same load), with a `_source` header recording
     the version, image digest and date. The
     engine under test is never its own oracle.
   - the schema (node and relationship files, labels, types, property
     names and their types) as a table in `src/schema.rs`, which the
     loader expands into its `UNWIND` statements;
   - `indexes.cypher` (upstream's index profile:
     `ID` on all eight labels before the data, eight lookup indexes
     after), `text-indexes.cypher` (the optional TEXT profile, selected
     with `--indexes text`).
   - `NOTICE` (upstream's MIT text, what was taken from which file, and
     the CC BY 4.0 attribution for the data).

   Only the verbatim query text is run. The `tuned/`
   rewrites stay in the examples repository: a slow verbatim query is the signal.

2. **Fair use and data.** Nothing in the repo is named an "LDBC
   Benchmark" or reports "LDBC Benchmark Results" (LDBC fair-use policy);
   the suite is "query latency on the graph-benchmark-ldbc workload". The
   data is fetched, never vendored: `query-latency fetch --sf 0.1|1`
   downloads from `datasets.ldbcouncil.org/snb-interactive-v1`, fails
   closed against the two pinned sha256s in `workloads/gbl/data.sha256`,
   and extracts with pure-Rust `ruzstd` and `tar` (`ureq` and `sha2` are
   already workspace dependencies). The cache is
   `target/query-latency/data/` unless `CYPHERLITE_QUERY_LATENCY_DATA`
   names another directory, so a `.cache/ldbc/` layout fetched elsewhere can be
   reused.

3. **Loader: batched `UNWIND` with parameters.** The loader reads each
   `|`-separated file with the `csv` crate and runs
   `UNWIND $rows AS r CREATE …` in batches through
   `cypherlite::Database`, with upstream's schema (one label per node
   file, `id` as INTEGER `ID`, empty cells left out, ISO date strings
   kept as strings, `length`/`classYear`/`workFrom` as INTEGER,
   relationship endpoints matched by `ID`). It fails unless every label
   and type count equals its file's rows and the totals equal the
   published ones. The default target is `:memory:`, loaded fresh each
   run; `--store PATH` builds a durable store once and reuses it (for
   SF1). Load time is recorded as a side metric, not gated.

4. **Runner.** Per query, in-process on one connection:
   - one untimed warmup, then timed rounds until at least 5 rounds and at
     least `--min-time` (default 1 s) have passed;
   - every run goes through `Connection::query_with_params_cancellable`
     with a per-query timeout (default 60 s at SF0.1, 300 s at SF1); a
     timeout is a recorded failure, not a hang;
   - each round records wall time and the engine's own
     `QueryResult::elapsed` (ADR-0221); the report keeps min, p50, mean,
     p99, max and the round count for both;
   - the last round's rows are checked against the expected answers by
     upstream's rules (list equality where order-sensitive, else multiset
     equality of sorted `(column, value)` tuples, colum

--- ADR-0246 ---
# ADR-0246: Defer the query-latency plan goldens

> Renamed from ADR-0229: the number collided with
> docs/adr/0229-* on main (both were taken by parallel PRs). The
> decision is unchanged; references were updated in the same change.

Status: Accepted

Date: 2026-10-13

## Decision
1. **No plan goldens.** The query-latency suite does not pin `EXPLAIN`
   output. ADR-0243 item 5 is withdrawn; nothing under
   `workloads/gbl/plans/` is created, and there is no
   `QUERY_LATENCY_UPDATE`.
2. **Planner cliffs are caught by latency.** ADR-0245's per-query compare
   (p50 ≤ max(1.5 × envelope, envelope + 0.5 ms)) carries that job: a K98
   cliff is a 100× or larger slowdown, far outside the band. The
   correctness checks of the suite are the answers (ADR-0243 item 4),
   errors and timeouts.
3. **An `EXPLAIN` that shows the physical plan is out of scope** for this
   work (maintainer decision). If a later ADR makes `EXPLAIN` render the
   part order, start node and index choice, plan goldens can be
   reconsidered under a new ADR.

--- ADR-0245 ---
# ADR-0245: Baseline environment and gate for the query-latency suite

> Renamed from ADR-0228: the number collided with
> docs/adr/0228-* on main (both were taken by parallel PRs). The
> decision is unchanged; references were updated in the same change.

Status: Accepted

Date: 2026-10-13

## Decision
1. **Environment.** The ADR-0070 recipe with a larger memory cap: compile
   unconstrained in `rust:1.88-bookworm`; run `query-latency run` in
   `debian:bookworm-slim` with `--cpu-period=10000 --cpu-quota=20000`
   and `--memory=$QUERY_LATENCY_MEMORY --memory-swap=$QUERY_LATENCY_MEMORY`
   (default `6g`). The data set is bind-mounted read-only; the graph is
   `:memory:`, so no tmpfs store is needed. `scripts/baseline-env.sh`
   gains a `query-latency` target; `BASELINE_ENV=host` stays a debug
   escape whose reports are never frozen or gate-compared.

2. **Environment class.** Reports carry an ADR-0071 `environment` class
   that names this recipe (`query-latency`, the memory cap, image
   digests, and `github-actions:ubuntu-24.04` or `local`).

3. **Freeze.** `create-loadtest-baselines.yml` also runs the suite
   `BASELINE_RUNS` times (default 5) and opens its PR with
   `baselines/query-latency-sf0.1.json`, a worst-of-N envelope: per query
   the highest p50 and highest mean of the engine-reported elapsed
   (ADR-0221), and over the run the highest peak RSS. Load time is
   recorded and not gated. `ops`-style raw round arrays are not committed.

4. **Compare**, per query, against the envelope:
   - answers, plan goldens, errors and timeouts: already hard failures
     (ADR-0243), independent of class;
   - **latency:** p50 ≤ max(1.5 × envelope p50, envelope p50 + 0.5 ms);
   - **memory:** peak RSS ≤ 1.15 × envelope.

   The bands are provisional until calibrated the ADR-0070 way: freeze
   from five runs, run a sixth held-out run, and widen a band only by
   what the held-out run needs, recording the numbers here before this
   ADR is accepted. The 0.5 ms allowance is chosen so a 10× regression of
   a 0.17 ms query (0.17 → 1.7 ms, the shape of q26's SF1 regression)
   fails, which a 2 ms or 5 ms allowance would not catch.

5. **Class mismatch.** As ADR-0071: the CI compare hard-fails
   `INCOMPATIBLE`; local `make gate` skips latency and RSS but still
   enforces answers, plans, errors and timeouts.

6. **Wiring.** `make query-latency` defaults to this environment; `make
   baseline-loadtests` includes it; `make gate` runs the compare once
   `baselines/query-latency-sf0.1.json` exists (until the first CI freeze
   lands, it skips the latency compare, as `memory-shape-loadtest` did
   under ADR-0289). A `query-latency` CI job on `ubuntu-24.04` runs per
   PR with the data set restored from `actions/cache`, and uploads the
   report as an artifact (`if: always()`).

7. **SF1 is not frozen or gated.** SF1 is a local run only (ADR-0243);
   its report stays under `target/`.

--- ADR-0479 ---
# ADR-0479: The QPP/LDBC test corpus as query-latency workloads

Status: Proposed

Claim: 40f21a6d20282427e4f9fa243e8915e51ef17ac8

## Decision
The corpus is workload directories inside
`testing/cypherlite-query-latency/workloads/` plus a first-class
`query-latency corpus` subcommand — extending the crate that already owns
the GBL lane (ADR-0243/0244/0245), with its data fetch, store reuse,
watchdog and report machinery reused, and no new framework:

- **`workloads/pathdb/`** — 142 translated queries + 65 path-mode
  restrictors over the same pinned GBL store (no new data rights), with
  a split seed layout: `seed-keys.json` is the one canonical
  `(seed label, first-hop types)` fact table (36 keys, one record per
  scale factor, each carrying the chosen node's id, degree and label;
  the key is canonical — the label plus the type set sorted and
  de-duplicated, so one fact has exactly one spelling, enforced on
  load), and `params-sf<SF>.json` holds only the derived per-query
  entries.
  PathDB's seed ids are LDBC datagen outputs that exist in none of our
  stores, so each is substituted by the **degree-median policy**
  (deterministic, representative, never a hub); the per-query entries
  are derived from the one fact table and checked against it on load
  (seed id and record label both).
- **`workloads/fraud-qpp/`** — six in-house re-authored queries (the
  external inspiration is unlicensed and was never copied): f01/f02 over
  the `cypherlite-datasets` fraud generator with its planted cycle as an
  engine-independent oracle, f06 over a designed sample fixture
  answer-checked exactly, f03-f05 kept until their generators exist.
- **`workloads/snb-bi/`** — added by the LABS-646 follow-up (2026-11-02),
  per the manifest §2 row deferred at this ADR's landing: the 16
  translated LDBC SNB BI analytics queries (ldbc/ldbc_snb_bi `47dd38b4`,
  Apache-2.0) over the same GBL store, with NO seed policy — upstream's
  parameters are literal values (dates, tags, windows), recorded per
  scale factor as one Cypher expression per parameter, which the lane
  evaluates once and binds natively (empty-answer params substituted
  same-kind and recorded, ADR-0247 precedent). The seven dialect forms
  the translation leans on were verified by execution before any file
  was marked `ok` — all supported; the workload README records the
  verdicts and the initial 11 `ok` / 5 `kept` split (the `kept` five are
  the unbounded `replyOf*0..` walk class, LABS-660).
- **`workloads/ukrailway/`** — added 2026-11-02, the manifest §5 cut
  order's last deferral: the two IN-HOUSE UK railway graph queries over
  the workload's OWN graph — the 18 MB dogofbrian/ukrailway data set
  (`ce82229e`, Apache-2.0) fetched on demand from the pinned commit,
  verified per-file against `data.sha256` (never committed) and
  imported into `:memory:` by the workload's `import.cypher` (LOAD CSV
  confined to the fetched directory) — no GBL store, no parameters (the
  queries carry their constants inline), no seed policy, no scale
  factor. r02/r03 were unverified drafts at this ADR's landing; both
  query texts and both answers were verified by execution against the
  pinned data before any file was marked `ok` (r02 1248 routePairs /
  19 changeoverStations, r03 15 hops and the station list — recorded in
  `oracle.json` as rows checks). r02 is minutes-scale (213.8 s measured
  in the lane), so the lane carries its own 600 s per-entry timeout,
  never the scale-factor-scaled default.

The **file format** contract: one statement per file, `$seed` parameters
(the engine's native parameter binding — ADR-0247's literal substitut

--- ADR-0244 ---
# ADR-0244: In-process sampling profiler for the query-latency suite

> Renamed from ADR-0227: the number collided with
> docs/adr/0227-* on main (both were taken by parallel PRs). The
> decision is unchanged; references were updated in the same change.

Status: Accepted

Date: 2026-10-13

## Decision
1. **A `profile` subcommand of `query-latency`** (ADR-0243):
   `query-latency profile --sf 0.1 --qid 19 [--seconds 10]
   [--frequency 997] [--indexes upstream|text] [--sampler pprof|none]`.
   It loads the workload, runs the query once untimed, then loops it for
   `--seconds` (at least one iteration) under the sampler. `--sampler
   none` runs the same loop with no in-process sampler, so an external
   one (`samply`, `perf`) can record the process instead.

2. **The sampler is `pprof-rs`** (`pprof` 0.15, feature `flamegraph`),
   in-process, timer-signal based, sampling every thread, including the
   connection's query worker thread. It is a dependency of
   `testing/cypherlite-query-latency` only, behind a crate feature
   `sampling` (default on, compiled on `cfg(unix)` only; on other
   targets the subcommand reports that sampling is unavailable).

3. **Outputs**, under
   `target/query-latency/profile/<workload>-sf<sf>-q<NN>/`:
   - `top.txt`: the file agents read. The 40 heaviest frames by self
     time and by inclusive time, then inclusive share by workspace crate
     (`cypherlite-planner`, `cypherlite-executor`, …), with `std`/`core`/
     `alloc` and the allocator reported as their own groups. The grouping
     follows `scripts/perf/03-bottleneck-summary.sh`.
   - `folded.txt`: collapsed stacks, for diffing two runs or re-rendering.
   - `flame.svg`: a flame graph for humans.
   - `summary.json`: query, iterations, mean engine elapsed, sample
     count, frequency, git commit and dirty flag.

4. **A `profiling` cargo profile** in the workspace `Cargo.toml`:
   inherits `release`, `debug = "line-tables-only"`, `strip = "none"`.
   `make query-latency-profile QID=19 [SF=0.1] [SECONDS=10]` builds with
   it and runs the subcommand on the host (not in the ADR-0245 Docker
   environment: a profile is a diagnosis, not a frozen measurement).

5. **No engine instrumentation.** Nothing in `cypherlite/*` changes; the
   sampler observes the release-optimized engine as shipped.

6. **The agent playbook** is `docs/testing/query-latency.md`: run the
   suite, pick the query, profile, read `top.txt`, form one hypothesis,
   change one thing, re-run `run --qids N` and `profile` and compare.
   AGENTS.md gets a short "How to investigate a slow query" pointer to
   it.

Precedent `preflight` for this task (a tool that tracks which decisions are still in force):
{"task":"Add a query-latency benchmark suite based on the LDBC workload, with plan golden files.","paths":[],"decisions":[{"id":"ADR-0246","title":"Defer the query-latency plan goldens","standing":"in_force","declared_status":"accepted","path":"docs/adr/0246-defer-query-latency-plan-goldens.md","gist":"1. No plan goldens. The query-latency suite does not pin EXPLAIN output. ADR-0243 item 5 is withdrawn; nothing under workloads/gbl/plans/ is created, and there is no QUERY_LATENCY_UPDATE. 2. Planner cliffs are caught by latency. ADR-0245's per-query compare (p50 ≤ max(1.5 × envelope, envelope + 0.5…","why":["matches task (clause+fulltext+vector)","controls ADR-0243 (§5)"],"live_clauses":[{"n":1,"title":"No plan goldens"},{"n":2,"title":"Planner cliffs are caught by latency"},{"n":3,"title":"An `EXPLAIN` that shows the physical plan is out of scope"}],"stale_clauses":[]},{"id":"ADR-0243","title":"Query-latency suite from the graph-benchmark-ldbc workload","standing":"partial","declared_status":"accepted","path":"docs/adr/0243-query-latency-suite.md","gist":"1. New crate testing/cypherlite-query-latency (R4: testing/ may depend on any workspace package). The first workload is gbl, under workloads/gbl/: - queries/q01.cypher … q30.cypher: upstream's Neo4j query text, verbatim, each after a // qN: <docstring> line that is not sent. - expected-sf1.json:…","why":["matches task (clause+fulltext+vector)"],"live_clauses":[{"n":1,"title":"New crate `testing/cypherlite-query-latency`"},{"n":2,"title":"Fair use and data"},{"n":3,"title":"Loader: batched `UNWIND` with parameters"},{"n":4,"title":"Runner"},{"n":6,"title":"Levels"},{"n":7,"title":"Entry points"}],"stale_clauses":[{"n":5,"title":"Plan goldens","by":["ADR-0246"],"note":"§5 'Plan goldens' superseded by ADR-0246"}],"evidence":[{"by":"ADR-0246","treatment":"WITHDRAWS","clauses":[5],"quote":"ADR-0246: item 5 (plan goldens) is withdrawn."}]},{"id":"ADR-0244","title":"In-process sampling profiler for the query-latency suite","standing":"in_force","declared_status":"accepted","path":"docs/adr/0244-in-process-query-sampling-profiler.md","gist":"1. A profile subcommand of query-latency (ADR-0243): query-latency profile --sf 0.1 --qid 19 [--seconds 10] [--frequency 997] [--indexes upstream|text] [--sampler pprof|none]. It loads the workload, runs the query once untimed, then loops it for --seconds (at least one iteration) under the sampler.…","why":["matches task (clause+fulltext+vector)"],"live_clauses":[{"n":1,"title":"A `profile` subcommand of `query-latency`"},{"n":2,"title":"The sampler is `pprof-rs`"},{"n":3,"title":"Outputs"},{"n":4,"title":"A `profiling` cargo profile"},{"n":5,"title":"No engine instrumentation"},{"n":6,"title":"The agent playbook"}],"stale_clauses":[]},{"id":"ADR-0245","title":"Baseline environment and gate for the query-latency suite","standing":"in_force","declared_status":"accepted","path":"docs/adr/0245-query-latency-baseline-environment-and-gate.md","gist":"1. Environment. The ADR-0070 recipe with a larger memory cap: compile unconstrained in rust:1.88-bookworm; run query-latency run in debian:bookworm-slim with --cpu-period=10000 --cpu-quota=20000 and --memory=$QUERY_LATENCY_MEMORY --memory-swap=$QUERY_LATENCY_MEMORY (default 6g). The data set is…","why":["matches task (clause+fulltext+vector)"],"live_clauses":[{"n":1,"title":"Environment"},{"n":2,"title":"Environment class"},{"n":3,"title":"Freeze"},{"n":4,"title":"Compare"},{"n":5,"title":"Class mismatch"},{"n":6,"title":"Wiring"},{"n":7,"title":"SF1 is not frozen or gated"}],"stale_clauses":[]},{"id":"ADR-0251","title":"Fast test architecture — memory-first tiers, OS-delta lanes, build-once, background cadences","standing":"in_force","declared_status":"accepted","path":"docs/adr/0251-test-architecture.md","gist":"The CypherLite test architecture is memory-first, delta-deduplicated on the OS matrix, build-once per SHA, and cadence-split for heavy gates. Coverage never shrinks: every test moved between tiers keeps running, in the tier that matches its actual dependency. ### 1. Memory-first test tiers Three…","why":["matches task (clause+fulltext+vector)"],"live_clauses":[{"n":1,"title":"Memory-first test tiers"},{"n":2,"title":"OS-matrix dedup"},{"n":3,"title":"Smoke lanes are true minimal e2e"},{"n":4,"title":"Machine-adaptive parallelism"},{"n":5,"title":"Build once per SHA, shared everywhere"},{"n":6,"title":"Background cadences"},{"n":7,"title":"Non-goals"}],"stale_clauses":[]}],"warnings":["ADR-0243 is partly superseded: §5 'Plan goldens' superseded by ADR-0246"],"omitted":11,"tokens":1144,"how_to_read":"live_clauses are good law; stale_clauses were taken out of force by the decision named in `by` - follow that decision instead."}

==================== TASK T03 ====================
Task: Add a new catalog DDL operation whose effect must be recorded in the write-ahead log and replayed on recovery.

Context retrieved for this task: the decision records of the repository, as written.

--- ADR-0402 ---
# ADR-0402: Zero-effect write notes in batch sessions

Status: Accepted
Claim: 6feb207321bcc9a8ada401ea8b2db8d3e9aad2ea

## Decision
1. **Default-on, batch sessions only, stderr only.** A batch session — the
   one-shot `QUERY` and piped-stdin halves of the invocation-mode trichotomy
   (ADR-0079 §4), the `is_batch` split ADR-0199 and ADR-0164 already read —
   reports a zero-effect write without being asked. There is no flag to enable
   or disable it: an opt-in misses the author who does not suspect the no-op,
   which is the whole audience, and a suppression flag is a separate decision.
   The line goes to stderr in every output mode, so stdout stays the
   machine-readable payload it is today.
2. **A zero-effect write is an executed write that applied nothing.** The
   criterion is the engine's effect record (`QueryResult::effect`, a
   `StatementEffect`): a mutation operator reached execution **and** the
   engine applied no change. Both facts come from execution, never from the
   plan's conservative query type (ADR-0332), the statement's spelling, or
   matching clause or procedure names in the CLI:

   - *A mutation operator reached execution* means the executor dispatched a
     data-write clause (`CREATE`, `MERGE`, `DELETE`, `SET`, `REMOVE`,
     `FOREACH`), schema DDL, a catalog write (`ALTER DATABASE`, the graph-type
     commands) or a writes-flagged procedure (`db.ontology.set`/`drop`/`apply`,
     `db.createLabel`). It is recorded before rows flow, so a write whose
     pipeline is empty — the LABS-313 shape — still counts as an attempt. The
     mark is a walk over the statement's clauses, `NEXT` stages and nested
     bodies, so a write inside a `CALL { … }` body or an untaken `WHEN`
     branch is an attempt even when that body never runs.
   - *Applied a change* means the statement pushed at least one change into
     the write redo, the one funnel every entity, schema and **catalog** change
     goes through. A catalog change therefore counts as applied even though
     every ADR-0309 mutation counter stays zero (`ALTER DATABASE`, `CREATE
     GRAPH TYPE`, `db.ontology.set`/`drop`), and a read-only statement counts
     as no attempt at all however the planner classified it — a top-level
     `CALL { … }` with a read-only body and a bare `LOAD CSV … RETURN` are
     write-*routed* by the conservative access fold but run no mutation
     operator, so they print nothing. A change the engine rolled back is not
     applied: a failed statement restores its statement-spanning state, and a
     batch the statement rolls back (`IN TRANSACTIONS … ON ERROR CONTINUE`)
     un-counts the changes it truncated, so only changes that survived count.

   Rows are not the signal: a write without `RETURN` returns no rows whatever
   it wrote. The counters are not the signal either, for the two reasons above;
   the engine's redo is. A plan artifact takes only the **note** out of scope,
   not the effect: `EXPLAIN` does not execute and carries the zero effect,
   `StatementEffect::None`, while `PROFILE` executes the wrapped statement and
   carries its true effect — an applied `PROFILE` write counts in its
   transaction's merged effect (Decision 4) — but its plan table is the run's
   own report, so it adds no note. Silence after a successful statement
   therefore means one of exactly three things: it read only, it applied a
   change, or it was a plan-producing run. A failed statement reports its
   failure and carries no note — including the one failure that still applied
   something: a statement that executed and then failed to render reports the
   render fai

--- ADR-0527 ---
# ADR-0527: Write engine seam

Status: Proposed
Claim: 5025a4cf9637dd08d17b136df08c846fbdc7ac75

## Decision
The redo operation is the change unit shared by query engines and write
engines. A write engine owns durable ordering and the commit clock:
open and recovery, the durable commit of redo groups, the checkpoint
taken from an export, follow, change-data capture, and the writer
lease.

The facade keeps group-commit admission, conflict checks, apply, and
the order in which a commit is published. A replacement write engine
replaces the durable part only.

Today's log, checkpoint, follow, and change capture become the local
write engine, behind that contract. The file layer, the snapshot
codecs, and the log record format stay a toolkit a write engine may
use. No alternate write engine is added.

The store manifest records the write engine identity beside the query
engine identity (ADR-0548). A store written before this change opens as
the local engine. Opening a store whose recorded identity is not the
engine being opened fails. The identities are optional manifest fields;
redo records and snapshot payloads keep their encoding.

--- ADR-0287 ---
# 0287. Catalog DDL stages seed NEXT chains with a unit row

- **Status**: Accepted
- **Renumbered**: from 0176 (shared-number cleanup)
- **Date**: 2026-10-07
- **Deciders**: Oskar Hane (agreed in the end-of-feature review conversation), CypherLite maintainers

## Decision
A schema/administration DDL stage seeds the next `NEXT` stage exactly like
a data write does. `stage_has_unit_output` returns true for a part ending
in:

- the IR-native DDL variants `Clause::CreateIndex`, `Clause::DropIndex`,
  `Clause::CreateConstraint`, `Clause::DropConstraint` — outright; and
- `Clause::Catalog(command)` exactly when the canonical row-producing
  predicate `cypherlite_front::show_columns::catalog_produces_rows(command)`
  says the command is NOT row-producing (schema/admin DDL:
  index/constraint/database/graph-type commands).

Row-producing catalog commands (the SHOW family and `TERMINATE
TRANSACTIONS`) keep their current row semantics: they seed the next stage
from their projected rows and never gain a unit row, so a zero-row SHOW
stage still starves the chain — unchanged. The unit seed still fires only
when the stage's own result is empty (`execute_plan_seeded` /
`execute_plan_read_seeded`), so a stage is never seeded twice.

The classification is not re-enumerated in the executor: the
`catalog_produces_rows` predicate in `cypherlite-front` (the single home
the zero-records change established, consumed by the executor's dispatch
and its `CALL { … }` merge check) is the one source of truth, exhaustive
over every parser clause, so a new catalog command is a compile error
there until classified.

--- ADR-0091 ---
# 0091. Quarantine retired bundle pages across catalog publication

- **Status**: Proposed
- **Date**: 2026-09-23
- **Deciders**: CypherLite maintainers

## Decision
1. **Quarantine retired selected-generation ranges.** On open, validate the
   selected superblock, catalog and WAL-tail mapping per ADR-0086. Track its
   catalog and inode physical ranges (including manifest, identity, shard and
   WAL inodes) to identify pages *freed or replaced* while publishing a new
   catalog. Freeing, truncating, deleting or replacing an inode, or retiring
   the old catalog, makes its selected-old pages *pending free*, even if the
   current in-memory catalog no longer names them. The allocator must not
   serve these pages from the freelist, map them to a new inode, or overwrite
   them with a new catalog or WAL extension while that old superblock could
   be selected on recovery. Validated old freelist ranges that are not owned
   by old live objects may still be used. Preserve the old superblock slot
   until replacement publication is durable. This pin is a restriction on
   *reallocation of retired pages*, not a promise that every byte of every
   still-live inode is immutable: ordinary WAL appends continue to use the
   existing ADR-0074 WAL-tail shortcut, including an in-place rewrite of a
   live partial last page. Do not count a live WAL page as available for
   reallocation merely because its logical EOF precedes the page end.

2. **Barrier controls reclamation.** For catalog-changing operations, write
   new data and a new catalog on separate pages, sync their contents, then
   write the alternate superblock and pass its host-file durability barrier
   (ADR-0077). The existing catalog-free WAL-tail shortcut is outside this
   replacement protocol. Only after the replacement barrier
   succeeds is the new generation selected and the previous generation's
   unreachable pages eligible for freelist reuse; establish the new selected
   read set for the next update. If a barrier fails or its completion is
   ambiguous, do **not** recycle quarantined pages or erase either possible
   catalog generation. Return an error and retain the pages until recovery
   reopens and validates the selected superblock, or a later proven barrier
   establishes an authoritative generation. Never treat a real catalog/page
   read error as an excuse to fall back and mutate the bundle. Recovery derives
   a safe freelist from validated page ownership rather than trusting a list
   that overlaps either still-selectable catalog's live extents.

3. **Virtual publication and compatibility.** Apply the same pin rule to
   `rename`, `remove_file`, `remove_dir_all`, catalog rewrites and checkpoint
   manifest replacement, not just to a snapshot writer. A pre-publication
   failure must not overwrite the previous manifest, its selected identity
   object (ADR-0092), or any WAL extent *retired by this replacement*; the
   previous catalog must still map them. This does not guarantee recovery of
   WAL records already present in a live, partially filled physical page if a
   concurrent/later append tears that page. After success, reclaim unreachable
   previous pages without permanent growth. Keep the on-disk bundle version,
   superblock format and single host file of ADR-0074; old bundles are
   validated and opened without eager rewrite. Memory and Native do not
   acquire `.cl`-style page generations.

--- ADR-0059 ---
# 0059. WAL redo payloads for catalog DDL are typed models

- **Status**: Proposed
- **Date**: 2026-09-17
- **Deciders**: CypherLite / MemoryDB merge

## Decision
1. **Typed payloads.** The three catalog-DDL redo ops carry typed,
   serde-serializable models captured once at DDL-execution time from the
   parsed clause:
   - `CatalogIndexDetail` carries `redo::IndexDetailSpec` (with
     `redo::IndexKindSpec` for the index kind) plus the evaluated
     `OPTIONS` map as tagged JSON (`redo::props_json`).
   - `PutGraphType` and `SetCurrentGraphType` carry
     `graph_type::GraphTypeSpec`.
2. **No re-parse on replay.** `Graph::apply_redo` stores these models
   verbatim. It never formats a DDL string and never re-parses Cypher
   text during replay.
3. **Loud decode failure.** WAL records written in the old Cypher-text
   shape fail serde decode at replay: replay returns `Err` and startup
   fails loudly. There is no silent skip or drop of an undecodable
   record. (Covered by `legacy_string_payload_no_longer_decodes` in
   `crates/cypherlite-executor/src/redo.rs`.)
4. **Pre-1.0 rationale.** Breaking the old record shape without a
   migration path is accepted because the crate is pre-1.0
   (`0.3.0-alpha`) and no ADR has ever guaranteed WAL payload
   compatibility — ADR-0012's format discipline covers checkpoint
   manifests only. The change is a correctness hardening: replay can no
   longer silently lose index or graph-type catalog state.

Precedent `preflight` for this task (a tool that tracks which decisions are still in force):
{"task":"Add a new catalog DDL operation whose effect must be recorded in the write-ahead log and replayed on recovery.","paths":[],"decisions":[{"id":"ADR-0402","title":"Zero-effect write notes in batch sessions","standing":"in_force","declared_status":"accepted","path":"docs/adr/0402-zero-effect-write-notes.md","gist":"1. Default-on, batch sessions only, stderr only. A batch session — the one-shot QUERY and piped-stdin halves of the invocation-mode trichotomy (ADR-0079 §4), the is_batch split ADR-0199 and ADR-0164 already read — reports a zero-effect write without being asked. There is no flag to enable or…","why":["matches task (clause+fulltext+vector)"],"live_clauses":[{"n":1,"title":"Default-on, batch sessions only, stderr only"},{"n":2,"title":"A zero-effect write is an executed write that applied nothing"},{"n":3,"title":"Per-statement note"},{"n":4,"title":"Commit-time summary"},{"n":5,"title":"Exit codes and streams are unchanged"},{"n":6,"title":"The wording is a byte-pinned observable contract"}],"stale_clauses":[]},{"id":"ADR-0091","title":"Quarantine retired bundle pages across catalog publication","standing":"in_force","declared_status":"proposed","path":"docs/adr/0091-bundle-generation-page-quarantine.md","gist":"1. Quarantine retired selected-generation ranges. On open, validate the selected superblock, catalog and WAL-tail mapping per ADR-0086. Track its catalog and inode physical ranges (including manifest, identity, shard and WAL inodes) to identify pages freed or replaced while publishing a new…","why":["matches task (clause+fulltext+vector)"],"live_clauses":[{"n":1,"title":"Quarantine retired selected-generation ranges"},{"n":2,"title":"Barrier controls reclamation"},{"n":3,"title":"Virtual publication and compatibility"}],"stale_clauses":[]},{"id":"ADR-0174","title":"Re-check constraints committed mid-transaction; cancellable validation loops","standing":"in_force","declared_status":"accepted","path":"docs/adr/0174-committed-catalog-constraint-rechecks.md","gist":"1. The scratch remembers the catalog it last validated against. RedoLog (the owner of the validation cursor, ADR-0173) gains a constraint fingerprint: every constraint's definition and derived enforced label, in name order, as named_constraints() and show_schema() reported them. The fingerprint…","why":["matches task (clause+fulltext+vector)"],"live_clauses":[{"n":1,"title":"The scratch remembers the catalog it last validated against"},{"n":2,"title":"Catalog drift joins the recheck set"},{"n":3,"title":"Validation loops are cancellable"},{"n":4,"title":"The equality pins are extended, not changed"}],"stale_clauses":[]},{"id":"ADR-0086","title":"Bounded decoding of persisted WAL, bundles, and Parquet","standing":"in_force","declared_status":"proposed","path":"docs/adr/0086-bounded-persistence-input.md","gist":"1. WAL framing and tail. A frame is an eight-byte CRC/length header plus 1..=64 MiB (67,108,864 bytes) of JSON payload. Reject zero, greater than 64 MiB, or otherwise unrepresentable lengths before allocation on open, replay, and records_after; check the length against the remaining physical…","why":["matches task (clause+fulltext+vector)"],"live_clauses":[{"n":1,"title":"WAL framing and tail"},{"n":2,"title":"Bundle catalog and physical page ownership"},{"n":3,"title":"Parquet recovery envelope, per shard"},{"n":4,"title":"Writer symmetry and failure"},{"n":5,"title":"Manifest, pull map, paths and numeric sentinels"},{"n":6,"title":"Streaming recovery, stable explicit replay API"}],"stale_clauses":[]},{"id":"ADR-0098","title":"Exclusive temporary files and durable atomic replacement","standing":"in_force","declared_status":"proposed","path":"docs/adr/0098-safe-atomic-replacement.md","gist":"1. Exclusive, unpredictable temporary name. For each atomic_write, choose a fresh name in the destination's containing virtual directory, derived from the destination only as a recognizable prefix and suffixed with at least 128 bits from an OS-backed cryptographically secure random source. Never…","why":["matches task (clause+fulltext+vector)"],"live_clauses":[{"n":1,"title":"Exclusive, unpredictable temporary name"},{"n":2,"title":"Write, publish, clean up"},{"n":3,"title":"Native namespace persistence"},{"n":4,"title":"Backend-specific persistence"},{"n":5,"title":"Post-rename sync failure"}],"stale_clauses":[]}],"warnings":[],"omitted":10,"tokens":1102,"how_to_read":"live_clauses are good law; stale_clauses were taken out of force by the decision named in `by` - follow that decision instead."}

==================== TASK T18 ====================
Task: Add property-based tests with proptest to the engine crates.

Context retrieved for this task: the decision records of the repository, as written.

--- ADR-0268 ---
# 0268. proptest dev-dependencies for property testing

- **Status**: Proposed
- **Renumbered**: from 0136 (shared-number cleanup)
- **Date**: 2026-09-28
- **Deciders**: CypherLite maintainers

## Decision
1. **Harness.** Adopt `proptest = "1.11"` and
   `proptest-state-machine = "0.8"` as **dev-dependencies of
   `cypherlite/cypherlite-storage` only**. They are not added to any crate's
   normal dependency list and not to any other engine crate. A later need in
   a different crate gets its own ADR.

2. **rand dual-major, test build only.** Accept the second rand major. The
   workspace stays on `rand 0.8`; only the `cypherlite-storage` test build
   links `rand 0.9` through proptest. No test may pass a `rand 0.8` `Rng`
   into a proptest strategy or vice versa; a test that seeds both an engine
   RNG and a proptest generator keeps the two streams separate. Bumping the
   workspace to `rand 0.9` is a separate change and not implied by this one.

3. **Regression files committed.** `.proptest-regressions` files (one per
   test source, proptest's `SourceParallel` persistence) are committed to the
   repository. A counterexample is a permanent regression test. No
   `.proptest-regressions` file is deleted, or its entries removed, without a
   tracked reason (an issue or a later ADR); `PROPTEST_DISABLE_FAILURE_PERSISTENCE`
   must not be set in CI.

4. **R6 does not apply.** proptest is a *dev*-dependency, and its tree is
   light: no native/C++ build, no async runtime, no networking, and a handful
   of small pure-Rust crates (the six listed above, plus optional
   `regex-syntax`/`rusty-fork`/`tempfile` only if those features are enabled).
   That is below R6's heavy-dependency trigger. This ADR is still recorded
   because the rand-major split and the committed-regression-file policy are
   decisions worth having in the log, not because R6 compels it.

--- ADR-0552 ---
# ADR-0552: Proptest adjacency reference model in relate-executor

Status: Proposed
Claim: f78d5d1ddf58b3cc63ccab422598f554c2db3378

## Decision
1. **Adopt `proptest` 1.11 as a dev-dependency of `relate-executor`**, at
   the storage crate's pin. No `proptest-state-machine`: the suite drives a
   plain generated vector of operations, like the other storage suites.
2. **Boundary ruling.** The workspace dependency rules of ADR-0103
   (R1–R5, enforced by the boundary check) govern workspace-internal
   edges by kind; external dev-dependencies are not edges the checker
   evaluates, and proptest's tree has no native/C++ build, async runtime,
   or networking, so the heavy-dependency trigger does not apply. The
   placement is boundary-clean, and the suite reaches the crate-internal
   structures it guards — the home an external test could not provide.
3. **Observable-semantics guard.** The property compares observable
   adjacency (visibility-filtered iteration), not physical hop vectors:
   deletes are MVCC tombstones that never touch adjacency today, and the
   rework may change those internals while this suite stays green.
4. The standing rules of the storage-only adoption apply unchanged in this
   crate: 256-case default with `PROPTEST_CASES` override (no pinned
   case count), committed regression files, and the rand 0.8 / rand 0.9
   dual-major separation (no test mixes the two RNG families).

--- ADR-0560 ---
# 0560. crates.io and PyPI distribution

Status: Proposed
Claim: 03840dd02e6982f4d54e2acd95fd19565dede688
Date: 2026-11-10
Deciders: the maintainers

## Decision
Publish to both registries from a dedicated `publish-registries.yml`
workflow — called by `release.yml` once the GitHub release exists, and
dispatchable by hand with a tag and per-registry toggles so dry runs and
partial-failure recovery never require re-cutting a release. npm's jobs
(ADR-0278) move into the same workflow; artifacts always come from the
release's assets, so the chained run and a manual re-publish share one
code path. Everything is lockstep with the release tag and fail-closed
until its runbook setup is done:

- **crates.io** — the 17-crate closure publishes in topological
  dependency order. The first publish of each crate is a manual
  token publish (a crate must exist before trusted publishing can be
  configured on it); afterwards each crate gets a GitHub Actions trusted
  publisher for `publish-registries.yml` and the pipeline takes over with
  OIDC, no stored token. A short settle delay or retry rides between
  crates because the registry index lags a fresh publish.
- **PyPI** — the `relate-db` wheels and sdist the `python` job already
  builds publish via the official publish action with trusted publishing
  (`id-token: write`, no token). PyPI's pending-publisher mechanism
  configures trust before the project exists, so no manual first publish
  is needed; a TestPyPI dispatch input gives a dry-run target.

Workspace dependency entries for the workspace's own crates carry a
version pin (crates.io ignores the path half), swept by
`scripts/release-bump.sh` like every other version surface. The one
exception is the shared test-support crate: it stays path-only so the
dev-dependencies that reference it are stripped at package time instead
of pointing at a crate that never publishes.

--- ADR-0085 ---
# 0085. wasm32 build split for the engine crates

- **Status**: Accepted
- **Date**: 2026-09-24
- **Deciders**: CypherLite maintainers

## Decision
Split the engine build so the wasm32 target compiles a strict subset,
using `#[cfg(target_arch = "wasm32")]` at module and item boundaries.
No new cargo features.

1. **Time.** Replace `std::time::Instant` with `web_time::Instant` in
   `cypherlite-storage` (WAL append timing) and `cypherlite` (commit
   group, query lifecycle). `web-time` is a workspace dep; on native it
   is a re-export of `std::time`, on wasm32 it maps to
   `performance.now()`.
2. **Threads.** On wasm32, `spawn_checkpoint_timer` is a no-op (no
   background threads and no durability boundary for `:memory:`),
   `schedule_checkpoint` runs the dump inline, and `run_on_query_worker`
   calls the closure directly on the current thread. Native keeps the
   64 MiB worker thread from ADR-0259 unchanged. The two paths are
   cfg-gated at the function level, not sprinkled inside a shared body.
3. **Storage codec.** `arrow` and `parquet` move under
   `[target.'cfg(not(target_arch = "wasm32"))'.dependencies]` in
   `cypherlite-storage`. The Parquet shard writer/reader in
   `snapshot.rs` moves into a single `mod native { ... }` block gated
   at the module. `SnapshotCodecKind::Parquet` remains as an enum
   variant on wasm32 for serialization symmetry, but the wasm-side
   `parquet_checkpoint_at` / `parquet_load` /
   `parquet_snapshot_data_bytes` helpers return a fixed storage error
   (`WASM_PARQUET_UNAVAILABLE`). `SnapshotCodecKind::default()` is
   `Parquet` on native and `Json` on wasm32, so `:memory:` on wasm32
   opens the JSON codec by default.
4. **Filesystem URIs.** `parse_filesystem_uri` and
   `reset_filesystem_uri` fail on wasm32 with a fixed storage error
   (`WASM_FS_UNAVAILABLE`). Only `:memory:` opens.
5. **Stack size.** `.cargo/config.toml` sets a wasm32 linker flag
   `-zstack-size=16777216` (16 MiB), a browser-friendly middle ground
   between the 1 MiB wasm32 default and the 64 MiB native worker stack.
   Native builds are unaffected.
6. **CI gate (from ADR-0084).** The `wasm` job runs
   `cargo check -p cypherlite-storage --target wasm32-unknown-unknown`
   and `cargo check -p cypherlite-wasm --target wasm32-unknown-unknown`
   in addition to `wasm-pack build`, so any dep upgrade that breaks
   wasm32 fails the merge.

--- ADR-0218 ---
# 0218. Statistics-based orientation of unbound comma-MATCH parts

- **Status**: Proposed
- **Date**: 2026-10-13
- **Deciders**: CypherLite maintainers (Linear [LABS-273](https://linear.app/neo4j/issue/LABS-273))
- **Related**: ADR-0024 (MATCH rewrites after bind), ADR-0046 (planner
  pipeline), LABS-157 / PR #221 (intra-clause orientation toward bound
  variables), ADR-0171 (label probe; a different consumer of label facts)

Note: drafted as 0213, renumbered past the in-flight sibling ADRs
0216/0217 (LABS-276) on rebase; 0216/0217 land with that branch.

## Decision
1. **Plan-time label statistics.** `cypherlite-planner` gains a
   `MatchStats` trait (`label_count(&self, label) -> Option<u64>`) and a
   `plan_with_stats` entry point; `plan` delegates with a `NoStats`
   null object (every count `None`), keeping every existing caller and
   the stats-free behavior unchanged. The
   facade (`cypherlite/src/connection.rs::plan_gate_classify`) already
   plans under the graph read guard, so it passes an adapter over
   `cypherlite-executor`'s `Graph::label_count` — the label-index set
   size, an O(1) approximation (it includes ids not visible at every
   snapshot, which is fine for an estimate). The engine crates stay
   acyclic: the trait lives in the planner, the executor only exposes a
   count, the facade adapts.

2. **Tie-break orientation by cardinality.** In `orient_path`, the
   coarse rank still dominates (a bound node always wins, a
   property-equality end still beats a label-only end). When both ends
   rank equal and statistics are available, the end with the smaller
   minimum label cardinality seeds the part: the path reverses only on a
   strictly smaller estimate, so equal or unknown estimates keep the
   written order.

3. **Order independent parts cheap-end first.** After the stable sort by
   descending seed rank, `order_patterns` floats a part ahead of its
   predecessors while they rank equal and the part's cheapest end (min of
   first/last label counts) is strictly smaller than theirs — a
   constrained adjacent-swap pass, not a re-sort: a part never passes a
   neighbor it shares a variable with, because that neighbor may be what
   binds it (LABS-157). Among equal ranks, a part that will scan 10 nodes
   runs before one that will scan 200 000. The cartesian product itself
   is mandated by the spec and stays; only the enumeration order of
   independent parts changes. Without statistics every estimate is
   `u64::MAX`, no comparison is strictly smaller, and the pass is a
   no-op, so stats-free plans are bit-identical to today.

Row order: comma-`MATCH` carries no order guarantee without `ORDER BY`;
PR #221 already reorders parts and reverses paths. The full openCypher
TCK (3892 scenarios) gates this change.

Precedent `preflight` for this task (a tool that tracks which decisions are still in force):
{"task":"Add property-based tests with proptest to the engine crates.","paths":[],"decisions":[{"id":"ADR-0552","title":"Proptest adjacency reference model in relate-executor","standing":"in_force","declared_status":"proposed","path":"docs/adr/0552-proptest-adjacency-model-in-executor.md","gist":"1. Adopt proptest 1.11 as a dev-dependency of relate-executor, at the storage crate's pin. No proptest-state-machine: the suite drives a plain generated vector of operations, like the other storage suites. 2. Boundary ruling. The workspace dependency rules of ADR-0103 (R1–R5, enforced by the…","why":["matches task (clause+fulltext+vector)"],"live_clauses":[{"n":1,"title":"Adopt `proptest` 1.11 as a dev-dependency of `relate-executor`"},{"n":2,"title":"Boundary ruling"},{"n":3,"title":"Observable-semantics guard"},{"n":4,"title":"The standing rules of the storage-only adoption apply unchanged in"}],"stale_clauses":[]},{"id":"ADR-0268","title":"proptest dev-dependencies for property testing","standing":"partial","declared_status":"proposed","path":"docs/adr/0268-proptest-property-testing.md","gist":"1. Harness. Adopt proptest = \"1.11\" and proptest-state-machine = \"0.8\" as dev-dependencies of cypherlite/cypherlite-storage only. They are not added to any crate's normal dependency list and not to any other engine crate. A later need in a different crate gets its own ADR. 2. rand dual-major, test…","why":["matches task (clause+fulltext+vector)"],"live_clauses":[{"n":1,"title":"Harness"},{"n":3,"title":"Regression files committed"},{"n":4,"title":"R6 does not apply"}],"stale_clauses":[{"n":2,"title":"rand dual-major, test build only","by":["ADR-0360"],"note":"§2 'rand dual-major, test build only' superseded by ADR-0360"}],"evidence":[{"by":"ADR-0360","treatment":"SUPERSEDES","clauses":[2],"quote":"**Workspace rand pin superseded by ADR-0360.** ADR-0360 migrated the workspace to `rand 0.9`; it supersedes this ADR's §2 workspace pin (the workspace no longer stays on `rand 0.8`, and the storage test build unifies with the workspace's rand 0.9 instead of linking a second major)."}]},{"id":"ADR-0360","title":"Workspace rand 0.9 migration","standing":"in_force","declared_status":"proposed","path":"docs/adr/0360-rand-09-workspace-migration.md","gist":"1. One workspace rand major. The root Cargo.toml declares rand = \"0.9\" (resolved to 0.9.5). cypherlite-executor, cypherlite-datasets, cypherlite-auth and the optional CLI telemetry feature keep consuming rand = { workspace = true }; no per-crate version is pinned and no compatibility shim or…","why":["controls ADR-0268 (§2)"],"live_clauses":[{"n":1,"title":"One workspace rand major"},{"n":2,"title":"The rename surface is applied at every call site"},{"n":3,"title":"wasm32 wiring is target-scoped in `cypherlite-storage`"},{"n":4,"title":"The frozen envelopes are re-frozen by CI, not hand-edited"},{"n":5,"title":"The residual dual version is accepted and bounded"}],"stale_clauses":[]},{"id":"ADR-0380","title":"First-party dependencies are not new dependencies, and the git import's recorded pair cost","standing":"partial","declared_status":"accepted","path":"docs/adr/0380-first-party-dependency-scope.md","gist":"### 1. The dependency rule concerns external crates The no-new-Cargo-dependency rule, and AGENTS.md R6 under it, states a fact about the build's external surface, not about every manifest edit. A first-party workspace edge — a { workspace = true } dependency on an engine crate already in the build…","why":["matches task (clause+fulltext+vector)"],"live_clauses":[{"n":1,"title":"The dependency rule concerns external crates"},{"n":2,"title":"The three instances"},{"n":3,"title":"Pairs are keyed by interned handles, and a row costs"},{"n":4,"title":"No changeset list, and the history goes before the write"},{"n":6,"title":"The correction lands as Later references"}],"stale_clauses":[{"n":5,"title":"The corrected peak, and the caps stand","by":["ADR-0392"],"note":"§5 'The corrected peak, and the caps stand' superseded by ADR-0392"}],"evidence":[{"by":"ADR-0392","treatment":"SUPERSEDES","clauses":[5],"quote":"ADR-0380 §5's itemised subtraction is superseded by §7's direct measurement."}]},{"id":"ADR-0392","title":"The git import commits per batch over a streamed plan","standing":"in_force","declared_status":"accepted","path":"docs/adr/0392-git-import-per-batch-commit.md","gist":"### 1. git-to-graph commits each 1,000-row batch as its own explicit transaction The shared phase runner (lab/write.rs::run_phases) takes a CommitPolicy: WholeImport (ADR-0157's one transaction around every phase — what fs-to-graph keeps, its work bounded by the walked tree) or PerBatch (begin,…","why":["controls ADR-0380 (§5)"],"live_clauses":[{"n":1,"title":"git-to-graph commits each 1,000-row batch as its own explicit transaction"},{"n":2,"title":"Index order, re-anchored to the batch order"},{"n":3,"title":"Failure semantics: committed batches stay, a re-run completes"},{"n":4,"title":"Rows are generated lazily from a bounded plan"},{"n":5,"title":"MAX_CO_CHANGED_PAIRS rises to 5,000,000"},{"n":6,"title":"Every refusal still fires before the store is first written"},{"n":7,"title":"The transient-overhead budget, measured"}],"stale_clauses":[]}],"warnings":["ADR-0268 is partly superseded: §2 'rand dual-major, test build only' superseded by ADR-0360","ADR-0380 is partly superseded: §5 'The corrected peak, and the caps stand' superseded by ADR-0392"],"omitted":9,"tokens":1341,"how_to_read":"live_clauses are good law; stale_clauses were taken out of force by the decision named in `by` - follow that decision instead."}

==================== TASK T02 ====================
Task: Bring MemoryDB to parity with the reference CypherLite for the CIP evaluation scenarios, and decide how the parity gate compares results.

Context retrieved for this task: the decision records of the repository, as written.

--- ADR-0047 ---
# 0047. MemoryDB reaches CypherLite CIP parity

- **Status**: Accepted
- **Date**: 2026-09-16
- **Deciders**: CypherLite / MemoryDB merge

## Decision
1. `memorydb::Database` must pass every CIP-eval scenario passed by the
   checked-in original CypherLite engine. Only scenarios that fail or are
   skipped by the original may fail or be skipped by MemoryDB.
2. The gate compares stable scenario identities as well as aggregate counts.
   Live Engine CIP is replaced by the frozen identity set in
   `testdata/cip-eval/ENGINE_PASSING.json` (ADR-0052). Aggregate CIP counts
   remain in `testdata/cip-eval/BASELINE.json` and
   `baselines/cip-eval-memorydb.json`.
3. Embedded catalog behavior previously excluded by ADR-0046 is now in scope,
   including SHOW users/roles/servers/databases, database DDL, graph types,
   Cypher-version selection, and composite USE where the original implements
   them.
4. `cypherlite-parser` remains the only product grammar. `memorydb-parser` may
   gain AST/IR types but its parser is diagnostic-only.
5. Semantics are ported onto the MemoryDB planner, executor, catalog, CSR,
   overlay, and WAL. The GraphStore storage path is not grafted onto MemoryDB.

--- ADR-0049 ---
# 0049. Gate the merged product in-tree

- **Status**: Accepted
- **Date**: 2026-09-16
- **Deciders**: CypherLite / MemoryDB merge

## Decision
`make gate` tests only the merged `cypherlite/` workspace:

1. legacy CypherLite surface tests and its CIP reference;
2. MemoryDB runtime, front-end, and 3897/3897 TCK;
3. strict MemoryDB-to-original scenario parity;
4. formatting and Clippy;
5. frozen load-test comparisons.

Sibling trees remain read-only historical baselines and are not runtime gate
dependencies.

--- ADR-0203 ---
# 0203. Newest-first expansion order (Neo4j relationship-chain parity)

- **Status**: Proposed
- **Date**: 2026-10-11
- **Deciders**: CypherLite maintainers (LABS-255, LABS-258)
- **Related**: ADR-0031 (typed adjacency), ADR-0033, ADR-0035 (ordered
  expand; tie-break superseded here), ADR-0034 / ADR-0037 (shortest-path
  searches), ADR-0144 (differential suite)

## Decision
Within each per-node, per-type adjacency chunk, relationships iterate
**newest-first**: the ADR-0035 chunk order keeps missing-`ts` first and
present `ts` descending, but the final tie-break flips from ascending
`RelId` to **descending `RelId`** (`cmp_ts_desc` in
`cypherlite-executor/src/store.rs`). ADR-0035's "then `RelId`" is read
as descending from here on.

This one order is the whole parity contract for expansion-driven row
order, with one addition for the GPM selector:

- `shortestPath` (ADR-0034 bidirectional BFS, ADR-0037 shallow
  intersection) inherits the tie-break from the walk: the equal-hop
  path reached through the newest relationships is found first and kept
  (both searches record the first meet and never replace it with an
  equal-length one).
- Aggregating projections keep their existing semantics — groups in
  first-encountered order (`IndexMap`), `ORDER BY` a stable sort — and
  now see MATCH rows in the reference's expansion order, so tied rows
  and `collect()` lists line up.
- GPM path selectors (`SHORTEST k` / `ANY SHORTEST` over the walk
  engine) break equal-length, equal-rel-type ties by the walk's
  **node-id sequence** (lexicographic) before falling back to
  enumeration order. Neo4j's stateful shortest path pops its priority
  queue by cost and then by node id, so the selected walk is the one
  with the smallest node-id sequence — not the one the (newest-first)
  expansion enumerated first. Evidence: CIP-73's @neo4j-verified
  scenario [14] (`SHORTEST 1 WALK` closed walk) returns `[1, 2, 1]`
  although node 4's relationship is the newest; and LABS-255's tied
  trails share one node sequence, so their parallel-relationship choice
  is still the expansion order's (newest rel wins). The node-sequence
  key only reorders members that tie on length AND type signature, so
  enumeration order — newest-first — still decides parallel-relationship
  ties, which share the node sequence.

--- ADR-0119 ---
# 0119. CIP-eval drops frozen scenarios that need Enterprise databases

- **Status**: Accepted
- **Date**: 2026-09-27
- **Deciders**: CypherLite maintainers (Linear LABS-102)

## Decision
1. Remove exactly these 24 identities from `ENGINE_PASSING.json`:
   - `CIP-170-cypher-versions-default-language/01-create-database.feature#0`
     to `#8` (9 identities);
   - `CIP-170-cypher-versions-default-language/02-alter-database.feature#0`
     to `#5` (6);
   - `CIP-170-cypher-versions-default-language/03-show-databases.feature#0`
     to `#2` (3);
   - `CIP-170-cypher-versions-default-language/04-effective-language-aaa.feature#2`,
     `CIP-170-cypher-versions-default-language/05-effective-language-bbb.feature#1`
     and
     `CIP-170-cypher-versions-default-language/07-effective-language-composite.feature#2`
     (3);
   - `CIP-141-call-variable-scope-clause/feature-interactions.feature#3`, `#4`
     and `#5` (3).
2. In the same change, lower `baselines/cip-eval.json` to 9 of 30 for CIP-170
   and 34 of 38 for CIP-141. The ratchet continues upward from there.
3. Keep the feature files unchanged. They record verified Neo4j Enterprise
   behaviour, and rewriting them to CE semantics would falsify their
   provenance. They stay in the suite as failing scenarios.
4. Update the `testdata/cip-eval/MANIFEST.md` rationales that say CypherLite
   has no system database or no multi-database catalog (CIP-42, 68, 242 and
   253, and the graph-reference CIPs 61, 147, 193 and 212). Record CIP-170 as
   supported only for `SET DEFAULT LANGUAGE` on the fixed namespaces.
5. This supersedes ADR-0047 §1 for these 24 identities only. Every other
   frozen identity remains a hard gate.

--- ADR-0046 ---
# 0046. CypherLite parser in front of the MemoryDB runtime

- **Status**: Accepted
- **Date**: 2026-09-16
- **Deciders**: CypherLite / MemoryDB merge

## Decision
1. **Front-end.** `Database::query` uses `cypherlite-parser` + `memorydb-front`. The historical parser is available only with `MEMORYDB_PARSER=memorydb` for diagnostics; it is not a product query path.
2. **TCK floor.** MemoryDB TCK remains 100% (pin 2024.3, 0 skips). CypherLite’s 3 TCK skips are not imported into that gate.
3. **CIP-eval stretch.** Source `cyperlite-original` cip-eval is the language baseline (pass counts only ratchet up). In-tree MemoryDB-backed cip-eval uses `baselines/cip-eval-memorydb.json` until it matches that baseline.
4. **Loadtests.** Fraud / identity / checkpoint must not regress vs frozen `baselines/` summaries (`errors == 0`, ops/s ≥ 90%, p99 ≤ 115%, logical bytes ≤ 110%).
5. **Tier 2 theater.** `SHOW ROLES/SERVERS/USERS`, `CREATE DATABASE`, composite `USE` are documented deviations, not silent fails. User docs may link this ADR.
6. **Contract.** `AGENTS.md` in this tree is the working contract (copied from MemoryDB, updated only via ADR).

Precedent `preflight` for this task (a tool that tracks which decisions are still in force):
{"task":"Bring MemoryDB to parity with the reference CypherLite for the CIP evaluation scenarios, and decide how the parity gate compares results.","paths":[],"decisions":[{"id":"ADR-0119","title":"CIP-eval drops frozen scenarios that need Enterprise databases","standing":"in_force","declared_status":"accepted","path":"docs/adr/0119-cip-eval-drops-enterprise-database-scenarios.md","gist":"1. Remove exactly these 24 identities from ENGINE_PASSING.json: - CIP-170-cypher-versions-default-language/01-create-database.feature#0 to #8 (9 identities); - CIP-170-cypher-versions-default-language/02-alter-database.feature#0 to #5 (6); -…","why":["matches task (clause+fulltext+vector)","controls ADR-0047 (§1)","controls ADR-0046 (a part)"],"live_clauses":[{"n":1,"title":"Remove exactly these 24 identities from ENGINE_PASSING.json:"},{"n":2,"title":"In the same change, lower baselines/cip-eval.json to 9 of 30"},{"n":3,"title":"Keep the feature files unchanged. They record verified Neo4j Enterprise"},{"n":4,"title":"Update the testdata/cip-eval/MANIFEST.md rationales that say CypherLite"},{"n":5,"title":"This supersedes ADR-0047 §1 for these 24 identities only. Every"}],"stale_clauses":[]},{"id":"ADR-0047","title":"MemoryDB reaches CypherLite CIP parity","standing":"partial","declared_status":"accepted","path":"docs/adr/0047-memorydb-cip-parity.md","gist":"1. memorydb::Database must pass every CIP-eval scenario passed by the checked-in original CypherLite engine. Only scenarios that fail or are skipped by the original may fail or be skipped by MemoryDB. 2. The gate compares stable scenario identities as well as aggregate counts. Live Engine CIP is…","why":["matches task (clause+fulltext+vector)","controls ADR-0046 (a part)"],"live_clauses":[{"n":2,"title":"The gate compares stable scenario identities as well as aggregate"},{"n":3,"title":"Embedded catalog behavior previously excluded by ADR-0046 is now in"},{"n":4,"title":"cypherlite-parser remains the only product grammar. memorydb-parser may"},{"n":5,"title":"Semantics are ported onto the MemoryDB planner, executor, catalog, CSR,"}],"stale_clauses":[{"n":1,"title":"memorydb::Database must pass every CIP-eval scenario passed by the","by":["ADR-0119"],"note":"§1 'memorydb::Database must pass every CIP-eval scenario passed by the' superseded by ADR-0119"}],"evidence":[{"by":"ADR-0119","treatment":"SUPERSEDES","clauses":[1],"quote":"ADR-0119 supersedes Decision 1 for 24 frozen CIP-eval identities, in CIP-170 and CIP-141, that need Neo4j Enterprise database administration or composite graphs."}]},{"id":"ADR-0049","title":"Gate the merged product in-tree","standing":"in_force","declared_status":"accepted","path":"docs/adr/0049-in-tree-merged-product-gate.md","gist":"make gate tests only the merged cypherlite/ workspace: 1. legacy CypherLite surface tests and its CIP reference; 2. MemoryDB runtime, front-end, and 3897/3897 TCK; 3. strict MemoryDB-to-original scenario parity; 4. formatting and Clippy; 5. frozen load-test comparisons. Sibling trees remain…","why":["matches task (clause+fulltext+vector)"],"live_clauses":[{"n":1,"title":"legacy CypherLite surface tests and its CIP reference;"},{"n":2,"title":"MemoryDB runtime, front-end, and 3897/3897 TCK;"},{"n":3,"title":"strict MemoryDB-to-original scenario parity;"},{"n":4,"title":"formatting and Clippy;"},{"n":5,"title":"frozen load-test comparisons."}],"stale_clauses":[]},{"id":"ADR-0046","title":"CypherLite parser in front of the MemoryDB runtime","standing":"partial","declared_status":"accepted","path":"docs/adr/0046-cypherlite-parser-memorydb-runtime.md","gist":"1. Front-end. Database::query uses cypherlite-parser + memorydb-front. The historical parser is available only with MEMORYDB_PARSER=memorydb for diagnostics; it is not a product query path. 2. TCK floor. MemoryDB TCK remains 100% (pin 2024.3, 0 skips). CypherLite’s 3 TCK skips are not imported into…","why":["matches task (clause+fulltext+vector)"],"live_clauses":[{"n":2,"title":"TCK floor"},{"n":3,"title":"CIP-eval stretch"},{"n":4,"title":"Loadtests"},{"n":6,"title":"Contract"}],"stale_clauses":[{"n":1,"title":"Front-end","by":["ADR-0277"],"note":"§1 'Front-end' superseded by ADR-0277"},{"n":5,"title":"Tier 2 theater","by":["ADR-0116"],"note":"§5 'Tier 2 theater' superseded by ADR-0116"}],"evidence":[{"by":"ADR-0116","treatment":"SUPERSEDES","clauses":[5],"quote":"ADR-0116: the Tier-2 theater deviations of Decision item 5 are superseded."},{"by":"ADR-0070","treatment":"SUPERSEDES","clauses":[],"quote":"ADR-0070: the two-host-class split is superseded."}]},{"id":"ADR-0277","title":"One Cypher parser","standing":"in_force","declared_status":"proposed","path":"docs/adr/0277-one-cypher-parser.md","gist":"1. parse_and_lower_statement only calls cypherlite_parser::parse and lower_statement. CYPHERLITE_PARSER is not read. 2. cypherlite-ir no longer parses. lex.rs, parse.rs, and parse_query are removed. The IR AST, clause walks, and aggregate-name set stay. 3. Tests that used to call parse_query lower…","why":["controls ADR-0046 (§1)"],"live_clauses":[{"n":1,"title":"parse_and_lower_statement only calls cypherlite_parser::parse and"},{"n":2,"title":"cypherlite-ir no longer parses. lex.rs, parse.rs, and parse_query"},{"n":3,"title":"Tests that used to call parse_query lower through"},{"n":4,"title":"The lowerer is split by clause family (clauses, patterns, expressions)."}],"stale_clauses":[]}],"warnings":["ADR-0047 is partly superseded: §1 'memorydb::Database must pass every CIP-eval scenario passed by the' superseded by ADR-0119","ADR-0046 is partly superseded: §1 'Front-end' superseded by ADR-0277"],"omitted":12,"tokens":1370,"how_to_read":"live_clauses are good law; stale_clauses were taken out of force by the decision named in `by` - follow that decision instead."}

==================== TASK T08 ====================
Task: Let embedders and Bolt clients choose which database a query runs against, and define what happens for an unknown database name.

Context retrieved for this task: the decision records of the repository, as written.

--- ADR-0146 ---
# 0146. Unknown-namespace selection is "Graph not found: \<name\>"

- **Status**: Accepted
- **Date**: 2026-09-28
- **Deciders**: CypherLite maintainers (agreed in conversation with the
  project owner on 2026-09-28)

## Decision
Unknown-namespace **selection** errors use CE's live text
`Graph not found: <name>`, identical to an unknown static `USE` target. The
`DatabaseNotFound` kind token is kept, so bindings' name scans and error
kinds are unchanged.

- `cypherlite_core::ce_messages::database_does_not_exist` now delegates to
  `graph_not_found`; both named entry points stay because the CE paths
  (session database selection vs. statement routing) are distinct call
  sites.
- The GQLSTATUS claim in ADR-0117 §6 is likewise superseded: live CE wires
  `42001` with a `42N00` cause, not top-level `22000` / root-cause `22N51`.
  CypherLite's Bolt server keeps the `CypherLite.Error` code per ADR-0260,
  so the wire code change is informational only; the fixture case's pinned
  root-cause GQLSTATUS is now `42N00`.
- ADR-0117 §6 is superseded by this ADR; the rest of ADR-0117 stands.

--- ADR-0304 ---
# ADR-0304: Bolt compatibility corpus as boltkit `.bolt` scripts, replayed against the real server

Status: Proposed
Claim: 6be6231e21d460a6e1364167cda6fed3d8829fca

## Decision
1. **The Bolt compatibility corpus is boltkit-format `.bolt` scripts, with
   the roles turned around.** The test harness is the client. It sends a
   script's `C:` lines to a real `cypherlite-bolt` process and checks the
   server's replies against the `S:` lines. Scripts live under
   `surfaces/cypherlite-bolt/tests/compat/scripts/`, and every `*.bolt`
   file found there recursively is part of the corpus. Each script runs
   against its own server, started through the `tests/common`
   `start_server`. The default flags are `--uri :memory: --auth none`, and
   a `!: SERVER_ARGS` line replaces them.
2. **The grammar follows boltkit where it applies to a client, and is
   strict everywhere else.** Kept from boltkit: `!:`, `C:` and `S:` lines,
   continuation lines, JSON fields, the Bolt 4.4 message names, `0xNN` for
   any tag, and the `<RAW>`, `<NOOP>` and `<EXIT>` commands. Changed or
   added for the client side:
   - `!: BOLT M.m` is the handshake the harness sends: the magic
     `60 60 B0 17` plus a single `00 00 m M` proposal, padded with zeros to
     four proposals. The harness then expects `00 00 m M` back. Without the
     line, the handshake proposes and expects `4.4`.
   - `!: HANDSHAKE <hex>` sets the expected 4-byte reply.
   - `!: AUTO HELLO` sends HELLO `{user_agent, scheme: "none"}` first and
     expects SUCCESS.
   - `!: AUTO GOODBYE` sends GOODBYE last and expects the server to close
     the connection.
   - `!: SERVER_ARGS` is new.
   - If a script's first `C:` line is a `<RAW>`, the script writes its own
     handshake and no automatic one is sent.
   - `C: <NOOP>` sends an empty chunk (`00 00`).
   - `S: <RAW>` expects exactly the given bytes.
   - `S: <EXIT>` expects the server to close the connection. End of stream
     and a reset both count.
   - A JSON integer is an Int. A number with a fraction or an exponent is a
     Float. `{"#NN": [fields]}` is a structure with hex tag `NN`.

   Anything else is a parse error that names `path:line`. That includes an
   unknown directive or `AUTO` value (boltkit's `!: PORT`, `!: AUTO RESET`),
   an unknown command (`<SLEEP>`) or message name, malformed JSON, a
   duplicate directive, a directive after the first `C:`/`S:` line, and a
   directive that contradicts a leading `<RAW>`. boltkit keeps text it
   cannot parse as JSON as a string field. The harness drops that lenient
   fallback.
3. **Matching rules.**
   - Tags must be equal.
   - An expected map matches when every listed key is present with a
     matching value. Extra server keys are allowed, and the string `"*"`
     as a map value matches any value.
   - Lists and structure fields match element by element under the same
     rules, and must have the same length.
   - Scalars match exactly, and an Int never equals a Float.

   Summary metadata (`type`, `qid`, `t_first`, `bookmark`, `db`) differs
   from Neo4j's and changes as the server is fixed. Subset maps let each
   script assert only what its case is about.
4. **Failures name the script line.** A mismatch reports the script path
   and line, the line as written, the expected value, and the decoded
   actual reply, written in the script notation. Every read and write has
   a 10 s timeout, so a server that never answers fails the step instead
   of hanging the suite. The harness is the Rust integration-test target
   `bolt_compat` (`tests/bolt_compat.rs`, with the `tests/compat/` module
   tree). It reuses `tests/common` and the crate's own `packstream` 

--- ADR-0116 ---
# 0116. Fixed namespaces with Neo4j Community Edition database semantics

- **Status**: Accepted
- **Date**: 2026-09-27
- **Deciders**: CypherLite maintainers (Linear LABS-102)
- **Later references**: ADR-0142 fills in the SHOW DATABASES fields this ADR
  left unspecified (`address`, `role`, `statusMessage`, `writer`) with fixed
  constants for Neo4j Desktop Browser compatibility, and confirms the
  `access`/status/`default`/`home` values decided here.
  ADR-0229 makes `system_ontologies` listed but not queryable: §1's
  "Readable with ordinary Cypher" and §4's 42N18 write gate are superseded —
  every statement routed there except §2's administration commands now
  fails with 42N17 (ADR-022

## Decision
1. **Three fixed namespaces.** Every store has exactly these. None can be
   created, dropped or renamed, and names match case-insensitively.

   | Namespace | SHOW `type` / `access` | Behaviour |
   |---|---|---|
   | `neo4j` | standard / read-write; `default` and `home` | The user data graph. Existing stores are this namespace. |
   | `system` | system / read-write | CE rules: SHOW commands, supported administration commands and procedure calls only. It holds no graph data. |
   | `system_ontologies` | standard / **read-only** | Readable with ordinary Cypher. Cypher cannot write it; only the `db.ontology.*` procedures change it (ADR-0121). It holds at most one ontology, the one for `neo4j`. |

2. **Administration commands follow CE.** These are supported:
   `SHOW DATABASE[S] [name]`, `SHOW DEFAULT DATABASE`, `SHOW HOME DATABASE`,
   and `ALTER DATABASE <name> [IF EXISTS] SET DEFAULT LANGUAGE CYPHER 5|25` as
   the only clause and without `WAIT`.

   Every other database administration command fails with
   `UnsupportedAdministrationCommand`: `Unsupported administration command:
   <statement>`. The statement is echoed verbatim, without a leading
   `CYPHER n`. This covers:
   - `CREATE [OR REPLACE] [COMPOSITE] DATABASE` and `DROP [COMPOSITE] DATABASE`;
   - every other `ALTER DATABASE` item: `SET ACCESS`, `SET OPTION`,
     `REMOVE OPTION`, `SET TOPOLOGY`, `WAIT`;
   - `START DATABASE` and `STOP DATABASE`;
   - `CREATE`, `ALTER` and `DROP ALIAS`, and `SHOW ALIAS[ES] … FOR DATABASE[S]`.

   The parser recognizes these forms so they reach this error rather than a
   syntax error. An `ALTER` of an unknown database fails with `Failed to alter
   the specified database '<name>': Database does not exist.`, unless
   `IF EXISTS` makes it a no-op. Administration commands run from any
   namespace, as they do for a CE client over Bolt. User, role, privilege and
   server commands are out of scope for this ADR and unchanged.
   **Later references** (2026-11-04, live-verified against Neo4j 2026.09
   CE): the closing claim above is wrong for composed forms — the bare
   `SHOW DATABASES` succeeds from the user database as decided here, but
   every composed form off-system (`YIELD …` composed with `MATCH`,
   `WITH`, `UNION`, `NEXT`, …) is rejected 51N28 `NotSystemDatabaseError`
   ("This is an administration command and it should be executed against
   the system database: SHOW DATABASES"). That boundary is DBMS
   session-model semantics — session routing and privilege enforcement —
   and is deliberately not implemented: a single-user embedded engine with
   no privileges and a store-level catalog (ADR-0276) has no wrong
   database a composed administration command could run against, so the
   no-`USE` composed forms keep running from any namespace (user decision
   2026-11-04; the spec harness tags those scenarios
   `@fails:admin-session-boundary`). Two rules from the same verification
   are implemented:
   - §4's system-namespace whitelist is completed: a `WITH` composing an
     administration command's `YIELD`, routed to `system`, fails with
     CE's `The following clauses are not allowed on a system database:
     WITH.` (wire 42001, `Neo.ClientError.Statement.SemanticError`;
     fixture case `use_system_show_databases_with`).
   - An explicit `USE` clause targeting a non-system namespace on a
     statement headed by one of these commands fails with CE's 42N79
     auto-routing rejection ("The `USE` clause is not required for
     

--- ADR-0080 ---
# 0080. CLI `pull` command: Query API v2 into `Database`

- **Status**: Proposed
- **Date**: 2026-09-22
- **Deciders**: CypherLite maintainers

## Decision
1. **`cypherlite pull` is a first-positional lifecycle command**, not a
   flag. Grammar:

   ```text
   cypherlite pull [--from FILE] --query Q [--param N=V] DATABASE
   ```

   `./pull` and `cypherlite -- pull` remain database paths. The command
   exits after pull; it does not enter the REPL or run a follow-up query.

2. **Transport is HTTP Query API v2 via workspace `ureq`.** Product crates
   do not depend on `neo4rs`. Aura hosts use
   `https://{host}/db/{database}/query/v2` (Bolt port stripped; truncated
   `.databases.neo4j` completed to `.io`). `neo4j://host:7687` maps to
   `http://host:7474`. `http://` / `https://` URIs are Query API origins
   (tests and explicit HTTP endpoints).

3. **Credentials.** `--from FILE` is a `KEY=VALUE` env file
   (`NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, optional
   `NEO4J_DATABASE`, default `neo4j`) — the Aura “Created” / `neo4j-cli
   --env-out-file` format. The password is never an argv flag. When
   `--from` is omitted, the process environment supplies the same keys
   (`NEO4J_USER` is an alias of `NEO4J_USERNAME`). Values that look like
   `NEO4J_PASSWORD=secret` are stripped to `secret`.

4. **Shape query.** `--query` is required (file path or inline). There is
   no Movies default. The parser rejects a non-graph `RETURN`
   (scalars, aggregates, `*`, projections) before any network call.

5. **Materialize is a source-scoped union/upsert**, not always-`CREATE`
   and not a full replace of `DATABASE`.

   - Extract keeps the remote `elementId` string on each node and
     relationship. Integers are interned only to wire start/end *within
     one response*.
   - Identity key: `(source, kind, remote elementId)` where `source` is
     the normalized Query API origin plus `NEO4J_DATABASE` (the v2 URL).
     Username and password are not part of the key. Two Aura databases
     may both use `4:uuid:1`.
   - Hit and local element still exists: **reuse**. Nodes: `SET n =
     $props` (source properties win) and **union labels**. Relationships:
     `SET r = $props`.
   - Hit but the local element was deleted: treat as new and remap.
   - Miss: `CREATE` and register the mapping.
   - Elements not in this query are left alone (union, not
     replace-the-database).
   - Local edits on a pulled entity are overwritten the next time that
     entity is pulled.
   - Neo4j `elementId` is not stable across delete+recreate at the
     source; pull does not invent business keys such as `Account.id`.
   - The mapping is **not** stored as user-visible properties. It lives
     on `Graph` (`DashMap` plus reverse index so `DeleteNode` /
     `DeleteRel` drop stale entries), in WAL as additive `RedoOp::
     PullIdentityPut { source, kind, remote_id, local_id }` in the **same
     commit** as the `CREATE`/`SET` ops (one explicit transaction for the
     whole pull), and in snapshot as `pull-identity.json` at checkpoint
     (same durability boundary as `manifest.json`). A missing file or
     `#[serde(default)]` is an empty map; `FORMAT_VERSION` stays 3.
     Snapshot restore loads the map before WAL replay; replay applies
     further `PullIdentityPut`s and deletes. Identity ops are not graph
     CDC events. `:memory:` is rejected — pull must persist.
   - HTTP/Neo4j stay out of the `cypherlite` crate. `cypherlite-load`
     uses a narrow `Connection` upsert API.

6. **Library boundary.** Fetch, extract, and upsert live in
   `cypherlite-load`. The public `cypherlite` crate does not grow HTTP or
   Ne

--- ADR-0200 ---
# ADR-0200: `query` command and `--database`

- **Status**: Proposed
- **Date**: 2026-10-10
- **Deciders**: CypherLite maintainers (Linear [LABS-247](https://linear.app/neo4j/issue/LABS-247/define-the-default-statement-behavior-for-cypherlite))

## Decision
1. **`query` is a first-positional command word in every bundle.** It is a
   statement-session verb, not an exit-after lifecycle command (ADR-0069).
   A directory named `query` is `--database query` or `--database ./query`.
2. **Grammar:** `cypherlite query [STATEMENT] [--database PATH] [session
   flags]`. `STATEMENT` is one Cypher statement or a `;`-separated list, the
   same slot as `-c` / `--command`. The two spellings cannot be combined.
   On the path-first form, no `QUERY` prints help and exits; it does not
   open the shell or read stdin. `query` with no `STATEMENT` keeps the
   session trichotomy: a terminal opens the shell and any other stdin is
   the script list.
3. **`-d` / `--database PATH`** is the store on `query`, on the path-first
   form, on `pull`, and on `info`. `-d` is the short form of `--database`.
   Omitted on a statement session, the store is `:memory:`. `pull` and `info`
   require it and reject `:memory:`. A value that starts with `-` is still a
   path (`-d -dashed_db`).
4. **The path-first form is** `cypherlite [OPTIONS] [--database PATH]
   [QUERY]`. The only positional is the statement. A second positional is a
   usage error. `clone SOURCE DEST` stays two positionals (ADR-0156).
   `lab fs-to-graph` keeps `--db` (ADR-0286).
5. **`query --help`** prints the command synopsis and the same query-run
   options as top-level help, including `--database`, from one shared
   options block.

Precedent `preflight` for this task (a tool that tracks which decisions are still in force):
{"task":"Let embedders and Bolt clients choose which database a query runs against, and define what happens for an unknown database name.","paths":[],"decisions":[{"id":"ADR-0307","title":"Bolt FAILURE carries Neo4j status codes","standing":"in_force","declared_status":"proposed","path":"docs/adr/0307-bolt-failure-carries-neo4j-status-codes.md","gist":"Every Bolt FAILURE carries a Neo4j status code. CypherLite.Error and CypherLite.InternalError are no longer sent. The message is unchanged: it is still the engine's Display text, verbatim, so CypherLite keeps its own wording. 1. Engine errors map by typed variant. failure_for_engine_error in…","why":["controls ADR-0117 (§7)","controls ADR-0116 (§9)","controls ADR-0146 (a part)"],"live_clauses":[{"n":1,"title":"Engine errors map by typed variant"},{"n":2,"title":"The ADR-0260 trust boundary stays"},{"n":3,"title":"Server-side conditions get codes too"},{"n":4,"title":"Memory errors are non-retryable"},{"n":5,"title":"A write-write conflict is retryable"},{"n":6,"title":"Three typed engine variants replace message matching"},{"n":7,"title":"The constants live in `failures.rs`"},{"n":8,"title":"Where the new variants are reported"}],"stale_clauses":[]},{"id":"ADR-0146","title":"Unknown-namespace selection is \"Graph not found: \\<name\\>\"","standing":"partial","declared_status":"accepted","path":"docs/adr/0146-unknown-namespace-selection-is-graph-not-found.md","gist":"Unknown-namespace selection errors use CE's live text Graph not found: <name>, identical to an unknown static USE target. The DatabaseNotFound kind token is kept, so bindings' name scans and error kinds are unchanged. - cypherlite_core::ce_messages::database_does_not_exist now delegates to…","why":["matches task (fulltext+vector)","controls ADR-0117 (§6)","controls ADR-0121 (§2)"],"live_clauses":[],"stale_clauses":[{"n":null,"title":"(part not itemised)","by":["ADR-0307"],"note":"a part is reversed by ADR-0307"}],"evidence":[{"by":"ADR-0307","treatment":"REVERSES","clauses":[],"quote":"ADR-0307 reverses \"CypherLite's Bolt server keeps the `CypherLite.Error` code\": the unknown-namespace error is now the typed `Error::DatabaseNotFound { name }` (same `Graph not found: <name>` text), and Bolt sends it as `Neo.ClientError.Database.DatabaseNotFound`, the code live CE sends."}]},{"id":"ADR-0117","title":"Namespace selection in the embedding APIs and over Bolt","standing":"partial","declared_status":"accepted","path":"docs/adr/0117-namespace-selection-apis-and-bolt.md","gist":"1. Default. Connecting without a namespace keeps today's behaviour: the session namespace is neo4j. 2. Rust. Add Database::connect_namespace(&self, name: &str) -> Result<Connection>, Connection::set_namespace(&mut self, name: &str) -> Result<()> and Connection::namespace(&self) -> &str.…","why":["matches task (clause+fulltext+vector)"],"live_clauses":[{"n":1,"title":"Default"},{"n":2,"title":"Rust"},{"n":3,"title":"C ABI"},{"n":4,"title":"Python"},{"n":5,"title":"WASM"}],"stale_clauses":[{"n":6,"title":"Unknown names","by":["ADR-0146"],"note":"§6 'Unknown names' superseded by ADR-0146"},{"n":7,"title":"Bolt","by":["ADR-0307"],"note":"§7 'Bolt' superseded by ADR-0307"}],"evidence":[{"by":"ADR-0307","treatment":"SUPERSEDES","clauses":[7],"quote":"ADR-0307: supersedes §7's FAILURE code for an unknown `db`."},{"by":"ADR-0146","treatment":"SUPERSEDES","clauses":[6],"quote":"ADR-0146: supersedes §6."}]},{"id":"ADR-0502","title":"The typed C ABI v2 — a native value walker, one error shape carried with the call, the JSON paths removed","standing":"partial","declared_status":"accepted","path":"docs/adr/0502-typed-c-abi-v2.md","gist":"The C ABI is replaced once, pre-public, by a typed v2: a native value walker and a typed params builder are the only value paths, one structured error shape travels with every fallible call, and the JSON value, JSON params, JSON handle API, thread-local error, column-stamp and alias surfaces are…","why":["controls ADR-0117 (a part)"],"live_clauses":[{"n":1,"title":"A native value walker replaces cypherlite_value_json"},{"n":2,"title":"One error shape, carried with the call"},{"n":3,"title":"The JSON handle API, the ADR-0224 column stamp and the"},{"n":4,"title":"A typed params builder mirrors the walker"},{"n":5,"title":"The kind enum stays minimal"},{"n":6,"title":"Element ids keep the engine's elementId() spelling"},{"n":7,"title":"Bookmarks are the engine's commit sequence"},{"n":8,"title":"The version is 2, and the break happens once"}],"stale_clauses":[{"n":null,"title":"(part not itemised)","by":["ADR-0310"],"note":"a part is withdrawn by ADR-0310"}],"evidence":[{"by":"ADR-0310","treatment":"WITHDRAWS","clauses":[],"quote":"ADR-0310 (revised while Proposed): Bolt adopts §7's engine commit sequence for its own bookmarks, retiring the listener counter this ADR's Consequences left out of scope."}]}],"warnings":["ADR-0146 is partly superseded: a part is reversed by ADR-0307","ADR-0117 is partly superseded: §6 'Unknown names' superseded by ADR-0146","ADR-0502 is partly superseded: a part is withdrawn by ADR-0310"],"omitted":18,"tokens":1235,"how_to_read":"live_clauses are good law; stale_clauses were taken out of force by the decision named in `by` - follow that decision instead."}

==================== TASK T15 ====================
Task: Map an ontology document onto a graph and a graph type when applying it, including how failures are reported.

Context retrieved for this task: the decision records of the repository, as written.

--- ADR-0226 ---
# 0226. Pin the ontology mappings: document to graph, ontology to graph type

- **Status**: Accepted
- **Date**: 2026-10-12
- **Deciders**: CypherLite maintainers (Linear LABS-132)

## Decision
### 1. Document → `system_ontologies` graph

Every node and relationship in the derived graph carries the property
`ontology :: STRING` with the value `'neo4j'` (ADR-0121 §5), naming the
database the stored ontology belongs to.

The graph mirrors the document as written, one graph element per document
construct:

| Document construct | Graph element | Properties (besides `ontology`) |
|---|---|---|
| document root | `(:Ontology)` | `schema`, `id`, `version`, `name`, `description` |
| `nodes` entry | `(:OntologyNode)` | `key` (the map key), `label` (the identifying label: `label`, or `labels.identifier`), `implied` (list, from `labels.implied`), `optional` (list, from `labels.optional`), `description`, `aliases` (list), `reference` |
| `relationships` entry | `(:OntologyRelationship)` | `key`, `type`, `from_count`, `from_min_count`, `from_max_count`, `to_count`, `to_min_count`, `to_max_count` (integers), `description`, `aliases`, `reference` |
| property of a node or relationship entry | `(:OntologyProperty)` | `name` (the map key), `type` (the token), `dimension` (integer), `mustExist`, `unique`, `key` (booleans), `one_of` (canonical JSON string), `pattern`, `description`, `aliases`, `reference` |
| constraint object | `(:OntologyConstraint)` | `constraint_type` (`key` \| `unique` \| `mustExist`), `name` |
| named extension | `(:OntologyExtension)` | `key` (e.g. `neo4j:index`), `custom: false`, `payload` (canonical JSON string of the value) |
| custom extension (envelope) | `(:OntologyExtension)` | `key: 'custom'`, `custom: true`, `type`, `schema`, `name`, `definition` (canonical JSON string) |

Absent optional fields produce absent graph properties (the spec's "absent
means none"). The shorthand flags stay flags: they are boolean properties
on `:OntologyProperty`, and only explicit constraint objects become
`:OntologyConstraint` nodes. Arbitrary JSON subtrees (`one_of` entries,
named-extension payloads, custom `definition` values) are stored as
canonical JSON text — compact, object keys sorted — so a JSON and a YAML
submission of the same logical document derive the same graph.

Relationships in the derived graph:

- `(:Ontology)-[:HAS_NODE]->(:OntologyNode)` and
  `(:Ontology)-[:HAS_RELATIONSHIP]->(:OntologyRelationship)`;
- owner `-[:HAS_PROPERTY]->(:OntologyProperty)`,
  `-[:HAS_CONSTRAINT]->(:OntologyConstraint)` and
  `-[:HAS_EXTENSION]->(:OntologyExtension)`, where the owner is the root, a
  node entry, a relationship entry or (for extensions) a property;
- `(:OntologyRelationship)-[:FROM]->(:OntologyNode)` and `-[:TO]->`,
  resolving `from.node` / `to.node` to the entry with that `key`;
- `(:OntologyConstraint)-[:CONSTRAINS]->(:OntologyProperty)` for each
  listed property.

**Deterministic ids.** Node ids are assigned 0, 1, 2, … in a fixed
traversal: the root first; then each `nodes` entry in document order — the
entry node, then its property, constraint and extension nodes, each group
in document order (`custom` entries in list order at the position of the
`custom` key); then each `relationships` entry likewise; then the root's
extension nodes. Relationship ids are assigned 0, 1, 2, … in creation
order: each element's `HAS_*` and `CONSTRAINS` edges are created with its
child node, and a relationship entry's `FROM`/`TO` edges when its node is
created (node entries always exist by then, `nodes` being traversed first).
The build is a pure function of the parsed document with source key order
preserved, so an unchanged document yi

--- ADR-0364 ---
# ADR-0364: Bump the ontology document gate to the main graph-spec schema

Status: Accepted
Claim: 0872cff15343509eed66966617919b69db51e2e8

## Decision
### 1. One gate URI, hard cutover

- The only accepted value of the root `schema` field is
  `https://neo4j.com/docs/ontology-graph-spec/1.0.0/schema.json` — main's
  `$id`. It is checked before structural validation, as ADR-0227 §7
  prescribes, on the `set` entry point. The old
  `https://neo4j.com/ontology-graph-spec/1.0.0/schema.json` and any other
  URI string fail with
  `Unsupported ontology spec version: '<uri>'. This version of CypherLite
  supports up to Ontology Graph Spec 1.0.0
  ('https://neo4j.com/docs/ontology-graph-spec/1.0.0/schema.json').`
  A non-string `schema` is not a URI at all and fails as a type error on
  that field. `PINNED_SCHEMA_URI` becomes the new URI;
  `MAX_SUPPORTED_SPEC_VERSION` stays `1.0.0`.
- **Hard cutover**: no dual gate, no URI alias, no rewrite of the
  submitted value, no automatic migration. A pre-bump document is not
  accepted by `set`; resubmitting a main-shape document is the migration.
  A document that carries the new URI but the old shape fails structural
  validation on its first old member (for example an integer `version` or
  `mustExist`); a document that carries the old URI fails at the gate
  before structure is looked at. In short, the raised gate together with
  the closed new shapes rejects every pre-bump document, whichever URI it
  carries.
- The vendored schema file's `$id` is the same URI; the gate is on the
  submitted document's `schema` field, not on the vendored `$id`.
- The exact-URI rule remains CypherLite policy: main's `schema` is a
  plain string, so the schema cannot enforce it. Keeping an exact marker
  is what makes a newer dialect fail loudly instead of being misread.
  Supporting a later spec version is still a new ADR (new vendored
  schema, validator update, raised gate).

### 2. Validation follows main's closed shapes

The vendored schema file is replaced in place with main @
`066515593ae59317d758bcf2cef54195e74bde39`, and the hand-rolled
validator checks exactly that document. The accepted shape is main's:

| Construct | Accepted shape |
|---|---|
| Root | required `schema`, `version`, `id`; `name`, `description` strings; `nodes`, `relationships` maps; `extensions`. `version` is any string (the integer/minimum rule is gone), carried verbatim. `schema` is gated per §1. The root is closed: no `$schema`/`$id` document members. |
| Node entry | keyed by node id; `label` nullable string; `labels` object with nullable `identifier`, `implied`/`optional` string arrays, `extensions` and no required members; `properties` map; `constraints` map; `extensions`; nullable `name`; `description`, `aliases`, `reference`. |
| Relationship entry | keyed by relationship id; required `type`, `from`, `to`; `properties` map; `constraints` map; `extensions`; nullable `name`; `description`, `aliases`, `reference`. |
| `RelationshipTarget` | no required members; `node` and `label` optional strings; `count`, `min_count`, `max_count` nullable integers with no minimums. |
| Property entry | keyed by property id; optional `type` from the closed `Neo4jType` enum; nullable `dimension` (integer); nullable `must_exist`, `unique`, `key`; `one_of` array of **strings**; nullable `name`; `description`, `reference`, `pattern`; `extensions`. `mustExist` and `aliases` are gone and are rejected as unknown members. |
| Node constraint | id-keyed map; required `type` (`EXISTS` \| `KEY` \| `PROPERTY_TYPE` \| `UNIQUE`) and `properties` (string array, no `minItems`); nullable `label`; `extensions`; null

--- ADR-0487 ---
# ADR-0487: Bump the ontology document gate to Ontology Graph Spec 1.1.0

Status: Accepted
Claim: 247bd141ff7cf03e5a7cf75eda2665ee4e52a8a3

## Decision
### 1. One gate URI, hard cutover again

- The only accepted value of the root `schema` field becomes
  `https://neo4j.com/docs/ontology-graph-spec/1.1.0/schema.json` — the
  release tag's `$id`, checked before structural validation as before.
  `PINNED_SCHEMA_URI` becomes the new URI and
  `MAX_SUPPORTED_SPEC_VERSION` becomes `1.1.0`; the
  `UnsupportedSpecVersion` message interpolates both, so it cannot drift.
  The retired 1.0.0 main URI, the older draft URI, and any other string
  fail at the gate.
- Hard cutover, for the same reasons as ADR-0364 §1: no dual gate, no URI
  alias, no rewrite, no automatic migration. A 1.0.0-main document fails
  `set` at the gate; a 1.1.0-URI document carrying a 1.0.0-only member
  fails structural validation on that member. Resubmitting a 1.1.0-shape
  document is the migration.
- Stored documents are never re-validated (ADR-0364 §4, unchanged): `get`
  keeps returning a stored 1.0.0 document's bytes verbatim, format
  conversion still runs no gate, and `apply` refuses it with the gate's
  error until it is replaced.

### 2. Validation follows the 1.1.0 shapes

The vendored schema file is replaced in place with the tag's schema and
the hand-rolled validator checks exactly that document. The six deltas
land as:

| Construct | Change |
|---|---|
| Node entry | `name` is an unknown member (the closed set loses it). |
| Relationship entry | `name` is an unknown member. |
| Property entry | `aliases` (string array) is accepted and carried, descriptive like node and relationship `aliases`; `mustExist` stays unknown. |
| Constraint objects (both owners) | one closed shape: `type`, `properties`, `extensions`, nullable `name`. `label` is an unknown member on node constraints too; the validator's node-vs-relationship constraint distinction collapses with it. |
| Document extensions | `data_source_tables` and `data_source_mappings`, deeply validated exactly as `tables`/`mappings` were; the old key spellings are unknown members. |
| Table columns | gained `nullable` (a plain optional boolean, read with the shared boolean reader); every other `TableColumn` member is unchanged. |
| Root, labels, endpoints, indexes, display, mappings | unchanged. |

### 3. Converter on the new shapes (ADR-0226 §2 re-based)

ADR-0364 §5 survives except where it reads the removed members:

- The §5.1/§5.4 node-constraint `label` rules die: a constraint always
  compiles against its owning element, and the label check is deleted
  with the member.
- Node and relationship display `name`s no longer exist to carry; the
  property, constraint and index `name`s remain descriptive (a constraint
  object's `name` still rides the graph-type constraint name).
- Property `aliases` is descriptive and compiles to nothing, exactly like
  node and relationship `aliases`.
- The token mapping (§5.2), the shorthand flags and the
  object-replaces-flag rule, the `PROPERTY_TYPE` loud failure, endpoint
  resolution, and every other §5.3/§5.4 loud mapping error stand
  unchanged.

### 4. Example fixture and provenance

`schema/example.json` is reworked to the 1.1.0 shape — same coverage
contract as ADR-0364 §6 (every `Neo4jType` token, all four constraint
types, the nullable/empty forms, every typed extension member) — with the
node/relationship `name`s and constraint `label`s removed, property
`aliases` added, and the document extension keys renamed.
`schema/README.md` records the new pin (`release-spec/v1.1.0` @
`5ff2c20aa7e428e7c563b17f573157293959a00

--- ADR-0120 ---
# 0120. Persist the ontology as a document and derive `system_ontologies`

- **Status**: Accepted
- **Date**: 2026-09-27
- **Deciders**: CypherLite maintainers (Linear LABS-102)

## Decision
1. **The document is the source of truth.** The stored state is the validated
   ontology JSON for `neo4j`, kept verbatim. There is at most one.
2. **The graph is derived.** The `system_ontologies` graph is built from the
   document at open and after each committed set or drop, and then replaces
   the previous graph atomically. Statements and transactions keep the graph
   they captured (ADR-0116 §5). The build is deterministic: node and
   relationship ids follow document order, so element ids (ADR-0116 §7) stay
   the same across restarts and change only when the ontology is replaced. The
   derived graph carries a fixed graph type that describes the ontology model.
3. **WAL operations.** Two new store-level redo ops, which are not graph ops:
   `OntologySet { database, spec }` and `OntologyDrop { database }`. The
   document is limited to 16 MiB, the ADR-0086 object envelope, and the limit
   is checked before the commit is written.
4. **WAL segment magic `MDBWAL02`.** The frame layout does not change.
   - A segment created while the store holds an ontology, committed or still
     pending in the WAL, starts with `MDBWAL02`. Other segments start with
     `MDBWAL01`.
   - When an ontology op commits while the active segment is `MDBWAL01`, the
     WAL first rotates to a fresh `MDBWAL02` segment.
   - An ontology op in an `MDBWAL01` segment is corruption.
   - A short header repaired under ADR-0086 §1 becomes `MDBWAL01`. Such a
     segment holds no frames, and ontology ops are never appended to it.
   - Native ownership checks (ADR-0090) recognize both magics.
5. **Parquet snapshot.** The manifest gains an optional `ontology_path` that
   selects one immutable `ontology/<128-bit-hex>.json` object. The object is
   written and published under the pull-identity rules of ADR-0092 and
   ADR-0089: exclusive create, sync and a durable name before the manifest,
   and old objects retired only after publication. A manifest with
   `ontology_path` has `format_version: 4`; one without it stays at 3. Readers
   accept 1 to 4.
6. **JSON snapshot.** `graph.json` gains an optional inline `ontology` string,
   for the same reasons ADR-0106 inlines pull identity. A `graph.json` that
   carries it is written with `value_encoding: 3`, which means value encoding
   2 plus the ontology field; one without it keeps 2. The JSON
   `manifest.json` envelope is unchanged.
7. **Bundles.** A `.cl` store keeps the ontology object at a virtual path. The
   bundle container and its single WAL stream are unchanged (ADR-0074).
8. **The format follows the content.** A store that never sets an ontology
   stays byte-for-byte in today's format and readable by older binaries. Once a
   store holds an ontology, older binaries fail at the `MDBWAL02` segment, the
   v4 manifest or `value_encoding: 3`, each time before modifying that data.
   After the ontology is dropped and a checkpoint publishes, new segments are
   `MDBWAL01` again. Once the `MDBWAL02` segments are recycled and the
   manifest is back at v3, older binaries can open the store again.

--- ADR-0227 ---
# 0227. Ontology document format: JSON or YAML, stored verbatim

- **Status**: Accepted
- **Date**: 2026-10-12
- **Deciders**: CypherLite maintainers (Linear LABS-132)

## Decision
1. **Signatures follow CIP-287.** `db.ontology.set(ontology :: STRING)`,
   `db.ontology.get(format = "yaml" :: STRING) :: (ontology :: STRING)`,
   `db.ontology.drop()` and `db.ontology.apply()`. There is no database
   argument: each procedure acts on the database it is executed against —
   the session database or the `USE` target (ADR-0116 §3). Executed against
   `system` or `system_ontologies`, the procedures fail with ADR-0121 §2's
   `Ontologies can only be stored for the user database 'neo4j'.`, now
   applied to the session/USE target rather than to a database argument; an
   unknown `USE` target fails at routing with 42N00 (ADR-0116 §3) before
   this surface is reached. The optional database argument may return as a
   future extension, without breaking these signatures.
2. **JSON or YAML in; the stored bytes stay verbatim.** `set` accepts a
   document in JSON or YAML 1.2. The submitted string is stored verbatim —
   ADR-0120 §1's "the validated ontology JSON kept verbatim" is amended to
   "the validated ontology document, JSON or YAML, kept verbatim" — and the
   ADR-0120 §3 16 MiB envelope limit applies to the submitted string
   regardless of syntax. The store records no JSON-vs-YAML marker — only
   the bytes.
3. **`get` returns the requested format.** `format` is `"yaml"` (the
   default — CIP-287's choice: more compact than JSON, so cheaper in agent
   context) or `"json"`; any other value fails with an argument error
   naming the two. When the requested format matches the stored one, `get`
   returns the stored bytes unchanged — YAML in, YAML out, comments and
   formatting included; likewise JSON. Otherwise it parses the stored
   document into the value model of (4) and serializes it canonically in
   the requested format: compact UTF-8 for JSON, block style with
   two-space indentation for YAML, in both cases preserving the document's
   key order, which the value model carries. Conversion never touches the
   stored bytes; a later `get` in the stored format still returns them
   unchanged. The stored format is detected at read time by a strict JSON
   parse: a stored document that parses as JSON counts as JSON, anything
   else as YAML.
4. **One parse path.** The string is parsed once as YAML 1.2 (a superset of
   JSON) into a JSON-equivalent value model: maps with string keys in
   source order, lists, strings, integers, floats, booleans, null. Source
   key order is preserved — ADR-0226's deterministic id assignment and
   (3)'s canonical serialization depend on it. Anything outside that model
   — non-string mapping keys, custom tags, non-finite floats — is rejected
   at parse time. Validation, version gating, graph derivation and
   format conversion all consume this one model, so both syntaxes behave
   identically after parsing.
5. **YAML crate: `saphyr`.** `cypherlite/cypherlite-ontology` depends on
   `saphyr` (with `saphyr-parser`) for YAML parsing and serialization. R6
   justification: pure safe Rust, no build script and no native code, a
   small transitive tree, YAML 1.2 semantics matching the spec's examples,
   and the actively maintained line of the yaml-rust family. `set` never
   re-serializes; the only product-path serialization is a converting
   `get` (3), which emits from the parsed value model and leaves the stored
   bytes alone.
6. **Hand-rolled validation against the vendored schema.** The pinned draft
   schema is vendored as `ontology-graph-spec.schema.json` in
   `cypherlite/cyphe

Precedent `preflight` for this task (a tool that tracks which decisions are still in force):
{"task":"Map an ontology document onto a graph and a graph type when applying it, including how failures are reported.","paths":[],"decisions":[{"id":"ADR-0229","title":"Remove the `system_ontologies` Cypher surface","standing":"in_force","declared_status":"accepted","path":"docs/adr/0229-remove-system-ontologies-cypher-surface.md","gist":"1. Listed, not queryable. system_ontologies stays a fixed, listed namespace. SHOW DATABASES keeps its row with ADR-0116 §6's values verbatim (type standard, access read-only, currentStatus and requestedStatus online, default and home false, empty aliases and constituents, the stored…","why":["matches task (clause+fulltext+vector)","controls ADR-0226 (§1)","controls ADR-0120 (§2)"],"live_clauses":[{"n":1,"title":"Listed, not queryable"},{"n":2,"title":"The error"},{"n":3,"title":"No derived graph"},{"n":4,"title":"The mapping code is deleted; ADR-0226 §1 is not shipped"},{"n":5,"title":"Element ids: decode-only"},{"n":6,"title":"`apply` is unchanged"}],"stale_clauses":[]},{"id":"ADR-0364","title":"Bump the ontology document gate to the main graph-spec schema","standing":"partial","declared_status":"accepted","path":"docs/adr/0364-ontology-spec-main-gate.md","gist":"### 1. One gate URI, hard cutover - The only accepted value of the root schema field is https://neo4j.com/docs/ontology-graph-spec/1.0.0/schema.json — main's $id. It is checked before structural validation, as ADR-0227 §7 prescribes, on the set entry point. The old…","why":["matches task (clause+fulltext+vector)","controls ADR-0227 (§6–7)","controls ADR-0228 (a part)"],"live_clauses":[{"n":3,"title":"Where CypherLite stays stricter, and why"},{"n":4,"title":"Stored documents are never re-validated"}],"stale_clauses":[{"n":1,"title":"One gate URI, hard cutover","by":["ADR-0487"],"note":"§1 'One gate URI, hard cutover' superseded by ADR-0487"},{"n":2,"title":"Validation follows main's closed shapes","by":["ADR-0487"],"note":"§2 \"Validation follows main's closed shapes\" superseded by ADR-0487"},{"n":5,"title":"ADR-0226 §2 converter on the new shapes","by":["ADR-0487"],"note":"§5 'ADR-0226 §2 converter on the new shapes' superseded by ADR-0487"},{"n":6,"title":"Example fixture: CypherLite-authored, main-shaped, validation-only","by":["ADR-0487"],"note":"§6 'Example fixture: CypherLite-authored, main-shaped, validation-only' superseded by ADR-0487"}],"evidence":[{"by":"ADR-0487","treatment":"SUPERSEDES","clauses":[1,2,5,6],"quote":"ADR-0364's §1 gate URI, §2 accepted shapes, §5.1/§5.4 constraint-label rules and §6 example are superseded by this ADR (noted there)"}]},{"id":"ADR-0226","title":"Pin the ontology mappings: document to graph, ontology to graph type","standing":"partial","declared_status":"accepted","path":"docs/adr/0226-ontology-mappings.md","gist":"### 1. Document → system_ontologies graph Every node and relationship in the derived graph carries the property ontology :: STRING with the value 'neo4j' (ADR-0121 §5), naming the database the stored ontology belongs to. The graph mirrors the document as written, one graph element per document…","why":["matches task (clause+fulltext+vector)","controls ADR-0121 (§5)"],"live_clauses":[{"n":3,"title":"How apply fails on violating data"},{"n":4,"title":"Only on success does the existing SET path run: the"}],"stale_clauses":[{"n":1,"title":"Document → system_ontologies graph","by":["ADR-0229"],"note":"§1 'Document → system_ontologies graph' superseded by ADR-0229"},{"n":2,"title":"Ontology → graph type (db.ontology.apply)","by":["ADR-0228"],"note":"§2 'Ontology → graph type (db.ontology.apply)' superseded by ADR-0228"}],"evidence":[{"by":"ADR-0229","treatment":"SUPERSEDES","clauses":[1],"quote":"ADR-0229 removes §1 from the shipped crate: the document→`system_ontologies` mapping, its deterministic build and its fixed graph type are deleted — the namespace is listed but not queryable, and no graph is derived (superseding ADR-0120 §2)."},{"by":"ADR-0228","treatment":"SUPERSEDES","clauses":[2],"quote":"ADR-0226 §2's \"`LIST<ANY>` to `LIST<ANY>`\" clause is superseded; the rest of the token mapping stands."}]},{"id":"ADR-0228","title":"Ontology list property types map to closed CIP-176 list types","standing":"partial","declared_status":"accepted","path":"docs/adr/0228-ontology-list-property-types-closed.md","gist":"In the ADR-0226 §2 mapping (cypherlite_ontology::to_graph_type_body): - LIST<X> maps to its closed CIP-176 form LIST<X NOT NULL> — the only spelling of the token a graph type accepts, matching the parser's own rule for property types. - LIST<ANY> declares nothing — like bare ANY and BYTES, it has…","why":["matches task (fulltext+vector)","controls ADR-0226 (§2)"],"live_clauses":[],"stale_clauses":[{"n":null,"title":"(part not itemised)","by":["ADR-0364"],"note":"a part is superseded by ADR-0364"}],"evidence":[{"by":"ADR-0364","treatment":"SUPERSEDES","clauses":[],"quote":"ADR-0228's \"declares nothing\" rule survives and its token vocabulary is superseded by §5.2."}]},{"id":"ADR-0487","title":"Bump the ontology document gate to Ontology Graph Spec 1.1.0","standing":"in_force","declared_status":"accepted","path":"docs/adr/0487-ontology-graph-spec-1-1-0-bump.md","gist":"### 1. One gate URI, hard cutover again - The only accepted value of the root schema field becomes https://neo4j.com/docs/ontology-graph-spec/1.1.0/schema.json — the release tag's $id, checked before structural validation as before. PINNED_SCHEMA_URI becomes the new URI and…","why":["matches task (fulltext+vector)","controls ADR-0364 (§1–2, §5–6)"],"live_clauses":[{"n":1,"title":"One gate URI, hard cutover again"},{"n":2,"title":"Validation follows the 1.1.0 shapes"},{"n":3,"title":"Converter on the new shapes (ADR-0226 §2 re-based)"},{"n":4,"title":"Example fixture and provenance"}],"stale_clauses":[]}],"warnings":["ADR-0364 is partly superseded: §1 'One gate URI, hard cutover' superseded by ADR-0487","ADR-0226 is partly superseded: §1 'Document → system_ontologies graph' superseded by ADR-0229","ADR-0228 is partly superseded: a part is superseded by ADR-0364"],"omitted":8,"tokens":1479,"how_to_read":"live_clauses are good law; stale_clauses were taken out of force by the decision named in `by` - follow that decision instead."}