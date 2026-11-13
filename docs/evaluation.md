# Evaluation

Everything below is reproducible: `make eval` (numbers) and `make data-check` (the store rebuilt from the pinned upstream commit has identical content). Corpus: `relatedb/relate` `docs/adr` at commit `1ebb65e` — 533 records. No model is called anywhere.

> **Read this first.** The extractor is rule‑based and was tuned on this one corpus, whose records are unusually regular. The audit labels were produced by the AI assistant that wrote the rules (a human has not re‑labelled them). So precision below is *optimistic*, and nothing here shows how it behaves on other styles of ADR. What it does show is that the approach is auditable end to end.

## 1. What the graph found

| | count |
|---|---|
| decisions | 533 |
| clauses (numbered holdings in `## Decision`) | 1 591 — 322 records have them |
| citation edges (per section) | 3 741 |
| treatment edges | 362 — 178 negative (supersedes / reverses / withdraws), 151 amends, 25 affirms, 8 reinstates |
| negative scope | 61 name clauses · 115 "an unspecified part" · 2 whole decision |
| **in force / partly superseded / out of force** | **418 / 113 / 2** |
| **not fully in force** | **115 = 21.6 %** |
| …still declared *Accepted* or *Proposed* | **111** (81 accepted, 30 proposed) |
| declared *Proposed* but cited by ≥ 3 other decisions as authority | 52 (the label is used loosely: 258 of 533 say *Proposed*) |
| longest chain of overruling | 5 |
| temporally impossible treatments (actor dated before target) | **0 of 184** dated |

Only 4 of the 533 records carry a formal `Superseded` status; the rest of the supersession lives in prose — which is why a reader of the status line is misled.

## 2. Exposure: how often does flat retrieval hand an agent a decision that is partly dead?

For each of the 533 decision titles used as a query, take the top‑5 BM25 results (excluding the decision itself).

| | |
|---|---|
| results that are partly or wholly out of force | 706 of 2 663 = **26.5 %** |
| queries with ≥ 1 such result in the top‑5 | 397 of 533 = **74.5 %** |

This measures the *prevalence of the problem* under our own standing labels (it is not an accuracy figure for the standing). Precedent's `preflight` does not hide those decisions; it flags the stale clauses and adds the controlling decision, within a token budget.

## 3. Extraction quality

### Precision (all negative edges, read against their evidence)

`data/gold/negative_treatments_audit.jsonl` — every negative edge with a label.

| round | edges read | correct | wrong | note |
|---|---|---|---|---|
| 1 (first extractor) | 127 | 123 (96.9 %) | 4 | verbs in `self‑replace`, adjective *retired*, … ; several clause lists too wide |
| final (after root‑cause fixes + recall rules) | 178 | 176 (98.9 %) | 1 | + 1 *plausible*. The wrong one: ADR‑0310 → ADR‑0502, "adopts §7 … retiring the listener counter" read as a withdrawal |

Every edge added after round 1 was read as well. Three of the four round‑1 false positives were fixed by changing the rule that caused them (not by special‑casing the sentence); regression tests pin them (`tests/test_real_adrs.py`). **Tuning caveat:** the rules were refined with this audit in hand; held‑out precision is unmeasured.

### Recall (held‑out sample)

Population: sentences that cite another decision, sit outside *Alternatives*, contain a trigger word (`supersed|revers|withdr|replac|retire|obsolet|no longer|instead of|overrid|rescind|drop|remov|deprecat`) and produced **no** negative edge — 242 after the final rules. A fresh random sample of 40, read by hand, had **1 clear miss** (*"ADR‑0079 §7's … behavior no longer holds for non‑loopback values"*) and **2 implicit ones** (*"no longer take the lock"*, *"instead of"*). Scaling to the pool: 6–18 missed statements against 178 found ⇒ **recall ≈ 91–97 % of explicit overruling statements**. Statements with no trigger word are invisible to this estimate, so true recall is lower. Earlier samples drove the rules (first: 6 of 45 missed), so only the last sample is held out.

### Paths

697 distinct repo paths are mentioned. 118 exist at HEAD under that name, 361 more resolve after a configured rename (`cypherlite→relate`) and a *unique* suffix match, 218 are gone (removed features: 103 live decisions point at one — a `ghost-path` finding).

## 4. Standing engine

Unit tests (`tests/test_standing.py`) cover: clause‑level attack, whole attack, unspecified part, **reversal of a reversal restores the original**, a chain of four alternating, mutual supersession ⇒ contested, an attacker that is only partly defeated stays alive, rejected decisions cannot supersede, temporal anomalies ignored, non‑negative treatments never attack. The demo corpus never contains an overruling that is itself fully overruled (`restored = 0`), so that path is exercised by tests and the synthetic fixture, not by the real data.

## 5. Guard

