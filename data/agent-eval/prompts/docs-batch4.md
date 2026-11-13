You are a coding agent in a repository that keeps architecture decision records (ADRs). Below are 6 independent tasks.
For each task you get context retrieved for it. Decide which numbered decision clauses your plan for the task must
respect or build on (ADR number and clause number), at most 8, most important first. Use only the context in this
file: do not read any other file, search the repository or run commands.

Answer with a single JSON array, one object per task, in this exact shape and nothing else:

[{"task_id": "T01", "relies_on": [{"adr": "ADR-0046", "clause": 2}], "note": "one sentence on your plan"}]

Use `"clause": null` for a decision that has no numbered clauses.


==================== TASK T01 ====================
Task: Add a new Cypher syntax feature to the parser that sits in front of the MemoryDB runtime, and keep the conformance gates green.

Context retrieved for this task: the decision records of the repository, as written.

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

--- ADR-0066 ---
# 0066. Retire the MemoryDB name in favor of cypherlite

- **Status**: Accepted
- **Date**: 2026-09-19
- **Deciders**: CypherLite / MemoryDB merge (post-merge cleanup)

## Decision
Retire the MemoryDB name from every live surface. The product name is
**cypherlite** everywhere it is visible. The new coordinates are:

- **npm package**: `cypherlite` (was `memorydb`).
- **Go module**: `github.com/neo4j-labs/cypherlite/clients/go` (was
  `github.com/memorydb/memorydb/clients/go`).
- **Java**: groupId/package `com.cypherlite` (was `com.memorydb`); the
  exception type `MemoryDbException` becomes `CypherLiteException`.
- **CIP scoreboard**: `baselines/cip-eval.json` (was
  `baselines/cip-eval-memorydb.json`), with its references in `AGENTS.md`, the
  `Makefile`, and CI updated to match.
- **Environment variables**: `CIP_EVAL_*` (was `CIP_EVAL_MEMORYDB_*`).
- **Diagnostic parser value**: `CYPHERLITE_PARSER=planner-ir` (was
  `CYPHERLITE_PARSER=memorydb`); the historical parser path is unchanged, only
  its diagnostic label is renamed.

The following are **exclusions** and stay untouched, because rewriting them
would falsify history rather than retire a live surface:

- immutable Accepted ADRs under `docs/adr/` — their text records decisions as
  they were made and is not edited;
- released `CHANGELOG.md` sections — shipped history is not retroactively
  rewritten;
- frozen research notes under `testdata/cip-eval/**/NOTES.md` — these are
  point-in-time research artifacts, not live product surfaces.

This ADR records the naming decision only. The mechanical rename of each
coordinate to the values above is carried out by the accompanying cleanup.

--- ADR-0454 ---
# ADR-0454: The obfuscated literal gates at the lexer

Status: Proposed

Claim: 5495436b8757cc3f6b8ed26a5021244869471ee7

## Decision
Register `obfuscated-literals` in the ADR-0371 preview registry
(`CYPHERLITE_PREVIEW=obfuscated-literals`), but gate it at the lexer: with
the feature enabled, a run of exactly six `*` lexes as one
`ObfuscatedLiteral` token that parses to a dummy `false` literal; with it
disabled, the run lexes as ordinary `Star` tokens and the parser fails
with its own syntax error — Neo4j's disabled-form behavior, not the
authored preview error. The front's detector loop carries the feature's
arm as `false` (nothing to detect: a statement that parsed never used the
disabled gate), and the front derives the lexer options from the store's
resolved preview set, so no second configuration surface exists.

--- ADR-0053 ---
# ADR 0053: CypherLite product names

## Decision
In the `cypherlite/` workspace only:

- The embeddable library crate is `cypherlite`; the type is `cypherlite::Database`.
- Runtime crates are `cypherlite-core`, `cypherlite-front`, `cypherlite-planner`,
  `cypherlite-executor`, `cypherlite-storage`, `cypherlite-catalog`.
- The planner AST crate is `cypherlite-ir`. It is not a second Cypher parser;
  `cypherlite-parser` remains the query lexer/AST; `cypherlite-front` lowers it
  to planner IR.
- One CLI: binary `cypherlite`. Flags `--memory-limit`, `--wal-dir`, and
  `--checkpoint-interval-secs` live here. Package `memorydb-cli` / binary
  `memorydb` is deleted.
- Product C ABI remains `cypherlite_*` (`cypherlite-ffi`) for Swift and the
  published header. Bolt language clients keep a distinct shared library
  (`cypherlite-bolt-ffi`, formerly `memorydb-ffi`, C symbols still `memorydb_*`).
  The two ABIs are not merged in this change.
- Strict TCK stays `cypherlite-tck` (3877 pass, 3 documented skips). The 3897/3897
  openCypher floor is `cypherlite-tck-opencypher` (formerly `memorydb-tck`).
  Feature corpora are not merged.
- Canonical env vars are `CYPHERLITE_SNAPSHOT_FORMAT`, `CYPHERLITE_MEMORY_LIMIT`,
  `CYPHERLITE_CHECKPOINT_INTERVAL_SECS`, `CYPHERLITE_COMMIT_TIMING`,
  `CYPHERLITE_SHARD_TARGET_BYTES`, `CYPHERLITE_PARSER`. If unset, the matching
  `MEMORYDB_*` name is still read.
- Clients implementing embedded Relate, and the `../memorydb` quarry,
  are out of scope.

==================== TASK T17 ====================
Task: Make the CLI discover the latest release from the static releases.json on the website, including how it downloads assets and what it does when discovery fails.

Context retrieved for this task: the decision records of the repository, as written.

--- ADR-0250 ---
# ADR-0250: Release discovery from a static releases.json on the website

Status: Accepted

Later references: ADR-0546 supersedes this ADR's publisher contract
(commits to a local `gh-pages` branch) — releases.json now rides the
release's assets and relate-web pulls it. The schema, the canonical URLs,
and the window rule are unchanged.

## Decision
Publish `releases.json` at the website root and make `upgrade`/`update` read
it. The GitHub REST API leaves the update path entirely — no fallback, not
even when `GITHUB_TOKEN` is set.

### 1. Canonical URL and hosting

- The canonical URL is
  `https://neo4j-labs.github.io/cypherlite/releases.json`.
- The file lives at the root of the `gh-pages` branch. It is written only by
  the release pipeline and never hand-edited — the same pipeline-owned
  convention as `install.sh` and `wasm/` (`gh-pages/MAINTAINING.md`).
- A new job in `.github/workflows/release.yml` publishes it after
  `release-notes` (so the notes in the file are final) and after
  `create-release` (so the asset list is complete), reading the release list
  with the workflow's `GITHUB_TOKEN`. It commits `releases.json` to
  `gh-pages` with the same checkout/commit/push pattern as the existing
  install.sh sync job. `deploy-pages.yml` copies the branch tree verbatim,
  so no change is needed there.
- The publisher reads the GitHub API; the CLI never does. The API's
  anonymous rate limit is a per-user problem, not a per-workflow one.

### 2. Schema (`schema_version` 1)

The document is UTF-8 JSON with exactly these top-level keys:

| Key | Type | Required | Nullable | Meaning |
| --- | --- | --- | --- | --- |
| `schema_version` | integer | yes | no | Schema revision; `1` as defined here |
| `generated_at` | string (RFC 3339 UTC, `Z`) | yes | no | When the publisher wrote the file |
| `latest` | release object | yes | yes | Newest stable release; `null` iff no stable release exists |
| `latest_prerelease` | release object | yes | yes | Newest published non-draft prerelease, or `null`; the CLI does not consume it (prereleases are out of scope), the slot is reserved |
| `releases` | array of release objects | yes | no | Recent-releases window, newest first; may be empty |

