---
name: precedent
description: Check whether architecture decisions (ADRs/RFCs) are still good law before changing code or designing something. Use when the task touches a codebase that keeps decision records, when asked "why is it like this", before overruling an earlier decision, or when drafting a new ADR.
---

# Precedent — decisions are case law

Decision records are immutable, so later decisions supersede, reverse or withdraw *parts* of earlier
ones while the old header still says "Accepted". Never act on a decision's text alone.

## Before you change code or design something

Call the `precedent` MCP tool `preflight` with the task and/or the files you will touch:

```
preflight(task="add support for creating and switching between multiple databases",
          paths=["relate/relate-storage/src/wal.rs"])
```

- `live_clauses` are binding. Respect them.
- `stale_clauses[].by` names the decision that replaced a clause: follow *that* decision.
- A `warnings` entry means you were about to rely on something that is out of force.

No MCP? Use the CLI instead: `uv run precedent preflight "<task>" -p <path> --json`.

## Understanding one decision

`decision_status("ADR-0116")` → clause-by-clause standing, who treated it, the quoted sentence that
says so, and the later decisions that still rely on clauses now out of force.

## When your change should overrule a decision

Do **not** edit the old record. Draft a new one and let the graph review it:

```
propose_decision(title=..., body=..., treats=[{target:"ADR-0116", kind:"SUPERSEDES", clauses:[3], reason:"..."}],
                 cites=[{target:"ADR-0229", clauses:[1]}])
```

It is a **dry run** by default and returns `errors` (each has a `fix`), `warnings`, the decisions whose
standing would change, and `dependents` — live decisions that rely on what you overrule. Resolve every
error, mention the dependents in your explanation, then resubmit with `acknowledge_impact=true`.
Save the returned `markdown` as the new ADR. Commit (`commit=true`) only when the user asks.

## Anything else

`search_decisions`, `explain_link(a, b)`, `cite_check()` and read-only `query_graph(cypher)`
(see `graph_schema()` for labels and example Cypher).
