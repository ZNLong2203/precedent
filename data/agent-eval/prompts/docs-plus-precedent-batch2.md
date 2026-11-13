You are a coding agent in a repository that keeps architecture decision records (ADRs). Below are 6 independent tasks.
For each task you get context retrieved for it. Decide which numbered decision clauses your plan for the task must
respect or build on (ADR number and clause number), at most 8, most important first. Use only the context in this
file: do not read any other file, search the repository or run commands.

Answer with a single JSON array, one object per task, in this exact shape and nothing else:

[{"task_id": "T01", "relies_on": [{"adr": "ADR-0046", "clause": 2}], "note": "one sentence on your plan"}]

Use `"clause": null` for a decision that has no numbered clauses.


==================== TASK T05 ====================
Task: Add a new lifecycle command to the CLI and let the CLI upgrade itself.

Context retrieved for this task: the decision records of the repository, as written.

--- ADR-0069 ---
# 0069. CLI lifecycle commands as positionals, plus self-upgrade design

- **Status**: Accepted
- **Date**: 2026-09-20
- **Deciders**: CypherLite maintainers (Linear LABS-26)

## Decision
Lifecycle verbs become positional commands, and `upgrade` is implemented as
one of them with the fetch/verify/replace design below.

1. **Positional lifecycle commands.** `skill`, `upgrade`, and `update` are
   recognized **only as the first argument** to the `cypherlite` CLI:
   - `cypherlite skill install [--agent NAME]`
   - `cypherlite skill remove [--agent NAME]`
   - `cypherlite upgrade [--yes] [--check]`
   - `cypherlite update` — an alias of `upgrade`.

   Database paths literally named `skill`, `upgrade`, or `update` stay
   reachable via a `./` prefix (e.g. `cypherlite ./skill`) or after `--`
   (e.g. `cypherlite -- skill`).
2. **The `--skill`/`-skill` and `--agent`/`-agent` flags are removed
   outright.** This is a breaking change. Because these flags never shipped
   in a release (they postdate the tree but predate 0.4.0, the first stable
   release), there is no installed base to migrate and therefore no
   migration-hint special-casing: the removed spellings hit the generic
   unknown-flag error like any other unrecognized argument.
3. **Upgrade fetch.** The command issues
   `GET https://api.github.com/repos/neo4j-labs/cypherlite/releases/latest`,
   attaching `Authorization: Bearer $GITHUB_TOKEN` only when the environment
   variable is set (the repository is currently internal; this is parity with
   `docs/static/install.sh`, ADR-0068). The release’s `tag_name` (leading `v`
   stripped) is semver-compared against the binary’s own `CARGO_PKG_VERSION`;
   if the latest release is not newer, the command prints an up-to-date
   message and exits 0.
4. **Asset resolution.** Asset ids are parsed from the release JSON with
   `serde_json` (no shell scraping). The platform binary
   `cypherlite-<os>-<arch>` and `SHA256SUMS` are downloaded via the GitHub API
   asset endpoint with an `Accept: application/octet-stream` header.
5. **Verification and dependencies.** The sha256 of the downloaded binary is
   verified against its `SHA256SUMS` entry using a **new** `sha2` workspace
   dependency. HTTP uses the **existing** workspace `ureq = "3.4"` dependency
   (already declared, previously unused). No other new dependencies are added.
6. **Atomic self-replace.** The verified binary is staged at a temporary path
   in `current_exe()`’s directory (guaranteeing the same filesystem), chmod
   755, then renamed over the running binary. This is macOS/Linux only, the
   same platform scope as the ADR-0068 installer; on Windows the command
   errors with a not-supported message pointing at the manual `.exe` download
   (a running `.exe` cannot be replaced).
7. **Skill refresh after a successful replace.** Agents are detected first;
   if none are detected the step is skipped silently. On an interactive TTY
   the command prompts `Update installed cypherlite skill? [Y/n]` with yes as
   the default; `--yes` auto-accepts; a non-interactive run without `--yes`
   prints a `run: cypherlite skill install` hint instead. On yes, the **new**
   binary is spawned as `cypherlite skill install` with inherited stdio, so
   the new embedded skill bundle is what gets installed (the old process only
   holds the old bundle).
8. **`--check` flag.** A read-only current-vs-latest report: it changes
   nothing on disk and exits 0.

--- ADR-0190 ---
# 0190. Scoped CLI help: a command index, per-command help, and synopsis-scoped usage errors