A **release object** has exactly these keys:

| Key | Type | Required | Nullable | Meaning |
| --- | --- | --- | --- | --- |
| `tag` | string | yes | no | Exact git tag including the leading `v`, e.g. `v0.10.0` |
| `published_at` | string (RFC 3339 UTC, `Z`) | yes | no | When the GitHub release was published |
| `notes` | string | yes | no | The release body markdown verbatim (after `release-notes`); the empty string when the release has no body — never `null` |
| `prerelease` | boolean | yes | no | Whether the release is a prerelease |
| `assets` | array of strings | yes | no | Exact GitHub release asset names, e.g. `cypherlite-darwin-arm64`, `SHA256SUMS`, `SHA256SUMS.sig`; may be empty |

**Window rule.** `releases` holds the **10 most recent stable releases**
(published, non-draft, non-prerelease), newest first, including the release
that generated the file; fewer when fewer exist. `latest` equals
`releases[0]` when `releases` is non-empty, and is `null` when it is empty.
Prereleases never appear in `releases` in schema version 1; a prerelease
publish updates `latest_prerelease` and `generated_at` only. The window is
recomputed from the live release list on every publish — the file is a full
snapshot, never an append log — so an older release drops out once ten newer
stable releases exist. The 10-entry cap keeps the file (notes included)
bounded while covering any changelog-shaped use.

**Invariants and compatibility.**

- Every `tag` is non-empty and matches the git tag exactly. For stable
  entries it is `v` followed by an `X.Y.Z` numeric triple; the CLI requires
  that shape for `latest.tag` and treats 

--- ADR-0546 ---
# ADR-0546: Release discovery files ship as release assets; the website pulls

Status: Proposed
Claim: 56a9b60b7880fcc173599dcc87a0ec4779a11e69

## Decision
This repository never pushes content into `relate-web`. The release
pipelines attach the pipeline-owned files to the release they belong to —
`releases.json` and `install.sh` on every core release, the signed
`extensions.json` pair on every extension release — and then fire one
`repository_dispatch` at `relate-web` carrying `{kind: cli|extension, tag}`.
`relate-web`'s publish workflow pulls the files from the release assets and
assembles its Pages artifact from build outputs; it commits nothing.

Signing stays in this repository: the release signing key (ADR-0115) lives
only in this repository's secrets, so the signed extension index is
generated here and rides the release as an asset. The extension-index
publisher skips its own output when scanning a release's assets.

The poke is authenticated by a new `RELATE_WEB_DISPATCH_TOKEN` secret and is
tolerant while `relate-web` is being stood up: an unset secret or a 404 logs
a skip and the release stays green; any other non-204 fails the run. The
manual backfill workflows (`publish-releases-json.yml`,
`publish-extensions-json.yml`) re-attach the files to the relevant release
and re-fire the poke.

The `gh-pages` apparatus is removed: the `docs` and `update-website`
release jobs, `update-website.yml`, `deploy-pages.yml`, and
`push-gh-pages.sh`. The cookbook and WASM playground publishing that
`deploy-pages.yml` assembled becomes `relate-web`'s job.

--- ADR-0550 ---
# ADR-0550: Temporary preview-host fallback for release discovery

Status: Proposed
Claim: f74871b5d6ec755e0b768164aa1c698d4e5bf226

## Decision
Release discovery reads the canonical URL first; when that read does not
yield a valid `releases.json` document — a transport failure, a read
failure, or a malformed document such as the lander page — it reads the
preview host's `releases.json` once, and only then fails. The failure
message keeps the ADR-0250 §4 shape (one line, the reinstall one-liner)
and names both URLs with each one's failure detail.

Both URLs have environment overrides (the existing
`RELATE_RELEASES_JSON_URL` seam and a new
`RELATE_RELEASES_JSON_FALLBACK_URL`), so tests point both at fixtures. The
fallback is never consulted when the primary yields a valid document.

The fallback applies to discovery only. Asset downloads still go through
the ADR-0358 routes, and the `SHA256SUMS` signature check (ADR-0115) is
unchanged: a hostile or broken preview host can influence which release is
offered, never which bytes run.

--- ADR-0571 ---
# ADR-0571: The installer resolves its release via releases.json

Status: Proposed
Claim: 1bc98c705f6b583a2938f156599d882ca8524a75

## Decision
`install.sh` resolves the release tag from `releases.json` and asks the
GitHub API only for the asset ids of that exact tag.

1. **Resolution.** The metadata URL is
   `https://relatedb.ai/releases.json`, overridable through
   `RELATE_RELEASES_JSON_URL` with the same empty-means-default rule
   `upgrade` documents (ADR-0250 §1), and it is the only source consulted:
   no fallback. The request carries no `Authorization` header (the file is
   public and on a different origin, ADR-0250 §5). The tag is `latest.tag`
   and must be a `vX.Y.Z` release tag — the stable-tag invariant the
   schema fixes and the publisher selects by (ADR-0250 §2); anything else
   is a malformed document, exactly as the CLI's parser treats it.
2. **Asset ids.** One per-tag request (the releases/tags endpoint, never
   the latest-release endpoint), with the `GITHUB_TOKEN` bearer header
   while the repository is internal (ADR-0068 §6). The response's
   `tag_name` must equal the requested tag: the API must describe exactly
   the release the metadata named. The asset download route is unchanged.
3. **Failure behavior.** Every resolution failure dies before any
   download with a one-line message naming the failed source, mirroring
   ADR-0250 §4's aborts; the `GITHUB_TOKEN` hint moves to the per-tag
   fetch failure — the one request the token can help. The ADR-0457
   binding, the legacy window, and the verify-before-download ordering
   are unchanged; only the tag's provenance changes.
4. **Harness.** The offline harness pins the contract: the stub serves an
   extension release at the old endpoint in every mode, so any request of
   it fails the install loudly; a case serves the publisher's committed
   output fixture as the metadata document end to end, so a serialization
   the installer's parse cannot read fails the suite instead of the
   one-liner; and section-0 drift guards hold the URL literal and the
   env-var name to the CLI's `releases_json.rs` constants.

--- ADR-0585 ---
# ADR-0585: The installer downloads release assets over the direct route

Status: Proposed
Claim: 149adbb71aa163c5711d79edb6162140bf2671a7

## Decision
`install.sh` consults no GitHub API endpoint. Every asset — the
`SHA256SUMS` manifest, its `SHA256SUMS.sig` signature, and the platform
binary — is downloaded from
`https://github.com/<repo>/releases/download/<tag>/<asset>`, the direct
browser route `upgrade` probes (ADR-0358 §1), unauthenticated.

1. **One transport.** `releases.json` remains the only metadata source
   (ADR-0571); its tag and the asset names determine every URL. Any
   non-2xx answer dies with the request and the HTTP status — the same
   pinned status text the CLI's release channel carries. The transport
   is TLS-only: the seam's base is gated to `https://` before the first
   request of any kind — deliberately narrower than the CLI seam's
   `approved_transport` loopback plain-http carve-out, because the
   installer is the end-user pipe-to-bash surface and its own test rig
   drives the seam without real HTTP — and every download request is
   protocol-pinned across redirects, so no hop can downgrade to
   plaintext.
2. **No token.** `GITHUB_TOKEN` is not read: the direct route cannot be
   helped by a token at either repository visibility, and curl would
   forward a custom Authorization header across the route's cross-host
   redirect to the asset CDN.
3. **One seam.** The base is overridable through
   `RELATE_RELEASE_DOWNLOAD_URL` — the same seam `upgrade` documents —
   with empty meaning the canonical default and no fallback between the
   two; a harness drift guard holds it to the CLI's constant.
