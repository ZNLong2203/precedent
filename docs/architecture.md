# Architecture

```
src/precedent/
  model.py        dataclasses: Decision, Clause, Unit, Citation, Treatment, PathRef, Corpus
  parse_adr.py    markdown records -> Decision / Clause / Unit
  treatments.py   prose -> Citation / Treatment (rules, evidence, confidence)
  paths.py        backticked repo paths -> CodePath, checked against `git ls-files`, rename-aware
  standing.py     grounded-semantics standing (pure functions, no I/O)
  lsa.py          offline TF-IDF + SVD embeddings (numpy)
  graph.py        Relate schema, loader, Store wrapper, load_model(), write_back()
  indexer.py      parse -> extract -> standing -> graph.build()
  api.py          status / search / preflight / explain over a store (JSON-able dicts)
  lint.py         cite-check categories (Cypher over the standing graph)
  guard.py        propose(): transactional review of a draft decision, fork on read-only stores
  overlaps.py     find_overlaps(): which clauses does a draft overlap? (ranking, no model)
  headers.py      fix-status: stale status lines -> one-line diffs, verified not to change any verdict
  mcp_server.py   MCP tools (async, in-process store)
  webexport.py    store -> docs/data/graph.json for the browser explorer
  cli.py          `precedent` command
docs/             GitHub Pages: index.html + assets/app.js run Relate-WASM; methodology/evaluation pages
data/             relate-adr.rl (the persistent store), LSA basis, gold audit
```

Everything above `graph.py` is pure Python over dataclasses; `graph.py` is the only module that knows Relate's driver, and `api.py` the only one that writes Cypher for reading. The browser explorer repeats the same Cypher against Relate compiled to WebAssembly.

## One graph, four surfaces

| surface | how it opens the store |
|---|---|
| CLI (`precedent …`) | in‑process, `read_only=True` |
| MCP (`precedent mcp`) | in‑process, read‑only by default; `--writable` for `propose_decision(commit=true)` |
| Relate's own tools (`relate`, `relate serve`) | the same `.rl` file — Bolt / HTTP / MCP |
| Browser | `graph.json` exported from the store, loaded into `@relate/relate-wasm` (`:memory:`, JSON codec) |

## Notes from building on Relate 1.0.1

Things we hit that other builders may want to know (all verified, none are complaints — the engine did what its docs say):

* **A writer excludes everyone, readers included.** Opening a store writable makes a second process fail with `storage locked`, even `read_only=True`. Many readers at once are fine. We surface this as a typed `StoreLocked` with advice, and keep the CLI and MCP read‑only unless asked.
* **Connections are thread‑affine** (`threadsafety = 1`, enforced). The Python MCP SDK runs synchronous tools on worker threads, so every Precedent tool is a coroutine and runs on the event‑loop thread that opened the store.
* **A `.rl` file is a complete fork.** Copying it yields an independent, writable graph — cheap what‑if sandboxes.
* **`SEARCH … FOR e`** accepts a stored vector (a property carried through `WITH`) as the query, which is how "More like this" works with no query embedding at all.
* **Full‑text cost scales with indexed bytes.** Indexing a compact `search_text` instead of the whole record halved search latency (47 → 25 ms before stop‑word removal).
* **`ORDER BY` after aggregation needs the key projected** (`RETURN s.id, s.num AS num, collect(...) ORDER BY num`); the error is explicit and easy to fix.
* **Python rows** are dict‑like; `Vector` values expose `.values`.
* The WASM build ships the whole engine — full‑text, vector `SEARCH`, `shortestPath`, constraints — so the browser can run the exact same Cypher as the backend.