`tests/test_guard.py`: dry run on a read‑only store forks the file and leaves the original untouched; citing an out‑of‑force clause is rejected with a fix naming the controlling decision; overruling something others rely on needs `acknowledge_impact`; a dry run really rolls back (counts and standing unchanged); a commit records the decision and updates derived standing; the rendered markdown **round‑trips** through the extractor to the same edges.

## 5a. Overlap finder

`find_overlaps(draft)` ranks existing decisions and clauses against the text of a draft (hybrid search for candidates, then per clause `0.6 × LSA cosine + 0.4 × idf‑weighted keyword share`; a clause *overlaps* at ≥ 0.40 and ≥ 80 % of its decision's best clause).

**Test.** The corpus supplies its own cases: every decision that took *named clauses* of an earlier decision out of force (55 pairs). Its Decision section is the "draft", with every ADR number, §‑reference and link removed so the answer is not handed over. We ask whether the overruled decision is among the candidates and whether its overruled clauses are flagged. Thresholds were chosen on the even‑numbered cases and are reported on the odd ones (`scripts/evaluate_overlaps.py`).

| | all 55 | held out (27) |
|---|---|---|
| overruled decision is the **first** candidate | 14.5 % | 14.8 % |
| … in the top 5 | 67.3 % | 66.7 % |
| … in the top **8** (the default) | **76.4 %** | **81.5 %** |
| … in the top 10 | 78.2 % | 81.5 % |
| when found: its overruled clauses that are flagged | 71.3 % | 60.9 % |
| when found: share of that decision's clauses flagged (flagging all of them would score 100 % recall) | 29.4 % | 24.2 % |

Read it as a **checklist, not a search engine**: it rarely puts the right decision first (a draft's own topic matches many records), and about one case in four it misses the decision altogether. When it does find it, it flags the clauses that were actually overruled well above chance (≈ 71 % recall for ≈ 29 % of clauses flagged). With only 27 held‑out cases the second column is indicative, not tight. The draft here is another ADR's text, which is cleaner than an agent's one‑line intent; short drafts will do worse.

## 5b. Header patches

`precedent fix-status` writes the *derived* standing back into the status line, in the corpus's own wording (`Superseded in part by ADR‑0229 (§1, §4–5)`). On the pinned corpus (`scripts/verify_headers.py`, which works on a throw‑away copy):

| check | result |
|---|---|
| headers still saying Accepted/Proposed/unknown although later decisions overruled the record | **111** (all *partly* overruled; none contested) |
| patch applies to the untouched checkout (`git apply --check`) | yes, 111 files, one line each |
| store text equals the file on disk for every patched record | yes |
| after applying every patch and re‑extracting: decisions whose standing, out‑clauses or controlling decisions changed | **0** |
| overruling relationships (actor → target) lost or gained | **0 / 0** |
| stale headers left | **0** (111 → 0) |
| suggestions that rest on an edge with confidence < 0.8 (marked ⚠ in the table and `review: true` in JSON) | 38 of 111 |
| suggestions that can name clauses | 38 of 111 (73 are overruled "in part" without an itemised clause, so the line names only the decision) |

One extractor change came out of this: a header `Superseded in part by ADR‑X` used to add an edge even when X's own text already overruled the record, so patched headers inflated the graph (362 → 415 edges). The vague header edge is now dropped when a precise one from the same decision exists. Re‑extracting the **unpatched** corpus is unchanged (362 edges, identical standing: the committed store did not need rebuilding); the patched corpus ends at 356 edges because six vague duplicates merge into precise ones. Unit tests: `tests/test_headers.py` (every status‑line style the parser reads, CRLF and continuation lines, drift refusal, diff applies with git, idempotence, lint clears).

## 6. Performance (Apple silicon, one process, real graph)

| operation | p50 | p95 |
|---|---|---|
| index 533 records → `.rl` (parse + extract + standing + load + vectors) | 1.4 s total | |
| `status` | 0.35 ms | 0.58 ms |
| hybrid `search` (BM25 + clause BM25 + vector + fusion) | 45 ms | 48 ms |
| `preflight` (search + expansion + cards) | 47 ms | 50 ms |
| browser: Relate‑WASM start + load 533 decisions / 2 458 edges | ≈ 0.5–0.8 s | |
| store size | 17.9 MB (incl. full text, 4 indexes) | |

Almost all of the search time is Relate's full‑text engine scoring ≈ 2 MB of indexed text; vector `SEARCH` on the 96‑d index takes 0.8 ms. We index a compact `search_text` (title + Decision + start of Context) rather than the whole record for that reason.

## 7. What this evaluation does not show

* Generalisation to other ADR styles or corpora (one corpus, tuned on it; the overlap thresholds too).
* That header patches are *correct in the maintainers' judgement*: they are proven not to change any computed verdict, and each carries its evidence, but a human still has to accept the wording (38 rest on weaker edges).
* That agents *do better* with preflight. We measured exposure and mechanism, not downstream task success.
* Independent labelling (all labels are the assistant's).
