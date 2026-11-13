"""Plain data model shared by the parser, the graph builder and the standing engine.

The vocabulary is borrowed from case law on purpose:

* a *decision* is a case (an ADR, RFC, KEP ...),
* a *clause* is a numbered holding inside it ("Decision 3", "§4"),
* a *treatment* is how a later decision treats an earlier one
  (supersedes, reverses, withdraws, amends, ...),
* *standing* is whether a clause is still good law.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Treatments that can take a clause out of force ("negative treatment").
NEGATIVE_KINDS: tuple[str, ...] = ("SUPERSEDES", "REVERSES", "WITHDRAWS")
# All treatment kinds we extract.  AMENDS / AFFIRMS never take anything out of force.
TREATMENT_KINDS: tuple[str, ...] = (*NEGATIVE_KINDS, "AMENDS", "AFFIRMS", "REINSTATES")

# Where in a decision a statement was found.
SECTIONS: tuple[str, ...] = (
    "header", "status", "context", "decision", "consequences", "alternatives", "later", "other",
)


@dataclass(frozen=True)
class Clause:
    """A numbered holding inside a decision (``1. **Three fixed namespaces.** ...``)."""

    n: int
    title: str
    text: str


@dataclass
class Decision:
    id: str  # canonical, e.g. "ADR-0116"
    num: int
    title: str
    path: str  # repo-relative path of the record
    status_raw: str | None
    status: str  # accepted | proposed | superseded | superseded_in_part | rejected | unknown
    date: str | None  # ISO date if declared
    sections: dict[str, str] = field(default_factory=dict)
    clauses: list[Clause] = field(default_factory=list)
    text: str = ""

    @property
    def clause_numbers(self) -> list[int]:
        return [c.n for c in self.clauses]


@dataclass(frozen=True)
class Unit:
    """A paragraph / list item of a decision, tagged with where it sits."""

    decision: str
    section: str  # one of SECTIONS
    clause: int | None  # clause the unit sits in (Decision section only)
    text: str


@dataclass(frozen=True)
class Citation:
    """One decision citing another (plain citation, no treatment implied)."""

    src: str
    dst: str
    section: str
    src_clause: int | None
    dst_clauses: tuple[int, ...]
    evidence: str


@dataclass(frozen=True)
class Treatment:
    """``actor`` treats ``target`` in the way ``kind`` says.

    ``target_clauses == ()`` means the treatment is about the whole decision.
    ``evidence`` is always the sentence the edge was derived from, so a human
    can verify it; ``rule`` names the extraction rule that fired.
    """

    actor: str
    target: str
    kind: str
    target_clauses: tuple[int, ...]
    evidence: str
    rule: str
    confidence: float
    reported_in: str  # decision whose text contained the statement
    affirmed_clauses: tuple[int, ...] = ()  # "Decisions 1 and 2 stand."
    whole: bool = False  # the sentence targets the entire decision (not a part of it)

    @property
    def scope(self) -> str:
        """``clauses`` (named clauses) > ``whole`` (entire decision) > ``partial`` (unspecified part)."""
        if self.target_clauses:
            return "clauses"
        return "whole" if self.whole else "partial"


@dataclass(frozen=True)
class PathRef:
    """A repo path mentioned in a decision."""

    decision: str
    path: str
    section: str
    exists: bool | None  # None = not checked
    current: str | None = None  # where the path lives today (same, or after a rename), if known


@dataclass
class Corpus:
    """Everything extracted from one decision-record directory."""

    name: str
    source_url: str
    commit: str
    license: str
    decisions: dict[str, Decision]
    citations: list[Citation]
    treatments: list[Treatment]
    paths: list[PathRef]
