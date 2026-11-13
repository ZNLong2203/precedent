# Method

How a directory of markdown decision records becomes a graph of *standing*. Every example sentence below is quoted from `relatedb/relate` `docs/adr` (Apache‑2.0) at commit `1ebb65e`.

```
 NNNN-title.md ──parse──▶ Decision, Clause, Unit ──extract──▶ Citation, Treatment (+evidence)
                                                    │
        git ls-files ──paths──▶ CodePath ───────────┤
                                                    ▼
                                   standing (grounded semantics) ──▶ Relate store (.rl)
                                                                         │
                          status · preflight · search · cite-check · propose · MCP · browser
```

## 1. Parsing ([`parse_adr.py`](../src/precedent/parse_adr.py))

* **Header**: `- **Status**: Accepted` / `Status: Accepted` / a `## Status` section; `Date`; the title.
* **Sections**: `Context`, `Decision`, `Consequences`, `Alternatives considered`, `Later references`.
* **Clauses**: top‑level numbered items of `## Decision` (`1. **Three fixed namespaces.** …` or `### 1.`), accepted only while numbering is strictly increasing so nested lists don't leak in. 322 of 533 records have them (1 591 clauses). A clause is the unit of standing — the way case law overrules a *holding*, not a whole case.
* **Units**: every paragraph / list item, tagged with its section and clause. Treatments are extracted per unit so the evidence is always one sentence.

## 2. Treatments ([`treatments.py`](../src/precedent/treatments.py))

A **treatment** is "decision A does something to decision B". Kinds: `SUPERSEDES`, `REVERSES`, `WITHDRAWS` (*negative* — they can take a clause out of force), `AMENDS`, `REINSTATES`, `AFFIRMS` (recorded, never negative). Each carries `scope` (`clauses` / `whole` / `partial` = "an unspecified part"), `evidence` (the sentence), `rule`, `confidence`.

| rule | fires on | example | conf. |
|---|---|---|---|
| `status-superseded` / `status-in-part` | `Status: Superseded [in part] by ADR-0013` | `Status: Superseded in part by ADR-0012` | .95 |
| `header-*` | `- **Amends**: ADR-0046` | | .95 |
| `later-actor-verb` | a **Later references** sentence `ADR‑A <verb> …` (the section is, by convention, written about the record it sits in) | *ADR‑0183 supersedes Decision 3's one part per clean run … Decisions 1 and 2 stand.* | .80–.90 |
| `later-passive-by` | `… is superseded by ADR‑A` | | .85 |
| `body-this-verb` | `This ADR supersedes ADR‑X §n` | *This replaces ADR‑0172 §1's drain‑on‑entry.* | .80 |
| `body-passive-this` | `ADR‑X's … is superseded by this ADR` | *ADR‑0492's Decision paragraphs 1 and 3 … are superseded by this ADR* | .80 |
| `body-later-actor` | `ADR‑A supersedes item 2's …` inside the *older* record | *ADR‑0359 supersedes item 2's engine‑side composition…* | .65 |
| `body-passive-implicit` | `ADR‑X's … is superseded.` (no actor: the deciding record acts); supports lists `ADR‑0011 / ADR‑0012 …` | *ADR‑0015's "clone the committed graph" execute step is superseded.* | .60 |
| `body-participle-by` / `body-later-note` / `body-imperative` / `body-named-verb` | `(retired by ADR‑A)`, `(later reversed: ADR‑A …)`, `Supersedes ADR‑X.`, `ADR‑A supersedes ADR‑B` | | .60–.70 |

**Scope.** `ADR‑0229 supersedes §1's … and §4's … ; §5's …` → `clauses = [1,4,5,7,10]`. No clause named → `partial`. `whole` only when the record itself is the object, stands alone (`supersedes ADR‑0012.`), or a status line says so — *"ADR‑0330's Pages‑deploy chain … superseded in full"* is a part of ADR‑0330, so it stays `partial`.

**Precision over recall.** A wrong "superseded" is worse than a missed one, so these are ignored for treatments: the *Alternatives considered* section (rejected options), hedged / negated text (`would`, `not`, `nothing is superseded`), verbs inside `` `code` `` or hyphenated compounds (`self‑replace`), upper‑case query keywords (`DROP INDEX`), the adjective in "**retired** pages", the pronoun "it", and clause numbers used for comparison (`the way §3 probes`), listed as exceptions (`except §2`) or said to *stay* (`§1 … stays`). Removal verbs (`removes`, `drops`) count as a partial *withdrawal* in Later references unless the object is a cost.

