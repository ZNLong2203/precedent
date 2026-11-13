You are a coding agent in a repository that keeps architecture decision records (ADRs). Below are 6 independent tasks.
For each task you get context retrieved for it. Decide which numbered decision clauses your plan for the task must
respect or build on (ADR number and clause number), at most 8, most important first. Use only the context in this
file: do not read any other file, search the repository or run commands.

Answer with a single JSON array, one object per task, in this exact shape and nothing else:

[{"task_id": "T01", "relies_on": [{"adr": "ADR-0046", "clause": 2}], "note": "one sentence on your plan"}]

Use `"clause": null` for a decision that has no numbered clauses.


==================== TASK T23 ====================
Task: Let --database accept a remote URL to a bundle and treat the downloaded copy like a local store.

Context retrieved for this task: the decision records of the repository, as written.

--- ADR-0496 ---
# ADR-0496: Run from URL — `--database` accepts a remote `.cl` bundle

Status: Proposed

Claim: 0b48269065bae51d75ccb7269b7e1901e66764dc

## Decision
1. **`--database` accepts an `http(s)` URL** naming a `.cl` single-file
   bundle. Detection is the scheme prefix, ungated (ADR-0104, ADR-0270), so
   every build parses a URL `--database` and every policy refusal below
   applies in every build; only the fetch is feature-gated. Every value that
   is not an `http(s)` URL keeps today's plain local-path behavior exactly.
2. **A GitHub file URL is rewritten** to its
   `raw.githubusercontent.com/<owner>/<repo>/<ref>/<path>` form — both the
   shareable **blob** page link people paste and GitHub's own **raw** verb
   (which would otherwise 302 there), so the bytes arrive in one request.
   Every other host (a raw URL, a loopback test server, anyone else's file
   host) is fetched unchanged, and **redirects are followed** (ureq's
   default chain), so a release-asset URL or any other `30x` that lands on
   the bundle bytes works.
3. **The URL must name a `.cl` file, and folder URLs are refused before any
   fetch**, with the working form named in the error: a repository URL, a
   `tree` URL, a non-`blob` verb, a blob URL with no file path, and a URL
   whose last path segment does not end in `.cl` (query and fragment
   stripped). A remote **native directory** is not supported: it is a
   multi-file layout with its own WAL protocol, and a `.cl` bundle is the
   one self-contained artifact. **`https://` is required for any host;
   plain `http://` is accepted only for a loopback host** (`localhost`,
   `127.0.0.0/8`, `::1`) — the e2e fixtures and a local dev server — and
   refused otherwise with the `https://` form named. There is no
   `--allow-plaintext`-style opt-in here (unlike `pull`, ADR-0122): a
   database fetched over plaintext arrives unverified on a transport anyone
   on the path can rewrite, and this fetch has no signature story either.
   The policy is enforced across **redirects** too: every `https://` fetch
   pins `https_only` on its client (the LABS-470 pin the release channel
   carries), so a `302` cannot downgrade the transport past the scheme the
   URL already passed. The loopback plain-`http` carve-out is the one
   release — there the pin would refuse the first hop — and a local server's
   own redirects are the local server's trust.
4. **The CLI fetches and stages.** One capped GET (1 GiB, 300 s global)
   through the shared `url_fetch` helper the `--fetch-params` fetch also
   rides — its **streaming** form (`get_into`), so the body goes straight to
   the staged file through a fixed-size buffer and a bundle at the cap never
   lives in RAM (`--fetch-params` keeps the buffered form, since it parses
   the document in memory); the bytes are written to a private temp path named by the shared
   `atomic_file::staging_name` recipe (pid + counter + nanosecond clock) with
   the `.cl` suffix, created `create_new` and `0o600` from birth.
   A **scratch** copy (a read-only open) is registered for cleanup before its
   first byte lands and removed on every post-parse exit (`exit_flushed`;
   `process::exit` skips destructors); a **kept** copy (a writable open)
   never registers, so nothing removes it. A failed fetch removes its own
   partial file directly — the rollback belongs to the fetch that owns the
   failed file, whatever the disposition of a download that never
   completed. The engine then opens the staged path through the ordinary
   `.cl` bundle route — codec, superblock, and embedded WAL are the store's
   own, not a remote variant.
5. **A downloaded copy is 

--- ADR-0500 ---
# ADR-0500: Store targets and sources — `--database` + `--load`, and ephemeral opens

Status: Proposed

Claim: d8430ab36fabfde21b3f0bd2891f31371a2fdd25

## Decision
1. **`--database PATH` (`-d`) names the store target only** — a store
   directory, a `.cl` bundle, or `:memory:` (the default, unchanged). An
   `http(s)` URL in `--database` is a usage error (exit 2) that names the
   working form (`--load <url>`). This withdraws ADR-0496's §1 (the
   URL-in-`--database` spelling) and its §5 kept-copy disposition — the
   feature never shipped in a release. Everything else ADR-0496 decided
   about the fetch itself (§2–§4, §6–§9: the GitHub rewrite, the redirect
   and scheme policy, the `.cl` requirement, the capped streaming stage,
   the safe-mode refusal, the feature gate, the CLI-process posture)
   carries over unchanged to `--load`'s remote sources.
2. **`--load SOURCE` names the store source** — a local `.cl` bundle, a
   native directory store, or an `http(s)` URL to a `.cl` bundle — loaded
   into the target. Two legs:
   - **`:memory:` target (the default): the ephemeral open.** The engine
     loads the source as usual and then **releases** it — `OpenMode::Ephemeral`,
     `Database::open_ephemeral(uri)`. The loaded store is `:memory:`-shaped
     for its whole life: nothing holds the source open or locked, it can
     be deleted or opened writable underneath, and the loaded copy is
     frozen snapshot freshness. A remote source's scratch copy is removed
     right after the load — nothing on disk at all.
   - **Durable target (`-d PATH --load SOURCE`): store creation.** The
     target path must not exist (fail-closed; exit 2 if it does); the
     source is cloned into it through the `clone` verb's own machinery
     (the full dir/`.cl` matrix, ADR-0156), and the run then opens the
     created store with the flags' normal mode — writable by default.
     This is the one capability the old shape could not express: a URL
     materialized into a durable store **at a path the user chose**.
