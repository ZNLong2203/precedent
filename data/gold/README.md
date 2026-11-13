# Gold audit of negative treatments

`negative_treatments_audit.jsonl` lists **every** negative treatment (supersedes / reverses / withdraws)
Precedent extracts from `relatedb/relate` `docs/adr` at commit `1ebb65e` — all 178 of them, not a sample —
with a label and, where the label is not `correct`, a note.

| label | meaning |
| --- | --- |
| `correct` | the evidence sentence says the actor takes (part of) the target out of force; kind, direction and target are right |
| `plausible` | probably right but the sentence is ambiguous |
| `wrong` | a false positive |

**Who labelled:** the AI assistant that built the extractor (Claude Sonnet 5.5) read each evidence sentence
against the target record. A human has not independently re-labelled them — treat the numbers as an
auditable first pass and open an issue if you disagree with a label.
**Tuning caveat:** the extraction rules were refined *using* this audit (4 false positives found in the first
pass of 127 edges were fixed at the root cause), so precision here is optimistic for unseen corpora.
Recall was estimated separately on a held-out sample; see `docs/evaluation.md`.
