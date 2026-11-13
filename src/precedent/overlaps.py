"""Before you write a decision: which existing clauses does your draft overlap?

An agent (or a person) about to record a new decision has two ways to get it wrong: overrule a clause
without saying so (the record then keeps claiming it is in force), or build on a clause that has
already been overruled.  ``find_overlaps`` points at both, at *clause* level, from the draft alone.

It is deliberately not a judge.  It ranks; the author decides what the draft really does, declares
it in ``propose_decision``, and the graph then checks the claim (who relies on it, what changes
standing).  Language is the agent's job, verification is the graph's.  No model is called here.
"""

from __future__ import annotations

import re
from typing import Any

import numpy as np

from .api import _STOP, STATE_WORD, Precedent, _ranges

# Clause relevance = W_VECTOR * cosine(LSA(draft), LSA(clause)) + W_LEXICAL * idf-weighted share of the draft's
# distinctive keywords found in the clause.  A clause *overlaps* when it scores at least STRONG and at least
# RELATIVE of the best clause of its decision (so one decision does not flag every clause).
W_VECTOR, W_LEXICAL = 0.6, 0.4
STRONG = 0.40
RELATIVE = 0.80
KEYWORD_CAP = 12  # the draft's most distinctive words count; the long tail does not


def _keywords(text: str) -> set[str]:
    return {w.lower() for w in re.findall(r"[A-Za-z][A-Za-z0-9_]{2,}", text) if w.lower() not in _STOP}


def _weights(api: Precedent, kw: set[str]) -> dict[str, float]:
    """Distinctive draft keywords with their idf: 'namespaces' says more than 'commit'."""
    if api.lsa is None:
        return {w: 1.0 for w in sorted(kw)[:KEYWORD_CAP]}
    idf = {w: float(api.lsa.idf[api.lsa.vocab[w]]) if w in api.lsa.vocab else 1.0 for w in kw}
    return dict(sorted(idf.items(), key=lambda x: -x[1])[:KEYWORD_CAP])


def _clause_scores(api: Precedent, draft: str, kw: set[str], clauses: list[dict[str, Any]]) -> list[float]:
    if not clauses:
        return []
    texts = [f"{c['title']} {(c['text'] or '')[:1500]}" for c in clauses]
    wt = _weights(api, kw)
    total = sum(wt.values()) or 1.0
    lex = [sum(w for k, w in wt.items() if k in _keywords(t)) / total for t in texts]
    if api.lsa is None:
        return lex
    vecs = api.lsa.transform(texts)
    cos = vecs @ api.lsa.transform([draft])[0]
    return [float(W_VECTOR * max(0.0, c) + W_LEXICAL * x) for c, x in zip(np.atleast_1d(cos), lex, strict=True)]


def _strong(ranked: list[tuple[dict[str, Any], float]]) -> list[tuple[dict[str, Any], float]]:
    best = ranked[0][1] if ranked else 0.0
    return [(c, s) for c, s in ranked if s >= STRONG and s >= RELATIVE * best]