4. **The integrity chain is unchanged.** `releases.json` selects but is
   never trusted; SSHSIG verification (ADR-0115), the signed
   version-header binding (ADR-0457) and the checksum gate run before
   the binary is trusted, whichever route delivered the bytes.

==================== TASK T21 ====================
Task: Add a new query notification kind and decide how it is exposed through the Rust API and on the wire.

Context retrieved for this task: the decision records of the repository, as written.

--- ADR-0363 ---
# ADR-0363: Query notifications: vocabulary and transport

Status: Proposed
Claim: 43ca09bd9b545e0b54a88119f2e03eaa69b93fe6

## Decision
1. **One vocabulary, one table.** The notification kinds, their code,
   GQLSTATUS, severity, category, title and remedy live in one module in
   `cypherlite-model` beside `plan_wire`, and the table below is that
   vocabulary. `PlanWarning`'s three variants are its operator-node subset and
   keep their names, messages, node placement and wire spelling; their text
   delegates to this table, so the plan table's warning column/footer and the notification
   list cannot drift. A notification record is
   `{ kind, description, remedy, operator_id }`: `description` carries the
   instance detail (the unknown name, the index text, the procedure name) and
   the kind supplies the metadata and the remedy.

| kind | code | GQLSTATUS | severity | category | trigger | remedy |
| --- | --- | --- | --- | --- | --- | --- |
| `CartesianProduct` | `Neo.ClientNotification.Statement.CartesianProduct` | `03N90` | INFORMATION | PERFORMANCE | A multi-pattern `MATCH` whose patterns share no node variable — the existing `PlanWarning::CartesianProduct`. | Give the patterns a join anchor: reuse a node variable across them, or add a pattern that relates their endpoints; otherwise run them as separate queries. |
| `UnboundedVariableLengthPattern` | `Neo.ClientNotification.Statement.UnboundedVariableLengthPattern` | `03N91` | INFORMATION | PERFORMANCE | A variable-length relationship pattern with no upper bound (`[:R*]`) that plans as an unbounded expansion. CypherLite fires on every such pattern, not only inside `shortestPath` (Neo4j's narrower trigger) — the cost shape is the same. | Bound the expansion (`[:R*1..5]`) where arbitrary length is not required, or add a selective endpoint/label predicate and a `LIMIT`. |
| `AllNodesScan` | `CypherLite.Notification.Statement.AllNodesScan` | `03C90` | INFORMATION | PERFORMANCE | A lone label-less node pattern (`MATCH (n)`) while the store carries a property index — the existing `PlanWarning::AllNodesScan`; the description names the first index text. | Name the label the scan intends (`MATCH (n:<Label>)`); on the index's label the scan becomes an index-backed lookup. |
| `MissingIndex` | `CypherLite.Notification.Statement.MissingIndex` | `03C91` | INFORMATION | PERFORMANCE | A label pattern with an equality property predicate (`MATCH (n:Person) WHERE n.email = $e`) and no `CREATE INDEX` range index on that `(Label, property)` pair. | `CREATE INDEX cypherlite_Person__email FOR (n:Person) ON (n.email)` — the exact runnable statement, with the name derived deterministically from label and property (case preserved; `_` escaped to `_5f`, every other non-alphanumeric byte to `_` plus two hex digits, and a double `__` separator between the escaped parts — escaped parts never contain `__`, so the split is unambiguous and distinct pairs cannot collide in the global index namespace). |
| `EagerAggregation` | `CypherLite.Notification.Statement.EagerAggregation` | `03C92` | INFORMATION | PERFORMANCE | An `EagerAggregation` operator whose input child's `estimated_rows` is at least 100,000 — the stated `EAGER_INPUT_NOTIFICATION_ROWS` threshold. | Reduce the rows reaching the aggregation with a selective label/property predicate or a `LIMIT` before it; profile again to confirm the buffered input shrank. |
| `EstimationMiss` | `CypherLite.Notification.Statement.EstimationMiss` | `03C93` | INFORMATION | PERFORMANCE | `PROFILE` only: the existing 10x overshoot policy fires (estimate at least 10x the actual rows, actual > 0) — the same 

--- ADR-0535 ---
# ADR-0535: The HINT notification category and the planner-hint kinds

Status: Proposed

Claim: be6e913fdc3a9fe75ba072f2f8f136692eedfb63

## Decision
The notification vocabulary (ADR-0363) adopts the `HINT` category — wire
spelling `HINT`, ranked after `SCHEMA` in the statement-scoped merge
order — with two Neo4j-analog kinds:

| kind | code | GQLSTATUS | severity | category | trigger | remedy |
| --- | --- | --- | --- | --- | --- | --- |
| `HintedIndexNotFound` | `Neo.ClientNotification.Schema.HintedIndexNotFound` | `01N31` | WARNING | HINT | A `USING INDEX [SEEK]` hint no catalog node index can serve: no non-vector node index on the hinted label covers every hinted property (range, text, point and fulltext indexes all serve; vector never). | Create the index, or drop the hint. |
| `JoinHintUnfulfillable` | `Neo.ClientNotification.Statement.JoinHintUnfulfillableWarning` | `01N30` | WARNING | HINT | A `USING JOIN ON` hint — the planner is not cost-based and never plans a hint-directed join, so every one is unfulfillable. | Try a different join key or restructure the query. |

Both kinds are occurrence-scoped (one row per hint, never collapsed) and
statement-scoped (no operator association). The kinds fire where a plan
tree is built, like every ADR-0363 derivation; the hints reach the
derivation through the IR's `MATCH` clause, which carries them from the
parser. The GQL-status description text reproduces the live server's
word-for-word.

--- ADR-0236 ---
# ADR-0236: Query API v2 value encoding follows the Neo4j contract

Status: Accepted

## Decision
`surfaces/cypherlite-http` encodes `data.values` per the Neo4j Query API v2
contract in both forms (plain for `application/json`, typed for the
negotiated `application/vnd.neo4j.query` media type, ADR-0232's negotiation
per the Accept header). Geometry — a CypherLite extension the Neo4j codecs
do not know — is `{"$type": "Unsupported", "_value": …}` in the typed form
and keeps the ADR-0223 shape in the plain form.

ADR-0223's kind-tagged codec is unchanged and stays the encoding for
snapshots, the CLI, and the MCP tools.

--- ADR-0181 ---
# 0181. Typed Query API JSON wire format for pull

- **Status**: Proposed
- **Date**: 2026-10-07
- **Deciders**: CypherLite maintainers (Linear LABS-186)

## Decision
1. **The pull path requests typed JSON with one multi-valued `Accept`
   header, and nothing else.**

   ```text
   application/vnd.neo4j.query.v1.2;q=1.0, application/vnd.neo4j.query.v1.1;q=0.9, application/vnd.neo4j.query.v1.0;q=0.8, application/vnd.neo4j.query;q=0.7
   ```

   `application/json` is not in the list: a source without typed JSON
   answers 406 and the pull fails with `LoadError::Http`, never with a
   silent untyped fallback. The server picks the newest media type it
   supports (observed `.v1.2` on 2026.09, `.v1.0` on 5.26). Request
   bodies stay `Content-Type: application/json`; the statement envelope
   (`statement` / `parameters`) does not change.

2. **Only `load_streaming` requests typed JSON.** `run_query` and
   `run_query_streaming` keep `Accept: application/json` and their
   current signatures: their callers (the graph-examples reference
   client's row comparison, the docker/admin probes) consume plain
   `data.values` JSON. Internally the shared `post_query` prelude takes
   the `Accept` value as an argument; the pull path gets its own
   streaming entry point (`http::run_query_streaming_typed`), which
   `load_streaming` alone calls. `subgraph_from_v2` and the streaming
   extractor decode typed bodies only (item 7).

3. **The typed wire shape is `{"$type": <tag>, "_value": <payload>}` and
   the tag table is fixed.** Property values, cells, and nested values
   all use the same envelope. The engine value each captured tag decodes
   to:

   | `$type` | `_value` payload | Engine value |
   | --- | --- | --- |
   | `Boolean` | JSON `true`/`false` | `Value::Bool` |
   | `Integer` | decimal JSON string (`"42"`) | `Value::Int` (see item 4) |
   | `Float` | JSON string (`"3.14159"`, `"3.2E9"`) | `Value::Float` (see item 4) |
   | `String` | JSON string | `Value::String` |
   | `Date` | ISO date string (`"2015-03-26"`) | `Value::Temporal(parse_iso("date", s))` |
   | `Time` | offset/zoned time string (`"12:50:35.556+01:00"`, `"01:02:03Z"`) | `parse_iso("time", s)` |
   | `LocalTime` | time string (`"12:50:35.556"`) | `parse_iso("localtime", s)` |
   | `LocalDateTime` | `"2015-07-04T19:32:24"` | `parse_iso("localdatetime", s)` |
   | `OffsetDateTime` | `"2015-11-21T21:40:32.142-01:00"` | `parse_iso("datetime", s)`; the engine has one `datetime` kind, so an offset-only datetime is a `DateTime` with `zone: None` |
   | `ZonedDateTime` | `"2015-11-21T21:40:32.142Z[Antarctica/Troll]"`, `"2020-01-01T10:00:00+01:00[Europe/Stockholm]"` | `parse_iso("datetime", s)`; the `[...]` name is kept as the zone |
   | `Duration` | ISO duration string (`"P14DT16H12M"`) | `parse_iso("duration", s)` |
   | `Point` | EWKT string (grammar in item 5) | `Value::Point(PointValue { srid, x, y, z })` |
   | `UUID` | canonical hyphenated string | `Value::Uuid(uuid_parse(s))`; `None` is malformed |
   | `Vector` | `{"coordinatesType": …, "coordinates": [ … ]}` | `Value::Vector { coord, values }` (item 6) |
   | `List` | JSON array of tagged values | `Value::List` — decode each element recursively |
   | `Node` | `{"_element_id", "_labels", "_properties"}` | element position: `SubgraphNode` (labels plus a `BTreeMap<String, Value>` property map) |
   | `Relationship` | `{"_element_id", "_start_node_element_id", "_end_node_element_id", "_type", "_properties"}` | element position: `SubgraphRel` (same property map) |
   | `Path` | flat JSON array of `Node`/`Relationship` typed objects | element position only (not a captured property tag): walked

--- ADR-0385 ---
# ADR-0385: gzip response compression on the HTTP Query API

Status: Proposed

Claim: 6a2a00a233e4d12ed7a7136da09d36eb8278399a

## Decision
One pure negotiation function on the Query API reply seam, plus a fixed
threshold, scope and encoder. Each item below reproduces the pinned policy
verbatim; the Decision adds no degree of freedom.

1. **Inputs negotiation.** Negotiate from the raw Accept-Encoding request header (RFC 9110 section 12.5.3 list syntax) with one pure function: split on commas, trim OWS, split each element on ';', compare the coding token case-insensitively, and parse an optional q parameter (0, 1, 0.0-0.999 or 1.000; an unparsable or out-of-range q makes that element q=0). Exactly two representations exist: gzip (the legacy x-gzip alias is accepted too) and identity. gzip's effective q is the explicit gzip/x-gzip element when present, else the '*' element when present, else unset. Select gzip only when effective q > 0 AND the serialized uncompressed body is >= threshold_bytes AND the gzip output is smaller than the input; otherwise send identity. A missing, empty or whitespace-only header selects identity. Other codings (br, zstd, deflate, compress) are parsed but never selected. Encoding negotiation can never fail a request: identity is always available, so there is no 406 from Accept-Encoding (the separate Accept media-type negotiation and its 406 are untouched). On gzip: add 'content-encoding: gzip', send the compressed bytes with content-length set to the compressed length, keep the one-shot body (no Transfer-Encoding; Connection: close unchanged), and encode with flate2::Compression::fast (level 1) because the encode runs on the connection thread and latency beats the last few percent of ratio. **Scoped by ADR-0386:** the one-shot body clause above (no `Transfer-Encoding`) and the "gzip output is smaller than the input" selection check apply only below `stream_threshold_bytes = 65536` (ADR-0386); at or above 65536 uncompressed serialized bytes the response is chunked and gzip wraps the chunked writer, selected by effective `q` and body size alone.
2. **Vary.** Add 'vary: Accept-Encoding' to every response written by the Query API reply seam, identity responses included, so a shared cache never serves a gzip variant to a client that did not advertise it and keeps the gzip variant keyed. `write_reply` appends it to its local header list beside the CORS echo and the WWW-Authenticate challenge, so http::write_response stays unchanged. Responses outside the seam - the GET / discovery document, the body-less 204 preflight, and the MCP transport - are never gzip and carry no Vary.
3. **q=0.** An explicit 'gzip;q=0' (or 'x-gzip;q=0') disables gzip for that request even when '*' has q>0: the more specific entry wins. q=0 on any other coding only excludes that coding, which we never send anyway. 'identity;q=0' and '*;q=0' do not produce a 406 and do not force gzip: when gzip is not selected the response is identity, because encoding is best-effort and must never fail a query that would otherwise succeed. Any effective q>0 selects gzip; no comparison against identity's q is needed because there is exactly one non-identity coding.
4. **Wildcard.** '*' with q>0 makes gzip acceptable when no explicit gzip/x-gzip element exists ('Accept-Encoding: *' selects gzip when the body clears the threshold and shrinks). An explicit gzip element overrides '*' in both directions: 'gzip;q=0, *;q=1' is identity; 'gzip;q=1, *;q=0' is gzip. '*;q=0' with no explicit gzip entry leaves gzip's effective q at 0, so identity. Empty list elements are ignored, not treated as a wildcard.
5. *

==================== TASK T12 ====================
Task: Make db.schema.visualization() return the indexes and constraints of the database.

Context retrieved for this task: the decision records of the repository, as written.

--- ADR-0166 ---
# 0166. `db.schema.visualization()`: populate `indexes`/`constraints` from the catalog

- **Status**: Accepted
- **Date**: 2026-10-05
- **Deciders**: CypherLite maintainers (Linear LABS-172)

## Decision
`db.schema.visualization()` populates each virtual label node's `indexes`
and `constraints` from the catalog **at call time**, on top of the
procedure's existing scan of stored entities (same scan-time cost model as
the rest of the procedure, ADR-0153). Everything is derived from the
overlay-aware `named_indexes()`/`named_constraints()` accessors, so the
rendering tracks in-flight DDL exactly as `SHOW INDEXES`/`SHOW CONSTRAINTS`
do.

1. **`indexes`: sorted list of decoded property-name strings, excluding
   constraint-backing indexes.** One string per catalog index whose `label`
   matches the virtual node's label, **except** an index whose name equals
   the name of a `unique`/`key` constraint in the catalog — that is the
   backing index `catalog_create_constraint` installs under the
   constraint's own name, and Neo4j lists such indexes only as `ownedIndex`
   on the constraint string (a field cypherlite omits, item 3). Evidence:
   the Docker probe's `:Client` label (uniqueness constraint on `id` with
   backing index `ownedIndex=2`, plus explicit indexes on `(name)` and
   `(name,id)`) rendered `indexes: ["name", "name,id"]` — the backing
   index's `"id"` was absent. This exclusion is specific to
   `db.schema.visualization()`; `SHOW INDEXES` intentionally keeps listing
   backing indexes (Neo4j parity there). The string is the index's property
   after decoding the legacy `property#kind` encoding
   (`split_legacy_property_encoding`). The list is sorted ascending. Because
   the catalog model is single-property (`IndexDef.property` is one
   `String`), no composite `"name,id"` rendering arises; if composite
   indexes are ever added to the catalog, each index's string becomes its
   comma-joined property list, matching Neo4j.
