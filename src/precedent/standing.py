"""Standing engine: is a decision (or one of its clauses) still good law?

Treatments are modelled as *attacks* in a Dung-style argumentation framework and standing is the
**grounded extension**:

* a clause nobody attacks is **in force**;
* a clause is **out of force** if some attacker is *certainly alive* (at least one of the
  attacker's own clauses is in force);
* a clause is **restored** (in force again) if every attacker is *certainly dead* (all of the
  attacker's clauses are out of force, or the attacker was never accepted);
* whatever is left (mutual attacks, cycles) is **contested**.

This is how the "decision was reversed, then the reversal was reversed" chains in real ADR logs
resolve without any hand-written special case, and it is the same rule the Relate-side
``what-if`` simulation runs on a scratch copy of the graph.

Three scopes of attack are supported (see :attr:`precedent.model.Treatment.scope`): ``clauses``
(named clauses), ``whole`` (entire decision) and ``partial`` (an unspecified part, tracked by the
virtual claim ``-1`` so the decision shows as *partially* in force without guessing which clause).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from .model import NEGATIVE_KINDS, Decision, Treatment

UNSPECIFIED = -1  # virtual claim: "some unspecified part of the decision"
BODY = 0  # claim for the non-numbered body of a decision

IN, OUT, UNDEC = "in", "out", "undecided"


@dataclass
class Standing:
    decision: str
    state: str  # in_force | partial | out | contested
    out_clauses: list[int] = field(default_factory=list)
    unspecified_part_out: bool = False
    defeated_by: dict[int, list[str]] = field(default_factory=dict)  # claim -> effective attackers
    attackers: list[str] = field(default_factory=list)  # every actor with a negative treatment
    restored: bool = False  # had attackers, but all of them are defeated
    contested_clauses: list[int] = field(default_factory=list)

    @property
    def controlling(self) -> list[str]:
        """The live decisions that took something away from this one."""
        seen: dict[str, None] = {}
        for actors in self.defeated_by.values():
            for a in actors:
                seen.setdefault(a, None)
        return list(seen)


def _claims_of(d: Decision) -> list[int]:
    return [BODY, *d.clause_numbers]


def _covered(t: Treatment, target: Decision) -> list[int]:
    """Claims of ``target`` that treatment ``t`` attacks."""
    if t.scope == "whole":
        return [*_claims_of(target), UNSPECIFIED]
    if t.scope == "clauses":
        known = set(target.clause_numbers)
        hit = [c for c in t.target_clauses if c in known]
        # clause numbers the parser could not resolve still count as "some part"
        return hit if len(hit) == len(t.target_clauses) else [*hit, UNSPECIFIED]
    return [UNSPECIFIED]


def anomalies(decisions: dict[str, Decision], treatments: list[Treatment]) -> list[Treatment]:
    """Negative treatments whose actor is *dated before* the target (renumbering, typos ...)."""
    bad = []
    for t in treatments:
        a, b = decisions[t.actor], decisions[t.target]
        if t.kind in NEGATIVE_KINDS and a.date and b.date and a.date < b.date:
            bad.append(t)
    return bad


@dataclass
class Report:
    """Result of :func:`compute`: per-decision standing plus which treatments actually took effect."""

    standing: dict[str, Standing]
    effective: set[tuple]  # (actor, target, kind, target_clauses) of treatments that are alive
    anomalies: list[Treatment]
    treatments: list[Treatment] = field(default_factory=list)  # every treatment considered

    def __getitem__(self, decision: str) -> Standing:
        return self.standing[decision]

    def counts(self) -> dict[str, int]:
        c: dict[str, int] = defaultdict(int)
        for s in self.standing.values():
            c[s.state] += 1
        return dict(c)


def treatment_key(t: Treatment) -> tuple:
    return (t.actor, t.target, t.kind, t.target_clauses)


def compute(
    decisions: dict[str, Decision],
    treatments: list[Treatment],
    *,
    min_confidence: float = 0.0,
) -> Report:
    """Grounded-semantics standing for every decision."""
    bad_list = anomalies(decisions, treatments)
    bad = {id(t) for t in bad_list}
    attacks: dict[tuple[str, int], list[Treatment]] = defaultdict(list)
    for t in treatments:
        if t.kind not in NEGATIVE_KINDS or id(t) in bad or t.confidence < min_confidence:
            continue
        if t.actor not in decisions or t.target not in decisions:
            continue
        for claim in _covered(t, decisions[t.target]):
            attacks[(t.target, claim)].append(t)

    dead_on_arrival = {d.id for d in decisions.values() if d.status in {"rejected", "withdrawn"}}
    state: dict[tuple[str, int], str] = {}
    for d in decisions.values():
        for c in _claims_of(d):
            state[(d.id, c)] = UNDEC
        if (d.id, UNSPECIFIED) in attacks:
            state[(d.id, UNSPECIFIED)] = UNDEC

    def alive(actor: str) -> bool:  # certainly in force: at least one real claim is IN
        return actor not in dead_on_arrival and any(state[(actor, c)] == IN for c in _claims_of(decisions[actor]))

    def dead(actor: str) -> bool:  # certainly out of force: every real claim is OUT
        return actor in dead_on_arrival or all(state[(actor, c)] == OUT for c in _claims_of(decisions[actor]))

    changed = True
    while changed:
        changed = False
        for key, cur in list(state.items()):
            if cur != UNDEC:
                continue
            atks = attacks.get(key, [])
            if not atks:
                state[key] = IN
                changed = True
            elif any(alive(t.actor) for t in atks):
                state[key] = OUT
                changed = True
            elif all(dead(t.actor) for t in atks):
                state[key] = IN
                changed = True

    effective: set[tuple] = set()
    for (target, _claim), atks in attacks.items():
        if state.get((target, _claim)) == OUT:
            effective.update(treatment_key(t) for t in atks if alive(t.actor))

    out: dict[str, Standing] = {}
    for d in decisions.values():
        real = _claims_of(d)
        outs = [c for c in real if state[(d.id, c)] == OUT]
        und = [c for c in real if state[(d.id, c)] == UNDEC]
        unspec = state.get((d.id, UNSPECIFIED)) == OUT
        defeated = {
            c: sorted({t.actor for t in attacks[(d.id, c)] if alive(t.actor)})
            for c in [*real, UNSPECIFIED]
            if state.get((d.id, c)) == OUT
        }
        every = sorted({t.actor for c in [*real, UNSPECIFIED] for t in attacks.get((d.id, c), [])})
        if und or state.get((d.id, UNSPECIFIED)) == UNDEC:
            st = "contested"
        elif len(outs) == len(real):
            st = "out"
        elif outs or unspec:
            st = "partial"
        else:
            st = "in_force"
        out[d.id] = Standing(
            decision=d.id,
            state=st,
            out_clauses=[c for c in outs if c != BODY],
            unspecified_part_out=unspec or (BODY in outs and len(outs) < len(real)),
            defeated_by={c: a for c, a in defeated.items() if a},
            attackers=every,
            restored=bool(every) and st == "in_force",
            contested_clauses=und,
        )
    return Report(out, effective, bad_list, list(treatments))


def label(state: str) -> str:
    return {
        "in_force": "in force",
        "partial": "partly superseded",
        "out": "out of force",
        "contested": "contested",
    }.get(state, state)