def find_overlaps(api: Precedent, draft: str = "", paths: list[str] | None = None, *, limit: int = 8, clauses_per: int = 3) -> dict[str, Any]:
    """Decisions and clauses a draft decision (plain text) and/or the files it touches overlap."""
    draft = (draft or "").strip()
    paths = [p for p in (paths or []) if p.strip()]
    if not draft and not paths:
        raise ValueError("give the draft text and/or the paths it touches")

    cand: dict[str, dict[str, Any]] = {}

    def bump(did: str, score: float, why: str) -> None:
        c = cand.setdefault(did, {"score": 0.0, "why": []})
        c["score"] += score
        if why not in c["why"]:
            c["why"].append(why)

    if draft:
        for i, h in enumerate(api.search(draft[:1500], k=max(2 * limit, 10))):
            bump(h["id"], h["score"] / (1 + 0.1 * i), "text matches (" + "+".join(h["matched_by"]) + ")")
    for p in paths:
        for r in api.paths_to_decisions(p):
            bump(r["id"], 0.4 if r.get("parent") else 1.0, f"refers to `{r['path']}`" + (" (enclosing directory)" if r.get("parent") else ""))
    if not cand:
        return {"candidates": [], "treats_template": [], "next": "nothing recorded overlaps this draft: write it without `treats`, citing only what you build on."}

    top = sorted(cand, key=lambda d: -cand[d]["score"])[:limit]
    info = api._info(top)
    kw = _keywords(draft)
    out: list[dict[str, Any]] = []
    template: list[dict[str, Any]] = []
    for did in top:
        d = info[did]
        rows = api.store.run(
            "MATCH (:Decision {id: $id})-[:HAS_CLAUSE]->(c:Clause) RETURN c.n AS n, c.title AS title, c.text AS text, c.standing AS standing, c.defeated_by AS by ORDER BY n",
            {"id": did},
        )
        scores = _clause_scores(api, draft, kw, rows) if draft else [0.0] * len(rows)
        ranked = sorted(zip(rows, scores, strict=True), key=lambda x: -x[1])
        strong = _strong(ranked)
        picked = {c["n"] for c, _ in ranked[:clauses_per]} | {c["n"] for c, _ in strong[:5]}  # the top few, plus every strong overlap
        shown = [{"n": c["n"], "title": c["title"], "standing": c["standing"], "defeated_by": c["by"] or [], "relevance": round(s, 2)} for c, s in ranked if c["n"] in picked]
        live = sorted(c["n"] for c, _ in strong if c["standing"] == "in_force")
        dead = sorted(c["n"] for c, _ in strong if c["standing"] == "out")
        controllers = sorted({b for c, _ in strong if c["standing"] == "out" for b in (c["by"] or [])} or (d["controlled_by"] or []))
        rec: dict[str, Any] = {
            "id": did, "title": d["title"], "standing": d["standing"], "relevance": round(cand[did]["score"], 2),
            "why": cand[did]["why"][:3], "clauses": shown, "overlaps_live": live, "overlaps_dead": dead,
        }
        if rows:
            if live:
                rec["read"] = (f"Your draft overlaps {_ranges(live)}, which still bind. If you mean to change them, declare it in `treats`; "
                               "if you only build on them, cite them in `cites`."
                               + (f" Already out of force: {_ranges(dead)} (by {', '.join(controllers)}) - cite that instead." if dead and controllers else ""))
                template.append({"target": did, "kind": "SUPERSEDES", "clauses": live, "reason": ""})
            elif dead:
                rec["read"] = (f"The part your draft touches ({_ranges(dead)}) is already out of force"
                               + (f" (by {', '.join(controllers)})" if controllers else "") + f". Build on {', '.join(controllers) or 'the later decision'}; do not cite {did} for it.")
            else:
                rec["read"] = "Related, but no single clause overlaps strongly. Cite it if you rely on it."
        else:
            rec["read"] = (f"{did} has no numbered clauses, so it is one rule: " + ("it still stands, so cite it or declare that you change it." if d["standing"] == "in_force"
                           else f"it is {STATE_WORD[d['standing']].lower()}: follow {', '.join(d['controlled_by'] or []) or 'its replacement'}."))
        out.append(rec)

    nxt = ("Call propose_decision with `treats` for every clause you really change (set `kind` to AMENDS if you only narrow it, and give a `reason`) "
           "and `cites` for what you build on. The graph then reports who relies on what you overrule.") if template else \
          "Nothing live overlaps strongly. Cite what you build on (`cites`); skip decisions marked out of force and cite their replacement instead."
    return {"candidates": out, "treats_template": template, "next": nxt,
            "how_to_read": "relevance is a heuristic ranking (vector + keyword overlap), not a ruling. `treats_template` is a starting point: edit `kind`, `clauses` and `reason`."}
