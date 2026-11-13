"""Extract citations and *treatments* (supersedes / reverses / withdraws / amends ...) from prose.

Design rules (all deliberate):

* **Deterministic.**  No model call: the same corpus always yields the same graph.
* **Evidence-carrying.**  Every treatment keeps the exact sentence it came from, plus the name of
  the rule that fired and a confidence, so a human (or an agent) can verify any edge.
* **Precision over recall for negative treatments.**  A wrong "superseded" label is worse than a
  missed one, so hypothetical / negated sentences and the *Alternatives considered* section are
  ignored for treatments (they still produce plain citations).
"""

from __future__ import annotations

import re
from dataclasses import replace

from .model import Citation, Decision, Treatment, Unit
from .parse_adr import ADR_REF, LINK_REF, adr_id

# --------------------------------------------------------------------------- verb lexicon
_VERBS: dict[str, str] = {
    "SUPERSEDES": r"supersed(?:e|es|ed|ing)|replac(?:e|es|ed|ing)|obsolet(?:e|es|ed|ing)|supplant(?:s|ed|ing)?|overrides|overridden|overrode|overrul(?:e|es|ed|ing)",
    "REVERSES": r"revers(?:e|es|ed|ing)|undone|overturn(?:s|ed|ing)?",
    "WITHDRAWS": r"withdr(?:aw|aws|ew|awn|awing)|rescind(?:s|ed)?|retract(?:s|ed)?|abandon(?:s|ed|ing)?|retires|retiring|retired(?=\s+(?:by|on|in|with|the|this|that|those|these|its|their|a|an)\b)",
    "REINSTATES": r"restor(?:e|es|ed|ing)|reinstat(?:e|es|ed|ing)",
    "AMENDS": r"amend(?:s|ed|ing)?|rais(?:e|es|ed)|extend(?:s|ed|ing)?|widen(?:s|ed)?|narrow(?:s|ed)?|refin(?:e|es|ed)|add(?:s|ed)|correct(?:s|ed)|renam(?:e|es|ed)|split(?:s)?|fold(?:s|ed)?|fill(?:s)? in|updat(?:e|es|ed)|chang(?:e|es|ed)|relax(?:es|ed)?|tighten(?:s|ed)?|drop(?:s|ped)?|remov(?:e|es|ed)|clarif(?:y|ies|ied)|lower(?:s|ed)|bump(?:s|ed)|mov(?:e|es|ed)|shorten(?:s|ed)?|reword(?:s|ed)?|revis(?:e|es|ed)|restrict(?:s|ed)?|limit(?:s|ed)|constrain(?:s|ed)|cap(?:s|ped)",
    "AFFIRMS": r"confirm(?:s|ed)?|stand(?:s)?|stay(?:s)?|remain(?:s)?|keep(?:s)?|retain(?:s)?|pin(?:s)?|implement(?:s|ed)|ratif(?:y|ies|ied)",
}
_PRIORITY = ("SUPERSEDES", "REVERSES", "WITHDRAWS", "REINSTATES", "AMENDS", "AFFIRMS")
_VERB_RX = {k: re.compile(r"(?<![\w-])(?:%s)\b" % v, re.IGNORECASE) for k, v in _VERBS.items()}
_PASSIVE_STEM = r"(supersed(?:ed)|replaced|reversed|withdrawn|amended|overridden|overruled|obsoleted|retired|restored)"
_STEM_KIND = {
    "supersed": "SUPERSEDES", "replac": "SUPERSEDES", "overrid": "SUPERSEDES", "overrul": "SUPERSEDES",
    "obsolet": "SUPERSEDES", "revers": "REVERSES", "withdr": "WITHDRAWS", "retir": "WITHDRAWS",
    "amend": "AMENDS", "restor": "REINSTATES",
}

# Words just before a verb that make the sentence hypothetical or negated.
_HEDGE = re.compile(
    r"\b(?:not|never|nothing|none|nobody|no longer|cannot|can't|won't|would|could|should|may|might|if|unless|"
    r"rather than|instead of|without|neither|nor|whether|to avoid|avoid(?:s|ing)?)\s+(?:\w+\s+){0,2}$",
    re.IGNORECASE,
)