## 3. Standing ([`standing.py`](../src/precedent/standing.py)) {#standing}

Treatments are **attacks** in a Dung‑style argumentation framework; standing is the **grounded extension**. Claims are `(decision, clause)` plus a virtual claim "some unspecified part".

1. A claim nobody attacks is **in force**.
2. A claim is **out of force** if some attacker is *certainly alive* — at least one of the attacker's own claims is in force.
3. A claim is **restored** if every attacker is *certainly dead* — all its claims are out of force, or it was never accepted (`rejected` / `withdrawn`).
4. What remains (mutual attacks, cycles) is **contested** — reported, never resolved arbitrarily.

Iterate 1–3 to a fixpoint (a few passes). Consequences, all covered by unit tests:

* *A supersedes B, then C reverses A* ⇒ A is out and **B is good law again** (`restored`). No special case.
* *A supersedes B and B supersedes A* ⇒ both **contested**.
* A decision attacked only in clause 2 keeps its other clauses; as an attacker it stays alive through them.
* A treatment whose actor is **dated before** its target is ignored and reported (renumbering, typos). On the corpus: 0 of 184 dated treatments.

Worked example — ADR‑0116, declared *Accepted*:

| clause | status | why |
|---|---|---|
| §1 Three fixed namespaces | ✗ | ADR‑0229 supersedes §1 |
| §2 Administration commands follow CE | ✓ | |
| §3 `USE` routes a statement | ✓ | |
| §4, §5, §7, §10 | ✗ | ADR‑0229 |
| §8 Settings stay in the existing catalog | ✗ | ADR‑0276: *"§8's placement sentence … is superseded by this ADR; its format and invariant statements stand."* |
| §9 Errors | ✗ | ADR‑0307: *"ADR‑0116 §9, ADR‑0117 §7, … are superseded the same way."* |

Result: `partial`, `out_clauses = [1,4,5,7,8,9,10]`, `controlled_by = [ADR‑0229, ADR‑0276, ADR‑0307]`.

## 4. Retrieval and preflight ([`api.py`](../src/precedent/api.py))

* **Search** fuses three rankings with reciprocal‑rank fusion: BM25 on decisions (`title` + `search_text`), BM25 on clauses, and cosine on 96‑d **LSA** vectors (TF‑IDF + truncated SVD — offline, deterministic, no model download). Vectors are stored in Relate's native vector index; the query is projected with the stored basis.
* **Preflight** seeds candidates from (a) decisions that `REFER_TO` the given paths (exact, renamed, or enclosing directory, weighted by where the path is mentioned: Decision 1.0 … Context 0.5) and (b) hybrid search on the task; down‑weights stale decisions (×0.35 out, ×0.85 partial); **pulls in the controlling decisions** of every stale one, naming exactly the clauses each took; and fills cards (live clauses, stale clauses with `by`, the quoted evidence) until the token budget.
* **Paths**: backticked repo paths are checked against `git ls-files`. Historical names are resolved by a configurable rename (`cypherlite→relate`) and then a *unique* suffix match; ambiguous matches are refused. 361 of 697 mentioned paths were resolved this way; 218 are gone.

## 5. The guard ([`guard.py`](../src/precedent/guard.py))

`propose` opens a transaction, writes the draft (node, treatment and citation edges, vector), reloads the model from the **uncommitted** graph, recomputes standing, diffs it against the pre‑state, checks the invariants below, and commits or rolls back. On a read‑only store it forks the `.rl` file and works on the copy. The returned markdown uses sentences the extractor itself recognises — re‑indexing the saved ADR reproduces the same edges (tested).

| code | severity | means | fix it suggests |
|---|---|---|---|
| `unknown-target` / `unknown-clause` | error | the id or clause does not exist | check with `search_decisions` |
| `cites-out-of-force` | error | you cite a clause that is already overruled | cite the controlling decision |
| `impact-unacknowledged` | error | live decisions rely on what you overrule | review them, then `acknowledge_impact=true` |
| `creates-contest` | error | the draft makes decisions mutually conflicting | decide which side stands |
| `already-out-of-force` | warning | you are overruling something already gone | cite the controller |
| `possible-duplicate` | warning | ≥ 85 % vector similarity, neither cited nor treated | read it, cite or supersede |
| `unknown-path` | warning | no decision mentions that path | fine for new code |

## 6. What is not modelled

Dates inside prose, partial supersession *within* a clause, supersession by something that is not a decision record (a code change, an issue), and anything phrased without a treatment verb ("no longer", "instead of" are known misses).