- **Status**: Accepted
- **Date**: 2026-10-08
- **Deciders**: CypherLite maintainers (Linear [LABS-202](https://linear.app/neo4j/issue/LABS-202))

## Decision
1. **Top-level help is a command index.** `cypherlite --help` prints the
   usage lines

   ```
   cypherlite [OPTIONS] [DATABASE] [QUERY]
   cypherlite <COMMAND> [ARGS]
   ```

   then a `Commands:` section with a one-line entry for every compiled-in
   command — `clone`, `info`, `pull`, `skill`, `upgrade` (naming its `update`
   alias), `telemetry`, `lab` — then all query-run options as before, and
   ends with the footer

   ```
   Run 'cypherlite <COMMAND> --help' for details on a command.
   ```

   No lifecycle command’s flags appear in it; only the query run keeps full
   flag detail there.

2. **Per-command help.** `-h`/`--help` anywhere after a compiled-in command
   word prints that command’s help (synopsis plus its flags/actions) to
   stdout and exits 0. `cypherlite update --help` prints the `upgrade` help;
   `lab` help omits the hidden `neo` action; a help flag before the command
   word still prints top-level help. A command word whose feature is compiled
   out keeps the not-included error (exit 2).

3. **Usage errors are scoped.** A usage error (exit 2) prints
   `Error: <msg>`, the relevant command’s synopsis line(s) as
   `Usage: cypherlite …`, and
   `Run 'cypherlite <command> --help' for more information.` — with the
   canonical name `upgrade` for `update`. Top-level parse errors (unknown
   flag, unexpected positional, invalid `--namespace`) use the query-run
   synopsis and `Run 'cypherlite --help' for more information.` The two
   literal stderr shapes are

   ```
   Error: clone requires SOURCE and DEST
   Usage: cypherlite clone [--wal-dir DIR] [--to-snapshot-format F] SOURCE DEST
   Run 'cypherlite clone --help' for more information.
   ```

   ```
   Error: unknown flag: --bogus
   Usage: cypherlite [OPTIONS] [DATABASE] [QUERY]
   Run 'cypherlite --help' for more information.
   ```

4. **Errors that print no usage today keep their stderr byte-for-byte.** A
   missing flag value, an invalid `--mode`/`--param`/`--fetch-params` value,
   and `--command` combined with a positional query are unchanged.

5. **Per-command help emits the existing telemetry events**
   (`CYPHERLITE-CLI_STARTUP` with kind `help`, and `CYPHERLITE-CLI_HELP`) —
   no schema change.

6. **Each command synopsis is defined once in source** and shared by its help
   and its usage error, so the two cannot drift.

--- ADR-0079 ---
# 0079. Anonymous usage metrics in the CLI

- **Status**: Proposed
- **Date**: 2026-09-21
- **Deciders**: CypherLite maintainers (Linear LABS-12, LABS-55, LABS-42)

## Decision
Anonymous usage telemetry is collected by the `cypherlite` CLI binary only,
sent to Mixpanel, identified by a random install ID, delivered off the hot
path, and governed by a layered opt-out that defaults to on.

1. **Scope: CLI binary only.** Telemetry lives in `crates/cypherlite-cli`.
   The embedded library (`cypherlite::Database`), the C ABI
   (`crates/cypherlite-ffi`), and `cypherlite-bolt` never phone home. Bolt
   may adopt metrics later via a new ADR; nothing here precludes it.
2. **Sink and transport: Mixpanel over the existing `ureq`.** Events are
   sent as `POST https://api.mixpanel.com/track` (default endpoint constant
   `DEFAULT_ENDPOINT`; the EU-residency host is
   `https://api-eu.mixpanel.com/track`) with a JSON array body of
   `{"event": ..., "properties": {"token": ..., "time": ...,
   "distinct_id": ..., "$insert_id": ..., ...}}` objects. The HTTP client is
   hand-rolled over the existing workspace `ureq = "3.4"` dependency
   (already used by `upgrade`, ADR-0069); install-ID and `$insert_id`
   randomness come from the existing workspace `rand` dependency (version
   pinned by ADR-0360). **Zero new dependencies.**
3. **Identity: random install ID, not a machine ID.** A random UUID is
   generated once and persisted as the install ID in state under the XDG
   config directory — `$XDG_CONFIG_HOME/cypherlite/` when
   `$XDG_CONFIG_HOME` is set, otherwise `~/.config/cypherlite/`. It is the
   `distinct_id` on every event. No hardware or OS machine identifier is
   ever read.
4. **Events v1 (minimal taxonomy).** Event names carry the
   `CYPHERLITE-CLI_` app prefix so the tracked surface is explicit in
   Mixpanel; a future Bolt adoption gets its own prefix (e.g.
   `CYPHERLITE-BOLT_`) rather than sharing the CLI's. Four events:
   - `CYPHERLITE-CLI_STARTUP` — `kind`: `oneshot` | `stdin` | `repl` |
     `version` | `help`.
   - `CYPHERLITE-CLI_QUERY` — `success` (bool), `source`: `oneshot` | `stdin` |
     `repl`, `storage`: `memory` | `persistent`, `output_mode`.
   - `CYPHERLITE-CLI_COMMAND` — lifecycle `command` name, `action`, `success`.
   - `CYPHERLITE-CLI_HELP` — fired when help is shown.

   Base dimensions on every event: `distinct_id` (install ID), `$os`,
   `arch`, CLI `version`, `uptime`, and `invoker` (`human` | `agent` |
   `ci`, derived from TTY detection, `CI` env, and known agent env vars).
   **Hard privacy rule:** never query text, never database paths, never
   parameter values — the event builder types have no fields for them, so
   capturing them is a compile error, not a policy violation.
5. **Delivery: non-blocking, best-effort, invisible.** Events go onto a
   bounded channel that drops on overflow; a single background thread drains
   it with a 2-second HTTP timeout; a bounded `flush()` runs on exit so the
   CLI is never perceptibly slowed. All telemetry errors are swallowed:
   nothing on stdout or stderr, exit codes unaffected.
6. **Opt-out: layered, default ON.** First match wins:
   `DO_NOT_TRACK=1` (the consoledonottrack convention) →
   `CYPHERLITE_TELEMETRY` env var (`0`/`false`/`off` disables) → persisted
   `telemetry: false` in `<config>/cypherlite/config.json` → enabled.
   Persistent control is a new positional lifecycle command `cypherlite
   telemetry on|off|status` following the ADR-0069 grammar (recognized only
   as the first argument; `./telemetry` and `-- telemetry` remain reachable
   as database paths). There is deliberately **no `--no-telemetry` flag**:
   per ADR-0069

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

--- ADR-0279 ---
# 0279. The `lab` command namespace

- **Status**: Accepted
- **Renumbered**: from 0156 (shared-number cleanup)
- **Date**: 2026-10-01
- **Deciders**: CypherLite maintainers
- Later references: ADR-0431 §11–§12 retires the namespace outright — the
  importers became first-party extension crates under the `extensions/`
  group (ADR-0434), the hidden `neo` egg is deleted entirely, and the
  `lab` command word is gone with no stub, superseded by `run`.

## Decision
1. **`lab` is a new first-positional command word** in the hand-rolled
   `cypherlite` parser, alongside the ADR-0069 lifecycle verbs. Its shape is
   `cypherlite lab <action> [--flags]`. A database path literally named `lab`
   stays reachable via a `./` prefix or after `--`, exactly as ADR-0069
   provides for `skill`, `upgrade`, and `update`.
2. **`lab` is reserved in every build, including builds where its feature is
   compiled out** (ADR-0104 rule 4). A build without the `lab` feature
   recognizes `cypherlite lab …` as a command and prints the shared
   not-included error with exit 2; it never falls through to opening a
   database named `lab`. The escape hatch (`./lab` or `-- lab`) is identical
   in every build.
3. **Actions are either visible or hidden.**
   - A **visible** action is listed in the hand-written `--help` text and in
     the command tables of `docs/api/cli/spec.md`, and is covered by tests.
   - A **hidden** action works, but is deliberately never listed in `--help`
     or in any spec table. It is an easter egg: not part of the documented
     surface, and not owed compatibility or a changelog entry. Hidden actions
     still get tests, because no behavior ships without tests (AGENTS.md §4).
   - The first visible action is `fs-to-graph` (ADR-0157). The first hidden
     action is `neo`.
4. **The `lab` Cargo feature ships in the `full` bundle only.** It is not in
   `agent` or `minimal`, so sandbox and query-only builds carry neither the
   experimental commands nor their dependencies. The feature table and bundle
   table in `docs/api/cli/spec.md` record this, per ADR-0104.
5. **`--help` lists only visible actions that are compiled in.** A build with
   the `lab` feature lists `lab fs-to-graph` and never `lab neo`; a build
   without the feature lists `lab` only as a recognized, not-included
   command (or omits it, matching how ADR-0104 handles other gated commands).

Precedent `preflight` for this task (a tool that tracks which decisions are still in force):
{"task":"Add a new lifecycle command to the CLI and let the CLI upgrade itself.","paths":[],"decisions":[{"id":"ADR-0069","title":"CLI lifecycle commands as positionals, plus self-upgrade design","standing":"partial","declared_status":"accepted","path":"docs/adr/0069-cli-lifecycle-commands.md","gist":"Lifecycle verbs become positional commands, and upgrade is implemented as one of them with the fetch/verify/replace design below. 1. Positional lifecycle commands. skill, upgrade, and update are recognized only as the first argument to the cypherlite CLI: - cypherlite skill install [--agent NAME] -…","why":["matches task (clause+fulltext+vector)"],"live_clauses":[{"n":1,"title":"Positional lifecycle commands"},{"n":2,"title":"The --skill/-skill and --agent/-agent flags are removed"},{"n":5,"title":"Verification and dependencies"},{"n":6,"title":"Atomic self-replace"},{"n":7,"title":"Skill refresh after a successful replace"},{"n":8,"title":"`--check` flag"}],"stale_clauses":[{"n":3,"title":"Upgrade fetch","by":["ADR-0250"],"note":"§3 'Upgrade fetch' superseded by ADR-0250"},{"n":4,"title":"Asset resolution","by":["ADR-0250"],"note":"§4 'Asset resolution' superseded by ADR-0250"}],"evidence":[{"by":"ADR-0250","treatment":"SUPERSEDES","clauses":[3,4],"quote":"ADR-0250 supersedes the §3 fetch step and the §4 asset resolution of this decision: `upgrade`/`update` reads `releases.json` from `https://neo4j-labs.github.io/cypherlite/releases.json` and downloads assets through the non-API route `https://github.com/neo4j-labs/cypherlite/releases/download/{tag}/{asset}`."},{"by":"ADR-0250","treatment":"SUPERSEDES","clauses":[],"quote":"ADR-0069's fetch step (API `releases/latest`, asset ids, the octet-stream asset endpoint) and its `GITHUB_TOKEN` consequence are superseded for the fetch/download mechanism; its version comparison, ADR-0115 verification, atomic replace, and skill-refresh steps are unchanged."}]},{"id":"ADR-0190","title":"Scoped CLI help: a command index, per-command help, and synopsis-scoped usage errors","standing":"in_force","declared_status":"accepted","path":"docs/adr/0190-scoped-cli-help.md","gist":"1. Top-level help is a command index. cypherlite --help prints the usage lines cypherlite [OPTIONS] [DATABASE] [QUERY] cypherlite <COMMAND> [ARGS] then a Commands: section with a one-line entry for every compiled-in command — clone, info, pull, skill, upgrade (naming its update alias), telemetry,…","why":["matches task (clause+fulltext+vector)"],"live_clauses":[{"n":1,"title":"Top-level help is a command index"},{"n":2,"title":"Per-command help"},{"n":3,"title":"Usage errors are scoped"},{"n":4,"title":"Errors that print no usage today keep their stderr byte-for-byte"},{"n":5,"title":"Per-command help emits the existing telemetry events"},{"n":6,"title":"Each command synopsis is defined once in source"}],"stale_clauses":[]},{"id":"ADR-0250","title":"Release discovery from a static releases.json on the website","standing":"partial","declared_status":"accepted","path":"docs/adr/0250-releases-json-update-discovery.md","gist":"Publish releases.json at the website root and make upgrade/update read it. The GitHub REST API leaves the update path entirely — no fallback, not even when GITHUB_TOKEN is set. ### 1. Canonical URL and hosting - The canonical URL is https://neo4j-labs.github.io/cypherlite/releases.json. - The file…","why":["controls ADR-0069 (§3–4)"],"live_clauses":[{"n":1,"title":"Canonical URL and hosting"},{"n":2,"title":"Schema (schema_version 1)"},{"n":6,"title":"Publisher contract"}],"stale_clauses":[{"n":3,"title":"Asset download URL template","by":["ADR-0358"],"note":"§3 'Asset download URL template' superseded by ADR-0358"},{"n":4,"title":"Failure behavior","by":["ADR-0358"],"note":"§4 'Failure behavior' superseded by ADR-0358"},{"n":5,"title":"GITHUB_TOKEN","by":["ADR-0358"],"note":"§5 'GITHUB_TOKEN' superseded by ADR-0358"}],"evidence":[{"by":"ADR-0358","treatment":"SUPERSEDES","clauses":[3,4,5],"quote":"ADR-0358 supersedes §3 (the download URL template as the only route), §4's no-API-fallback rule (\"not even when `GITHUB_TOKEN` is set\") and §5's token claim (that the optional bearer header makes the direct route work while the repository is internal)."},{"by":"ADR-0546","treatment":"SUPERSEDES","clauses":[],"quote":"ADR-0250's schema and canonical URLs are unchanged; its gh-pages publisher contract is superseded by this one."}]},{"id":"ADR-0242","title":"`agent-context` discovery command and `skill list`/`skill check`","standing":"in_force","declared_status":"accepted","path":"docs/adr/0242-agent-context-command-and-skill-drift-check.md","gist":"1. cypherlite agent-context [COMMAND] is a positional lifecycle command (ADR-0069) in the agent-context Cargo feature, bundled into full and agent (ADR-0104); in a minimal build the word is a not-included command like any other compiled-out verb. With no argument it prints a compact index: the…","why":["matches task (clause+fulltext+vector)"],"live_clauses":[{"n":1,"title":"`cypherlite agent-context [COMMAND]`"},{"n":2,"title":"It renders from the same COMMANDS descriptor table that feeds"},{"n":3,"title":"`skill list`"},{"n":4,"title":"Docs, help text, and tests land in the same change"}],"stale_clauses":[]},{"id":"ADR-0279","title":"The `lab` command namespace","standing":"in_force","declared_status":"accepted","path":"docs/adr/0279-lab-command-namespace.md","gist":"1. lab is a new first-positional command word in the hand-rolled cypherlite parser, alongside the ADR-0069 lifecycle verbs. Its shape is cypherlite lab <action> [--flags]. A database path literally named lab stays reachable via a ./ prefix or after --, exactly as ADR-0069 provides for skill,…","why":["matches task (clause+fulltext+vector)"],"live_clauses":[{"n":1,"title":"`lab` is a new first-positional command word"},{"n":2,"title":"lab is reserved in every build, including builds where its"},{"n":3,"title":"Actions are either visible or hidden"},{"n":4,"title":"The `lab` Cargo feature ships in the `full` bundle only"},{"n":5,"title":"`--help` lists only visible actions that are compiled in"}],"stale_clauses":[]}],"warnings":["ADR-0069 is partly superseded: §3 'Upgrade fetch' superseded by ADR-0250","ADR-0250 is partly superseded: §3 'Asset download URL template' superseded by ADR-0358"],"omitted":12,"tokens":1576,"how_to_read":"live_clauses are good law; stale_clauses were taken out of force by the decision named in `by` - follow that decision instead."}

==================== TASK T13 ====================
Task: Speed up constraint checking so that a write only validates what it touched.

Context retrieved for this task: the decision records of the repository, as written.

--- ADR-0172 ---
# 0172. Incremental constraint validation

- **Status**: Accepted
- **Date**: 2026-10-06
- **Deciders**: Oskar Hane (agreed in conversation), CypherLite maintainers

## Decision
Constraint validation becomes **incremental**:

- A validation re-checks only what the writes since the previous validation
  could have broken.
- It also fully re-checks any constraint created or re-derived in that span.
- Its accept/reject decisions and error texts are identical to today's
  whenever the state before those writes satisfied every constraint.
  Each successful validation establishes that state.
- The entry point `validate_constraints(graph)` and both call sites
  (`exec/mod.rs:101`, `exec/call.rs:534`) stay unchanged.

### 1. The validation slice: how touched entities are tracked

Every `ExecGraph` write primitive appends a redo op to
`WriteScratch.pending_redo` for each call that writes. A call that changes
nothing pushes nothing: removing a missing property, adding a label the node
already has, removing a label it lacks. The primitives are `create_node`,
`create_rel`, `add_labels`, `remove_labels`, `set_property_node`,
`set_property_rel`, `delete_rel` and `delete_node` (`overlay/mod.rs:985`,
`:1016`, `:1090`, `:1113`, `:1146`, `:1178`, `:1233`, `:1267`). Map `SET`,
`+=`, MERGE and dynamic labels all go through them (`exec/write.rs:163-209`,
`:250-297`, `exec/create.rs:293-348`). The redo log is therefore the
scratch's change log.

**Cursor.** `WriteScratch` gains `validated_redo: usize`:

- On entry, `validate_constraints` takes the slice
  `pending_redo[validated_redo..]` and sets `validated_redo =
  pending_redo.len()` before checking anything. This is drain-on-entry.
- `take_redo` resets the cursor to 0.

**Classification.** The slice is classified into hash sets:

| Op in the slice | Recorded as |
| --- | --- |
| `CreateNode`, `AddLabels`, `RemoveLabels`, `SetNodeProp`, `RemoveNodeProp` | **touched node** (its id) |
| `RemoveLabels` (in addition to the above) | **label-loss node** |
| `CreateRel`, `SetRelProp`, `RemoveRelProp` | **touched relationship** |
| `CreateConstraint { name }`, `CatalogDerivedConstraint { constraint }` | name added to the **recheck set** |
| `SetCurrentGraphType` | every constraint with an enforced-label kind (`ConstraintType::is_enforced_label_kind`) added to the recheck set |
| `DeleteNode`, `DeleteRel`, index ops, other catalog ops, `PullIdentityPut` | nothing; deletion can never introduce a violation |

**Liveness and reads.**

- "Carrying L" and "of type T" are evaluated on the live `ExecGraph` view at
  validation time.
- An id that is no longer live is skipped, just as `graph.node(id)` returning
  `None` is skipped today.
- Entities are read with facet accessors, never with `node()` or `rel()`
  (ADR-0075's rule): `node_labels`, `node_prop`, `rel_type`, `rel_prop`,
  `rel_ends`.

**Lifetime of the slice.**

- **Autocommit:** the slice is the statement.
- **Explicit transaction:** the slice is the current statement. The cursor
  advanced past the earlier statements when they validated. A statement that
  fails marks the transaction failed (`connection.rs:745`), so a partly
  validated log can never commit.
- **`CALL { } IN TRANSACTIONS`:** the slice is the batch plus any outer writes
  not yet validated. `scratch_snapshot` and `restore_scratch` (`call.rs:515`,
  `:541`) clone and restore the cursor together with the log. A failed batch
  therefore hands its unvalidated outer writes to the next validation.

### 2. What each kind re-validates

In the table, P is the constraint's property list and
`p` ranges over P. L is the label of a node constraint and T the type of a
relationship co

--- ADR-0337 ---
# ADR-0337: CREATE CONSTRAINT OPTIONS lowering and eval errors propagate

Status: Proposed
Claim: e9fa7c0d09c8d2ea73586864e1b74293836f8c31

## Decision
`catalog_create_constraint` propagates the lowering and eval errors with
`?` and validates only the resulting shape: a key other than
`indexConfig`, a non-map value, or a non-empty map is the existing
`InvalidOptionsMap` semantic error; an absent parameter surfaces the typed
`ParameterMissing` (ADR-0308), and an eval failure surfaces its own error.
The constraint is not created on any failure.

--- ADR-0439 ---
# ADR-0439: Commit-time uniqueness admission

Status: Proposed
Claim: 5798c270ad9a66d0453660cb9673e523348ab0e9

## Decision
`flush_group` gains a commit-time uniqueness admission check, backed by a maintained, single-version per-constraint tuple map on `Graph`.

### The probe

A new module family `graph/constraint_keys/` owns the map and the admission side. `mod.rs` holds the map vocabulary, its byte constants, and the backfill/rebuild lifecycle; `seams.rs` holds the `apply_redo`-seam maintenance; `simulation.rs` holds the one redo-op classification, the constrained `KeyView`, and the slot simulation; `ddl.rs` holds the batch DDL accumulator and the one net-transition projection both the probe and the estimate drive; `admission.rs` holds the commit-loop probe; `estimate.rs` holds the entry-growth estimate. The dependency runs one way: the admission and estimate sides import the map's vocabulary, the map never names them. The field sits on `Graph` beside `label_counts` and `pair_counts`, not in `Indexes`: that bundle is lazily maintained, while this map is eagerly current.

- **Key**: the constraint identity (its catalog name) and the full tuple, a `Box<[GroupKey]>` in the constraint's `properties` order, each component built with `GroupKey::for_property_index`. That is the equivalence key the existing probes use (ADR-0172 §3, ADR-0184, ADR-0185).
- **Value**: a `TupleEntry` of `holders: Vec<EntityId>` and `charged: u64` — the live entities holding the tuple and the bytes this entry was charged, so removal refunds exactly what creation charged. `EntityId` is `Node(NodeId)` or `Rel(RelId)`; the constraint identity fixes which variant.
- **One holder per live constrained entity per constraint.** Entries are keyed by the tuple, so the normal case is one entry with one holder; a second holder is a pre-existing violation recorded by replay or a replicated record, never installed by admission.
- **Unkeyable tuples**: a null or NaN component produces no entry. Nulls never equal under a `unique` constraint (several nulls may coexist), a NaN never equals itself, and a `key` constraint's missing property is the required-property check, not uniqueness. An entity with such a tuple can neither violate nor be violated.
- **Composite constraints** get one true composite key. This does not change ADR-0184's smallest-bucket choice for the statement-time validator; at commit time the whole tuple is the key, so bucket cardinality and declaration order cannot matter.
- **Relationship constraints** use the same map with `RelId` as the holder. They have no backing index postings at all, so this is their first exact committed-state probe. They are in scope even though LABS-551's reproducer is node-only: the same map and the same seams cover them at no extra design cost, and carving them out would preserve the identical gap for `RELATIONSHIP KEY`.

Single-version state is sufficient: the check runs under the publication write guard, serialized against every other commit and against reload, and only current committed state matters. A rejected slot never applies; a retry runs on a fresh snapshot after this group applies.

**Lock order.** The map lock is taken last, after the entity (`nodes` / `rels`) and `label_index` guards. No path holds the map lock while acquiring an entity guard: the admission probe builds its tuples from committed entities first, then takes the map lock for the lookups, matching the `apply_redo` primitives' order. The entry-growth estimate snapshots the map's specs, per-constraint charges, and scope under the lock, releases it for the simulation (which interns D

--- ADR-0184 ---
# 0184. Composite uniqueness probes pick the smallest committed-plus-scratch bucket

- **Status**: Accepted
- **Date**: 2026-10-08
- **Deciders**: Oskar Hane (agreed in conversation), CypherLite maintainers

## Decision
A uniqueness probe over a constraint with two or more properties chooses
its property per touched tuple:

1. For every property `p_i` of the constraint, compute the committed
   bucket length plus the scratch bucket length at `V[i]`: the size of
   `Graph::equality_postings(L, p_i, V[i])` plus the size of the
   `prop_ix` seek `(L, p_i, V[i])`.
2. Pick the `i` with the smallest sum; ties go to the lowest `i`.
3. Take candidates from that same `p_i` on **both** sides: the committed
   equality postings for `(L, p_i)` at `V[i]` and the scratch seek for
   `(L, p_i)` at `V[i]`. Union them and re-verify.

Both sides must name the same property because the two structures cover
different populations under one key. The committed postings hold every
committed version of every committed node under its committed value. The
scratch `prop_ix` is an additions-only log of the pairings the scratch's
writes introduced (ADR-0173): a scratch-created node is posted under
every property, but a committed node copied into the scratch by a `SET`
of another property is posted there only under the changed key. Suppose
the probe named `p_i` for the committed side but a different `p_j` for
the scratch side, and the statement changed `y.p_i` to `V[i]`, copying
`y` into the scratch: `y`'s committed posting for `p_i` carries its old
value, and its only scratch posting is under the changed key `p_i`, so a
scratch seek under `p_j` misses it and the conflict is missed. The union
at one `(p_i, V[i])` covers every partner:

- a committed-only node is found on the committed side, its live value
  being its committed value;
- a node the scratch changed on `p_i` is found on the scratch side, which
  posted the changed key;
- a node the scratch copied because of a change to another property is
  found on the committed side, which holds its unchanged `p_i` value;
- a scratch-created node is found on the scratch side, which posts every
  property at `CreateNode`.

A property whose value has no key (NaN) counts as an empty bucket on both
sides; a tuple with a NaN component equals nothing, so choosing that
property yields no candidates, which is the correct verdict.

Verification is ADR-0172 §3 step 3 unchanged: every candidate `y ≠ x` is
checked on the snapshot+scratch view for liveness, for the constraint's
label, and for `eq_non_null` on every component. Error selection is
ADR-0172 §6 unchanged: a conflict is still raised at the later id of the
pair, and the first constraint in name order that fails produces the
error. Only the bucket that supplies candidates changes.

A single-property constraint keeps today's probe: its only property is
the chosen one.

Cost: the length computation materializes the pair it counts, so the
first probe of a composite constraint pays the one-time lazy build of one
pair per constrained property (each O(|L|) once, ADR-0063), where
ADR-0172 §3 built only the first. Every later probe pays the smallest
bucket's candidates plus dirty catch-up. Bucket lengths are superset
counts (stale versions included), so the choice is a heuristic;
correctness never depends on it.

--- ADR-0017 ---
# 0017. Write-write conflicts are returned to the client; the engine does not retry

- **Status**: Accepted
- **Date**: 2026-08-28
- **Deciders**: MemoryDB maintainers

## Decision
A write-set conflict at WAL append is **`Error::Conflict`**. The engine
does not retry. The overlay is discarded; nothing is appended to the WAL.
The client retries, aborts, or compensates.

The Display string is `write-write conflict` so the C ABI
(`MEMORYDB_ERROR` + `memorydb_error_message`) and language wrappers can
detect it without a new status code.

Precedent `preflight` for this task (a tool that tracks which decisions are still in force):
{"task":"Speed up constraint checking so that a write only validates what it touched.","paths":[],"decisions":[{"id":"ADR-0173","title":"Overlay-owned redo log and scratch equality index","standing":"in_force","declared_status":"proposed","path":"docs/adr/0173-overlay-owned-redo-log-and-scratch-index.md","gist":"1. ScratchPropIndex (overlay/prop_ix.rs) owns the scratch equality index. It has a seek, which builds a (label, key) pair on first use from the scratch nodes, and post methods. The any-label bucket is one named constant that both use. Buckets are keyed key → label, so a post looks up &str keys and…","why":["matches task (clause+fulltext+vector)","controls ADR-0172 (§1–3, §8)"],"live_clauses":[{"n":1,"title":"`ScratchPropIndex`"},{"n":2,"title":"Posting is driven by the redo funnel"},{"n":3,"title":"`RedoLog`"},{"n":4,"title":"Validate, then mark"},{"n":5,"title":"`all_node_ids` / `all_rel_ids`"},{"n":6,"title":"`RedoOp::is_catalog`"},{"n":7,"title":"An unknown kind tag fails validation"}],"stale_clauses":[]},{"id":"ADR-0172","title":"Incremental constraint validation","standing":"partial","declared_status":"accepted","path":"docs/adr/0172-incremental-constraint-validation.md","gist":"Constraint validation becomes incremental: - A validation re-checks only what the writes since the previous validation could have broken. - It also fully re-checks any constraint created or re-derived in that span. - Its accept/reject decisions and error texts are identical to today's whenever the…","why":["matches task (clause+fulltext+vector)"],"live_clauses":[{"n":5,"title":"Full re-validation for the recheck set"},{"n":6,"title":"Error selection: identical to today"},{"n":7,"title":"Explicit transactions and CALL { } IN TRANSACTIONS"}],"stale_clauses":[{"n":1,"title":"The validation slice: how touched entities are tracked","by":["ADR-0173"],"note":"§1 'The validation slice: how touched entities are tracked' superseded by ADR-0173"},{"n":2,"title":"What each kind re-validates","by":["ADR-0173"],"note":"§2 'What each kind re-validates' superseded by ADR-0173"},{"n":3,"title":"property type (ddl.rs:395-405).","by":["ADR-0173"],"note":"§3 'property type (ddl.rs:395-405).' superseded by ADR-0173"},{"n":4,"title":"Fallback for relationship unique / key, which have no backing","by":["ADR-0185"],"note":"§4 'Fallback for relationship unique / key, which have no backing' superseded by ADR-0185"},{"n":8,"title":"Fixed cost per validation","by":["ADR-0173"],"note":"§8 'Fixed cost per validation' superseded by ADR-0173"}],"evidence":[{"by":"ADR-0185","treatment":"SUPERSEDES","clauses":[4],"quote":"This replaces the ADR-0172 §4 walk (`rel_partners`)."},{"by":"ADR-0173","treatment":"SUPERSEDES","clauses":[8],"quote":"This replaces ADR-0172 §8's `binary_search` merge."}]},{"id":"ADR-0174","title":"Re-check constraints committed mid-transaction; cancellable validation loops","standing":"in_force","declared_status":"accepted","path":"docs/adr/0174-committed-catalog-constraint-rechecks.md","gist":"1. The scratch remembers the catalog it last validated against. RedoLog (the owner of the validation cursor, ADR-0173) gains a constraint fingerprint: every constraint's definition and derived enforced label, in name order, as named_constraints() and show_schema() reported them. The fingerprint…","why":["matches task (clause+fulltext+vector)"],"live_clauses":[{"n":1,"title":"The scratch remembers the catalog it last validated against"},{"n":2,"title":"Catalog drift joins the recheck set"},{"n":3,"title":"Validation loops are cancellable"},{"n":4,"title":"The equality pins are extended, not changed"}],"stale_clauses":[]},{"id":"ADR-0185","title":"Lazy relationship equality postings for relationship uniqueness probes","standing":"in_force","declared_status":"accepted","path":"docs/adr/0185-relationship-equality-postings.md","gist":"Relationships get the same lazy equality postings nodes have. - Committed postings. Graph gains rel_prop_pairs: DashMap<(u32, u32), RelPropPairIndex>, keyed by (relationship type id, property key id) — the rel twin of prop_pairs (graph/mod.rs:225-228) with built, postings: GroupKey → HashSet<RelId>…","why":["controls ADR-0172 (§4)"],"live_clauses":[],"stale_clauses":[]},{"id":"ADR-0184","title":"Composite uniqueness probes pick the smallest committed-plus-scratch bucket","standing":"in_force","declared_status":"accepted","path":"docs/adr/0184-composite-key-smallest-bucket-probe.md","gist":"A uniqueness probe over a constraint with two or more properties chooses its property per touched tuple: 1. For every property p_i of the constraint, compute the committed bucket length plus the scratch bucket length at V[i]: the size of Graph::equality_postings(L, p_i, V[i]) plus the size of the…","why":["matches task (clause+fulltext+vector)"],"live_clauses":[{"n":1,"title":"For every property p_i of the constraint, compute the committed"},{"n":2,"title":"Pick the i with the smallest sum; ties go to"},{"n":3,"title":"Take candidates from that same p_i on both sides: the"}],"stale_clauses":[]}],"warnings":["ADR-0172 is partly superseded: §1 'The validation slice: how touched entities are tracked' superseded by ADR-0173"],"omitted":9,"tokens":1292,"how_to_read":"live_clauses are good law; stale_clauses were taken out of force by the decision named in `by` - follow that decision instead."}

==================== TASK T07 ====================
Task: Add support for creating and switching between multiple databases.

Context retrieved for this task: the decision records of the repository, as written.

--- ADR-0276 ---
# 0276. Store-level databases catalog

- **Status**: Accepted
- **Renumbered**: from 0145 (shared-number cleanup)
- **Date**: 2026-09-28
- **Deciders**: CypherLite maintainers

## Decision
The databases catalog is **store-level**: one table shared by every
namespace graph of a store.

- A crate-internal `DatabasesCatalog` (`Arc`-shared through `StoreServices`,
  like the procedure registry and CSV policy of ADR-0116 §10) holds the
  `name → (defaultLanguage, composite)` table. It seeds exactly the three
  fixed namespaces at `CYPHER 25`, non-composite, and keeps the ADR-0116 §8
  invariants: fixed names match case-insensitively and store canonically,
  entries for other names are ignored, a fixed namespace can never be
  dropped, and a checkpoint image is sanitized to exactly the fixed
  namespaces on load.
- `TheaterData` no longer carries `databases`. The read-admission snapshot
  (`ShowSchema`) is now a real struct that pairs a capture of the shared
  catalog with the graph's theater maps, so SHOW readers and the
  speculative overlay (`apply_overlay` on `PutDatabase`/`DropDatabase`)
  keep their admitted-copy semantics unchanged.
- **Formats do not change.** `CheckpointTheater` still serializes the table
  under the top-level `databases` key (declared first, preserving the
  historical flattened-key order); the `PutDatabase`/`DropDatabase` redo
  ops are untouched. Committed replay (`Graph::apply_redo`) writes the
  shared catalog instead of the graph theater, and checkpoint capture /
  restore read and install the shared catalog. Old stores open unchanged
  and the golden-store fixtures hold.

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

--- ADR-0142 ---
# 0142. Browser/Desktop-compat record shapes for dbms.components, SHOW DATABASES, and dbms.info

- **Status**: Accepted
- **Date**: 2026-09-29
- **Deciders**: CypherLite maintainers (Linear LABS-139)
- **Later references**: ADR-0152 supersedes row 1's `versions` value: the
  'Neo4j Kernel' row now reports a calver string with a `-cypherlite`
  product suffix (`2026.10-cypherlite`, following Aura's `5.27-aura`
  convention) so browser.neo4j.io's throwing `>= 4.4.0` sdk gate passes.
  The hyphenated suffix keeps the string distinguishable from a real Neo4j
  version, addressing this ADR's honesty objection; the 'CypherLite' row
  still reports the honest workspace version.

## Decision
1. **`dbms.components` returns three rows, in this order:**

   | # | name | versions | edition |
   |---|---|---|---|
   | 1 | `Neo4j Kernel` | `[<workspace version, e.g. '0.9.1'>]` | `community` |
   | 2 | `Cypher` | `['5', '25']` | `community` |
   | 3 | `CypherLite` | `[<workspace version>]` | `community` |

   Row 1 carries **both** reader roles: Desktop finds the version row **by
   name** (`n.find(e=>e.name==='Neo4j Kernel')`, evidence 3 above), while the
   public web Browser reads the **first** record (`extractServerInfo` takes
   `versions[0]` of record 0, `neo4j-browser@neo4j-2026.08.0`
   `utils.ts:34-64`). Row 1 must therefore be first **and** named
   `Neo4j Kernel`. Row 2 keeps its existing name and versions and feeds
   Desktop's `cypherVersions` (found by name `Cypher`). Row 3 identifies
   CypherLite to consumers that iterate all rows. `edition` is `'community'`
   on all rows: CypherLite has no enterprise tier (matching ADR-0116's
   Community Edition semantics).

   **Deliberate consequence:** the workspace version (e.g. `0.9.1`) is below
   Desktop's `4.4.0` gate, so Desktop shows the **non-fatal** "not
   officially supported" warning. That warning is accepted as honest
   output; claiming a `>= 4.4.0` version was rejected (see Alternatives).

2. **SHOW DATABASES rows carry concrete values** in both the `neo4j` and
   `system` namespaces (ADR-0116):

   | field | neo4j | system |
   |---|---|---|
   | `access` | `'read-write'` | `'read-write'` |
   | `address` | `'localhost:7687'` | `'localhost:7687'` |
   | `role` | `'primary'` | `'primary'` |
   | `requestedStatus` | `'online'` | `'online'` |
   | `currentStatus` | `'online'` | `'online'` |
   | `statusMessage` | `''` | `''` |
   | `writer` | `true` | `true` |
   | `default` | `true` | `false` |
   | `home` | `true` (unchanged) | `false` (unchanged) |

   `name`, `type`, `aliases` and `constituents` are unchanged. `address` is
   the constant `'localhost:7687'`: Desktop builds the instance id
   `name@address` and rejects an empty address (evidence 4 above), and the
   engine does not know the Bolt bind address, so the value is a
   display/instance-id placeholder — correct for the default Bolt bind and
   the published Docker port, cosmetic-only otherwise.

3. **`dbms.info()` returns one row**
   `{id: 'cypherlite', name: 'system', creationDate: '1970-01-01T00:00:00Z'}`.
   `name` is the constant `'system'`: the procedure arm sees only the graph,
   not the session's current database, and the engine is single-database.
   `creationDate` is a documented placeholder: the engine tracks no
   creation time, and the Desktop UI merely displays the fields (evidence 5
   above).

--- ADR-0316 ---
# ADR-0316: Bolt accepts client NOOP chunks between messages

Status: Proposed
Claim: 4d1b4621cb4d85399bc0e0b76153c18e9baf52cf

## Decision
1. An empty chunk received where a message would start is a NOOP. The
   server skips it and keeps reading. Any number of NOOPs may precede or
   separate messages.
2. A NOOP counts as connection activity for the ADR-0110 idle timeout: it
   re-arms the wait for the next message. It is not a message, so it gets
   no reply and does not change session state.
3. The NOOP rule lives in the one chunk-framing helper that both the
   server's message reader and the public `protocol::read_message` use, so
   test clients skip the server's ADR-0312 keep-alive NOOPs by the same
   rule.

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

Precedent `preflight` for this task (a tool that tracks which decisions are still in force):
{"task":"Add support for creating and switching between multiple databases.","paths":[],"decisions":[{"id":"ADR-0276","title":"Store-level databases catalog","standing":"in_force","declared_status":"accepted","path":"docs/adr/0276-store-level-databases-catalog.md","gist":"The databases catalog is store-level: one table shared by every namespace graph of a store. - A crate-internal DatabasesCatalog (Arc-shared through StoreServices, like the procedure registry and CSV policy of ADR-0116 §10) holds the name → (defaultLanguage, composite) table. It seeds exactly the…","why":["matches task (fulltext+vector)","controls ADR-0116 (§8)"],"live_clauses":[],"stale_clauses":[]},{"id":"ADR-0229","title":"Remove the `system_ontologies` Cypher surface","standing":"in_force","declared_status":"accepted","path":"docs/adr/0229-remove-system-ontologies-cypher-surface.md","gist":"1. Listed, not queryable. system_ontologies stays a fixed, listed namespace. SHOW DATABASES keeps its row with ADR-0116 §6's values verbatim (type standard, access read-only, currentStatus and requestedStatus online, default and home false, empty aliases and constituents, the stored…","why":["matches task (fulltext+vector)","controls ADR-0116 (§1, §4–5, §7, §10)"],"live_clauses":[{"n":1,"title":"Listed, not queryable"},{"n":2,"title":"The error"},{"n":3,"title":"No derived graph"},{"n":4,"title":"The mapping code is deleted; ADR-0226 §1 is not shipped"},{"n":5,"title":"Element ids: decode-only"},{"n":6,"title":"`apply` is unchanged"}],"stale_clauses":[]},{"id":"ADR-0142","title":"Browser/Desktop-compat record shapes for dbms.components, SHOW DATABASES, and dbms.info","standing":"partial","declared_status":"accepted","path":"docs/adr/0142-browser-compat-record-shapes.md","gist":"1. dbms.components returns three rows, in this order: | # | name | versions | edition | |---|---|---|---| | 1 | Neo4j Kernel | [<workspace version, e.g. '0.9.1'>] | community | | 2 | Cypher | ['5', '25'] | community | | 3 | CypherLite | [<workspace version>] | community | Row 1 carries both reader…","why":["matches task (clause+fulltext+vector)"],"live_clauses":[{"n":1,"title":"`dbms.components` returns three rows, in this order:"},{"n":2,"title":"SHOW DATABASES rows carry concrete values"},{"n":3,"title":"`dbms.info()` returns one row"}],"stale_clauses":[{"n":null,"title":"(part not itemised)","by":["ADR-0152"],"note":"a part is superseded by ADR-0152"}],"evidence":[{"by":"ADR-0152","treatment":"SUPERSEDES","clauses":[],"quote":"Later References: ADR-0152 supersedes row 1's `versions` value: the 'Neo4j Kernel' row now reports a calver string with a `-cypherlite` product suffix (`2026.10-cypherlite`, following Aura's `5.27-aura` convention) so browser.neo4j.io's throwing `>= 4.4.0` sdk gate passes."}]},{"id":"ADR-0152","title":"Neo4j Kernel version string reported by dbms.components","standing":"in_force","declared_status":"accepted","path":"docs/adr/0152-neo4j-kernel-version-reporting-policy.md","gist":"dbms.components reports the 'Neo4j Kernel' row (ADR-0142 row 1) with versions[0] = 2026.10-cypherlite — the current Neo4j calver month plus the -cypherlite product suffix, the same two-part-plus-suffix shape as Aura's 5.27-aura. - The string is a policy constant, not derived from the workspace…","why":["controls ADR-0142 (a part)"],"live_clauses":[],"stale_clauses":[]},{"id":"ADR-0116","title":"Fixed namespaces with Neo4j Community Edition database semantics","standing":"partial","declared_status":"accepted","path":"docs/adr/0116-fixed-namespaces-community-edition-semantics.md","gist":"1. Three fixed namespaces. Every store has exactly these. None can be created, dropped or renamed, and names match case-insensitively. | Namespace | SHOW type / access | Behaviour | |---|---|---| | neo4j | standard / read-write; default and home | The user data graph. Existing stores are this…","why":["matches task (clause+fulltext+vector)"],"live_clauses":[{"n":2,"title":"Administration commands follow CE"},{"n":3,"title":"`USE` routes a statement"},{"n":6,"title":"SHOW output is real"}],"stale_clauses":[{"n":1,"title":"Three fixed namespaces","by":["ADR-0229"],"note":"§1 'Three fixed namespaces' superseded by ADR-0229"},{"n":4,"title":"Namespace rules","by":["ADR-0229"],"note":"§4 'Namespace rules' superseded by ADR-0229"},{"n":5,"title":"Transactions read any namespace and write only `neo4j`","by":["ADR-0229"],"note":"§5 'Transactions read any namespace and write only `neo4j`' superseded by ADR-0229"},{"n":7,"title":"Element ids name their namespace","by":["ADR-0229"],"note":"§7 'Element ids name their namespace' superseded by ADR-0229"},{"n":8,"title":"Settings stay in the existing catalog","by":["ADR-0276"],"note":"§8 'Settings stay in the existing catalog' superseded by ADR-0276"},{"n":9,"title":"Errors","by":["ADR-0307"],"note":"§9 'Errors' superseded by ADR-0307"},{"n":10,"title":"Engine shape","by":["ADR-0229"],"note":"§10 'Engine shape' superseded by ADR-0229"}],"evidence":[{"by":"ADR-0229","treatment":"SUPERSEDES","clauses":[1,4,5,7,10],"quote":"ADR-0229 makes `system_ontologies` listed but not queryable: §1's \"Readable with ordinary Cypher\" and §4's 42N18 write gate are superseded — every statement routed there except §2's administration commands now fails with 42N17 (ADR-0229 §2's text), reads included; §5's capture captures a permanently empty graph; §7's `cypherlite.system_ontologies` segment is decode-only (no id…"},{"by":"ADR-0276","treatment":"SUPERSEDES","clauses":[8],"quote":"ADR-0116 §8's placement sentence (\"stays in `TheaterData.databases`\") is superseded by this ADR; its format and invariant statements stand."}]}],"warnings":["ADR-0142 is partly superseded: a part is superseded by ADR-0152","ADR-0116 is partly superseded: §1 'Three fixed namespaces' superseded by ADR-0229"],"omitted":12,"tokens":1447,"how_to_read":"live_clauses are good law; stale_clauses were taken out of force by the decision named in `by` - follow that decision instead."}

==================== TASK T04 ====================
Task: Change the CLI install script that is served from the website: where it is hosted, which platforms it supports and how it is invoked.

Context retrieved for this task: the decision records of the repository, as written.

--- ADR-0068 ---
# 0068. CLI install script distributed as a GitHub Pages static asset

- **Status**: Accepted
- **Date**: 2026-09-19
- **Deciders**: CypherLite maintainers (Linear LABS-25)

## Decision
Distribute the CLI install script as a static file on the existing GitHub Pages
docs site, using the release binaries ADR-0067 already defines.

1. **URL.** The canonical installer URL is
   `https://neo4j-labs.github.io/cypherlite/install.sh`. It is **not**
   `https://cypherlite.github.io/install.sh`: no `cypherlite` GitHub
   organization exists, and project Pages sites are served from
   `<org>.github.io/<repo>`.
2. **Hosting.** The script lives at `docs/static/install.sh`. The Docusaurus
   build copies everything under `docs/static/` to the site root, so the
   existing `gh-pages` deploy publishes it at the URL above. No new CI
   workflow is added and the GitHub Pages source setting is unchanged.
3. **Platforms.** macOS and Linux only, on both `amd64` and `arm64`
   (`cypherlite-linux-amd64`, `cypherlite-linux-arm64`,
   `cypherlite-darwin-amd64`, `cypherlite-darwin-arm64`). Windows stays on the
   manual `.exe` download documented in the README.
4. **Install directory.** The script installs to `$HOME/.local/bin`. It does
   not require `sudo` and does not write outside the user’s home directory.
5. **Assets.** The installer downloads the raw release binary for the detected
   platform directly. Assets are named `cypherlite-<os>-<arch>` (no tarballs)
   and are verified against the release’s `SHA256SUMS`, which is in macOS
   `shasum` format (`<hex>  <name>`, two spaces). This is the existing release
   contract; the installer changes nothing in `release.yml`.
6. **Authentication.** While the repository is internal, all GitHub API and
   release-asset requests carry `Authorization: Bearer $GITHUB_TOKEN`. When
   `GITHUB_TOKEN` is unset the script is a no-op auth-wise, so it works
   unchanged once the repository is public and the token is unnecessary.
7. **Invocation.** The documented one-liner is:
   ```
   curl -sSfL https://neo4j-labs.github.io/cypherlite/install.sh | GITHUB_TOKEN=$(gh auth token) bash
   ```
   The environment prefix **must** be on `bash`, not on `curl`. An environment
   prefix on the left of a pipe applies only to that command and never reaches
   the script on the right-hand side through the pipe; attaching it to `bash`
   is what makes `$GITHUB_TOKEN` visible to the installer.

Implementation of `docs/static/install.sh`, the README install section, and the
`gh auth token` guidance is owned by separate changes; this ADR only fixes the
distribution decision.

--- ADR-0459 ---
# ADR-0459: The authenticated WebSocket Origin default is loopback plus the hosted Neo4j web apps

Status: Proposed

Claim: a6a26180966760d49666b6a6b30fbc4097c7fbda

## Decision
### 1. The auth-on default: loopback plus the hosted Browser and Console

An empty `--ws-allow-origin` list resolves to loopback Origins (any port)
**plus** the hosted Neo4j web applications, with auth on:

- `https://browser.neo4j.io` — the Neo4j Browser web application.
- `https://console.neo4j.io` — the Neo4j (Aura) Console.

This is the same hosted set the HTTP surface's `OriginAllowlist::Default`
already allows, and the list now lives once in
`cypherlite_serve::origin::HOSTED_WEB_APP_ORIGINS`, consulted by both
surfaces so they cannot drift. Matching is canonical-to-canonical, the
same exact comparison `--ws-allow-origin` entries use. The loopback arm
is unchanged: host-based, any port, the serialized-spelling
classification ADR-0266 states. A missing `Origin` header remains a
non-browser client and is allowed.

Any other Origin needs an explicit `--ws-allow-origin` entry; `*` remains
the explicit any-Origin opt-in. `--auth none` keeps its loopback-only
default unchanged (the CSWSH guard).

Accepted tradeoff: a compromised *local* application on another localhost
port still passes the loopback arm. Local compromise is game over by
definition — the same reasoning ADR-0266's loopback arm already records.

`https://browser.graphapp.io` is **not** in the default set. The repo's
HTTP default does not include it, the Neo4j Browser manual documents
`browser.neo4j.io` as the hosted Browser, and the graph-app host is a
separate deployment; an operator using it passes `--ws-allow-origin`
(today's e2e WebSocket test already does). Extending the default set is
one entry in `HOSTED_WEB_APP_ORIGINS`.

### 2. The wider-origin opt-in is reachable from the product binary

`cypherlite serve` gains the repeatable `--ws-allow-origin ORIGIN` flag
(the crate-level `Args` already had it). Without it, the tightened
default would leave a deployment that serves a self-hosted Browser from a
non-loopback origin with no product-binary remedy, which is not a
compatibility break an operator can act on. The flag parses through the
shared origin grammar (`cypherlite_serve::origin::OriginFlagValue`), is
stored canonically, and an explicit list replaces the auth-dependent
default's wider reach exactly as the library flag does.

`--no-websocket` stays library-level only (ADR-0368 records that split);
this ADR does not widen that surface set further.

### 3. An opt-in WebSocket session cap, default off

`--ws-max-connections N` (crate `Args` and `cypherlite serve`) /
`CYPHERLITE_WS_MAX_CONNECTIONS` bounds concurrent WebSocket sessions,
resolved flag → environment → unlimited (`0`). It reuses the shared
`cypherlite_serve::ConnectionCap`: the permit is taken when a connection
classifies as a WebSocket upgrade, before the upgrade read, held for the
whole session, and an over-cap connection is accepted then closed with no
HTTP response and the log line
`bolt: --ws-max-connections <N> reached; closing connection` — the same
accept-then-close policy the process cap applies.

The default is **off**, deliberately. The process-wide
`--max-connections` cap is unchanged and still bounds every accepted
connection, so `cypherlite serve` deployments are not exposed by this
default; the knob exists for an operator who raised the process cap for
bulk raw-Bolt transfer and wants browser sessions bounded separately, or
who runs the crate-level listener. A non-zero WebSocket default would
refuse the bulk-transfer workload the maintainer confirmed as the intent
behind the currently unbou

--- ADR-0288 ---
# 0288. The cookbook navigation links the repository while it is internal

- **Status**: Accepted
- **Renumbered**: from 0177 (shared-number cleanup)
- **Date**: 2026-10-07
- **Deciders**: CypherLite maintainers (decided in conversation)

## Decision
1. The cookbook navigation always links the repository (`--repo-url`) as
   `GitHub`, as the landing page does, whether or not `lychee.toml` excludes
   it. The navigation then matches across the site.
2. This is the only exception to ADR-0133. The footer's GitHub link, the
   "built from <ref>" and "Write a recipe" links, the index page's README
   and source links, prose links into the repository, and `companion` links
   still follow the list.
3. The build's link check (`checkLinks` in `scripts/cookbook/lib/links.mjs`)
   takes the URLs that may be linked anyway (`exempt`); the build passes
   exactly the repository URL. A link to any other not-yet-public URL,
   including any path under the repository, still fails the build.

--- ADR-0156 ---
# 0156. Clone a native directory without writing it

- **Status**: Proposed
- **Date**: 2026-10-02
- **Deciders**: CypherLite maintainers

## Decision
1. **`Database::clone_directory` copies a native directory.** The CLI
   command is `cypherlite clone [--wal-dir DIR] SOURCE DEST` (ADR-0069:
   an exit-after verb is a positional command, not a flag). `:memory:`
   and `.cl` are refused before any lock is taken, for both the source
   and the destination. The source is always a frozen read-only open,
   never a follower. `CloneOptions` is `wal_dir` only, and it applies
   only to that source open. The destination is written in the codec
   that open observed. Clone does not take a codec.
2. **The cut is the LSN visible when the read-only load finishes.** The
   clone does not tail later commits. The source is not appended,
   checkpointed, migrated, trimmed, or recycled.
3. **The destination is a new store.** It must not already exist and must
   not be the source directory. The clone publishes `checkpoint_at` into
   that directory at the loaded LSN and `commit_ts`, using the source
   codec, then creates an empty WAL segment there so a later read-only
   open succeeds. The next commit on the clone is `lsn + 1`. The
   destination WAL is always `<dest>/wal`, even when the source WAL is
   external.
4. **A failed clone removes the destination it created**, while it still
   holds the destination writer lease. A failure before the destination
   exists leaves nothing behind.

--- ADR-0262 ---
# 0262. Skill install adopts a recognizable cypherlite bundle

- **Status**: Accepted
- **Renumbered**: from 0111 (shared-number cleanup)
- **Date**: 2026-09-26
- **Deciders**: CypherLite maintainers (Linear LABS-124)

## Decision
**`skill install`'s replace check adopts a recognizable cypherlite bundle.** A
destination is replaceable without `--force` when it is any of:

1. **missing** — the destination does not exist (`NotFound`), so it is safe to
   create fresh. An unreadable or otherwise-uninspectable destination is
   **not** missing: any metadata error other than `NotFound` is refused without
   `--force` (fail closed, matching ADR-0261's `Foreign` classification);
2. **marker-owned** — it carries `.cypherlite-installed` as a real regular
   file (symlinks not followed), the existing ownership proof; or
3. **a recognizable cypherlite bundle** — no marker, but `<dir>/SKILL.md`
   exists and its YAML frontmatter declares `name: cypherlite` **and**
   contains a `version:` line. The version value may be a concrete version or
   the literal `{{VERSION}}` placeholder; either counts as a machine-written
   cypherlite bundle.

`--force` keeps its existing meaning: the user explicitly requested a clobber,
so it replaces any destination without further checks. A missing directory and
a plain `--force` are still allowed through exactly as before.

**`skill remove` keeps the strict marker refusal.** Removal has no
replacement bundle to fall back on, so accepting a recognizable-but-unmarked
directory would delete a directory that might be user-authored with no way to
recover it. Only a marker-owned directory (or `--force`) is removable.

**The upgrade refresh stops passing `--force`.** With the install-side check
now recognizing Legacy bundles, the refresh no longer needs to force: it
spawns `cypherlite skill install` for the recognized targets without `--force`,
and the child re-derives "this is ours" immediately before it deletes and
recreates the directory. That is the TOCTOU fix — the decision and the write
now happen in the same process, at the same instant.

**One shared recognizer lives in `crate::skill`.** The recognizable-bundle
predicate (`name: cypherlite` plus a `version:` line, read from `SKILL.md`
frontmatter) moves to `surfaces/cypherlite-cli/src/skill/` as a single shared
function. Both `skill_cmd`'s install-side replace check and `upgrade_cmd`'s
classifier call it, so the two call sites cannot drift. ADR-0261 already made
the marker rules shared, load-bearing policy; this decision extends the same
rule to the bundle recognizer.

Recognizing a bundle is **identification**, not a staleness gate: an install
always replaces the destination it recognized. `skill install` is invoked
either directly by a user or by the refresh after a successful binary
self-replace, and in both cases the incoming bundle is the one that should win.

Precedent `preflight` for this task (a tool that tracks which decisions are still in force):
{"task":"Change the CLI install script that is served from the website: where it is hosted, which platforms it supports and how it is invoked.","paths":[],"decisions":[{"id":"ADR-0546","title":"Release discovery files ship as release assets; the website pulls","standing":"in_force","declared_status":"proposed","path":"docs/adr/0546-release-discovery-via-relate-web.md","gist":"This repository never pushes content into relate-web. The release pipelines attach the pipeline-owned files to the release they belong to — releases.json and install.sh on every core release, the signed extensions.json pair on every extension release — and then fire one repository_dispatch at…","why":["matches task (fulltext+vector)","controls ADR-0250 (a part)","controls ADR-0330 (a part)"],"live_clauses":[],"stale_clauses":[]},{"id":"ADR-0358","title":"Probe-then-fallback upgrade download route for the internal repository","standing":"in_force","declared_status":"accepted","path":"docs/adr/0358-upgrade-download-route.md","gist":"upgrade keeps the direct browser download route as its first and preferred route and falls back to the authenticated GitHub API asset route only when the direct route answers 404. The route policy: 1. The direct route is tried first. upgrade fetches SHA256SUMS from…","why":["matches task (clause+vector)","controls ADR-0250 (§3–5)"],"live_clauses":[{"n":1,"title":"The direct route is tried first"},{"n":2,"title":"A 2xx probe serves the whole upgrade"},{"n":3,"title":"A 404 on the probe, with GITHUB_TOKEN set, falls back"},{"n":4,"title":"A 404 on the probe without a token aborts"},{"n":5,"title":"Any other probe failure aborts exactly as today — no fallback"},{"n":6,"title":"The `Authorization` header is sent only on `api.github.com` requests"},{"n":7,"title":"The ADR-0115 verification chain is unchanged"},{"n":8,"title":"Two base-URL test seams join the existing `CYPHERLITE_RELEASES_JSON_URL`"}],"stale_clauses":[]},{"id":"ADR-0068","title":"CLI install script distributed as a GitHub Pages static asset","standing":"partial","declared_status":"accepted","path":"docs/adr/0068-cli-install-script-via-github-pages.md","gist":"Distribute the CLI install script as a static file on the existing GitHub Pages docs site, using the release binaries ADR-0067 already defines. 1. URL. The canonical installer URL is https://neo4j-labs.github.io/cypherlite/install.sh. It is not https://cypherlite.github.io/install.sh: no cypherlite…","why":["matches task (clause+fulltext+vector)"],"live_clauses":[{"n":1,"title":"URL"},{"n":2,"title":"Hosting"},{"n":3,"title":"Platforms"},{"n":4,"title":"Install directory"},{"n":5,"title":"Assets"}],"stale_clauses":[{"n":6,"title":"Authentication","by":["ADR-0585"],"note":"§6 'Authentication' superseded by ADR-0585"},{"n":7,"title":"Invocation","by":["ADR-0585"],"note":"§7 'Invocation' superseded by ADR-0585"}],"evidence":[{"by":"ADR-0585","treatment":"SUPERSEDES","clauses":[6,7],"quote":"ADR-0585 supersedes §6's authentication model for the installer: the repository is public, `install.sh` downloads every asset from the direct release route unauthenticated, reads no `GITHUB_TOKEN`, and consults no GitHub API endpoint; §7's token-prefixed invocation is historical."},{"by":"ADR-0585","treatment":"SUPERSEDES","clauses":[6],"quote":"ADR-0068 §6's authentication model is superseded for the installer, ADR-0571's reserved future decision is taken, and ADR-0358's \"always the API asset route\" characterization of `install.sh` becomes history — Later references notes on all three."}]},{"id":"ADR-0585","title":"The installer downloads release assets over the direct route","standing":"in_force","declared_status":"proposed","path":"docs/adr/0585-installer-downloads-via-direct-route.md","gist":"install.sh consults no GitHub API endpoint. Every asset — the SHA256SUMS manifest, its SHA256SUMS.sig signature, and the platform binary — is downloaded from https://github.com/<repo>/releases/download/<tag>/<asset>, the direct browser route upgrade probes (ADR-0358 §1), unauthenticated. 1. One…","why":["controls ADR-0068 (§6–7)"],"live_clauses":[{"n":1,"title":"One transport"},{"n":2,"title":"No token"},{"n":3,"title":"One seam"},{"n":4,"title":"The integrity chain is unchanged"}],"stale_clauses":[]},{"id":"ADR-0250","title":"Release discovery from a static releases.json on the website","standing":"partial","declared_status":"accepted","path":"docs/adr/0250-releases-json-update-discovery.md","gist":"Publish releases.json at the website root and make upgrade/update read it. The GitHub REST API leaves the update path entirely — no fallback, not even when GITHUB_TOKEN is set. ### 1. Canonical URL and hosting - The canonical URL is https://neo4j-labs.github.io/cypherlite/releases.json. - The file…","why":["matches task (clause+fulltext+vector)"],"live_clauses":[{"n":1,"title":"Canonical URL and hosting"},{"n":2,"title":"Schema (schema_version 1)"},{"n":6,"title":"Publisher contract"}],"stale_clauses":[{"n":3,"title":"Asset download URL template","by":["ADR-0358"],"note":"§3 'Asset download URL template' superseded by ADR-0358"},{"n":4,"title":"Failure behavior","by":["ADR-0358"],"note":"§4 'Failure behavior' superseded by ADR-0358"},{"n":5,"title":"GITHUB_TOKEN","by":["ADR-0358"],"note":"§5 'GITHUB_TOKEN' superseded by ADR-0358"}],"evidence":[{"by":"ADR-0358","treatment":"SUPERSEDES","clauses":[3,4,5],"quote":"ADR-0358 supersedes §3 (the download URL template as the only route), §4's no-API-fallback rule (\"not even when `GITHUB_TOKEN` is set\") and §5's token claim (that the optional bearer header makes the direct route work while the repository is internal)."},{"by":"ADR-0546","treatment":"SUPERSEDES","clauses":[],"quote":"ADR-0250's schema and canonical URLs are unchanged; its gh-pages publisher contract is superseded by this one."}]}],"warnings":["ADR-0068 is partly superseded: §6 'Authentication' superseded by ADR-0585","ADR-0250 is partly superseded: §3 'Asset download URL template' superseded by ADR-0358"],"omitted":8,"tokens":1478,"how_to_read":"live_clauses are good law; stale_clauses were taken out of force by the decision named in `by` - follow that decision instead."}

==================== TASK T24 ====================
Task: Tighten how Cypher 25 CREATE/INSERT validates references to entities created in the same clause.

Context retrieved for this task: the decision records of the repository, as written.

--- ADR-0513 ---
# ADR-0513: Cypher 25 CREATE/INSERT entity-reference admission, and the TCK setup re-pin it forces

Status: Proposed
Claim: 37bb8f9563e4f754cb82c5a35ed253dd02a0aa4c

## Decision
1. **Reject every read of a same-clause-created entity.** The
   self-reference rule covers plain property reads, function arguments,
   list/map-comprehension bodies, map-projection variable selectors and
   subquery/pattern expressions, in `CREATE` and `INSERT`, for every
   element of the clause (not only the ones already enforced). A
   comprehension-style binder shadows the name it introduces, so
   `CREATE (n {prop: true IN [n IN [false] | n]})` stays legal — the
   "may reference an entity from an earlier clause" family pins it. A name
   bound *before* the clause, or created by an *earlier* clause, is an
   existing entity and stays readable (`CREATE (a {prop: 7}) CREATE (b
   {prop: a.prop})`). The rule remains Cypher-25-only; an explicit
   `CYPHER 5` preamble keeps the 01N00 warning semantics.
2. **A null (or otherwise non-node) binding in a CREATE/MERGE node
   position is 22N01.** It is neither a fresh node (today) nor a lenient
   no-op: the statement fails with Neo4j's message and `TypeError` class.
   This is the write-side companion of ADR-0498's MATCH ruling (a
   null-bound pattern endpoint matches nothing when *reading*; a write
   cannot manufacture the entity the row did not bind).
3. **Re-pin the three openCypher 2024.3 TCK setup queries** that use the
   now-rejected shape. Each is a `having executed:` fixture whose scenario
   asserts WITH/SKIP/LIMIT or join semantics, never the create-dependency
   form; splitting the single multi-pattern CREATE into one CREATE clause
   per pattern produces the identical fixture graph. The scenarios stay in
   the pin, allowlisted and passing — the 2024.3 corpus is not a Cypher 25
   corpus and this is the smallest local deviation that keeps its intent
   (the ADR-0188 / ADR-0472 precedent, under ADR-0002's authority
   ordering: a live-verified current-Neo4j behaviour outranks the 2024.3
   floor).

--- ADR-0584 ---
# ADR-0584: One Cypher version — CYPHER 25 only, the preamble a no-op

Status: Proposed
Claim: fe268ee9f3a090fc75922f6bdad84bb1ff5eb4b7

## Decision
1. **One Cypher version: 25.** The `CYPHER 25` statement preamble is an
   accepted no-op — it parses and changes nothing; an unprefixed
   statement already speaks Cypher 25.
2. **Every other `CYPHER <n>` integer fails with one authored
   unsupported-version error**, `CYPHER 5` included. Settled text, `<n>`
   the requested integer:
   `UnsupportedCypherVersion: CYPHER <n> is not supported; the only supported Cypher version is CYPHER 25`
   The preamble fails it at parse, the language value at command
   execution — where each is checked today.
3. **`ALTER DATABASE … SET DEFAULT LANGUAGE` admits only `CYPHER 25`**
   (ADR-0116 §2, narrowed). The stored value stays display-only catalog
   state (§8 unchanged); no store format changes and a value an older
   binary wrote is not rewritten.
4. **The version machinery is removed as unreachable.** The dialect fact,
   the gate allowlist, the create-self-reference stand-down (ADR-0513
   Decision 1's arm), the SHOW-family version branches and the version
   threading through the AST, lowering, IR, plan and query context exist
   to tell 5 from 25; with 25 the only admitted version none can fire.

--- ADR-0520 ---
# ADR-0520: The spec harness owns the Cypher language corpora; the in-repo TCK gate retires

Status: Proposed

Claim: c1cd635a933fe5179538651e44871b47ce9850a3

## Decision
1. **The corpora live in the harness.** `features/relate-tck/` and
   `features/cip-eval/` are harness-owned suites. New TCK extension
   scenarios and new CIP-derived scenarios are added there, not in this
   repository.

2. **The in-repo harness retires.** `testing/relate-tck` and
   `testing/relate-cip-eval` leave the workspace with the vendored corpora
   they ran, their 3892-id allowlist, the shrink-only skip list, the
   cucumber-expanded denominator, the `TCK_ONLY` / `TCK_DUMP_PASSING`
   knobs, `baselines/cip-eval.json`, and the `make test-tck` /
   `make cip-eval` entry points and CI steps.

3. **The 3892-of-3892 pinned-2024.3 claim is retired.** No engine document
   publishes a current TCK pass count or a "TCK compliant" claim any more. The
   language floor is still the openCypher TCK (ADR-0056), measured by the
   harness's `tck` suite — the upstream suite synced from Neo4j's
   compatibility-spec-suite — so the measured corpus is the current
   upstream TCK, not a vendored 2024.3 snapshot. An engine/TCK divergence
   is a harness report line, never an in-repo allowlist or re-pin edit.

4. **Reporting-only, and no relocated ratchet.** The two suites join the
   ADR-0482 §4 posture unchanged: the lane reports coverage with the fixed
   traffic-light bands and exits 0 in every band. No `baselines/*.json`,
   re-freeze workflow, skip list or threshold gate moves to the harness
   with them (user decision, 2026-11-05).

5. **The landing run's report is the record.** The transfer run (engine
   `f26e1c4d0`, `relate-db 0.16.1` wheel) reports:

   | Suite | Scenarios | Passed | Failed | Skipped | Expected-fail | Left failing |
   | --- | --- | --- | --- | --- | --- | --- |
   | `relate-tck` | 489 | 448 | 0 | 0 | 41 | 0 |
   | `cip-eval` | 5917 | 4942 | 924 | 51 | 0 | 924 |

   - `relate-tck` is the engine-green corpus (489/489 in the retired
     runner). Its 41 expected fails are harness-side contract gaps, marked
     per outline row in `features/expected_fail_list.txt`: 36 where the
     corpus labels Neo4j's error class (`ArgumentError`, `SyntaxError`)
     while the Python binding exposes only the coarse TCK class
     (`TypeError`) and carries the cause in the message — the retired Rust
     runner matched the labelled detail first — and 5 where a Gherkin `\n`
     cell escape cannot survive behave's substitution.
   - `cip-eval` is the stretch tracker; its failures are untagged and left
     failing on purpose. The retired suite was deliberately lenient (any
     error satisfied a `should be raised` step, unknown steps were
     skipped); the harness enforces the shared TCK grammar, so the same
     5917 scenarios report 924 left failing, classified by the report's
     failure categories (511 `setup-failed-syntax`, 256
     `error-class-mismatch`, 49 `side-effects`, 41 `result-vector`, 35
     `result-temporal-fidelity`, and smaller buckets). The 51 skips are
     the existing admin/RBAC policy: the embedded engine does not execute
     `SHOW USERS/ROLES/TRANSACTIONS` or `CREATE/DROP DATABASE`.
   - The same landing run reports the harness's synced `tck` suite at 6833
     passed / 25 failed / 7 Neo4j-expected-fail / 87 skipped: that is the
     openCypher TCK measurement that replaces the retired pin.

6. **Documentation records the retirement.** `docs/tck/compliance.md`
   becomes a pointer at the harness with the retired pin kept as clearly
   marked history; `AGENTS.md` names the spec harness as the
   language-contrac

--- ADR-0578 ---
# ADR-0578: Fulltext fuzzy terms and clause boost

Status: Proposed
Claim: 723bf0a96ab22e3bede3571861cb6f973ab137c8

## Decision
1. **Syntax.** `term~`, `term~N`, `term^B` and `field:term~N^B` are parsed
   into typed clause fields (an optional edit bound, a boost defaulting to
   1). A bare `~` is 2 edits; an integer above 2 clamps to 2; `~x` with
   `0 <= x < 1` is a minimum similarity, an edit bound of `floor((1 - x) *
   term length)` capped at 2 (`~0` is exact). A non-integer of 1 or more
   (`~1.5`) is a syntax error. Text after a `~` that is not a `^` boost is
   a separate word (`term~1x` is a bare `~` plus the term `1x`), and a
   detached `~1` or `^2` binds to the previous word, as Lucene's lexer
   reads them. A boost is an unsigned number: `^0` is legal (the clause
   still matches, scoring 0); `^`, `^x` and `^-1` are syntax errors. The
   suffix never leaks digits as terms.
2. **Expansion.** A fuzzy clause expands, per field, against that field's
   vocabulary (the document-frequency table already built per scan) by a
   bounded Damerau-Levenshtein distance (optimal string alignment: insert,
   delete, substitute, adjacent transposition each cost one; early exit
   past the bound). Lucene defaults apply: no pinned prefix, at most 50
   expansions, ordered closest, then most frequent, then lexicographic so
   results are deterministic. The expansions form an any-of group, so
   `AND`/`OR`/`NOT`/required semantics are unchanged.
3. **Scoring.** Each expanded term scores with the existing calibrated
   BM25, multiplied by a closeness weight of `1 - edits / min(query length,
   term length)`; exact terms weigh 1. A candidate whose weight would be
   zero is not a match. The clause's boost multiplies its score last;
   boost never changes which rows match.
4. **Reuse.** The distance routine is a small crate-private module so a
   future Cypher string-similarity function can share it.
5. **Calibration.** The suffix grammar, clamping, the closeness weight
   (0.875 at one edit and 0.75 at two on an eight-character term, scores
   exactly weight times BM25), exact boost scaling and the AND/NOT
   behaviour were confirmed on Neo4j 2026.09-enterprise. Not modelled:
   Lucene's document-frequency blending across expansions, and a fuzzy
   word that analyzes to several tokens applies the suffix to each token.

--- ADR-0337 ---
# ADR-0337: CREATE CONSTRAINT OPTIONS lowering and eval errors propagate

Status: Proposed
Claim: e9fa7c0d09c8d2ea73586864e1b74293836f8c31

## Decision
`catalog_create_constraint` propagates the lowering and eval errors with
`?` and validates only the resulting shape: a key other than
`indexConfig`, a non-map value, or a non-empty map is the existing
`InvalidOptionsMap` semantic error; an absent parameter surfaces the typed
`ParameterMissing` (ADR-0308), and an eval failure surfaces its own error.
The constraint is not created on any failure.

Precedent `preflight` for this task (a tool that tracks which decisions are still in force):
{"task":"Tighten how Cypher 25 CREATE/INSERT validates references to entities created in the same clause.","paths":[],"decisions":[{"id":"ADR-0584","title":"One Cypher version — CYPHER 25 only, the preamble a no-op","standing":"in_force","declared_status":"proposed","path":"docs/adr/0584-one-cypher-version-cypher25-noop.md","gist":"1. One Cypher version: 25. The CYPHER 25 statement preamble is an accepted no-op — it parses and changes nothing; an unprefixed statement already speaks Cypher 25. 2. Every other CYPHER <n> integer fails with one authored unsupported-version error, CYPHER 5 included. Settled text, <n> the requested…","why":["matches task (clause+fulltext+vector)","controls ADR-0513 (§1)"],"live_clauses":[{"n":1,"title":"One Cypher version: 25"},{"n":2,"title":"Every other CYPHER <n> integer fails with one authored"},{"n":3,"title":"`ALTER DATABASE … SET DEFAULT LANGUAGE` admits only `CYPHER 25`"},{"n":4,"title":"The version machinery is removed as unreachable"}],"stale_clauses":[]},{"id":"ADR-0513","title":"Cypher 25 CREATE/INSERT entity-reference admission, and the TCK setup re-pin it forces","standing":"partial","declared_status":"proposed","path":"docs/adr/0513-cypher25-create-entity-reference-admission.md","gist":"1. Reject every read of a same-clause-created entity. The self-reference rule covers plain property reads, function arguments, list/map-comprehension bodies, map-projection variable selectors and subquery/pattern expressions, in CREATE and INSERT, for every element of the clause (not only the ones…","why":["matches task (clause+fulltext+vector)"],"live_clauses":[{"n":2,"title":"A null (or otherwise non-node) binding in a CREATE/MERGE node"},{"n":3,"title":"Re-pin the three openCypher 2024.3 TCK setup queries"}],"stale_clauses":[{"n":1,"title":"Reject every read of a same-clause-created entity","by":["ADR-0584"],"note":"§1 'Reject every read of a same-clause-created entity' superseded by ADR-0584"}],"evidence":[{"by":"ADR-0584","treatment":"WITHDRAWS","clauses":[1],"quote":"ADR-0584 removes Decision 1's CYPHER-5 arm — \"The rule remains Cypher-25-only; an explicit `CYPHER 5` preamble keeps the 01N00 warning semantics.\" With CYPHER 25 the only admitted version, a preamble can no longer select Cypher 5, the stand-down is unreachable, and the create-self-reference rule applies to every statement."}]},{"id":"ADR-0116","title":"Fixed namespaces with Neo4j Community Edition database semantics","standing":"partial","declared_status":"accepted","path":"docs/adr/0116-fixed-namespaces-community-edition-semantics.md","gist":"1. Three fixed namespaces. Every store has exactly these. None can be created, dropped or renamed, and names match case-insensitively. | Namespace | SHOW type / access | Behaviour | |---|---|---| | neo4j | standard / read-write; default and home | The user data graph. Existing stores are this…","why":["matches task (clause+fulltext+vector)"],"live_clauses":[{"n":2,"title":"Administration commands follow CE"},{"n":3,"title":"`USE` routes a statement"},{"n":6,"title":"SHOW output is real"}],"stale_clauses":[{"n":1,"title":"Three fixed namespaces","by":["ADR-0229"],"note":"§1 'Three fixed namespaces' superseded by ADR-0229"},{"n":4,"title":"Namespace rules","by":["ADR-0229"],"note":"§4 'Namespace rules' superseded by ADR-0229"},{"n":5,"title":"Transactions read any namespace and write only `neo4j`","by":["ADR-0229"],"note":"§5 'Transactions read any namespace and write only `neo4j`' superseded by ADR-0229"},{"n":7,"title":"Element ids name their namespace","by":["ADR-0229"],"note":"§7 'Element ids name their namespace' superseded by ADR-0229"},{"n":8,"title":"Settings stay in the existing catalog","by":["ADR-0276"],"note":"§8 'Settings stay in the existing catalog' superseded by ADR-0276"},{"n":9,"title":"Errors","by":["ADR-0307"],"note":"§9 'Errors' superseded by ADR-0307"},{"n":10,"title":"Engine shape","by":["ADR-0229"],"note":"§10 'Engine shape' superseded by ADR-0229"}],"evidence":[{"by":"ADR-0229","treatment":"SUPERSEDES","clauses":[1,4,5,7,10],"quote":"ADR-0229 makes `system_ontologies` listed but not queryable: §1's \"Readable with ordinary Cypher\" and §4's 42N18 write gate are superseded — every statement routed there except §2's administration commands now fails with 42N17 (ADR-0229 §2's text), reads included; §5's capture captures a permanently empty graph; §7's `cypherlite.system_ontologies` segment is decode-only (no id…"},{"by":"ADR-0276","treatment":"SUPERSEDES","clauses":[8],"quote":"ADR-0116 §8's placement sentence (\"stays in `TheaterData.databases`\") is superseded by this ADR; its format and invariant statements stand."}]},{"id":"ADR-0229","title":"Remove the `system_ontologies` Cypher surface","standing":"in_force","declared_status":"accepted","path":"docs/adr/0229-remove-system-ontologies-cypher-surface.md","gist":"1. Listed, not queryable. system_ontologies stays a fixed, listed namespace. SHOW DATABASES keeps its row with ADR-0116 §6's values verbatim (type standard, access read-only, currentStatus and requestedStatus online, default and home false, empty aliases and constituents, the stored…","why":["controls ADR-0116 (§1, §4–5, §7, §10)"],"live_clauses":[{"n":1,"title":"Listed, not queryable"},{"n":2,"title":"The error"},{"n":3,"title":"No derived graph"},{"n":4,"title":"The mapping code is deleted; ADR-0226 §1 is not shipped"},{"n":5,"title":"Element ids: decode-only"},{"n":6,"title":"`apply` is unchanged"}],"stale_clauses":[]},{"id":"ADR-0276","title":"Store-level databases catalog","standing":"in_force","declared_status":"accepted","path":"docs/adr/0276-store-level-databases-catalog.md","gist":"The databases catalog is store-level: one table shared by every namespace graph of a store. - A crate-internal DatabasesCatalog (Arc-shared through StoreServices, like the procedure registry and CSV policy of ADR-0116 §10) holds the name → (defaultLanguage, composite) table. It seeds exactly the…","why":["controls ADR-0116 (§8)"],"live_clauses":[],"stale_clauses":[]}],"warnings":["ADR-0513 is partly superseded: §1 'Reject every read of a same-clause-created entity' superseded by ADR-0584","ADR-0116 is partly superseded: §1 'Three fixed namespaces' superseded by ADR-0229"],"omitted":13,"tokens":1535,"how_to_read":"live_clauses are good law; stale_clauses were taken out of force by the decision named in `by` - follow that decision instead."}

==================== TASK T06 ====================
Task: Add a new anonymous usage event to the CLI's metrics and decide how events are delivered.

Context retrieved for this task: the decision records of the repository, as written.

--- ADR-0079 ---
# 0079. Anonymous usage metrics in the CLI

- **Status**: Proposed
- **Date**: 2026-09-21
- **Deciders**: CypherLite maintainers (Linear LABS-12, LABS-55, LABS-42)

## Decision
Anonymous usage telemetry is collected by the `cypherlite` CLI binary only,
sent to Mixpanel, identified by a random install ID, delivered off the hot
path, and governed by a layered opt-out that defaults to on.

1. **Scope: CLI binary only.** Telemetry lives in `crates/cypherlite-cli`.
   The embedded library (`cypherlite::Database`), the C ABI
   (`crates/cypherlite-ffi`), and `cypherlite-bolt` never phone home. Bolt
   may adopt metrics later via a new ADR; nothing here precludes it.
2. **Sink and transport: Mixpanel over the existing `ureq`.** Events are
   sent as `POST https://api.mixpanel.com/track` (default endpoint constant
   `DEFAULT_ENDPOINT`; the EU-residency host is
   `https://api-eu.mixpanel.com/track`) with a JSON array body of
   `{"event": ..., "properties": {"token": ..., "time": ...,
   "distinct_id": ..., "$insert_id": ..., ...}}` objects. The HTTP client is
   hand-rolled over the existing workspace `ureq = "3.4"` dependency
   (already used by `upgrade`, ADR-0069); install-ID and `$insert_id`
   randomness come from the existing workspace `rand` dependency (version
   pinned by ADR-0360). **Zero new dependencies.**
3. **Identity: random install ID, not a machine ID.** A random UUID is
   generated once and persisted as the install ID in state under the XDG
   config directory — `$XDG_CONFIG_HOME/cypherlite/` when
   `$XDG_CONFIG_HOME` is set, otherwise `~/.config/cypherlite/`. It is the
   `distinct_id` on every event. No hardware or OS machine identifier is
   ever read.
4. **Events v1 (minimal taxonomy).** Event names carry the
   `CYPHERLITE-CLI_` app prefix so the tracked surface is explicit in
   Mixpanel; a future Bolt adoption gets its own prefix (e.g.
   `CYPHERLITE-BOLT_`) rather than sharing the CLI's. Four events:
   - `CYPHERLITE-CLI_STARTUP` — `kind`: `oneshot` | `stdin` | `repl` |
     `version` | `help`.
   - `CYPHERLITE-CLI_QUERY` — `success` (bool), `source`: `oneshot` | `stdin` |
     `repl`, `storage`: `memory` | `persistent`, `output_mode`.
   - `CYPHERLITE-CLI_COMMAND` — lifecycle `command` name, `action`, `success`.
   - `CYPHERLITE-CLI_HELP` — fired when help is shown.

   Base dimensions on every event: `distinct_id` (install ID), `$os`,
   `arch`, CLI `version`, `uptime`, and `invoker` (`human` | `agent` |
   `ci`, derived from TTY detection, `CI` env, and known agent env vars).
   **Hard privacy rule:** never query text, never database paths, never
   parameter values — the event builder types have no fields for them, so
   capturing them is a compile error, not a policy violation.
5. **Delivery: non-blocking, best-effort, invisible.** Events go onto a
   bounded channel that drops on overflow; a single background thread drains
   it with a 2-second HTTP timeout; a bounded `flush()` runs on exit so the
   CLI is never perceptibly slowed. All telemetry errors are swallowed:
   nothing on stdout or stderr, exit codes unaffected.
6. **Opt-out: layered, default ON.** First match wins:
   `DO_NOT_TRACK=1` (the consoledonottrack convention) →
   `CYPHERLITE_TELEMETRY` env var (`0`/`false`/`off` disables) → persisted
   `telemetry: false` in `<config>/cypherlite/config.json` → enabled.
   Persistent control is a new positional lifecycle command `cypherlite
   telemetry on|off|status` following the ADR-0069 grammar (recognized only
   as the first argument; `./telemetry` and `-- telemetry` remain reachable
   as database paths). There is deliberately **no `--no-telemetry` flag**:
   per ADR-0069

--- ADR-0104 ---
# 0104. Cargo feature bundles, starting with the CLI

- **Status**: Accepted
- **Date**: 2026-09-25
- **Deciders**: CypherLite maintainers

## Decision
Offer compile-time capability as **Cargo feature bundles**: named feature sets
on the crate that owns the capability. The CLI is the first crate to adopt
this.

### Rules for every feature and bundle

1. A bundle is a named Cargo feature that only enables other features. Every
   feature only **adds** capability. There are no negative (`no-*`) features,
   so Cargo's feature unification can never remove something another
   dependent relies on.
2. `full` is the `default` feature. A plain `cargo build` or `cargo install`
   produces exactly today's binary.
3. Release artifacts (GitHub releases, install script, Homebrew) stay
   `full`-only for now. Smaller bundles are built from source
   (`cargo build -p cypherlite-cli --no-default-features --features agent`).
   Publishing other bundles as artifacts needs its own ADR.
4. A command word whose feature is compiled out is **still recognized as a
   command**. As the first argument (not after `--`, not `./`-prefixed), it
   prints `Error: the '<command>' command is not included in this build of
   cypherlite` to stderr and exits with code **2**. The argv grammar from
   ADR-0069 is therefore identical in every bundle: `cypherlite pull` never
   silently opens a database named `pull`, and `./pull` or `-- pull` is the
   escape in every build.
5. The hand-written `--help` text lists only the commands compiled into the
   binary. `docs/api/cli/spec.md` documents every command with the feature
   that provides it, plus the bundle table below, so a given build's
   `--help` matches the spec for that feature set.
6. CI builds, runs clippy on, and tests every named bundle (`full`, `agent`,
   `minimal`), not only the default. Tests for a gated command are gated on
   the same feature. The compiled-out path (rule 4) is tested in the bundles
   that exclude the command.
7. Later engine-level features (for example Parquet checkpoints or a `.cl`
   bundle VFS) follow the same rules. Each gets its own ADR that names the
   feature, what it gates, and which bundles include it.

### CLI features

| Feature | Gates | Optional dependencies | Without it |
| --- | --- | --- | --- |
| `repl` | `rustyline` line editor in `repl.rs` (history, editing, multi-line prompt) | `rustyline` | Interactive mode uses the existing `run_plain_interactive` plain-stdin loop; one-shot and piped stdin are unaffected |
| `pull` | `cypherlite pull` command (`pull_cmd.rs`) | `cypherlite-load` | `pull` is a recognized, not-included command (exit 2) |
| `skill` | `cypherlite skill install\|remove` (`skill/`, `skill_cmd.rs`, embedded skill bundle) | none | `skill` is a recognized, not-included command (exit 2) |
| `upgrade` | `cypherlite upgrade` and its `update` alias (`upgrade_cmd.rs`) | `ureq`, `sha2` | `upgrade`/`update` are recognized, not-included commands (exit 2) |
| `telemetry` | `cypherlite telemetry on\|off\|status` (`telemetry_cmd.rs`) and all usage-metrics emission (`telemetry/`) | `ureq`, `rand` | `telemetry` is a recognized, not-included command (exit 2); emission compiles to a no-op, so the binary makes no telemetry network calls |

A shared dependency (`ureq`) is linked when any feature that needs it is on.

### CLI bundles

| Bundle | Features | Intended use |
| --- | --- | --- |
| `full` (**default**) | `repl`, `pull`, `skill`, `upgrade`, `telemetry` | Today's release binary; developer workstations |
| `agent` | `skill`, `pull` | Sandbox/Docker images for AI agents: one-shot/stdin queries, JSON output, no self-upda

--- ADR-0545 ---
# 0545. Telemetry delivery off the exit path: local spool, next-run drain

- **Status**: Proposed
Claim: 6c5984093ab0d983ef961918dd5fc35a78024136
- **Date**: 2026-11-08
- **Deciders**: Relate maintainers

## Decision
Exits write locally; the next enabled run delivers.

1. **Exit = one local append.** `flush` writes the run's pending
   envelopes to the run's own spool file — one JSONL file per process
   under the config directory, one local write, no thread handoff, no
   network. The spool is bounded and drops past the bound, mirroring the
   in-memory overflow semantics; no fsync at exit, telemetry stays
   best-effort.
2. **Next-run drain.** An enabled run spawns one detached drain thread
   at its first recorded event — a run that records nothing (the `off`
   command above all) never starts a delivery — which claims spool
   files, renaming each to a unique claim
   name, sweeping claim files left by crashed or concurrent drains too,
   and POSTs them in bounded batches while the run's own work proceeds,
   taking at most a bounded set of files per sweep and dropping the
   excess past a bounded set of pending files. The sweep takes
   regular files only: a planted symbolic link is never claimed, read,
   or followed — including one swapped in after the sweep's filter, by
   a post-rename re-check. A claim is deleted only after a confirmed
   response; undelivered claims stay for the next sweep, and a claim
   whose content cannot be read is attempt-once — removed on the spot,
   like a corrupt line, so undeliverable content never starves a
   sweep. Delivery is
   at-least-once, effectively-once via the per-event `$insert_id`
   (ADR-0079 §2) the sink already dedups on.
3. **No in-run delivery.** The bounded channel and its worker thread
   disappear; a run's events sit in a bounded in-memory backlog and
   spool at exit. The 2 s HTTP timeout governs the drain POSTs. A
   session's events report one run late — immaterial for aggregate
   metrics, since event `time` is stamped at emit.
4. **The flush budget and `RELATE_TELEMETRY_FLUSH_MS` are removed** —
   nothing on the exit path needs a network bound.
5. **Opt-out.** Disabled runs spool and drain nothing. `telemetry off`
   is one ordered transition — disarm the run's pipeline, persist the
   key, clear any existing spool — so the run that turns telemetry off
   neither delivers, records, nor leaves a spool file of its own:
   turning telemetry off means no further transmissions, pending ones
   included.
6. **Windows config directory.** Resolution gains `%APPDATA%\relate`,
   then `%USERPROFILE%\.config\relate`, after the existing XDG/HOME
   order. Strictly additive — `None` becomes a path on Windows — giving
   Windows a persistent install ID, a working first-run notice, and
   extension-registry discovery (ADR-0429 §6).
7. **Portability rules.** Spool mechanics use std-only primitives:
   claims by exclusive create and atomic rename, short-lived opens only
   (Windows denies rename of files another process holds open), no
   advisory file locks, no platform-conditional code.
8. **Docs and guardrail, same change.** The CLI spec's usage-metrics
   section and privacy listing name the spool and its bounds; the env
   table loses the removed knob. A cold-start-to-first-query benchmark
   lands with the change and runs per-OS.

--- ADR-0190 ---
# 0190. Scoped CLI help: a command index, per-command help, and synopsis-scoped usage errors

- **Status**: Accepted
- **Date**: 2026-10-08
- **Deciders**: CypherLite maintainers (Linear [LABS-202](https://linear.app/neo4j/issue/LABS-202))

## Decision
1. **Top-level help is a command index.** `cypherlite --help` prints the
   usage lines

   ```
   cypherlite [OPTIONS] [DATABASE] [QUERY]
   cypherlite <COMMAND> [ARGS]
   ```

   then a `Commands:` section with a one-line entry for every compiled-in
   command — `clone`, `info`, `pull`, `skill`, `upgrade` (naming its `update`
   alias), `telemetry`, `lab` — then all query-run options as before, and
   ends with the footer

   ```
   Run 'cypherlite <COMMAND> --help' for details on a command.
   ```

   No lifecycle command’s flags appear in it; only the query run keeps full
   flag detail there.

2. **Per-command help.** `-h`/`--help` anywhere after a compiled-in command
   word prints that command’s help (synopsis plus its flags/actions) to
   stdout and exits 0. `cypherlite update --help` prints the `upgrade` help;
   `lab` help omits the hidden `neo` action; a help flag before the command
   word still prints top-level help. A command word whose feature is compiled
   out keeps the not-included error (exit 2).

3. **Usage errors are scoped.** A usage error (exit 2) prints
   `Error: <msg>`, the relevant command’s synopsis line(s) as
   `Usage: cypherlite …`, and
   `Run 'cypherlite <command> --help' for more information.` — with the
   canonical name `upgrade` for `update`. Top-level parse errors (unknown
   flag, unexpected positional, invalid `--namespace`) use the query-run
   synopsis and `Run 'cypherlite --help' for more information.` The two
   literal stderr shapes are

   ```
   Error: clone requires SOURCE and DEST
   Usage: cypherlite clone [--wal-dir DIR] [--to-snapshot-format F] SOURCE DEST
   Run 'cypherlite clone --help' for more information.
   ```

   ```
   Error: unknown flag: --bogus
   Usage: cypherlite [OPTIONS] [DATABASE] [QUERY]
   Run 'cypherlite --help' for more information.
   ```

4. **Errors that print no usage today keep their stderr byte-for-byte.** A
   missing flag value, an invalid `--mode`/`--param`/`--fetch-params` value,
   and `--command` combined with a positional query are unchanged.

5. **Per-command help emits the existing telemetry events**
   (`CYPHERLITE-CLI_STARTUP` with kind `help`, and `CYPHERLITE-CLI_HELP`) —
   no schema change.

6. **Each command synopsis is defined once in source** and shared by its help
   and its usage error, so the two cannot drift.

--- ADR-0263 ---
# 0263. Restrict the telemetry endpoint override to HTTPS

- **Status**: Accepted
- **Renumbered**: from 0112 (shared-number cleanup)
- **Date**: 2026-09-26
- **Deciders**: CypherLite maintainers

## Decision
`CYPHERLITE_MIXPANEL_ENDPOINT` must be `https://` for any host, or `http://`
only when the host is loopback. The scheme and host are compared
case-insensitively, and IPv6 hosts are compared with the surrounding brackets
trimmed (so `http://[::1]/…` is accepted). The accepted loopback hosts are
exactly `localhost`, `127.0.0.1`, and `::1`.

A rejected override **disables telemetry for the run**: no worker thread is
spawned and no request is made. It prints exactly one stderr warning naming both
the variable and the rejected value:

```
warning: ignoring CYPHERLITE_MIXPANEL_ENDPOINT=<url>: http:// is allowed only for loopback hosts; telemetry disabled for this run
```

`<url>` is the rejected value, reproduced verbatim. The warning is the only
output; the CLI otherwise behaves as if telemetry were opted out for that run
(exit codes and stdout are unaffected, per ADR-0079 §5).

This narrows only the override path. `CYPHERLITE_MIXPANEL_TOKEN` is unchanged,
and the default endpoint remains `https://api.mixpanel.com/track`.

Precedent `preflight` for this task (a tool that tracks which decisions are still in force):
{"task":"Add a new anonymous usage event to the CLI's metrics and decide how events are delivered.","paths":[],"decisions":[{"id":"ADR-0545","title":"Telemetry delivery off the exit path: local spool, next-run drain","standing":"in_force","declared_status":"proposed","path":"docs/adr/0545-telemetry-spool-delivery.md","gist":"Exits write locally; the next enabled run delivers. 1. Exit = one local append. flush writes the run's pending envelopes to the run's own spool file — one JSONL file per process under the config directory, one local write, no thread handoff, no network. The spool is bounded and drops past the…","why":["matches task (clause+fulltext+vector)","controls ADR-0079 (§5)"],"live_clauses":[{"n":1,"title":"Exit = one local append"},{"n":2,"title":"Next-run drain"},{"n":3,"title":"No in-run delivery"},{"n":4,"title":"The flush budget and `RELATE_TELEMETRY_FLUSH_MS` are removed"},{"n":5,"title":"Opt-out"},{"n":6,"title":"Windows config directory"},{"n":7,"title":"Portability rules"},{"n":8,"title":"Docs and guardrail, same change"}],"stale_clauses":[]},{"id":"ADR-0079","title":"Anonymous usage metrics in the CLI","standing":"partial","declared_status":"proposed","path":"docs/adr/0079-anonymous-usage-metrics.md","gist":"Anonymous usage telemetry is collected by the cypherlite CLI binary only, sent to Mixpanel, identified by a random install ID, delivered off the hot path, and governed by a layered opt-out that defaults to on. 1. Scope: CLI binary only. Telemetry lives in crates/cypherlite-cli. The embedded library…","why":["matches task (clause+fulltext+vector)"],"live_clauses":[{"n":1,"title":"Scope: CLI binary only"},{"n":2,"title":"Sink and transport: Mixpanel over the existing `ureq`"},{"n":3,"title":"Identity: random install ID, not a machine ID"},{"n":4,"title":"Events v1 (minimal taxonomy)"},{"n":6,"title":"Opt-out: layered, default ON"},{"n":7,"title":"Dev/test overrides"},{"n":8,"title":"Documentation in the same change"}],"stale_clauses":[{"n":5,"title":"Delivery: non-blocking, best-effort, invisible","by":["ADR-0545"],"note":"§5 'Delivery: non-blocking, best-effort, invisible' superseded by ADR-0545"}],"evidence":[{"by":"ADR-0545","treatment":"SUPERSEDES","clauses":[5],"quote":"ADR-0545 replaces §5's delivery shape: the exit flush no longer waits on the network — pending events spool locally and the next enabled run delivers them."}]},{"id":"ADR-0190","title":"Scoped CLI help: a command index, per-command help, and synopsis-scoped usage errors","standing":"in_force","declared_status":"accepted","path":"docs/adr/0190-scoped-cli-help.md","gist":"1. Top-level help is a command index. cypherlite --help prints the usage lines cypherlite [OPTIONS] [DATABASE] [QUERY] cypherlite <COMMAND> [ARGS] then a Commands: section with a one-line entry for every compiled-in command — clone, info, pull, skill, upgrade (naming its update alias), telemetry,…","why":["matches task (clause+fulltext+vector)"],"live_clauses":[{"n":1,"title":"Top-level help is a command index"},{"n":2,"title":"Per-command help"},{"n":3,"title":"Usage errors are scoped"},{"n":4,"title":"Errors that print no usage today keep their stderr byte-for-byte"},{"n":5,"title":"Per-command help emits the existing telemetry events"},{"n":6,"title":"Each command synopsis is defined once in source"}],"stale_clauses":[]},{"id":"ADR-0429","title":"The CLI extension registry — manifest, discovery, and the `run` mount (LABS-470)","standing":"in_force","declared_status":"proposed","path":"docs/adr/0429-cli-extension-registry.md","gist":"### 1. The mount: run, the one new reserved word for command-kind cypherlite run <name> [flags] is the command-kind mount point. run is a new first-positional command word in the hand-rolled parser, in the ADR-0069 shape (recognized only as the first argument), reserved in every build (ADR-0104): a…","why":["matches task (clause+fulltext+vector)"],"live_clauses":[{"n":1,"title":"The mount: run, the one new reserved word for command-kind"},{"n":2,"title":"The manifest: JSON under the XDG config dir"},{"n":3,"title":"kind is a closed vocabulary from day one"},{"n":4,"title":"protocol is per-mount-point"},{"n":5,"title":"The host parses argv from the flag table"},{"n":6,"title":"Discovery: the XDG directory only"},{"n":7,"title":"Trust sits at install time, never silently at runtime"},{"n":8,"title":"Bundle placement: extensions at full + agent"}],"stale_clauses":[]},{"id":"ADR-0345","title":"Plan surface alignment — CLI text rendering, Bolt and HTTP passthrough","standing":"partial","declared_status":"accepted","path":"docs/adr/0345-plan-surface-alignment-cli-bolt-http.md","gist":"1. CLI: EXPLAIN/PROFILE print the Neo4j-compatible fixed-width ASCII tree — columns Operator | Id | Details | Estimated Rows | Rows | DB Hits | Memory (Bytes), tree glyphs +/| |/|\\, and the footer totals line — omitting the Page Cache column (ADR-0344). The ASCII rendering is also carried as the…","why":["matches task (clause+fulltext+vector)"],"live_clauses":[{"n":2,"title":"Bolt: EXPLAIN/PROFILE responses carry the plan as SUCCESS summary"},{"n":3,"title":"HTTP Query API: the response envelope carries queryPlan (EXPLAIN) /"},{"n":4,"title":"The _profile_ data-row columns are deprecated: phase 1 stops adding"}],"stale_clauses":[{"n":1,"title":"CLI: EXPLAIN/PROFILE print the Neo4j-compatible fixed-width ASCII","by":["ADR-0359"],"note":"§1 'CLI: EXPLAIN/PROFILE print the Neo4j-compatible fixed-width ASCII' superseded by ADR-0359"}],"evidence":[{"by":"ADR-0359","treatment":"SUPERSEDES","clauses":[1],"quote":"ADR-0359 supersedes item 1's engine-produced rendering and the `string-representation` argument's origin: the engine emits the plan tree only, `EXPLAIN` no longer returns a plan column, and every boundary renders the plan text through `cypherlite-formatter` on demand."}]}],"warnings":["ADR-0079 is partly superseded: §5 'Delivery: non-blocking, best-effort, invisible' superseded by ADR-0545","ADR-0345 is partly superseded: §1 'CLI: EXPLAIN/PROFILE print the Neo4j-compatible fixed-width ASCII' superseded by ADR-0359"],"omitted":11,"tokens":1492,"how_to_read":"live_clauses are good law; stale_clauses were taken out of force by the decision named in `by` - follow that decision instead."}