3. **The release is a swap, not a teardown.** After the load, every holder
   of the source lets go — the store target, the WAL's open segment handle
   (`Wal::release_source`: the replayed LSN/counters/magic stay, a fresh
   in-process WAL takes the source's place), and the store holds a
   `MemoryVfs` stand-in in its place. Any path
   that should never run on a read-only store behaves like `:memory:`'s,
   never like a released file's.
4. **Ephemeral is read-only by definition** — it is a mode variant beside
   `ReadOnly`, not an option on top of one: writes have nothing to write
   back to and a follower reads the source's WAL after load, so neither
   combination can be constructed. `:memory:` with `Ephemeral` is the
   plain memory open (the release is the no-op it never takes). The first
   cut carried an `OpenOptions::ephemeral: bool`, and the review's
   blocker was right to kill it: the flag was non-orthogonal with `mode`
   and its validation ran after the lease — a fail-before-lease violation.
   As a mode variant the illegal combinations are unrepresentable.
5. **CLI resolution.** `Flags::open_mode` stays the one open-mode
   resolution: it answers `OpenMode::Ephemeral` exactly when `--load` is
   given with the `:memory:` target, else the access slot's ADR-0480
   resolution. `--read-only=live` with any `--load` is a **parse-time**
   usage error (nothing is ever followed — the source is loaded once and
   released); `--read-only` with a creating load (durable target) is
   refused at resolution. The `--ephemeral` flag of this ADR's first cut
   died before shipping: "`--load` into the defa

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

--- ADR-0159 ---
# 0159. Snapshot round trip between a native directory and a `.cl` bundle

- **Status**: Accepted
- **Date**: 2026-10-03
- **Deciders**: CypherLite maintainers (Linear LABS-167)

## Decision
1. **One new CLI lifecycle verb `snapshot`.** Following ADR-0069, it is an
   exit-after positional command recognized only as the first argument.
   Its single positional argument is the native directory `DATABASE`, and
   exactly one of two direction flags is required:
   - `cypherlite snapshot DATABASE --to FILE.cl` exports a native
     directory database to a single-file `.cl` bundle.
   - `cypherlite snapshot DATABASE --from FILE.cl` imports a `.cl` bundle
     into a fresh native directory `DATABASE`.
   - `--wal-dir DIR` is allowed only with `--to` (the external WAL of the
     directory source, mirroring `clone`); combining it with `--from` is a
     usage error. Usage errors exit 2; runtime errors exit 1, mirroring
     `clone` and `pull`.
2. **The source is always opened read-only via the ADR-0136 path**
   (`OpenMode::ReadOnly` / `open_store_readonly`): stable-cut manifest
   retry, bounded reads, fail-closed on corruption. The command never
   writes to or exclusively locks the source. A writer-held `.cl` source
   fails with a lock error, since a bundle writer holds `LOCK_EX` on the
   host file (ADR-0136).
3. **The destination must not exist** — the same contract as `clone`
   (ADR-0156). A failed run removes any partially created destination,
   file or directory.
4. **The destination keeps the source's snapshot codec in both
   directions** — json stays json, parquet stays parquet. There is no
   codec conversion.
5. **Engine: two new public `Database` methods.**
   `snapshot_to_bundle(source, dest, SnapshotOptions)` and
   `restore_from_bundle(source, dest, SnapshotOptions)` generalize the
   `clone.rs` publish path across the dir/`.cl` boundary. `SnapshotOptions`
   carries `wal_dir: Option<PathBuf>`, used only by `snapshot_to_bundle`.
6. **The command is compiled into every CLI bundle like `clone` — no new
   Cargo feature.** This deviates from the ADR-0104 rule that a new
   capability gets its own feature: snapshot/restore is as fundamental to
   moving data as clone, adds no dependencies, and keeping it
   always-available avoids a bundle in which a user's backup tool
   vanishes.

--- ADR-0081 ---
# 0081. Opt-in, rooted local-file capability for LOAD CSV

- **Status**: Proposed
- **Date**: 2026-09-23
- **Deciders**: CypherLite maintainers

## Decision
**Local-file `LOAD CSV` is denied by default.** A database may opt in by
setting `OpenOptions.load_csv_dir: Option<PathBuf>` to a pre-existing CSV
directory. `OpenOptions.load_csv_max_bytes: Option<u64>` configures the
maximum number of source bytes for each file; setting a limit alone never
enables file access. At database open, resolve a relative configured directory
against the process working directory, canonicalize it, and require an
existing directory. Retain that canonical directory as the sole allowlist
root; it need not be, and is never inferred from, the database directory.
This works equally for `:memory:` and `.cl` databases.

`CYPHERLITE_LOAD_CSV_DIR` is an explicit environment opt-in when
`OpenOptions.load_csv_dir` is `None`. A supplied `OpenOptions.load_csv_dir`
takes precedence over the environment. Both `cypherlite` and
`cypherlite-bolt` expose `--load-csv-dir PATH`; their flag takes precedence
over `CYPHERLITE_LOAD_CSV_DIR`, and with neither set they deny local files.
An absent root remains disabled even if `load_csv_max_bytes` is set.

The default per-file read limit is **8 MiB (8,388,608 bytes)**, allowing
ordinary small CSV imports while bounding a single cached source to a
modest size. A caller may override it with
`OpenOptions.load_csv_max_bytes = Some(n)` only for
`1 <= n <= 67,108,864` (**64 MiB ceiling**); reject zero or larger
values at database open as invalid configuration, never interpret either as
unlimited. The ceiling accommodates larger local imports while keeping even
an explicitly raised per-file read bounded. The limit applies to actual
bytes consumed, regardless of pre-read file size: read at most `limit + 1`
bytes, and reject the source if the extra byte exists. Do not use an
unbounded `read_to_string` or trust metadata length as the enforcement.

For query-supplied sources, accept plain **relative** paths resolved under
the configured root and local `file:///` **absolute** paths only when the
target remains under that root. Reject bare absolute paths, lexical `..`
traversal, all other schemes, `file://` authorities (including `localhost`),
and malformed file URLs. Canonicalize the candidate target, verify it lies
within the canonical root by path components rather than string prefix,
and require it to be a regular file before opening it. An in-root symlink
to an out-of-root target is therefore rejected; devices, directories and
FIFOs are rejected as non-regular. There is no HTTP fetching.

On Unix, a local absolute URL has the form `file:///tmp/rows.csv`. On Windows,
only a forward-slash drive-rooted URL such as `file:///C:/csv/rows.csv` maps
to the absolute path `C:/csv/rows.csv` before canonicalization. A URL with an
authority, backslashes, a UNC/device/verbatim prefix, a drive-relative path,
percent encoding or lexical traversal is malformed; the canonical root still
confines the resulting path.

Every client-facing denial, invalid path, unavailable/non-regular file, or
I/O failure gets a generic typed `LOAD CSV file unavailable` error; a file
that exceeds the cap gets a generic typed `LOAD CSV file exceeds byte limit`
error. Invalid option values fail database open with a generic configuration
error. None of these errors includes the requested path, canonical path,
OS errno, or OS error text.

Cache successfully read source bytes (or parsed rows) by canonical target
**per statement**, shared across its input rows and nested execution paths.
Repeated references to the same file in one statement

==================== TASK T14 ====================
Task: Add a query command to the CLI that runs a Cypher statement against a database path.

Context retrieved for this task: the decision records of the repository, as written.

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

--- ADR-0518 ---
# ADR-0518: Command did-you-mean on query-run usage errors

Status: Proposed

Claim: 6f77dc329a909082c162abd012dc35e28a288a92

## Decision
The two query-run usage-error exits that fire while a statement is
pending — the unknown-flag exit and the unexpected-argument exit — carry
the ADR-0230 command suggestion for the pending statement:

1. **Applicability.** When the exit fires and a statement is already
   pending (the first positional, or `--command`'s value), the
   suggestion runs `suggest::suggest_command` on that statement — the
   same matcher, the same candidate table (`help::COMMANDS` plus the
   `update` alias), the same rendering (blank line, then
   `did you mean "<word>"?  -- <synopsis>` through `print_error`). No
   statement pending (`--bolt 7687 service`, flag first), or a first
   word that is not a plausible command typo (`RETURN 1 --bolt`) — no
   suggestion, byte-for-byte today's output.
2. **Parsing stays authoritative.** Nothing new is rejected or rerouted;
   the suggestion is printed by the exit that already fired. ADR-0230's
   rejection of a pre-check stands: a statement that would parse is
   never decorated, because no exit fires for it.
3. **One suggestion slot.** The exit carries at most one did-you-mean
   line. When the pending statement matches a command, the command line
   replaces the flag suggestion — the flag candidate list belongs to the
   exit's usage scope, which is the wrong scope for the command the user
   meant, so a flag suggestion beside a command suggestion can only add
   noise (`servcie --databse x` suggests `serve`; the retry then gets
   `--database` from the flag matcher on its own exit). No command match
   — the flag suggestion behaves exactly as before (ADR-0192).
4. **Scope.** Exit codes are unchanged (still 2 for usage errors), the
   JSON envelope gains no field, and the engine-error fallback
   (ADR-0230 §1) is untouched. Lifecycle verbs' own parsers are
   untouched: their exits have no pending statement, so there is nothing
   to suggest.

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
     

--- ADR-0199 ---
# 0199. Statement progress when a multi-statement run fails

- **Status**: Proposed
- **Date**: 2026-10-09
- **Deciders**: CypherLite maintainers (Linear [LABS-240](https://linear.app/neo4j/issue/LABS-240))

## Decision
1. **Report progress when a multi-statement run fails.** A run with more than
   one statement (one-shot `-c`, piped stdin, an interactive line holding
   several) that stops on a failed statement reports where it stopped. A run of a
   single statement, and a run that succeeds, print exactly what they print today.
2. **Stderr gets one extra line**, after the existing error line and before
   anything else:
   `statement 2 of 3 failed; 1 completed and committed; 1 not run`.
   Inside an open `.begin` transaction the middle clause reads
   `1 completed, not committed (open transaction)`.
3. **The error envelope gains three optional fields** (additive to ADR-0194),
   present only for a multi-statement run:

   | Field | Meaning |
   | --- | --- |
   | `statement` | 1-based index of the failed statement |
   | `statements` | how many statements the input held |
   | `committed` | how many earlier statements are durable: all that completed, or `0` while an explicit transaction is open |

   ```json
   {"error":{"code":"validation_error","exit_code":6,"kind":"syntax","message":"…","retryable":false,"statement":2,"statements":3,"committed":1}}
   ```
4. **What counts as a statement** is what the splitter yields and the run
   executes: a Cypher statement or a `.`-command, so the index matches what was
   typed. Empty fragments are not counted; `statements` is the number of runnable
   fragments, so a trailing `;` does not add one. **Only a failed Cypher
   statement reports.** A failed `.`-command (for example `.commit` with no open
   transaction) stops the run as it does today, with its existing error line and
   exit code and no envelope (ADR-0194 keeps dot-commands outside the error
   object); giving them one is a separate decision.
5. **No change to execution.** A failure still stops a piped or one-shot batch
   at the first error (ADR-0194's exit code is that statement's class). This ADR
   adds reporting only.
6. **Interactive sessions** report nothing extra. A line holding several
   statements keeps going after a failure in the shell, so "N not run" would be
   false there, and the user sees the state at the prompt. Only a run that stops
   at its first failure (`-c`, piped stdin) reports.

==================== TASK T10 ====================
Task: Add a new ontology management procedure under db.ontology.

Context retrieved for this task: the decision records of the repository, as written.

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

--- ADR-0557 ---
# 0557 — List only the procedures an embedded engine can answer

Status: Proposed
Claim: e7abcfac69d86bd9722ef4f59954d4828a970085

## Decision
The catalogue lists only what the engine can answer. The cluster, routing,
fleet-management, CDC, session/connection/lock/pool/JMX/security/scheduler,
usage-statistics and server-configuration families leave the registry, as do
the vector-property setters and the index-resampling pair.

What stays is the graph and schema introspection, the fulltext and vector
query procedures, the catalog writes, the ontology family, the client-facing
server-info rows (`dbms.components`, `dbms.info`, `dbms.listConfig`,
`dbms.clientConfig`, `dbms.licenseAgreementDetails`, `dbms.showCurrentUser`),
graph counts, and the embedded-relevant rows that become executable next:
`db.checkpoint`, `db.awaitIndex`, `db.listLocks`, `db.clearQueryCaches`,
`db.prepareForReplanning`.

==================== TASK T22 ====================
Task: Extend the quantified path pattern kernel (the frontier NFA) with a rule for re-arriving at a node, and bound its work.

Context retrieved for this task: the decision records of the repository, as written.

--- ADR-0536 ---
# ADR-0536: The frontier NFA over the regular-pattern space

Status: Proposed

Claim: 7fc50840830bff8d0f272e1481181b2c4586d4ee

## Decision
1. The compile's structural rule generalizes from "exactly one
   top-level `Quantified` element" to **one regular pattern over the
   closed vocabulary with at most one range-quantified region**: any
   number of exact-count regions (`min == max`, zero included — a pure
   concatenation chain), at most one region whose count is a range or
   unbounded, plain rels elsewhere. The soundness argument is
   unchanged: an exact-count region contributes a fixed length and
   unrolls acyclically, so the global hop interval still pins at most
   one cycle.
2. **Exact counts unroll; ranges keep the cycle.** A quantifier with
   `min == max` compiles through the existing structural unroll (k
   copies, linear states) instead of the cycle form. Per-level frontier
   sets are then the unrolled automaton's states — the (node, state)
   pair with state = depth — carried by the existing ever-visited pair
   set and sparse tables (ADR-0521); no new data structure. In an
   exact-only pattern every pair is reachable at exactly one level, so
   the below-min candidate class cannot arise (accepting states sit at
   depth k) and the dedup filter never blocks an in-bounds expansion.
   The state ceiling and the table budget's run-time decline bound the
   k-fold state cost.
3. Everything else rides unchanged: the matcher's gates (spine, pinned
   bindings, conjunct vocabulary, carrying row, mode), the consumer
   decode, the pools, the emission, the work budget, the cost gate, and
   the re-arrival rule — which is also the default-pool
   rel-uniqueness argument for fixed chains (a node-simple
   representative chain is rel-distinct; the rest take the bounded
   search, exactly as for quantified shapes). The ladder pre-gate
   shares the compile's generalized count fact, one spelling.

--- ADR-0478 ---
# ADR-0478: The frontier-NFA QPP kernel

Status: Proposed

Claim: 50180de65cdaeec90c5c4613b6e3c057519b7ef8

## Decision
Add the **frontier family** to the contracted-kernel layer (ADR-0473):

1. **The kernel.** A Thompson NFA compiled at plan time from the
   `QuantifiedPathPattern` IR element — the one element every var-length
   spelling lowers to since ADR-0471, so every spelling gets the kernel —
   over interned rel-type ids with direction-tagged transitions and hop
   bounds `{min, max: Option<u32>}`. The run is a level-synchronous BFS
   over deduplicated (node, automaton-state) pairs on the `ExecGraph`
   overlay view — write scratch and pinned ts visible, the same liveness
   rules `hop` applies, the cancel window sampled per level — not the
   base `Graph` the prototype reads. **Accept on arrival, before the
   dedup filter**: an accepting transition reaching `v` at a hop count in
   `[min, max]` marks the endpoint even when `v` was first visited at an
   earlier level; dedup gates *expansion* only. Parent-pointer plus
   traversed-rel-id tables (one `RelId` per (node, state) slot) feed an
   output-sensitive capped reconstruction — cap × depth after the BFS,
   never per trail — binding the row shapes the DFS would emit: the path
   variable, the group lists, the target's bindings. Structural proofs
   decline (nested quantifiers, state count above the 64-pair bitmask
   ceiling, uncompilable outer context); the cost gate engages on the
   planner's own estimates — an unbounded quantifier over any type, or
   estimated paths at a constant factor (4x in the first cut) over
   estimated distinct endpoints; bounded acyclic-schema recursions
   (replyOf/isSubclassOf forests, measured 0.2–0.7 ms) stay on the DFS.

2. **The answer-shape gate** — the semantic half, as much a proof as the
   structural half. The frontier serves exactly the answer shapes that
   are functions of the (node, state) *pair*, not of the *path*:
   reachability/EXISTS (an exists-probe arm), distinct-endpoint answers
   (`count(DISTINCT y)`, `RETURN DISTINCT y`, arrival-time folds over
   distinct endpoints such as `min(y.k)`), un-ordered capped path
   emission (`RETURN p LIMIT n`), and bounded WALK mode. Everything else
   declines to the unchanged DFS — fail-through, answers identical,
   pinned by differential tests: full enumeration (uncapped
   TRAIL/SIMPLE/ACYCLIC — two trails to one node are two answers),
   ordered caps (ORDER BY + LIMIT needs the full candidate set to sort),
   selectors (ANY/ALL SHORTEST — the GPM shortest machinery owns them;
   they already stand down early conjuncts and the inliner), path counts
   (`count(p)` counts paths, not endpoints), patterns whose quantification
   accumulates a group any inlined allReduce (ADR-0469) reads — the
   inliner's per-branch prefix semantics cannot survive dedup: one
   (node, state) pair stands for many prefixes with different
   accumulator values, so that shape keeps the DFS with its inliner —
   and rel-predicate hops (an inner rel's `WHERE` declines; an inner
   node's in-vocabulary `WHERE` rides as an arrival-time check).

3. **The re-arrival trail-existence rule** — default-pool exactness
   (DIFFERENT RELATIONSHIPS ⇒ TRAIL pool). The prototype's measured
   divergence: on SF0.1 `knows{1,2}` the engine's trail answers count
   855 distinct endpoints, the frontier 856 — the delta is the seed,
   re-reached by a rel-reusing 2-walk whose shortest *trail* falls below
   `min`; the engine's own true-walk spelling returns exactly 856. A
   re-arrival that reaches an already-visited (node, state) pair is
   acc

--- ADR-0519 ---
# ADR-0519: The diagnostic pattern-engine switch `RELATE_PATTERN_ENGINE` (auto|nfa|walk)

Status: Proposed

Claim: aee82c9112e1597f2af78744f215ba1362f959c7

## Decision
Ship `RELATE_PATTERN_ENGINE`, a diagnostic-only engine switch with
three values:

- **`auto`** — the default: unset, empty, and `auto` route exactly as
  today; every rung's own proofs and cost gates decide, unchanged.
- **`nfa`** — force the frontier family's rung onto every
  frontier-compilable clause: `frontier_match::compile_frontier` bypasses
  its cost gate (`frontier_engages`) alone. Every other proof stands —
  the structural and answer-shape gates, the table-allocation ceiling,
  the re-arrival budget's run-time fall-through (ADR-0516) — and every
  decline still fails through to the rungs below. The batch
  scan-filter chain and the chain/hub-star kernels stand down for the
  clauses the frontier takes: they sit below it on both operator
  ladders, and the contracted matcher declines quantified shapes
  structurally, so the families are disjoint.
- **`walk`** — stand the traversal kernels down: the chain/hub-star
  kernels and the frontier family decline every clause, and the batch
  scan-filter chain plus the per-row walker serve — the differential
  suites' `with_kernels_disabled` behavior, now reachable from a real
  process.

Resolution follows the `RELATE_PARSER` precedent's site and
precedence: read once at `Database::open`, in the fail-before-lease
preflight (beside `RELATE_PREVIEW`), parsed case-insensitively; a
present value that is not one of the three fails the open with
`invalid RELATE_PATTERN_ENGINE: … expected auto, nfa, or walk` — no
silent fallback. The resolved value is installed on the store-level
`StoreServices` bundle (beside the preview set, through
`Graph::configure_pattern_engine`), so every namespace of the store
routes alike and a follow reload keeps it; the rungs read it through
`Graph::pattern_engine`.

Boundaries, stated once:

- **Diagnostic-only.** The switch is a measurement instrument for the
  spike, not a supported tuning knob: no stability promise, no
  performance claim for either forced value.
- **Never Cypher syntax.** No query-level spelling, no `USING` hint, no
  plan-level surface; a statement cannot select its engine, and PROFILE
  output changes only through the operators' existing annotations.
- **Removal condition.** The switch dies with the old engines it
  switches between: when the spike concludes and the per-row walker or
  the kernels it selects among are replaced or removed, the switch is
  removed in the same change. While it lives, `auto` must remain
  today's routing exactly.

Executor tests pin the routing (`exec/kernels/engine_switch_tests`):
forced-`nfa` engages the frontier on a cost-declined frontier-compilable
shape (engagement and frontier counters), forced-`walk` leaves a
chain-kernel shape and a frontier shape to the per-row walker (zero
engagements, identical rows), and the `auto` twins route as before. The
variable is documented beside `RELATE_PREVIEW` in the Rust and CLI
specifications and in the dialect notes (`AGENTS.md`), the doc set the
`RELATE_PARSER` mentions live in.

--- ADR-0350 ---
# ADR-0350: Bound-node pivot for multi-pattern path expansion

Status: Proposed
Claim: 8762c0120daf1131301b380b08c129cde38bb336

## Decision
When a pattern element at index `k > 0` has its variable bound to a node
in the incoming row, start the expansion at `k` instead of `0`:

- the forward machinery (`match_node` → `expand_rel` → `walk`) covers the
  suffix `k..end` exactly as today, with node `k`'s candidates short-
  circuiting to the bound id (`node_candidates`'s row-bound arm);
- a new **backward walker** covers the prefix `k-1..0`, mirroring the
  forward walk over single-hop rels with each rel's direction flipped;
  it binds nodes/rels under their **original** indices, so
  `bind_named_path` and the `__node{i}`/`__trail{i}` keys stay correct;
- prefixes containing a variable-length or quantified rel, a shortest-
  path function, or a `RepeatableElements` mode fall back to the
  index-0 start (the backward walker is single-hop only in this first
  cut).

The pivot is chosen at execution time (the binding is a runtime fact):
the first element whose variable is row-bound to a `Node`, preferring
the smallest `k > 0` so the largest bound prefix is exploited.

--- ADR-0568 ---
# ADR-0568: Shortest selectors are physical operators of the one pattern evaluator

Status: Accepted
Claim: 594510b89903e28db6a7f97010b824b587221308

## Decision
1. **Selectors are physical operators.** Every shortest selector is a
   physical operator of the one pattern evaluator, chosen by plan shape.
   The ADR-0186 route, with ADR-0189's shared search and ADR-0556's
   pair search, is formalized as the engine's BFS operator. Enumeration
   followed by selection is the fallback operator for shapes the BFS
   cannot follow, such as multi-relationship or quantified bodies. The
   routed shapes, selector set and result contract of ADR-0186 are
   unchanged; this decision adds no behaviour. Operators obey ADR-0555
   (streaming) and charge retained state per ADR-0463.
2. **The expression form normalizes onto the pattern machinery.**
   The front end lowers the shortest expression onto the same pattern
   plus selector form the clause uses, and the expression form's private
   search driver is deleted: one evaluator, one set of semantics. The
   unified engine takes the global shortest across all start and end
   candidates. Two accidental behaviours of the expression form are
   removed: `shortestPath` stopping at the first start candidate that has
   a trail, and `allShortestPaths` letting the first candidate fix the
   length cap (a result that depended on candidate order). An expression
   with a minimum length above one already takes the global shortest, so
   this makes the form consistent with itself. Preserved: one value per
   input row; null when nothing qualifies; a list for `allShortestPaths`;
   closed-trail behaviour when start equals end; the zero-length path when
   start matches end; exact enumeration for a minimum length above one;
   the 32-hop default for an unbounded variable-length relationship.
3. **Witness choice is unspecified.** Among equally short paths, which
   one a single-path selector returns is not part of the contract. No
   Neo4j-parity or newest-first tie-break is promised; ADR-0203's order
   stays an implementation detail of enumeration, not a guarantee.
   Lengths, row counts and all-shortest result sets stay exact.
4. **Native shortest on the frontier NFA is a separate research track.**
   The design note on that question stands. It does not gate this
   decision and a later ADR must carry any change of the operator set.

==================== TASK T19 ====================
Task: Let the server and the MCP server open a database read-only or in follow mode, including in the Docker image.

Context retrieved for this task: the decision records of the repository, as written.

--- ADR-0128 ---
# 0128. Docker image for the cypherlite-bolt server

- **Status**: Accepted
- **Date**: 2026-09-26
- **Deciders**: CypherLite maintainers (agreed in conversation)

**Later references**: ADR-0249 retargets the image's runtime from the
bolt-only `cypherlite-bolt` to the unified `cypherlite serve` (Bolt +
HTTP + MCP, ports 7687/7474/7475, one credential); the scratch/chef/
UID 1000/`/data` volume/PID-1-signal decisions here stand unchanged.
ADR-0248 adds the `serve --host` flag the container binds with.

## Decision
Ship a multi-stage `Dockerfile` + a Rust `entrypoint` binary + a
`make docker` target:

- **Build stage**: `rust:1.88-alpine` (the MSRV toolchain on musl), release
  builds of `cypherlite` (full bundle), `cypherlite-bolt`, and the
  `entrypoint` binary. The `.dockerignore` keeps the context to what cargo
  needs. Build speed comes from two pinned tools: **cargo-chef** splits
  dependency compilation into its own layer (`cook` from `recipe.json`,
  package-scoped to the two shipped crates so testing natives stay out) —
  that layer is a cache hit until Cargo.toml/lock change, and layer
  round-trips are the cache mechanism that actually works with the CI's
  `type=local` exporter (cache mounts do not export — measured); and
  **sccache** (version + sha256 pinned) wraps rustc for the workspace
  crates, since cargo's fingerprints are mtime-based and `COPY` refreshes
  every mtime (measured: a restored target cache rebuilt everything).
  Measured locally: full build ~90 s; a source-only change ~13 s. Nothing
  from a cache mount lands in the image — the runtime stage copies the
  binaries out of `/out`. The build runs natively on `rust:1.88-alpine` —
  its host triple
  *is* `x86_64-unknown-linux-musl`, so the binaries are static by default
  with no cross-compiler.
- **Runtime stage**: `FROM scratch` — musl-static binaries only (the
  `cypherlite` full bundle, `cypherlite-bolt`, and a tiny Rust `entrypoint`
  binary, since scratch has no shell), plus the CA bundle at the standard
  path for ureq/rustls. Numeric `USER 1000:1000` (scratch has no
  `/etc/passwd`); the data volume must be writable by that UID.
- **Ports**: `EXPOSE 7687` (Bolt) and `7474` (reserved for the future
  HTTP/Query surface; the server is Bolt-only today).
- **Config resolution, most to least canonical**:
  (1) container args pass straight through to `cypherlite-bolt` (a
  `CMD` default of `--bind 0.0.0.0:7687 --uri /data/graph
  --allow-plaintext`); (2) a mounted
  `/config/seed.json` (path override: `CYPHERLITE_CONFIG`) drives seeding —
  ordered steps (`query`, `load`+`query`, `pull`+`query`), JSON not YAML
  because `serde_json` is in-tree and `serde_yaml` is archived; (3) env
  fallback for one-liners (`CYPHERLITE_QUERY`, `CYPHERLITE_LOAD` +
  `CYPHERLITE_LOAD_QUERY` (the `--load` flag, still on its own unmerged
  PR), `CYPHERLITE_PULL_FROM` + `CYPHERLITE_PULL_QUERY` (ADR-0080),
  `CYPHERLITE_FORCE_SEED`). The
  engine's native env vars (`CYPHERLITE_MEMORY_LIMIT`,
  `CYPHERLITE_DURABILITY_MODE`, `CYPHERLITE_CHECKPOINT_INTERVAL_SECS`,
  `CYPHERLITE_LOAD_CSV_DIR`) pass straight through untouched.
- **Seeding** runs through the plain CLI before the server execs: once when
  the database URI does not exist yet (always for `:memory:`, or with
  `CYPHERLITE_FORCE_SEED=1`), never while the server is live.
- The server is exec'd last, so it is PID 1 and owns the container
  lifecycle (signals, exit codes) — including the SIGINT/SIGTERM handlers
  that make `Ctrl-C` and `docker stop` effective against PID 1.

--- ADR-0249 ---
# ADR-0249: Docker image serves Bolt + HTTP + MCP from one `cypherlite serve` process

Status: Accepted

## Decision
The image's primary runtime becomes **`cypherlite serve`** — one
process, all three surfaces, one credential:

- `CMD ["--host", "0.0.0.0", "--database", "/data/graph", "--bolt",
  "7687"]`. The port map is Bolt 7687, HTTP Query API v2 7474 (the Neo4j
  HTTP convention, already reserved), MCP streamable-HTTP 7475; all three
  are `EXPOSE`d. `--http`/`--mcp` stay out of the CMD on purpose: the
  entrypoint appends their defaults for a single run and derives
  non-overlapping bases under `INSTANCES=N`, which an explicit CMD pin
  would defeat.
- The `entrypoint` binary stays the PID-1 seed-then-serve supervisor
  (ADR-0128) but now execs/supervises `/bin/cypherlite serve`. Its arg
  mapping retargets: `--uri` is a legacy alias of `--database`; `--bind
  HOST:PORT` is a legacy spelling of `--host HOST --bolt PORT` (the
  fleet port base); `--allow-plaintext` is accepted and dropped with a
  note — `serve` is plaintext-only and `--host 0.0.0.0` is itself the
  deliberate, loudly-warned exposure (ADR-0248). When argv omits them,
  the entrypoint appends the image defaults (host `0.0.0.0`, ports
  7687/7474/7475, database `/data/graph`) so the seeded store is the one
  served.
- `INSTANCES=N` fleet semantics are unchanged except the port step now
  applies consistently to all three ports: instance *i* gets base+*i*−1
  on each surface. An unset `--http`/`--mcp` base derives from the bolt
  base so the three stepped ranges can never overlap — bolt B..B+N−1,
  http B+N..B+2N−1, mcp B+2N..B+3N−1 (the adjacent single-run defaults
  7474/7475 would collide under stepping; measured: INSTANCES=2 bound
  instance 2's HTTP onto instance 1's MCP port). Explicitly-set bases
  must be pairwise N apart, a loud startup error otherwise. Per-instance
  suffixed URIs are unchanged.
- Auth is the shared ADR-0232 story: `CYPHERLITE_AUTH` (or `--auth`, or
  the generated token in `docker logs`) is one credential that unlocks
  all three surfaces.
- The `cypherlite-bolt` binary **stays in the image** as the
  single-protocol alternative: it is the only shipped server with TLS
  (`--tls-cert`/`--tls-key`), both binaries are musl-static and ride the
  same cargo-chef layer, so keeping it costs a few MB of scratch-image
  size against losing the TLS-capable path. `cypherlite` stays for
  seeding and ad-hoc queries (`docker exec`).
- Seeding (`/config/seed.json`, env fallbacks) is unchanged — it runs
  `cypherlite` CLI steps before any server starts.

--- ADR-0306 ---
# ADR-0306: Read-only and follow opens for serve and cypherlite-mcp

Status: Proposed
Claim: 24e79bb65278a3d77ada43b582d9324265f528b2

## Decision
1. **`serve` accepts `--read-only` and `--follow` after the verb** —
   post-verb flags like `--host`/`--auth`. `--follow` implies read-only;
   `--read-only --follow` together means follow. A repeated flag is a
   usage error (exit 2), the same once-only policy as every optional
   `serve` flag.
2. **The store opens with `OpenMode::ReadOnly` / `OpenMode::Follow`** —
   the same opens as `cypherlite query` (ADR-0136, ADR-0137). Nothing new
   lands in the engine.
3. **Every served surface shares that one handle.** HTTP, MCP, and Bolt
   ride the one read-only/following `Arc<Database>`; a write fails with
   the engine's read-only error on every surface. The MCP surface sets
   `McpServerConfig.read_only` from the opened handle, so `write-cypher`
   is not listed — an always-failing tool would be a dead end for hosts
   that auto-approve `readOnlyHint` tools.
4. **No final checkpoint runs on shutdown** — the existing read-only skip
   in the shared final-checkpoint policy (`session::final_checkpoint`
   refuses when `db.is_read_only()`).
5. **The startup banner prints one line naming the access mode**
   (read-only or follow) on stderr, with the rest of the banner.
6. **`--read-only`/`--follow` given before the `serve` verb is a usage
   error (exit 2) naming the post-verb spelling.** It must never be
   silently ignored: a silently-writable server is the exact hazard the
   user meant to fence.
7. **The Docker entrypoint (ADR-0249) treats both as valueless flags**
   when passing argv through — forwarded like any other `serve` flag, no
   value consumed and no mapping.
8. **The `cypherlite-mcp` binary's `--read-only` now opens
   `OpenMode::ReadOnly`** (still hiding `write-cypher`), and a new
   `--follow` opens `OpenMode::Follow`, implying read-only.

--- ADR-0368 ---
# ADR-0368: One product binary: serve absorbs the bolt and mcp bins

Status: Accepted

Claim: decb658cbaabb0f999c0aebe15419492464c072d

## Decision
`cypherlite serve` is the one product binary for serving a CypherLite store
(LABS-381):

1. **Retire the standalone `cypherlite-bolt` and `cypherlite-mcp` bins.**
   Both crates stay exactly where they are — `surfaces/cypherlite-bolt`
   owns the Bolt protocol, transport, TLS, and PackStream;
   `surfaces/cypherlite-mcp` owns the MCP server and both its transports —
   and all their tests stay. `cargo build -p cypherlite-bolt` /
   `-p cypherlite-mcp` builds the libraries. The Docker `entrypoint` bin
   (ADR-0128) stays: the scratch image still needs its seed-then-exec
   PID-1 supervisor, and it execs `cypherlite serve` (ADR-0249).
2. **`serve --mcp` takes the stdio transport too**: `--mcp stdio` or
   `--mcp PORT`, a typed union (`McpMode::Stdio | McpMode::Http(u16)`),
   not a port-shaped string. `stdio` runs the MCP stdio transport in the
   foreground — newline-delimited JSON-RPC on the process's stdin/stdout
   until the host closes stdin, then the final checkpoint and a clean
   exit 0 — after every listener surface is spawned. Stdio skips the auth
   story entirely (ADR-0232 §1); an explicit `--auth` on a stdio-only run
   is a loud usage error, not an ignored flag, and no token file is
   persisted. The once-only policy rejects combining the two transports.
   `--mcp PORT` (streamable HTTP) is unchanged.
3. **The bolt e2e harness drives the crate's own `serve(&Args)` listener
   in-process** (a thread of the test process, the same flag vocabulary
   through `cli_args::Args`): the flags serve does not carry — TLS,
   `--no-websocket`, the handshake/idle/query timeouts — keep their
   coverage through the library entry point instead of a product process.
   The MCP crate's stdio e2e drives `serve_stdio` over a real duplex
   stream in-process, and the CLI's own e2e suite spawns
   `cypherlite serve --mcp stdio` as a child — the product path an MCP
   host actually spawns.
4. **The Docker image carries `cypherlite` and `entrypoint` only.** The
   image loses the TLS-capable `--entrypoint /bin/cypherlite-bolt`
   alternative: serve has no TLS, so an encrypted-Bolt deployment fronts
   the container with a TLS-terminating proxy.

Capabilities the standalone bolt binary uniquely exposed — TLS
(`--tls-cert`/`--tls-key`/`--tls-client-ca`), `--load-csv-dir`,
`--no-websocket`, `--ws-allow-origin`, `--allow-plaintext`, the
`--handshake/--idle/--query-timeout-secs` limits, `--max-result-bytes`,
and the storage knobs (`--memory-limit`, `--checkpoint-interval-secs`,
`--durability-mode`, `--wal-dir`) — have no product-binary surface after
this ADR. They remain library-level (embed `cypherlite_bolt::serve`) and
stay covered by the crates' own tests; giving serve any of them is a
future ADR, not a silent flag here.

--- ADR-0232 ---
# ADR-0232: Network surfaces charter — shared auth, Query API v2 subset, MCP transport

Status: Accepted

## Decision
### 1. One shared auth story

All HTTP-bearing network surfaces (Query API v2 endpoint, MCP over
HTTP) use **generated-token basic auth, identical in kind to the Bolt
surface (ADR-0126)**:

- resolution order: `--auth user:password` flag wins, then
  `CYPHERLITE_AUTH=user:password`, else a generated token printed at
  startup and persisted as a `<dir>.auth-token` sibling (mode 0600,
  fresh per start for `:memory:`);
- `none` disables authentication (the zero-config story);
- a present-but-malformed value is a loud startup error, never a silent
  fallback;
- credential comparison is constant-time, as in Bolt's `auth.rs`.

On the wire, HTTP surfaces carry the credential as an RFC 7617
`Authorization: Basic` header; MCP over stdio skips the challenge
entirely (the parent process spawned the server — there is no trust
boundary to cross). The *credential itself* — one user, one password or
generated token — is the same across surfaces, so a single printed
token unlocks Bolt, HTTP, and MCP-HTTP alike.

### 2. Where the shared auth code lives

The Bolt `auth.rs` mechanism is **extracted into a new small surface
crate, `surfaces/cypherlite-auth`** (package name `cypherlite-auth`),
exporting `AuthConfig` (resolution, persistence, constant-time check)
with no HTTP- or Bolt-specific types. `cypherlite-bolt`, the HTTP Query
API surface, and the MCP surface each depend on it and adapt its
`check` to their wire shape (HELLO map vs `Authorization` header). The
crate is a pure adapter of engine-neutral logic: it stays in
`surfaces/` per R3, and the engine never sees it.

### 3. Query API v2 statement-endpoint subset

Exactly one route, the auto-commit statement endpoint:

- **Route:** `POST /db/{databaseName}/query/v2` (the `/db` prefix keeps
  the path distinct from any future root-level endpoint; the
  `{databaseName}` is validated against the ADR-0116 fixed namespaces
  and an unknown name fails).
- **Request fields:** `statement` (string, required), `parameters`
  (object, optional, `$name` bindings), `includeCounters` (boolean,
  default false). Nothing else — no `accessMode`, no `impersonatedUser`,
  no `maxExecutionTime`, no `txConfig`.
- **Response envelope (success):** `data.fields` (column names),
  `data.values` (rows of wire-JSON values per ADR-0223), `bookmarks`
  (empty array — no bookmark manager), and `counters` (stats counters
  in the snake_case vocabulary, present when `includeCounters` is true
  or the statement updated the graph).
- **Error envelope:** `{"errors":[{"code","message"}]}` with the
  GQLSTATUS-style codes the engine already produces (e.g. `42N00` for
  an unknown database), mirroring the Bolt trust-boundary sanitization
  of ADR-0260.

Explicitly **out** per the user's instruction: no routing headers or
server-discovery endpoint, no transaction persistence (`POST /tx`,
`tx/{id}` begin/commit/rollback are not implemented and return 404),
no multi-statement batching, no profiled-query format negotiation.

### 4. MCP transport and SDK

**Both stdio and streamable HTTP.** Streamable HTTP is required because
the `cypherlite serve --mcp PORT` flag implies a network listener, and
it matches the reference server's default for Docker deployments.
stdio is required because the dominant MCP hosts (Claude Desktop,
Claude Code) spawn servers as child processes over stdio, and the
reference server supports it; an HTTP-only server would be unusable for
the local-agent case that motivates LABS-299. Legacy SSE transport is
not impleme

==================== TASK T11 ====================
Task: Add a CLI verb that snapshots a native database directory into a single-file bundle and back.

Context retrieved for this task: the decision records of the repository, as written.

--- ADR-0159 ---
# 0159. Snapshot round trip between a native directory and a `.cl` bundle

- **Status**: Accepted
- **Date**: 2026-10-03
- **Deciders**: CypherLite maintainers (Linear LABS-167)

## Decision
1. **One new CLI lifecycle verb `snapshot`.** Following ADR-0069, it is an
   exit-after positional command recognized only as the first argument.
   Its single positional argument is the native directory `DATABASE`, and
   exactly one of two direction flags is required:
   - `cypherlite snapshot DATABASE --to FILE.cl` exports a native
     directory database to a single-file `.cl` bundle.
   - `cypherlite snapshot DATABASE --from FILE.cl` imports a `.cl` bundle
     into a fresh native directory `DATABASE`.
   - `--wal-dir DIR` is allowed only with `--to` (the external WAL of the
     directory source, mirroring `clone`); combining it with `--from` is a
     usage error. Usage errors exit 2; runtime errors exit 1, mirroring
     `clone` and `pull`.
2. **The source is always opened read-only via the ADR-0136 path**
   (`OpenMode::ReadOnly` / `open_store_readonly`): stable-cut manifest
   retry, bounded reads, fail-closed on corruption. The command never
   writes to or exclusively locks the source. A writer-held `.cl` source
   fails with a lock error, since a bundle writer holds `LOCK_EX` on the
   host file (ADR-0136).
3. **The destination must not exist** — the same contract as `clone`
   (ADR-0156). A failed run removes any partially created destination,
   file or directory.
4. **The destination keeps the source's snapshot codec in both
   directions** — json stays json, parquet stays parquet. There is no
   codec conversion.
5. **Engine: two new public `Database` methods.**
   `snapshot_to_bundle(source, dest, SnapshotOptions)` and
   `restore_from_bundle(source, dest, SnapshotOptions)` generalize the
   `clone.rs` publish path across the dir/`.cl` boundary. `SnapshotOptions`
   carries `wal_dir: Option<PathBuf>`, used only by `snapshot_to_bundle`.
6. **The command is compiled into every CLI bundle like `clone` — no new
   Cargo feature.** This deviates from the ADR-0104 rule that a new
   capability gets its own feature: snapshot/restore is as fundamental to
   moving data as clone, adds no dependencies, and keeping it
   always-available avoids a bundle in which a user's backup tool
   vanishes.

--- ADR-0074 ---
# 0074. Single-file bundle VFS selected by `.cl` path

- **Status**: Accepted
- **Date**: 2026-09-21
- **Deciders**: CypherLite maintainers

## Decision
1. **One host file.** Dual superblocks, the inode catalog, WAL extents,
   and snapshot objects live in a single regular file. No sidecar
   `-wal`/`-shm`, no OS `wal/` directory, no OS `.tmp` files. Virtual
   `{path}.tmp` is an inode in the same container; `atomic_write` rename
   is a catalog pointer swap.

2. **URI selection.** After stripping `file://`, if the path ends with
   `.cl` (ASCII, case-insensitive, ignoring a trailing `/` or `\`) the
   engine opens `BundleVfs`. Every other filesystem URI stays
   `NativeVfs`. `:memory:` is unchanged. No `bundle://` scheme.

3. **Create vs open.** A missing `foo.cl` creates a new container.
   An existing **directory** named `*.cl` is an error. An existing
   regular file without bundle magic is an error.

4. **`OpenOptions.wal_dir` is rejected** on `.cl` URIs. A second host
   WAL would break “one file.”

5. **Durability (ADR-0077).** The container fd uses the same platform
   barrier as Native (`fdatasync` / `F_BARRIERFSYNC` / `sync_all`).
   Group-commit `durability_barrier` writes WAL tail pages, then a
   superblock generation (WAL-tail shortcut: inode id + logical length +
   file page count). Catalog pages are rewritten only when extents or
   names change (create, rename, delete, rotate’s new segment). Crash
   recovery takes the higher valid superblock checksum; unreachable pages
   join the freelist.

6. **Not in this change:** shrink/compaction, mmap as source of truth,
   OPFS, object-store VFS.

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

--- ADR-0496 ---
# ADR-0496: Run from URL — `--database` accepts a remote `.cl` bundle

Status: Proposed

Claim: 0b48269065bae51d75ccb7269b7e1901e66764dc

## Decision
1. **`--database` accepts an `http(s)` URL** naming a `.cl` single-file
   bundle. Detection is the scheme prefix, ungated (ADR-0104, ADR-0270), so
   every build parses a URL `--database` and every policy refusal below
   applies in every build; only the fetch is feature-gated. Every value that
   is not an `http(s)` URL keeps today's plain local-path behavior exactly.
2. **A GitHub file URL is rewritten** to its
   `raw.githubusercontent.com/<owner>/<repo>/<ref>/<path>` form — both the
   shareable **blob** page link people paste and GitHub's own **raw** verb
   (which would otherwise 302 there), so the bytes arrive in one request.
   Every other host (a raw URL, a loopback test server, anyone else's file
   host) is fetched unchanged, and **redirects are followed** (ureq's
   default chain), so a release-asset URL or any other `30x` that lands on
   the bundle bytes works.
3. **The URL must name a `.cl` file, and folder URLs are refused before any
   fetch**, with the working form named in the error: a repository URL, a
   `tree` URL, a non-`blob` verb, a blob URL with no file path, and a URL
   whose last path segment does not end in `.cl` (query and fragment
   stripped). A remote **native directory** is not supported: it is a
   multi-file layout with its own WAL protocol, and a `.cl` bundle is the
   one self-contained artifact. **`https://` is required for any host;
   plain `http://` is accepted only for a loopback host** (`localhost`,
   `127.0.0.0/8`, `::1`) — the e2e fixtures and a local dev server — and
   refused otherwise with the `https://` form named. There is no
   `--allow-plaintext`-style opt-in here (unlike `pull`, ADR-0122): a
   database fetched over plaintext arrives unverified on a transport anyone
   on the path can rewrite, and this fetch has no signature story either.
   The policy is enforced across **redirects** too: every `https://` fetch
   pins `https_only` on its client (the LABS-470 pin the release channel
   carries), so a `302` cannot downgrade the transport past the scheme the
   URL already passed. The loopback plain-`http` carve-out is the one
   release — there the pin would refuse the first hop — and a local server's
   own redirects are the local server's trust.
4. **The CLI fetches and stages.** One capped GET (1 GiB, 300 s global)
   through the shared `url_fetch` helper the `--fetch-params` fetch also
   rides — its **streaming** form (`get_into`), so the body goes straight to
   the staged file through a fixed-size buffer and a bundle at the cap never
   lives in RAM (`--fetch-params` keeps the buffered form, since it parses
   the document in memory); the bytes are written to a private temp path named by the shared
   `atomic_file::staging_name` recipe (pid + counter + nanosecond clock) with
   the `.cl` suffix, created `create_new` and `0o600` from birth.
   A **scratch** copy (a read-only open) is registered for cleanup before its
   first byte lands and removed on every post-parse exit (`exit_flushed`;
   `process::exit` skips destructors); a **kept** copy (a writable open)
   never registers, so nothing removes it. A failed fetch removes its own
   partial file directly — the rollback belongs to the fetch that owns the
   failed file, whatever the disposition of a download that never
   completed. The engine then opens the staged path through the ordinary
   `.cl` bundle route — codec, superblock, and embedded WAL are the store's
   own, not a remote variant.
5. **A downloaded copy is 

--- ADR-0136 ---
# 0136. Frozen read-only open beside a native writer

- **Status**: Proposed
- **Date**: 2026-09-29
- **Deciders**: CypherLite maintainers

## Decision
1. **Identity lock is shared; the writer lease is exclusive.** Every live
   native opener takes `LOCK_SH` on the existing root `.cypherlite.lock` and,
   when the WAL directory is distinct, on its `.cypherlite.lock`, for the
   life of the process. A writable open also creates and exclusively locks
   a stable `.cypherlite.writer` beside each of those markers. The writer
   file is mode `0600` when newly created, is never unlinked on close, and
   is not a database identity: nested scans still key only on
   `.cypherlite.lock` and `.cl`. A second writable open fails that lease
   with `Error::Locked`. Reset and offline adoption keep `LOCK_EX` on
   `.cypherlite.lock`, which conflicts with every shared holder. On Windows
   a shared `LockFileEx` rejects `WriteFile` on the owning handle, so a
   first open writes the role bytes under a brief exclusive lock and then
   returns to `LOCK_SH`. Identity checks open the marker for file
   attributes only, because a second read of a locked range returns
   `ERROR_LOCK_VIOLATION`. A read-only open accepts a root marker of
   `ROOT` or an empty marker on a directory that already has root
   evidence and rejects a WAL role or any other bytes, and after the
   Windows upgrade back to `LOCK_SH` the opener checks identity again
   and returns `Error::Storage` if the directory changed.
2. **Read-only open does not create or repair.** `OpenMode::ReadOnly`
   and CLI `--read-only` open an existing native directory or `.cl` file.
   A missing store is `Error::Storage` and creates nothing: no directory,
   marker, segment, or writer lease. The native reader opens markers
   read-only and takes only the shared identity locks. A `.cl` reader
   takes `LOCK_SH` on the existing host file; the writer still holds
   `LOCK_EX` on that file, so a bundle reader and a bundle writer do not
   run together. `:memory:` with `read_only` is a write fence and takes
   no file lock.
3. **The loaded graph is a snapshot.** Read-only open loads the manifest
   and shards, replays complete WAL frames, and stops at a torn tail
   without truncating it. If the manifest bytes change during the load,
   or a read fails because a checkpoint removed a file mid-load, the open
   retries a bounded number of times and then returns `Error::Storage`.
   After a stable load the process does not read the files again.
   Migrate-on-open, orphan sweep, checkpoint timers, the durability
   timer, and persist-on-drop do not run. Legacy snapshots are served
   through the legacy reader and are not rewritten (ADR-0127).
4. **Mutations fail.** `try_wal_commit`, `checkpoint`, and
   `apply_replicated` return `Error::Semantic` (`database is read-only`).
   Reads stay available.