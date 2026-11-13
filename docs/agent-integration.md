# Agent integration

Precedent speaks **MCP** over stdio (an in‑process Relate store — no ports, no Relate server) and ships a **Claude Code skill**.

## Claude Code

```bash
git clone https://github.com/ZNLong2203/precedent && cd precedent && uv sync
claude         # the repo's .mcp.json registers the `precedent` server; approve it when asked
```

or add it to any project:

```bash
claude mcp add precedent -- uv --directory /path/to/precedent run --quiet precedent mcp --store data/relate-adr.rl
mkdir -p ~/.claude/skills && cp -r skills/precedent ~/.claude/skills/        # optional: the skill
```

Writable mode (so `propose_decision(commit=true)` can record decisions) is opt‑in: `precedent mcp --writable`.

## Tools

| tool | read‑only | what it gives the agent |
|---|---|---|
| `preflight(task, paths, budget_tokens, limit)` | ✓ | decisions to respect, stale clauses flagged, controlling decisions pulled in, ≤ budget tokens |
| `decision_status(decision)` | ✓ | clause‑level standing, treatments with quoted evidence, who relies on it, code paths |
| `search_decisions(query, limit)` | ✓ | hybrid BM25 + vector, each hit with its standing |
| `explain_link(a, b)` | ✓ | shortest path of citations / treatments |
| `cite_check(categories, limit)` | ✓ | stale statuses, reliance on dead clauses, ghost paths … |
| `graph_schema()` / `query_graph(cypher)` | ✓ | schema + a **read‑only** Cypher escape hatch (writes are refused; rows are capped and say so) |
| `find_overlaps(draft, paths, limit)` | ✓ | for a draft decision: clauses it would overrule (still binding) and ground already out of force (cite the replacement); a `treats` template to edit |
| `propose_decision(...)` | dry run by default | the guard: errors with `fix`, warnings, standing changes, dependents, ADR markdown |

Errors are written for the model: `decision_status("ADR-9999")` → *"ADR‑9999 is not in this store; use `search_decisions` to find the id"*; a bad draft → `cites-out-of-force … fix: cite ADR‑0005 instead`.

## What the agent actually sees

`preflight("add support for creating and switching between multiple databases")` (real output, trimmed):

```json
{
  "decisions": [
    { "id": "ADR-0276", "title": "Store-level databases catalog", "standing": "in_force",
      "why": ["matches task (fulltext+vector)", "controls ADR-0116 (§8)"] },
    { "id": "ADR-0229", "title": "Remove the `system_ontologies` Cypher surface", "standing": "in_force",
      "why": ["matches task (fulltext+vector)", "controls ADR-0116 (§1, §4–5, §7, §10)"],
      "live_clauses": [{ "n": 1, "title": "Listed, not queryable" }, { "n": 2, "title": "The error" }, "…"] },
    { "id": "ADR-0142", "standing": "partial", "stale_clauses": [{ "n": null, "by": ["ADR-0152"], "note": "a part is superseded by ADR-0152" }], "…": "…" },
    { "id": "ADR-0152", "standing": "in_force", "why": ["controls ADR-0142 (a part)"], "…": "…" },
    { "id": "ADR-0116", "title": "Fixed namespaces with Neo4j Community Edition database semantics",
      "standing": "partial", "declared_status": "accepted",
      "stale_clauses": [
        { "n": 1, "title": "Three fixed namespaces", "by": ["ADR-0229"], "note": "§1 'Three fixed namespaces' superseded by ADR-0229" },
        { "n": 8, "title": "Settings stay in the existing catalog", "by": ["ADR-0276"], "note": "…" },
        { "n": 9, "title": "Errors", "by": ["ADR-0307"], "note": "…" }, "…"
      ],
      "evidence": [{ "by": "ADR-0229", "treatment": "SUPERSEDES", "clauses": [1, 4, 5, 7, 10],
                     "quote": "ADR-0229 makes `system_ontologies` listed but not queryable: §1's \"Readable with ordinary Cypher\" and §4's 42N18 write gate are superseded — every statement routed there except §2's administration commands now fails with 42N17 …" }] }
  ],
  "warnings": [
    "ADR-0142 is partly superseded: a part is superseded by ADR-0152",
    "ADR-0116 is partly superseded: §1 'Three fixed namespaces' superseded by ADR-0229"
  ],
  "omitted": 12,
  "tokens": 1447,
  "how_to_read": "live_clauses are good law; stale_clauses were taken out of force by the decision named in `by` - follow that decision instead."
}
```

Without Precedent the agent would find ADR‑0116 first (it is the best textual match), read "Accepted", and design against three fixed namespaces that ADR‑0229 and ADR‑0276 have since changed.

## Writing a decision: find the overlaps, then let the graph review

An agent drafting a decision can go wrong two ways: overrule a clause without saying so (the old record then claims to be in force), or build on a clause that is already dead. `find_overlaps` takes the draft text and answers both, at clause level. The agent does the language; Precedent never calls a model.

```bash
uv run precedent overlaps "Allow creating and dropping additional databases at runtime instead of the three fixed namespaces"
```

```
◐ ADR-0116 Fixed namespaces with Neo4j Community Edition database semantics   ◐ PARTLY SUPERSEDED
   §3 `USE` routes a statement                0.46  binds
   §6 SHOW output is real                     0.41  binds
   §8 Settings stay in the existing catalog   0.40  out of force by ADR-0276
   §1 Three fixed namespaces                  0.40  out of force by ADR-0229
   Your draft overlaps §3, §6, which still bind. … Already out of force: §1, §8 (by ADR-0229, ADR-0276) - cite that instead.
```

It returns a `treats_template` (edit `kind`, `clauses`, `reason`) to hand to `propose_decision`. It is a ranking, not a ruling: on 55 known overrulings the overruled decision is in the top 8 candidates 76 % of the time ([evaluation](evaluation.md#5a-overlap-finder)), so treat a miss as possible.

## Overruling a decision, safely

`propose_decision` is the only write path, and it is a *review*: it writes the draft into the graph inside a Relate transaction, recomputes standing on the uncommitted state, and rolls back unless `commit=true` **and** nothing is wrong (on a read‑only server it forks the `.rl` file instead).

```bash
uv run precedent propose examples/proposal-multi-tenant.json
```

```
verdict: rejected   (simulated in fork)
✗ impact-unacknowledged  2 live decision(s) rely on what this draft overrules: ADR-0227, ADR-0229
   fix: review them (use `decision_status`), amend them in the same draft, then resubmit with acknowledge_impact=true
what changes if this lands:   ADR-0116  ◐ PARTLY SUPERSEDED → ◐ PARTLY SUPERSEDED   §1, §3–5, §7–10   ADR-0590 new
```

## Other agents and tools

* **Relate's own MCP** (`relate serve --database data/relate-adr.rl --read-only --mcp 7475`) exposes `get_schema`, `read_cypher`, `write_cypher` over the same file — Precedent's server is the intent‑level layer above it.
* **Neo4j Browser / drivers**: `relate serve … --bolt 7687`, then `bolt://localhost:7687` (no auth with `--auth none`, local use only).
* **CI**: `uv run precedent cite-check --fail-on-warn --store your.rl` fails a build on stale statuses, reliance on superseded clauses and the like.
* **Fixing the stale statuses it finds**: `uv run precedent fix-status --diff | git -C your-repo apply` writes `Superseded in part by ADR-0229 (§1, §4–5)` into each stale header (`--write --repo your-repo` edits in place). Suggestions resting on a weaker edge are marked; review the diff like any other change.