2. **`constraints`: sorted list of rendered `Constraint(...)` strings.**
   One string per catalog constraint with `relationship == false` whose
   `label` matches, sorted by constraint name, rendered as:

   ```
   Constraint( name='<name>', type='<TYPE>', schema=(:<Label> {<props>}) )
   ```

   `<props>` is the constraint's comma-joined property list; a constraint
   with no properties renders `schema=(:<Label>)`. `<TYPE>` is Neo4j's
   **space** style, mapped from the catalog kind:

   | Catalog kind | Rendered type |
   | --- | --- |
   | `unique` | `NODE PROPERTY UNIQUENESS` |
   | `key` | `NODE KEY` |
   | `exists` | `NODE PROPERTY EXISTENCE` |
   | `propertyType` | `NODE PROPERTY TYPE` |
   | `labelExistence` / `nodeLabelExistence` | `NODE LABEL EXISTENCE` |
3. **No `id`/`ownedIndex` fields.** CypherLite's catalog is name-keyed and
   has no schema-rule or owned-index ids; synthesizing fake ones would be
   misleading, so the rendered string omits both fields (and the commas
   that would separate them).
4. **Relationship constraints appear on no virtual node.** Constraints
   with `relationship == true` are skipped entirely — Neo4j parity (the
   probe's `TRANSFER_TO` existence constraint appeared nowhere).
5. **Virtual relationships keep carrying no properties.** ADR-0153 is
   unchanged on that point; Neo4j's `{name: "<TYPE>"}` on virtual
   relationships is a separate concern, out of scope here.

--- ADR-0153 ---
# 0153. `db.schema.visualization()` semantics

- **Status**: Accepted
- **Date**: 2026-09-30
- **Deciders**: CypherLite maintainers (Linear LABS-150)

## Decision
`db.schema.visualization()` is implemented with the Neo4j-compatible
signature and return columns, no CypherLite-specific additions:

```
db.schema.visualization() ::
  (nodes LIST<NODE>,
   relationships LIST<RELATIONSHIP>)
```

### Semantics

- **Inferred by scanning stored entities** (ADR-0112's rule). The schema
  graph is derived from the entities actually stored; a declared graph type
  element that no stored entity exercises contributes nothing.
- **One virtual node per stored label.** The set of labels is the union of
  labels over all stored nodes; each contributes exactly one virtual node,
  sorted alphabetically.
- **One virtual relationship per distinct `(startLabel, relType, endLabel)`
  triple.** A stored relationship contributes one triple per label
  combination of its endpoints: a multi-label endpoint is expanded over
  every label it carries (Neo4j's shape). Triples are sorted by
  `startLabel`, `relType`, `endLabel`. Virtual relationships carry no
  properties.
- **Virtual entities carry negative ids**, allocated from `-1` down
  (nodes first, then relationships). Real, store-backed entities start at
  `0` and count up, so a negative id unambiguously marks "no real backing";
  writes against these entities follow the CIP-257 virtual-entity rules
  (`DELETE` / property `SET`/`REMOVE` are no-ops, label `SET`/`REMOVE` and
  `CREATE` off of one fail).
- **Virtual nodes are registered in the CIP-257 virtual-node side table**
  (`graph_type_visualize::register_virtual_node`), so
  `startNode()`/`endNode()` on a virtual relationship resolve its endpoints
  without a store lookup.
- **Node property shape is Neo4j's `{name, indexes, constraints}`.**
  `name` is the label itself; `indexes` and `constraints` are empty lists,
  documented placeholders (constraint rendering has its own catalog
  surface; index introspection is not part of this procedure).
- **No stored labels yields zero rows.** An empty graph — including a
  graph containing only unlabeled entities — returns no rows, because there
  is no label set to visualize.

--- ADR-0187 ---
# 0187. `db.schema.visualization()`: virtual relationships carry a `name` property

- **Status**: Accepted
- **Date**: 2026-10-08
- **Deciders**: CypherLite maintainers (Linear [LABS-185](https://linear.app/neo4j/issue/LABS-185))

## Decision
Every virtual relationship returned by `db.schema.visualization()` carries
a property map with **exactly one entry**:

- `name`: a `STRING` equal to the relationship's type — `type(r)` — for
  every relationship `r` in the result's `relationships` list.

Reading `r.name` off the returned value yields the type, so `type(r)` and
`r.name` agree on the same virtual relationship.

Everything else in ADR-0153, as amended by ADR-0166, is unchanged:

- **Virtual node shape** stays Neo4j's `{name, indexes, constraints}`, with
  `indexes`/`constraints` populated from the catalog at call time
  (ADR-0166).
- **Negative virtual ids** stay allocated from `-1` down (nodes first,
  then relationships), and virtual nodes stay registered in the CIP-257
  virtual-node side table so `startNode()`/`endNode()` resolve endpoints.
- **Triple expansion** stays: one virtual relationship per distinct
  `(startLabel, relType, endLabel)` triple, with multi-label endpoints
  expanded over every label combination.
- **Sort order** stays: nodes sorted alphabetically by label;
  relationships sorted by `startLabel`, `relType`, `endLabel`.
- **Zero-rows empty behavior** stays: a graph with no stored labels
  returns no rows.

The CIP-257 `SHOW CURRENT GRAPH TYPE AS GRAPH` producer is untouched: its
virtual relationships keep their own CIP-257 property shapes
(`{relationshipType, properties, constraints}` and friends), which are
pinned by that surface's own scenarios.

--- ADR-0201 ---
# 0201. Pull carries the source's constraints and indexes

- **Status**: Proposed
- **Date**: 2026-10-11
- **Deciders**: CypherLite maintainers
- **Related**: ADR-0080 (original sync), ADR-0156 / ADR-0158 (streaming
  pull), ADR-0291 (schema DDL is runnable)

## Decision
After the data stream completes, `load_streaming` fetches the source
schema over the same Query API v2 connection
(`SHOW CONSTRAINTS YIELD name, type, entityType, labelsOrTypes,
properties, propertyType` and `SHOW INDEXES YIELD name, type, entityType,
labelsOrTypes, properties, owningConstraint, state`) and replays each row
as a standalone `CREATE … IF NOT EXISTS` statement against the target,
one statement per row inside the loader's existing `with_txn` transaction
policy.

Mapping: `NODE_PROPERTY_UNIQUENESS` → `IS UNIQUE`,
`NODE_PROPERTY_EXISTENCE` → `IS NOT NULL`, `NODE_KEY` → `IS NODE KEY`,
`NODE_PROPERTY_TYPE` → `IS TYPED <propertyType>`, and the
`RELATIONSHIP_*` equivalents on a `FOR ()-[r:TYPE]-()` target. Indexes:
`RANGE` → `CREATE INDEX`, `TEXT` → `CREATE TEXT INDEX`, `POINT` →
`CREATE POINT INDEX`, on node or relationship targets. Filtered out
without counting: indexes with a non-null `owningConstraint` (they back a
constraint and arrive with its replay), non-`ONLINE` indexes, and
`LOOKUP` indexes (engine-internal). Everything else — unknown constraint
kinds (e.g. node-label existence), `FULLTEXT`/`VECTOR` indexes, rows with
no label or no properties — is skipped with a stderr note and counted.

Schema replay never fails a pull: the data is already loaded, so a source
that cannot answer the SHOW queries (older server, missing privilege)
yields a stderr warning and zero counts, and a single rejected DDL is one
skip. `LoadStats` gains a `schema: SchemaStats` field
(`constraints_applied`, `constraints_skipped`, `indexes_applied`,
`indexes_skipped`, all `Default`) and the pull output line becomes
`pulled N new / M reused nodes, P new / Q reused rels (+ C constraints,
I indexes; S schema skipped) to PATH`.

Engine gaps found while probing: none among the mapped kinds — node and
relationship uniqueness/existence/key/property-type constraints and
RANGE/TEXT/POINT indexes all run and enforce. The recorded gaps are the
unmapped `FULLTEXT`/`VECTOR` index kinds (configuration not recoverable
from `SHOW INDEXES`) and any future constraint kind outside the mapping
table.

--- ADR-0112 ---
# 0112. Inferred schema via `db.schema.*` procedures

- **Status**: Accepted
- **Date**: 2026-09-26
- **Deciders**: CypherLite maintainers

## Decision
### Procedures and exact return columns

Implement the two procedures with Neo4j-compatible signatures and return
columns. No count or other CypherLite-specific columns are added.

```
db.schema.nodeTypeProperties() ::
  (nodeType STRING,
   nodeLabels LIST<STRING>,
   propertyName STRING,
   propertyTypes LIST<STRING>,
   mandatory BOOLEAN)

db.schema.relTypeProperties() ::
  (relType STRING,
   propertyName STRING,
   propertyTypes LIST<STRING>,
   mandatory BOOLEAN)
```

Both currently-registered stubs become executable, and their `returns` list is
populated to match. Their READ mode and names are unchanged.

### Semantics

- **Inferred by scanning stored entities.** The property schema is derived by
  scanning the entities actually stored in the database. It is **not** sourced
  from the declared graph type spec; a declared type that no stored entity
  exercises contributes no rows.
- **Type names are `valueType()` names.** Each entry in `propertyTypes` is a
  Cypher type name — the same names the engine's `valueType()` function returns
  (`cypherlite/cypherlite-executor/src/eval/typename.rs`). This follows Neo4j's
  Cypher 25 behaviour; Neo4j's Cypher 5 returned Java type names, which we do
  not adopt.
- **`mandatory`** is `true` when the property key is present on every entity in
  the category, and `false` otherwise.
- **`nodeType`** is the node's full sorted label set rendered as `:A:B` (all
  labels, colon-prefixed, sorted). **`relType`** is the relationship's single
  type rendered as `[:TYPE]`.
- **The row rule for categories with no properties.** A node or relationship
  category that has no properties produces exactly one row for that category
  with `propertyName: null`, `propertyTypes: []` (the empty list), and
  `mandatory: false`. This follows Neo4j's documented convention for these
  procedures: a category is still listed even when it has no properties, rather
  than being omitted. (The convention is chosen to match Neo4j; the exact
  property-less example is not reproduced in the operations manual, so this is
  stated as CypherLite's pinned rule rather than a quoted source.)

### Scope

Phase 1 is exactly the two procedures above. Per-label counts and any other
introspection aggregates remain reachable through plain Cypher (`count(...)`,
`labels(n)`, `type(r)`). Reintroducing a `.schema` shell dot-command, or any
other CLI sugar over these procedures, is deferred to a separate phase-2 ADR
that must reference ADR-0058.

==================== TASK T09 ====================
Task: Change how the ontology is persisted and how the system_ontologies graph is derived from it.

Context retrieved for this task: the decision records of the repository, as written.

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

--- ADR-0229 ---
# 0229. Remove the `system_ontologies` Cypher surface

- **Status**: Accepted
- **Date**: 2026-10-13
- **Deciders**: CypherLite maintainers (Linear LABS-132)

## Decision
1. **Listed, not queryable.** `system_ontologies` stays a fixed, listed
   namespace. `SHOW DATABASES` keeps its row with ADR-0116 §6's values
   verbatim (`type` standard, `access` read-only, `currentStatus` and
   `requestedStatus` `online`, `default` and `home` false, empty `aliases`
   and `constituents`, the stored `defaultLanguage`), and the name stays
   accepted everywhere a namespace name is parsed: session-namespace
   selection over the embedding APIs and Bolt (ADR-0117), a static `USE`
   target (ADR-0116 §3), and the CLI `--namespace` flag (ADR-0118). But
   every statement routed to it fails — reads included.

   What still runs while routed to `system_ontologies` is exactly
   ADR-0116 §2's database-administration commands — `SHOW DATABASE[S]
   [name]`, `SHOW DEFAULT DATABASE`, `SHOW HOME DATABASE`, `ALTER
   DATABASE … SET DEFAULT LANGUAGE` — which act on the store catalog,
   never on a namespace's graph, and keep §2's any-namespace rule. Every
   other statement routed there — data clauses, DDL, procedure and
   function calls (`db.ontology.*` and `db.info()` included) — fails with
   the error in (2), whether it reads or writes.

   The `db.ontology.*` procedures are unaffected: they act on the stored
   document and on `neo4j`'s graph type, never on the namespace's graph.
   Run against `neo4j` they behave exactly as ADR-0227 §1 pins; routed to
   `system_ontologies` they now fail in (2)'s gate, before ADR-0227 §1's
   `Ontologies can only be stored for the user database 'neo4j'.` (that
   text now fires only on `system`).

2. **The error.** Every statement routed to `system_ontologies` — read or
   write, `USE`-routed or session-routed, wrapped in `EXPLAIN` or
   `PROFILE` included — fails at the plan-based semantic gate (the layer
   of ADR-0116 §4's gates, above the EXPLAIN early-return) with:

   - GQLSTATUS **42N17**, the family of `unsupported_system_clauses`
     (`Neo.ClientError.Statement.SemanticError`; the class-level
     `SemanticError` kind token, no new `ErrorKind` variant), raised by a
     new formatter in `cypherlite/cypherlite-core/src/ce_messages.rs`;
   - message text, exactly:
     `This database is not queryable. Use the db.ontology.* procedures on the user database 'neo4j' instead.`
     so the engine renders
     `semantic error: SemanticError: This database is not queryable. Use the db.ontology.* procedures on the user database 'neo4j' instead.`

   42N17 fits where 42N18 would not: the namespace rejects every clause,
   not just writes, and 42N17 is already the namespace-restriction code
   ("'MATCH' is not allowed on the system database"). The text follows the
   family's phrasing (`read_only_write`'s "this database",
   `ontology_neo4j_only`'s "the user database 'neo4j'",
   `element_id_no_namespace`'s imperative pointer) and is CypherLite's
   own: live CE has no counterpart error, because live CE allows reads.
   The ADR-0116 §4 42N18 arm for `system_ontologies` is removed with it;
   `WriteOnReadOnlyAccessDatabase` stays the recorded CE text for
   read-only databases (ADR-0116 §9).

3. **No derived graph.** ADR-0120 §2 is superseded: no
   `system_ontologies` graph is built at open or after a committed set or
   drop. The document stays the sole stored source of truth (ADR-0120 §1,
   as amended by ADR-0227: the validated ontology document, JSON or YAML,
   kept verbatim). The store formats do not change: ADR-0120 §3's redo ops
   and 16 MiB envelope, §4's `MDBWAL02` segment magic, §

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

--- ADR-0121 ---
# 0121. `db.ontology.*` procedures manage the single ontology

- **Status**: Accepted
- **Date**: 2026-09-27
- **Deciders**: CypherLite maintainers (Linear LABS-102)

## Decision
1. **Signatures follow Neo4j.**
   - `db.ontology.set(database :: STRING, ontology :: STRING)` validates the
     document against a supported Ontology Spec version and replaces the
     stored ontology. A newer spec version fails, naming the highest
     supported version.
   - `db.ontology.get(database :: STRING) :: (ontology :: STRING)` returns the
     stored document unchanged, or `null` when none is set.
   - `db.ontology.drop(database :: STRING)` removes it. Dropping when none is
     set succeeds.
   - `db.ontology.apply(database :: STRING)` converts the stored ontology to a
     graph type and applies it to `neo4j` with `ALTER CURRENT GRAPH TYPE SET`
     semantics, replacing the current graph type. It fails when no ontology is
     set, or when the data violates the resulting graph type.

   Where Neo4j's final signatures differ, for example in the name of `get`'s
   output column, CypherLite follows Neo4j.
2. **One database.** `database` must name `neo4j`, matched case-insensitively.
   An unknown name fails with `DatabaseNotFound` and `Database does not exist.
   Database name: '<name>'.`. `system` and `system_ontologies` fail with
   `Ontologies can only be stored for the user database 'neo4j'.`
3. **Transactions.**
   - `set` and `drop` run only in implicit (auto-commit) transactions. Inside
     an explicit transaction they fail with `'db.ontology.set' can only be
     executed in an implicit transaction, but tried to execute in an explicit
     transaction.` (or the same text naming `drop`). The wording follows
     Neo4j's error for `CALL { … } IN TRANSACTIONS`.
   - A statement that calls `set` or `drop` may not write anything else.
     Otherwise it fails with Neo4j's `Writing to more than one database per
     transaction is not allowed.` (42N03).
   - `get` reads the calling transaction's captured snapshot (ADR-0116 §5).
   - `apply` writes only `neo4j` and may run in explicit transactions.
4. **No privileges.** Any caller may run every procedure. The proposal's
   `EXECUTE BOOSTED` grants and property-based access rules do not apply.
5. **The mapping follows Neo4j.** The document-to-graph mapping and the
   ontology graph type implement Neo4j's published mapping for Ontology Spec
   v1. That includes the `ontology` property naming the database on every node
   and relationship, so queries against `system_ontologies` work the same in
   both products. CypherLite ships no mapping of its own, and implementing
   these procedures waits until Neo4j publishes it.
6. **Always built.** The procedures are part of the Cypher surface in every
   build: all CLI bundles, the Rust crate, the language bindings, Bolt and
   WASM. They are not a Cargo feature. The mapping lives in a new engine crate,
   `cypherlite/cypherlite-ontology`, that `cypherlite` always depends on. That
   follows ADR-0103's R1, and the crate adds no heavy dependency (R6).
7. **Listed like other procedures.** `SHOW PROCEDURES` lists them with their
   signatures and modes.

--- ADR-0378 ---
# ADR-0378: Gate the `db.ontology.*` procedures behind `CYPHERLITE_PREVIEW`

Status: Proposed

Claim: 74fe11e0a20154c0acbd649101a091ea1698a860

## Decision
The `db.ontology.*` family is the first, narrow exception to ADR-0371's
syntax-only scope policy, and the exception is recorded where the policy
lives.

- **Registry row.** `PreviewFeature::Ontology` is appended to
  `PREVIEW_FEATURE_TABLE` in `cypherlite/cypherlite-core/src/preview.rs`
  with the kebab-case name `ontology`; its doc comment names this ADR and
  the removal condition below. No other spelling of the name exists.
- **All four procedures gate**, not only the writers:
  `db.ontology.set`, `db.ontology.get`, `db.ontology.drop` and
  `db.ontology.apply`.
- **One owner for the resolved set.** The set lives on the store-level
  executor services (`StoreServices`, ADR-0116 §10), installed at open and
  carried by a follow reload. `Shared.preview` is gone; the statement
  admission that gates CIP-278 `COMBINE` (ADR-0379) captures
  `Graph::preview()` under a read guard before parsing, and the `CALL`
  gate and the `SHOW PROCEDURES` catalog read the same bundle. ADR-0379's
  "first production reader of `Shared.preview`" sentence is superseded
  here; its Later references note points at this decision.
- **The disabled error** is ADR-0371's authored text, unchanged:

  ```
  semantic error: SemanticError: preview feature 'ontology' is not enabled: set CYPHERLITE_PREVIEW=ontology
  ```
- **Placement.** The gate is a compile-time check in
  `Connection::plan_gate_classify` (`cypherlite/cypherlite/src/gate.rs`),
  after planning and **before** compile-time `CALL` validation. The
  preview error therefore precedes arity and `YIELD` errors and the
  ADR-0116 §4 / ADR-0229 namespace gates: with the gate off, a call that
  is also malformed or routed to `system_ontologies` reports the preview
  error; with the gate on, every later gate runs exactly as today (the
  42N17 text included). Because it sits above the EXPLAIN early-return
  and is reached by every statement path, it covers nested calls
  (`CALL { … }` bodies, expression subqueries) and `EXPLAIN`/`PROFILE`
  wrappers in implicit and explicit transactions alike. The plan walk is
  the existing full-descent one, so no new pass is added.
- **Discovery agrees with callability.** While disabled, `SHOW
  PROCEDURES` omits the four rows in every composed form — plain,
  `YIELD`/`WHERE`, `UNION`, and `EXISTS`/`COUNT` subqueries; while
  enabled it lists them unchanged. The catalog and the call gate read the
  same store-level set, so no composition can list a row that cannot be
  called.
- **One set per store.** The preview set lives on the store-level
  executor services — the bundle that already shares the LOAD CSV policy
  across all three namespace graphs (ADR-0116 §10) — installed at open
  and re-installed on follow reload, so every namespace and every
  session/transaction of the store sees the same opt-in.
- **Persistence is unaffected.** The gate governs the Cypher procedure
  surface, not stored state: open, WAL replay (including `MDBWAL02`
  segments), checkpoint and follow reload keep working with the gate
  off, and a store that holds an ontology opens fine.
- **The hidden Rust facades are not gated.** `Database::ontology_document`,
  `Database::commit_ontology_set` and `Database::commit_ontology_drop`
  keep working without the opt-in; they exist for the engine's own
  persistence tests and for hosts that manage the document directly, and
  they are `#[doc(hidden)]`, not the public procedure contract.
- **42N17 is unchanged.** The ADR-0229 §2 text (`This database is not
  que

==================== TASK T20 ====================
Task: Return a query plan summary with Neo4j-shaped plan arguments on the drained result.

Context retrieved for this task: the decision records of the repository, as written.

--- ADR-0357 ---
# ADR-0357: Plan summary on the drained result, with Neo4j-shaped plan args

Claim: d6fa67d25bc682d31fd0b198f0888472ea01f4f0
Status: Accepted

## Decision
1. **Placement**: the Bolt `plan`/`profile` pair rides the SUCCESS that
   **ends** the result — the PULL or DISCARD that consumes its last row,
   the same SUCCESS ADR-0309 gives `type`, `t_last`, `db`, `stats` and
   `bookmark` (and the depth-truncation marker of ADR-0353) — never the
   RUN SUCCESS, which stays ADR-0309's `{fields, columnTypes, t_first}`
   plus the transaction `qid`. The ending SUCCESS repeats `t_first`
   (Neo4j carries it on both), and a DISCARD that ends the result carries
   the plan pair too.
2. **Neo4j-shaped plan args**: `PlanNode::to_neo4j_value(&self, statement)
   -> Value` — the engine hosts the one decoration, the lowest shared
   module for its three sibling surfaces. Called on a result's plan
   **root** (the callers hold it as `result.plan: Option<Box<PlanNode>>`
   and destructure their own `Option` once, which they need anyway for the
   `is_profiled` key pick): the decoration is root-only by intent — the
   representation renders the whole statement's plan and the
   planner/runtime identity is a root fact — never a child node. It adds
   `string-representation` (the engine's one rendering, headed by the
   `Cypher`/`Planner`/`Runtime`/`Runtime version` lines), `version` (`5` —
   the Cypher language version, ADR-0046's openCypher 5 front-end),
   `planner`/`planner-impl`/`planner-version` and
   `runtime`/`runtime-impl`/`runtime-version` (all `cypherlite` — the honest
   names; never Neo4j's `COST`/`SLOTTED`, which would claim a planner and
   runtime this engine does not run), and `Memory` (the root's
   row-materialization bytes, mirrored under Neo4j's arg name).
   `EstimatedRows` mirrors as a float. The decorated args are built from
   the same node/args assembly `to_value` uses, never a re-parse of the
   serialized form, and the typed table/speedscope renderers keep walking
   the undecorated `to_value` tree — the engine-form wire accessor stays
   strict (an integer or absent, anything else fails loudly, ADR-0345),
   so the float mirror is read only by Neo4j-form consumers, never by the
   plan-table layout.
3. **The engine's own wire form stays unchanged**: `Id`, `Details`,
   `EstimatedRows` (integer), `Rows`, `TimeNs`, `DbHits`, `MemoryBytes`.
   The mirroring lives in the separate `to_neo4j_value` entry, never in
   `to_value`, and every surface calls it before converting the value to
   its own wire type — so Bolt, the HTTP Query API and the CLI's machine
   modes carry the same plan metadata without `to_value` growing
   Neo4j-specific fields.
4. The driver smoke (`python_driver_smoke.py`) pins the placement and the
   decorated args through the official driver.
5. **Statement retention is accounted**: an open result keeps the RUN's
   statement text for the ending summary's plan pair, and that text counts
   against `--max-result-bytes` (ADR-0110) beside the rows' logical bytes —
   reserved in both the buffered and the execution-failed arm — so a
   transaction full of huge statements cannot park unbounded text outside
   the cap.

--- ADR-0162 ---
# 0162. Query type on QueryResult and the Bolt RUN summary

- **Status**: Accepted
- **Date**: 2026-10-05
- **Deciders**: CypherLite maintainers

## Decision
1. **`QueryResult` gains a public `query_type` field of a new public enum
   `QueryType`**, set for every statement — plain runs, EXPLAIN, and
   PROFILE alike — at result construction, exactly like `namespace`
   (ADR-0117 §7). The enum is re-exported by the `cypherlite` facade like
   `Namespace`. The value set is pinned to Neo4j's (LABS-175):
   `Read` / `Write` / `ReadWrite` / `Schema`, with wire codes `"r"`,
   `"w"`, `"rw"`, `"s"`.
2. **Classification is plan-based and total.** It is derived from the
   logical plan above the EXPLAIN/dispatch split in
   `Connection::run_query`, reusing `clause_kind::is_write_clause` and
   the `call_is_write` procedure hook, extended to tell schema DDL
   (index/constraint create/drop) apart from data writes: no write or
   schema clause → `r`; data writes without reads → `w`; reads and data
   writes → `rw`; schema DDL → `s`. Every planned statement gets exactly
   one value. EXPLAIN and PROFILE report the **wrapped statement's**
   type, so `EXPLAIN` answers "may this run on a read-only target?"
   without executing anything.
3. **The Bolt RUN SUCCESS summary gains a `type` key** carrying the same
   `"r"` / `"w"` / `"rw"` / `"s"` code — the key Neo4j drivers read for
   routing. Bolt stays a transport (ADR-0057), not Neo4j feature parity;
   this is one cheap summary key beside the ADR-0117 §7 `db` echo, not a
   `queryPlan` tree.
4. **EXPLAIN's `plan` column shape is unchanged.** The query type is
   result metadata, never a result row, so the TCK/cip-eval Gherkin
   assertions that trim and match plan lines are untouched.

--- ADR-0373 ---
# ADR-0373: Export the plain-JSON Query API plan field

Status: Accepted

Claim: 2928220f99c4c103845827d87a9df560f0e271bb

## Decision
Publish `cypherlite_http::query_plan_field(tree) -> (&'static str, Value)`.

It calls `plan_field(tree, false)` and returns that function's key and
plain-JSON node. `EXPLAIN` yields `queryPlan`. `PROFILE` yields
`profiledQueryPlan`. A tree that is neither is not produced by the
engine; the key still follows `PlanNode::is_profiled`.

The typed `{"$type","_value"}` encoding stays inside the HTTP server,
which keeps calling `plan_field` with the flag its Accept negotiation
chose. Embedders that speak plain JSON do not grow a second entry point
for a negotiation they do not perform.

--- ADR-0345 ---
# ADR-0345: Plan surface alignment — CLI text rendering, Bolt and HTTP passthrough

Claim: d3eea77402bb5046b38a44399d25859321049487
Status: Accepted

## Decision
1. CLI: `EXPLAIN`/`PROFILE` print the Neo4j-compatible fixed-width ASCII
   tree — columns `Operator | Id | Details | Estimated Rows | Rows |
   DB Hits | Memory (Bytes)`, tree glyphs `+`/`| |`/`|\`, and the footer
   totals line — omitting the Page Cache column (ADR-0344). The ASCII
   rendering is also carried as the node's `string-representation`
   argument so any structured consumer can show the text form.
2. Bolt: EXPLAIN/PROFILE responses carry the plan as SUCCESS summary
   metadata (`plan` / `profile`), in the Neo4j dict shape.
3. HTTP Query API: the response envelope carries `queryPlan` (EXPLAIN) /
   `profiledQueryPlan` (PROFILE) with the recursive node shape.
4. The `_profile_*` data-row columns are deprecated: phase 1 stops adding
   them to EXPLAIN output; their removal from PROFILE lands with phase 2
   (PROFILE tree + metrics) so the metrics they approximated remain
   available in a non-corrupting shape in between.

--- ADR-0365 ---
# ADR-0365: The HTTP Query API v2 plan node shape

Claim: 3c58bc85e11d6188a86c46ae434985cb1e13a4fe
Status: Proposed

## Decision
1. **The HTTP Query API v2 plan node is the v2 shape, not the Bolt wire
   shape.** `queryPlan` / `profiledQueryPlan` carry nodes with
   `operatorType` (suffixed `@cypherlite`; Neo4j writes `@neo4j`),
   **`arguments`** (never `args`), `identifiers`, `children` (always
   present; a leaf's is the empty list, matching Neo4j), `warnings` when
   the node carries any, and the metric fields `dbHits`, `records`, `time`
   (fractional milliseconds), `hasPageCacheStats` (always `false` — the
   engine is in-memory), `pageCacheHits`/`pageCacheMisses` (0) and
   `pageCacheHitRatio` (0.0).
2. **`arguments` is the engine's own args map, projected, not rebuilt.**
   It carries the display and identity args (`Id`, `Details`,
   `EstimatedRows`, and on the root `version`, `planner*`, `runtime*`,
   `Memory`, `GlobalMemory`, `string-representation`) *and* the engine's
   PROFILE metric entries (`Rows`, `TimeNs`, `DbHits`, `MemoryBytes`) —
   Neo4j's own `arguments` keeps its `Rows`/`DbHits` there too, so the
   richer internal form survives the projection instead of being stripped.
   The node-level metric fields (`dbHits`, `records`, `time`) are the same
   values in Neo4j's field spelling: the surface adapts the seam, the
   engine keeps one form.
3. **The node is read through the canonical accessor**
   (`cypherlite_model::wire::plan_node_wire`) and the single-sourced key
   vocabulary (`wire::plan_keys`): the wire form is engine-built and
   invariant, so a malformed node fails loudly there instead of being
   defaulted at the boundary. The v2 args key `arguments` is a local
   constant in the HTTP surface (the engine's and Bolt's key is `args`).
4. **The CORS preflight allow-list admits the headers Browser-like tooling
   sends** — `sentry-trace` and `baggage` beyond `Authorization` and
   `Content-Type` — so the discovery probe is not rejected before any query
   runs.