"""The guard: an agent drafts a decision, the *graph* reviews it before it lands.

``propose`` writes the draft into the graph inside a Relate transaction, recomputes standing on the
uncommitted state (read-your-writes), checks invariants, and then either commits or rolls back.
The default is a dry run, so the same call doubles as a **what-if simulator**:

    "If I supersede ADR-0116 clauses 1 and 4, which decisions change standing, and who relies on
     what I am about to overrule?"

Errors are *explainable*: each carries a stable ``code``, a message, and a ``fix`` hint - the same
contract Relate itself uses for agent-facing errors.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from . import standing as st
from .api import STATE_WORD, Precedent, _ranges, canonical_id
from .graph import Store, load_model, write_back
from .model import NEGATIVE_KINDS, TREATMENT_KINDS

VERB = {"SUPERSEDES": "supersedes", "REVERSES": "reverses", "WITHDRAWS": "withdraws", "AMENDS": "amends"}
PROPOSABLE = tuple(VERB)


class ProposalError(ValueError):
    pass


def _err(code: str, message: str, fix: str) -> dict[str, str]:
    return {"code": code, "message": message, "fix": fix}


def _join_nums(nums: list[int]) -> str:
    return ", ".join(map(str, nums[:-1])) + f" and {nums[-1]}" if len(nums) > 1 else str(nums[0])


def render_markdown(adr_id: str, spec: dict[str, Any]) -> str:
    """Render the draft in the record format the extractor reads, so re-indexing reproduces the same edges."""
    lines = [f"# {adr_id}: {spec['title']}", "", "- **Status**: Proposed", f"- **Date**: {spec['date']}", "", "## Context", "",
             spec.get("context") or "TODO: state the problem and the constraints.", "", "## Decision", ""]
    if spec.get("body"):
        lines += [f"1. **{spec['title']}.** {spec['body'].strip()}", ""]
    for t in spec["treats"]:
        scope = f" Decisions {_join_nums(t['clauses'])}" if t["clauses"] else ""
        why = f": {t['reason']}" if t.get("reason") else "."
        verb = VERB[t["kind"]]
        lines.append(f"This ADR {verb} {t['target']}{scope}{why}")
    for c in spec["cites"]:
        scope = f" Decisions {_join_nums(c['clauses'])}" if c["clauses"] else ""
        lines.append(f"This decision builds on {c['target']}{scope}.")
    lines += ["", "## Consequences", "", spec.get("consequences") or "TODO: what becomes easier or harder.", ""]
    if spec.get("governs"):
        lines += ["Touches: " + ", ".join(f"`{p}`" for p in spec["governs"]) + ".", ""]
    return "\n".join(lines)


def normalise_spec(raw: dict[str, Any]) -> dict[str, Any]:
    if not str(raw.get("title", "")).strip():
        raise ProposalError("`title` is required")
    treats = []
    for t in raw.get("treats", []) or []:
        kind = str(t.get("kind", "SUPERSEDES")).upper()
        if kind not in PROPOSABLE:
            raise ProposalError(f"treatment kind {kind!r} is not one of {', '.join(PROPOSABLE)}")
        treats.append({"target": canonical_id(str(t["target"])), "kind": kind, "clauses": sorted({int(c) for c in t.get("clauses", []) or []}),
                       "reason": str(t.get("reason", "")).strip(), "whole": not t.get("clauses")})
    cites = [{"target": canonical_id(str(c["target"])), "clauses": sorted({int(x) for x in c.get("clauses", []) or []})} for c in raw.get("cites", []) or []]
    return {
        "title": str(raw["title"]).strip(), "body": str(raw.get("body", "")), "context": str(raw.get("context", "")),
        "consequences": str(raw.get("consequences", "")), "date": str(raw.get("date") or dt.date.today().isoformat()),
        "treats": treats, "cites": cites, "governs": [str(p) for p in raw.get("governs", []) or []],
        "acknowledge_impact": bool(raw.get("acknowledge_impact", False)),
    }


@contextlib.contextmanager
def scratch_copy(path: str) -> Iterator[Store]:
    """A throw-away writable fork of a store: Relate stores are single files, so a fork is a file copy."""
    tmp = Path(tempfile.mkdtemp(prefix="precedent-fork-"))
    try:
        dst = tmp / "fork.rl"
        shutil.copyfile(path, dst)
        store = Store(dst)
        try:
            yield store
        finally:
            store.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def propose(api: Precedent, raw: dict[str, Any], *, commit: bool = False) -> dict[str, Any]:
    """Review (and optionally record) a draft decision. Never raises for rule violations - it reports them."""
    spec = normalise_spec(raw)
    if api.store.read_only:
        if commit:
            raise PermissionError("the store is open read-only; reopen it writable (e.g. `precedent mcp --writable`) to commit")
        with scratch_copy(api.store.path) as fork:
            return _review(fork, api, spec, commit=False, mode="fork")
    return _review(api.store, api, spec, commit=commit, mode="transaction")


def _review(store: Store, api: Precedent, spec: dict[str, Any], *, commit: bool, mode: str) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    db = store.db
    db.autocommit = False
    try:
        decisions0, treatments0 = load_model(store)
        before = st.compute(decisions0, treatments0)
        next_num = max(d.num for d in decisions0.values()) + 1
        new_id = f"ADR-{next_num:04d}"

        # ---- static checks against the pre-state ------------------------------------------------
        for t in spec["treats"]:
            tgt = decisions0.get(t["target"])
            if tgt is None:
                errors.append(_err("unknown-target", f"{t['target']} is not in the graph", "check the id with `search_decisions`"))
                continue
            known = set(tgt.clause_numbers)
            bad = [c for c in t["clauses"] if tgt.clause_numbers and c not in known]
            if bad:
                errors.append(_err("unknown-clause", f"{t['target']} has no clause {_ranges(bad)} (it has {_ranges(sorted(known)) or 'no numbered clauses'})",
                                   "use clause numbers that exist, or omit `clauses` to treat the whole decision"))
            s0 = before[t["target"]]
            if t["kind"] in NEGATIVE_KINDS:
                if s0.state == "out" or (t["clauses"] and set(t["clauses"]) <= set(s0.out_clauses)):
                    warnings.append(_err("already-out-of-force", f"{t['target']} {_ranges(t['clauses']) or ''} is already out of force (by {', '.join(s0.controlling)})".replace("  ", " "),
                                         "cite the controlling decision instead of overruling a decision that is already gone"))
        for c in spec["cites"]:
            tgt = decisions0.get(c["target"])
            if tgt is None:
                errors.append(_err("unknown-target", f"{c['target']} is not in the graph", "check the id with `search_decisions`"))
                continue
            s0 = before[c["target"]]
            stale = [n for n in c["clauses"] if n in s0.out_clauses] or (c["clauses"] if s0.state == "out" else [])
            if s0.state == "out" or stale:
                errors.append(_err("cites-out-of-force",
                                   f"{c['target']} {_ranges(stale) or '(whole decision)'} is out of force (controlled by {', '.join(s0.controlling) or 'a later decision'})",
                                   f"cite {', '.join(s0.controlling) or 'the controlling decision'} instead, or drop this citation"))
        for p in spec["governs"]:
            if not api.paths_to_decisions(p) and not store.one("MATCH (p:CodePath) WHERE p.path = $p OR p.current = $p RETURN p.path AS p LIMIT 1", {"p": p}):
                warnings.append(_err("unknown-path", f"no existing decision mentions `{p}`", "fine for new code; otherwise check the path"))
        if errors:  # do not write a draft that cannot be valid
            db.rollback()
            return _report(spec, new_id, errors, warnings, [], [], None, committed=False, mode=mode, before=before, after=before)

        # ---- write the draft (inside the transaction) -------------------------------------------
        text = render_markdown(new_id, spec)
        emb = api.lsa.transform([spec["title"] + "\n" + spec["body"] + "\n" + spec["context"]])[0] if api.lsa else None
        store.run(
            "CREATE (d:Decision {id: $id, num: $num, title: $title, path: $path, status: 'proposed', status_raw: 'Proposed', date: $date, "
            "text: $text, gist: $gist, n_clauses: 0, standing: 'in_force', out_clauses: [], partial_unspecified: false, controlled_by: [], attackers: [], restored: false})",
            {"id": new_id, "num": next_num, "title": spec["title"], "path": f"docs/adr/{next_num:04d}-{_slug(spec['title'])}.md", "date": spec["date"],
             "text": text, "gist": " ".join((spec["body"] or spec["title"]).split())[:300]},
        )
        if emb is not None:
            store.run("MATCH (d:Decision {id: $id}) SET d.embedding = vector($v, $k, FLOAT32)", {"id": new_id, "v": [float(x) for x in emb], "k": api.lsa.dim})
        for t in spec["treats"]:
            evidence = f"This ADR {VERB[t['kind']]} {t['target']}" + (f" Decisions {_join_nums(t['clauses'])}" if t["clauses"] else "") + (f": {t['reason']}" if t["reason"] else ".")
            store.run(
                f"MATCH (a:Decision {{id: $a}}), (b:Decision {{id: $b}}) CREATE (a)-[:{t['kind']} {{scope: $scope, clauses: $clauses, evidence: $ev, rule: 'proposal', "
                "confidence: 1.0, affirmed: [], reported_in: $a, effective: false}]->(b)",
                {"a": new_id, "b": t["target"], "scope": "clauses" if t["clauses"] else "whole", "clauses": t["clauses"], "ev": evidence},
            )
        for c in spec["cites"]:
            store.run("MATCH (a:Decision {id: $a}), (b:Decision {id: $b}) CREATE (a)-[:CITES {section: 'decision', src_clause: null, clauses: $c, evidence: $ev}]->(b)",
                      {"a": new_id, "b": c["target"], "c": c["clauses"], "ev": f"This decision builds on {c['target']}"})

        # ---- recompute on the uncommitted state and diff ---------------------------------------
        decisions1, treatments1 = load_model(store)
        after = st.compute(decisions1, treatments1)
        changes = []
        for did, s1 in after.standing.items():
            s0 = before.standing.get(did)
            if s0 is None or (s0.state, s0.out_clauses, s0.unspecified_part_out) != (s1.state, s1.out_clauses, s1.unspecified_part_out):
                changes.append({"decision": did, "title": decisions1[did].title, "before": s0.state if s0 else "new", "after": s1.state,
                                "out_clauses_after": s1.out_clauses, "controlled_by": s1.controlling})
        if any(s.state == "contested" for d, s in after.standing.items() if before.standing.get(d) is None or before.standing[d].state != "contested"):
            errors.append(_err("creates-contest", "the draft makes some decisions mutually conflicting", "resolve the conflict explicitly: decide which side stands"))

        # ---- who relies on what we overrule? ---------------------------------------------------
        dependents: list[dict[str, Any]] = []
        for t in spec["treats"]:
            if t["kind"] not in NEGATIVE_KINDS:
                continue
            rows = store.run(
                "MATCH (s:Decision)-[c:CITES]->(d:Decision {id: $t}) WHERE c.section IN ['decision', 'consequences'] AND s.id <> $new "
                "AND ($whole OR any(n IN c.clauses WHERE n IN $cl)) RETURN s.id AS id, s.title AS title, s.standing AS standing, collect(c.clauses) AS cl",
                {"t": t["target"], "new": new_id, "whole": not t["clauses"], "cl": t["clauses"]})
            for r in rows:
                dependents.append({"id": r["id"], "title": r["title"], "standing": r["standing"], "relies_on": t["target"] + (" " + _ranges(t["clauses"]) if t["clauses"] else ""),
                                   "uses_clauses": sorted({n for lst in r["cl"] for n in lst})})
        live_dependents = [d for d in dependents if d["standing"] != "out"]
        if live_dependents and not spec["acknowledge_impact"]:
            errors.append(_err("impact-unacknowledged", f"{len(live_dependents)} live decision(s) rely on what this draft overrules: {', '.join(sorted({d['id'] for d in live_dependents})[:6])}",
                               "review them (use `decision_status`), amend them in the same draft, then resubmit with acknowledge_impact=true"))

        # ---- near-duplicates -------------------------------------------------------------------
        if emb is not None:
            near = store.run(
                "MATCH (d:Decision) SEARCH d IN (VECTOR INDEX decision_vec FOR vector($v, $k, FLOAT32) LIMIT 4) SCORE AS s RETURN d.id AS id, s",
                {"v": [float(x) for x in emb], "k": api.lsa.dim})
            related = {t["target"] for t in spec["treats"]} | {c["target"] for c in spec["cites"]}
            for r in near:
                if r["id"] != new_id and r["s"] >= 0.85 and r["id"] not in related:
                    warnings.append(_err("possible-duplicate", f"{r['id']} is {r['s']:.0%} similar and is neither cited nor treated", f"read {r['id']} and cite or supersede it"))

        ok = not errors
        if ok and commit and mode == "transaction":
            write_back(store, decisions1, after)
            db.commit()
            committed = True
        else:
            db.rollback()
            committed = False
        return _report(spec, new_id, errors, warnings, changes, dependents, text, committed=committed, mode=mode, before=before, after=after)
    except BaseException:
        db.rollback()
        raise
    finally:
        db.autocommit = True


def _slug(title: str) -> str:
    import re

    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:48] or "decision"


def _report(spec, new_id, errors, warnings, changes, dependents, markdown, *, committed, mode, before, after) -> dict[str, Any]:
    verdict = "committed" if committed else ("rejected" if errors else "dry-run ok")
    return {
        "id": new_id, "title": spec["title"], "verdict": verdict, "committed": committed, "simulated_in": mode,
        "errors": errors, "warnings": warnings, "standing_changes": changes,
        "summary": {"state_counts_before": before.counts(), "state_counts_after": after.counts()},
        "dependents": dependents, "markdown": markdown,
        "note": "No change was made to the store (dry run)." if not committed else f"{new_id} recorded; derived standing updated.",
        "explain": {s: STATE_WORD[s] for s in ("in_force", "partial", "out", "contested")},
    }