# Clause references: "§4", "§4-6", "Decision 3", "Decisions 1 and 2", "item 5", "clause 2".
_CLAUSE_TOKEN = re.compile(
    r"(?:§|\bDecisions?\s+|\bitems?\s+|\bclauses?\s+|\brules?\s+)(\d{1,2}(?:\s*(?:,|and|&|–|-|to)\s*\d{1,2})*)",
    re.IGNORECASE,
)
_CLAUSE_AFTER_ADR = re.compile(r"^\W{0,3}(?:s\s)?(?:'s\s)?(?:§|\bDecisions?\s+|\bitems?\s+|\bclauses?\s+)(\d{1,2}(?:\s*(?:,|and|&|–|-|to)\s*\d{1,2})*)", re.IGNORECASE)
_STANDS = re.compile(
    r"(?:§|\bDecisions?\s+|\bitems?\s+|\bclauses?\s+)(\d{1,2}(?:\s*(?:,|and|&|–|-|to)\s*\d{1,2})*)\s+(?:both\s+)?(?:stand|stands|remain|remains|stay|stays|still\s+(?:stand|stands|hold|holds))\b",
    re.IGNORECASE,
)
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z`\[(*\-§])|;\s+(?=(?:ADR[- ]\d|\[ADR[- ]\d))|\s[—–]\s(?=ADR[- ]\d)")
_ABBREV = re.compile(r"\b(?:e\.g|i\.e|vs|etc|cf|approx)\.$", re.IGNORECASE)
_ANY_VERB_RX = re.compile(r"(?<![\w-])(?:%s)\b" % "|".join(f"(?:{v})" for v in _VERBS.values()), re.IGNORECASE)
_NUM_RANGE = re.compile(r"\d{1,2}")


def sentences(text: str) -> list[str]:
    parts = _SENT_SPLIT.split(text)
    merged: list[str] = []
    for p in parts:
        if merged and _ABBREV.search(merged[-1]):
            merged[-1] += " " + p
        else:
            merged.append(p)
    return [p.strip() for p in merged if p and p.strip()]


def _numbers(token: str) -> list[int]:
    nums = [int(x) for x in _NUM_RANGE.findall(token)]
    if re.search(r"(?:–|-|\bto\b)", token) and len(nums) == 2 and nums[0] < nums[1] <= nums[0] + 12:
        return list(range(nums[0], nums[1] + 1))
    return nums


_EXCEPT = re.compile(
    r"\b(?:except|other than|apart from|besides|but not)\s+(?:the\s+)?(?:§|Decisions?\s+|items?\s+|clauses?\s+)\d{1,2}(?:\s*(?:,|and|&|–|-|to)\s*\d{1,2})*",
    re.IGNORECASE,
)


_COMPARATIVE = re.compile(r"(?:the way|as|like|per|adopts?|follows?|uses?|reuses?|matches|matching|mirrors|same as|pins? how|see)\s+(?:the\s+)?$", re.IGNORECASE)
_STANDS_AFTER = re.compile(r"\b(?:stays?|stands?|unchanged|remains?)\b", re.IGNORECASE)


def clause_refs(text: str) -> tuple[int, ...]:
    """Clause numbers named in ``text`` (``§4``, ``Decisions 1 and 2``).

    Dropped on purpose: exceptions ("except §2"), comparisons ("the way §3 probes a node") and
    clauses the same sentence says *stay* in force.
    """
    text = _EXCEPT.sub("", text)
    out: set[int] = set()
    for m in _CLAUSE_TOKEN.finditer(text):
        if _COMPARATIVE.search(text[max(0, m.start() - 16) : m.start()]):
            continue
        tail = re.split(r"[.;—]", text[m.end() : m.end() + 70], maxsplit=1)[0]
        tail = re.sub(r'["“”`][^"“”`]*["“”`]?', " ", tail)  # quoted text is the thing being treated
        tail = re.sub(r"\([^)]*\)?", " ", tail)  # parenthetical asides don't decide the clause's fate
        if _STANDS_AFTER.search(tail):
            continue
        out.update(_numbers(m.group(1)))
    return tuple(sorted(out))


def _whole_object(object_text: str, target_num: int | None = None) -> bool:
    """Does the verb act on the decision itself ("supersedes ADR-0012", "reverses this ADR")?

    The reference must stand alone: a possessive ("ADR-0012's naming"), a clause or noun that
    follows it ("ADR-0012 alternative 3", "ADR-0012 §2") means a *part* is meant.
    """
    t = object_text.lstrip()
    if re.match(r"in part\b", t, re.IGNORECASE):
        return False
    pat = r"(?:this\s+(?:ADR|decision|record)\b|the\s+whole\b|all\s+of\b"
    pat += (rf"|\[?ADR[- ]0*{target_num}\b" if target_num is not None else r"|\[?ADR[- ]\d{1,4}\b") + r")"
    m = re.match(pat, t, re.IGNORECASE)
    if not m:
        return False
    rest = t[m.end() :]
    rest = re.sub(r"^[\]\)]*(?:\([^)]*\))?", "", rest)  # a markdown link target: [ADR-0012](0012-x.md)
    return bool(re.match(r"\s*(?:$|[.,;:)\]—–]|and\b|in\b|for\b|with\b|because\b|so\b|as\b|where\b|when\b|entirely\b|completely\b|wholly\b|outright\b)", rest, re.IGNORECASE))


def _clauses_after(text: str, end: int) -> tuple[int, ...]:
    m = _CLAUSE_AFTER_ADR.match(text[end : end + 60])
    return tuple(_numbers(m.group(1))) if m else ()


def _strip_other_adr_clauses(text: str) -> str:
    """Remove ``ADR-NNNN §k`` spans so clause refs that belong to *another* ADR don't leak."""
    return re.sub(r"ADR[- ]\d{1,4}\W{0,3}(?:'s\s)?(?:§|Decisions?\s+|items?\s+)\d{1,2}(?:\s*(?:,|and|&|–|-|to)\s*\d{1,2})*", "ADR", text, flags=re.IGNORECASE)


def _adr_mentions(text: str) -> list[tuple[int, int, int]]:
    """(number, start, end) of every decision reference in ``text``, in order."""
    out: list[tuple[int, int, int]] = []
    for m in ADR_REF.finditer(text):
        out.append((int(m.group(1)), m.start(), m.end()))
    for m in LINK_REF.finditer(text):
        if not any(s <= m.start() < e for _, s, e in out):
            out.append((int(m.group(1)), m.start(), m.end()))
    out.sort(key=lambda t: t[1])
    return out


def _best_kind(text: str, *, allow: tuple[str, ...] = _PRIORITY) -> tuple[str | None, re.Match | None]:
    """Strongest un-hedged verb kind in ``text`` and the regex match of the verb that triggered it."""
    for kind in _PRIORITY:
        if kind not in allow:
            continue
        for m in _VERB_RX[kind].finditer(text):
            if len(m.group(0)) > 2 and m.group(0).isupper():  # CREATE / DROP / SHOW INDEX: query keywords
                continue
            if text[: m.start()].count("`") % 2 == 1:  # inside `code`: an identifier such as `drop`, not a verb
                continue
            before = text[max(0, m.start() - 40) : m.start()]
            if _HEDGE.search(before):
                continue
            return kind, m
    return None, None


def _clauses_for(sent: str, verb_end: int, m_start: int, m_end: int) -> tuple[int, ...]:
    """Clause numbers a treatment applies to: right after the target ADR, else between verb and ADR."""
    after = _clauses_after(sent, m_end)
    if after:
        return tuple(sorted(after))
    between = _strip_other_adr_clauses(sent[verb_end:m_start]) if verb_end <= m_start else ""
    return clause_refs(between)


def _kind_from_stem(word: str) -> str:
    w = word.lower()
    for stem, kind in _STEM_KIND.items():
        if w.startswith(stem):
            return kind
    return "AMENDS"


def _evidence(sentence: str, limit: int = 380) -> str:
    s = " ".join(sentence.split())
    return s if len(s) <= limit else s[: limit - 1].rstrip() + "…"


# --------------------------------------------------------------------------- rules
_THIS = r"(?:this(?:\s+(?:ADR|decision|record|change|amendment|proposal))?|we)"
_ACTIVE_THIS = re.compile(rf"\b{_THIS}\s+(?:(?:also|now|partly|partially|explicitly|hereby|then|further)\s+)*(?P<verb>{'|'.join(_VERBS['SUPERSEDES'].split('|') + _VERBS['REVERSES'].split('|') + _VERBS['WITHDRAWS'].split('|') + _VERBS['REINSTATES'].split('|') + _VERBS['AMENDS'].split('|'))})\b", re.IGNORECASE)
_IMPERATIVE = re.compile(r"^(?P<verb>supersedes|replaces|reverses|withdraws|amends|restores|obsoletes|overrides)\b", re.IGNORECASE)
_PASSIVE_BY = re.compile(rf"\b(?:is|are|was|were|gets|stays|becomes|been)\s+(?:(?:partly|partially|now|hereby|in part)\s+)*{_PASSIVE_STEM}\s+(?:in part\s+)?by\s+(?:\[)?(?P<actor>ADR[- ]\d{{1,4}}|this\b|the present\b)", re.IGNORECASE)
_PARTICIPLE_BY_ADR = re.compile(rf"\b{_PASSIVE_STEM}\s+(?:in part\s+)?by\s+(?:\[)?ADR[- ](?P<actor>\d{{1,4}})", re.IGNORECASE)
_AUX = re.compile(r"\b(?:is|are|was|were|be|been|being|gets|get)\s+(?:\w+\s+){0,2}$", re.IGNORECASE)
_PASSIVE_NO_ACTOR = re.compile(rf"\b(?:is|are|was|were)\s+(?:(?:partly|partially|now|hereby|in part)\s+)*{_PASSIVE_STEM}(?!\s+by\s+(?:\[?ADR|this\b|the present))", re.IGNORECASE)
_LATER_REVERSED = re.compile(r"\blater\s+(?P<verb>reversed|withdrawn|superseded|replaced)\b[^)]{0,80}?ADR[- ](?P<actor>\d{1,4})", re.IGNORECASE)
_STATUS_BY = re.compile(r"Superseded(?P<part>\s+in part)?\s+by\s+.*?(?:ADR[- ]|\]\()(?P<actor>\d{1,4})", re.IGNORECASE)
_FIELD_REL = re.compile(r"^(?P<key>Amends|Supersedes|Superseded By|Amended):\s*(?P<val>.*)$", re.IGNORECASE)


class _Collector:
    def __init__(self, decisions: dict[str, Decision]):
        self.decisions = decisions
        self.treatments: dict[tuple, Treatment] = {}
        self.citations: dict[tuple, Citation] = {}

    def add_treatment(self, t: Treatment) -> None:
        if t.actor == t.target or t.actor not in self.decisions or t.target not in self.decisions:
            return
        key = (t.actor, t.target, t.kind, t.target_clauses)
        old = self.treatments.get(key)
        if old is None or t.confidence >= old.confidence:
            if old is not None:
                t = replace(t, affirmed_clauses=t.affirmed_clauses or old.affirmed_clauses, whole=t.whole or old.whole)
            self.treatments[key] = t

    def add_citation(self, c: Citation) -> None:
        if c.src == c.dst or c.dst not in self.decisions:
            return
        key = (c.src, c.dst, c.section, c.src_clause)
        old = self.citations.get(key)
        if old is None:
            self.citations[key] = c
        else:
            merged = tuple(dict.fromkeys((*old.dst_clauses, *c.dst_clauses)))
            self.citations[key] = Citation(old.src, old.dst, old.section, old.src_clause, merged, old.evidence)


def _citations(col: _Collector, unit: Unit) -> None:
    for num, start, end in _adr_mentions(unit.text):
        dst = adr_id(num)
        if dst == unit.decision:
            continue
        lo = max(0, start - 160)
        col.add_citation(
            Citation(unit.decision, dst, unit.section, unit.clause, _clauses_after(unit.text, end), _evidence(unit.text[lo : end + 220]))
        )


_FULL = re.compile(r"\b(?:in full|in its entirety|entirely|completely|wholly|outright)\b", re.IGNORECASE)
_THIS_PASSIVE = re.compile(
    r"\bthis\s+(?:ADR|decision|record)\s+(?:is|was|has\s+been)\s+(?:now\s+)?(?:superseded|replaced|withdrawn|reversed|obsoleted)\s+by\b",
    re.IGNORECASE,
)


def _later_references(col: _Collector, unit: Unit) -> None:
    """Statements in ``## Later references`` of decision T: ``ADR-A <verb> ... (about T)``."""
    target = unit.decision
    target_num = int(target.split("-")[1])
    last_treatment: Treatment | None = None
    for sent in sentences(unit.text):
        mentions = [m for m in _adr_mentions(sent) if adr_id(m[0]) != target]
        stands = tuple(sorted({n for m in _STANDS.finditer(sent) for n in _numbers(m.group(1))}))
        if stands and last_treatment is not None:
            merged = tuple(sorted({*last_treatment.affirmed_clauses, *stands}))
            last_treatment = replace(last_treatment, affirmed_clauses=merged)
            col.add_treatment(last_treatment)
        if not mentions:
            continue
        passive = _PASSIVE_BY.search(sent)
        if passive and passive.group("actor").lower().startswith(("this", "the present")):
            _body_sentence(col, unit, sent)  # "ADR-0035: its sentence is superseded by this ADR" -> this ADR acts
            continue
        if passive and passive.group("actor")[0] in "Aa":
            actor_num = int(re.search(r"\d+", passive.group("actor")).group())
            kind = _kind_from_stem(passive.group(1))
            rule, base, vm = "later-passive-by", 0.85, None
            scope_text = sent
            whole = bool(_THIS_PASSIVE.search(sent)) and "in part" not in sent.lower()
        else:
            actor_num, _a_start, a_end = mentions[0]
            tail = sent[a_end:]
            kind, vm = _best_kind(tail[:240])
            if kind is None or vm is None:
                continue
            # "ADR-0279's namespace is superseded by `run`": the cited ADR is the *patient*, not the actor
            if re.match(r"(?:'s|’s)", tail) and _AUX.search(tail[: vm.start()]):
                continue
            rule, base = "later-actor-verb", 0.8
            scope_text = tail
            whole = _whole_object(tail[vm.end() :], target_num)
        if (
            vm is not None and rule == "later-actor-verb" and kind == "AMENDS"
            and re.match(r"(?:remov|drop|delet)", vm.group(0), re.IGNORECASE)
            and not re.search(r"\b(?:cost|overhead|term|latency|allocations?|copies|copy|lock|census|remaining)\b", tail[vm.end() : vm.end() + 60], re.IGNORECASE)
        ):
            kind, base = "WITHDRAWS", 0.7  # "ADR-0029 removes the localhost HTTP sidecar": what it removes is gone
        clauses = clause_refs(_strip_other_adr_clauses(scope_text))
        if clauses:
            whole = False
        conf = base + (0.05 if clauses else 0.0) - (0.1 if len({m[0] for m in mentions}) > 1 else 0.0)
        if kind == "AFFIRMS":
            conf -= 0.1
        t = Treatment(adr_id(actor_num), target, kind, clauses, _evidence(sent), rule, round(min(conf, 0.95), 2), target, stands, whole)
        col.add_treatment(t)
        last_treatment = t


def _status_unit(col: _Collector, unit: Unit) -> None:
    m = _STATUS_BY.search(unit.text)
    if not m:
        return
    actor = adr_id(int(m.group("actor")))
    part = bool(m.group("part"))
    col.add_treatment(
        Treatment(actor, unit.decision, "SUPERSEDES", (), _evidence(unit.text), "status-in-part" if part else "status-superseded", 0.95, unit.decision, (), not part)
    )


def _header_relation(col: _Collector, unit: Unit) -> None:
    m = _FIELD_REL.match(unit.text)
    if not m:
        return
    key = m.group("key").lower()
    val = m.group("val")
    clauses = clause_refs(val)
    for num, _s, _e in _adr_mentions(val):
        other = adr_id(num)
        ev = _evidence(unit.text)
        if key == "amends":
            col.add_treatment(Treatment(unit.decision, other, "AMENDS", clauses, ev, "header-amends", 0.95, unit.decision))
        elif key == "supersedes":
            col.add_treatment(Treatment(unit.decision, other, "SUPERSEDES", clauses, ev, "header-supersedes", 0.95, unit.decision, (), not clauses))
        elif key == "superseded by":
            col.add_treatment(Treatment(other, unit.decision, "SUPERSEDES", (), ev, "header-superseded-by", 0.95, unit.decision, (), True))
        elif key == "amended":
            col.add_treatment(Treatment(other, unit.decision, "AMENDS", (), ev, "header-amended-by", 0.85, unit.decision))


def _body_sentence(col: _Collector, unit: Unit, sent: str) -> None:
    this = unit.decision
    mentions = _adr_mentions(sent)
    if not mentions:
        return
    others = [m for m in mentions if adr_id(m[0]) != this]

    # (a) "this ADR supersedes ADR-X's §2"
    m = _ACTIVE_THIS.search(sent)
    if m and not _HEDGE.search(sent[max(0, m.start() - 40) : m.start()]):
        kind, _vm = _best_kind(m.group("verb"))
        for num, s, e in others:
            if s >= m.end() and s - m.end() <= 200:
                clauses = _clauses_for(sent, m.end(), s, e)
                whole = not clauses and _whole_object(sent[m.end() : e + 16], num)
                col.add_treatment(Treatment(this, adr_id(num), kind or "AMENDS", clauses, _evidence(sent), "body-this-verb", 0.8, this, (), whole))
                break
        return

    # (b) "ADR-X's ... is superseded by this decision" / "... by ADR-Y"
    p = _PASSIVE_BY.search(sent)
    if p:
        actor = p.group("actor")
        kind = _kind_from_stem(p.group(1))
        if actor.lower().startswith(("this", "the present")):
            tgt = [mm for mm in others if mm[1] < p.start()]
            if tgt:
                num, s, e = tgt[-1]
                clauses = tuple(sorted({*_clauses_after(sent, e), *clause_refs(_strip_other_adr_clauses(sent[e : p.start()]))}))
                # whole only if the ADR itself is the passive subject: "ADR-X is superseded by this ..."
                whole = not clauses and sent[e : p.start()].strip() == ""
                col.add_treatment(Treatment(this, adr_id(num), kind, clauses, _evidence(sent), "body-passive-this", 0.8, this, (), whole))
        else:
            a_num = int(re.search(r"\d+", actor).group())
            tgt = [mm for mm in mentions if mm[1] < p.start() and mm[0] != a_num]
            if tgt:
                num, s, e = tgt[-1]
                col.add_treatment(Treatment(adr_id(a_num), adr_id(num), kind, tuple(sorted(_clauses_after(sent, e))), _evidence(sent), "body-passive-named", 0.65, this))
        return

    # (b2) "ADR-0015's execute step is superseded." - no actor named: the decision that says so acts.
    #      Handles lists of subjects: "ADR-0011 / ADR-0012 / ADR-0015 '...' is reversed here".
    first = mentions[0]
    this_num = int(this.split("-")[1])
    if first[1] <= 2:
        pn = _PASSIVE_NO_ACTOR.search(sent, first[2])
        if pn and not _HEDGE.search(sent[max(0, pn.start() - 40) : pn.start()]):
            kind = _kind_from_stem(pn.group(1))
            subjects = [first]
            for m_ in mentions[1:]:
                if m_[1] >= pn.start():
                    break
                gap = sent[subjects[-1][2] : m_[1]]
                if len(gap) <= 70 and not re.search(r"[.;:]", gap) and not _ANY_VERB_RX.search(gap):
                    subjects.append(m_)
                else:
                    break
            for k, (num, _s, e) in enumerate(subjects):
                if adr_id(num) == this or num >= this_num:
                    continue
                seg_end = subjects[k + 1][1] if k + 1 < len(subjects) else pn.start()
                clauses = tuple(sorted({*_clauses_after(sent, e), *clause_refs(_strip_other_adr_clauses(sent[e:seg_end]))}))
                # whole only when this ADR is the single, unqualified subject ("ADR-0012 is superseded [in full].")
                alone = len(subjects) == 1 and not re.match(r"\s*(?:'s|’s)", sent[e : e + 4])
                whole = not clauses and alone and (sent[e : pn.start()].strip() == "" or bool(_FULL.search(sent)))
                col.add_treatment(Treatment(this, adr_id(num), kind, clauses, _evidence(sent), "body-passive-implicit", 0.6, this, (), whole))
            return

    # (b3) "ADR-0359 supersedes item 2's ..." inside this decision: a later ADR acts on a clause of *this* one
    if len(mentions) == 1 and mentions[0][1] <= 2 and mentions[0][0] > int(this.split("-")[1]):
        a_num, _s, a_e = mentions[0]
        am = re.match(r"\s*(?:(?:now|also|partly|then|later)\s+)*(%s)\b" % "|".join(_VERBS[k] for k in ("SUPERSEDES", "REVERSES", "WITHDRAWS")), sent[a_e:], re.IGNORECASE)
        if am:
            clauses = clause_refs(sent[a_e + am.end(1) : a_e + am.end(1) + 60])
            if clauses:
                kind, _vm = _best_kind(am.group(1))
                col.add_treatment(Treatment(adr_id(a_num), this, kind or "SUPERSEDES", clauses, _evidence(sent), "body-later-actor", 0.65, this))
                return

    # (c) "(later reversed: ADR-0472 keeps them ...)": a later decision reverses what this unit says
    lr = _LATER_REVERSED.search(sent)
    if lr:
        kind = _kind_from_stem(lr.group("verb"))
        clause = (unit.clause,) if unit.clause else ()
        col.add_treatment(Treatment(adr_id(int(lr.group("actor"))), this, kind, clause, _evidence(sent), "body-later-note", 0.7, this))
        return

    # (d) imperative list item: "Supersedes decision 4 of ADR-0558; the rest stands."
    im = _IMPERATIVE.match(sent)
    if im and others:
        kind, _vm = _best_kind(im.group("verb"))
        num, s, e = others[0]
        clauses = _clauses_for(sent, im.end(), s, e)
        whole = not clauses and _whole_object(sent[im.end() : e + 16], num)
        col.add_treatment(Treatment(this, adr_id(num), kind or "AMENDS", clauses, _evidence(sent), "body-imperative", 0.7, this, (), whole))
        return

    # (e) third-party narration, strict: "ADR-A supersedes ... ADR-B" (active verb right after ADR-A)
    if len(mentions) >= 2:
        a_num, _a_s, a_e = mentions[0]
        negatives = "|".join(_VERBS[k] for k in ("SUPERSEDES", "REVERSES", "WITHDRAWS"))
        am = re.match(rf"\s*(?:(?:now|also|partly|then|later)\s+)*({negatives})\b", sent[a_e:], re.IGNORECASE)
        if am:
            kind, _vm = _best_kind(am.group(1))
            rest = [mm for mm in mentions[1:] if mm[0] != a_num and mm[1] >= a_e + am.end(1)]
            if rest and kind:
                num, s, e = rest[0]
                col.add_treatment(Treatment(adr_id(a_num), adr_id(num), kind, tuple(sorted(_clauses_after(sent, e))), _evidence(sent), "body-named-verb", 0.6, this))
                return

    # (f) "ADR-X (retired by ADR-Y)": passive participle without an auxiliary
    pb = _PARTICIPLE_BY_ADR.search(sent)
    if pb:
        a_num = int(pb.group("actor"))
        tgt = [mm for mm in mentions if mm[1] < pb.start() and mm[0] != a_num]
        if tgt:
            num, s, e = tgt[-1]
            col.add_treatment(Treatment(adr_id(a_num), adr_id(num), _kind_from_stem(pb.group(1)), tuple(sorted(_clauses_after(sent, e))), _evidence(sent), "body-participle-by", 0.65, this))


def extract(decisions: dict[str, Decision], units: list[Unit]) -> tuple[list[Citation], list[Treatment]]:
    """Run every rule over every unit.  Returns ``(citations, treatments)``."""
    col = _Collector(decisions)
    for unit in units:
        _citations(col, unit)
        if unit.section == "later":
            _later_references(col, unit)
            _header_relation(col, unit)
        elif unit.section == "status":
            _status_unit(col, unit)
        elif unit.section == "header":
            _header_relation(col, unit)
        elif unit.section in {"context", "decision", "consequences", "other"}:
            # "alternatives" is skipped on purpose: verbs there describe options that were rejected.
            for sent in sentences(unit.text):
                _body_sentence(col, unit, sent)
    cits = sorted(col.citations.values(), key=lambda c: (c.src, c.dst, c.section, c.src_clause or 0))
    treats = sorted(col.treatments.values(), key=lambda t: (t.target, t.actor, t.kind, t.target_clauses))
    return cits, treats
