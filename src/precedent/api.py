"""The domain API shared by the CLI, the MCP server and the web exporter.

Every function returns plain JSON-serialisable dicts so an agent can consume them directly, and
every answer carries its *provenance* (the sentence, rule and decision each claim came from).
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

from .graph import Store
from .lsa import LSA
from .model import NEGATIVE_KINDS, TREATMENT_KINDS

KINDS_CYPHER = "|".join(TREATMENT_KINDS)
NEG_CYPHER = "|".join(NEGATIVE_KINDS)
STATE_WORD = {"in_force": "IN FORCE", "partial": "PARTLY SUPERSEDED", "out": "OUT OF FORCE", "contested": "CONTESTED"}
SECTION_WEIGHT = {"decision": 1.0, "consequences": 0.8, "later": 0.6, "context": 0.5, "other": 0.3, "header": 0.3}
PARTICIPLE = {"SUPERSEDES": "superseded", "REVERSES": "reversed", "WITHDRAWS": "withdrawn"}
ID_RX = re.compile(r"^(?:ADR[-\s]?)?0*(\d{1,4})$", re.IGNORECASE)


def canonical_id(raw: str) -> str:
    m = ID_RX.match(raw.strip())
    if not m:
        raise ValueError(f"not a decision id: {raw!r} (expected e.g. ADR-0116 or 116)")
    return f"ADR-{int(m.group(1)):04d}"


def est_tokens(obj: Any) -> int:
    return max(1, math.ceil(len(str(obj)) / 4))


def _sanitise_query(q: str) -> str:
    words = re.findall(r"[A-Za-z0-9_]{2,}", q)
    return " ".join(words[:24])


def _ranges(nums: list[int]) -> str:
    """[1, 2, 3, 5] -> '§1–3, §5'."""
    nums = sorted(set(nums))
    out, i = [], 0
    while i < len(nums):
        j = i
        while j + 1 < len(nums) and nums[j + 1] == nums[j] + 1:
            j += 1
        out.append(f"§{nums[i]}" if i == j else f"§{nums[i]}–{nums[j]}")
        i = j + 1
    return ", ".join(out)


class Precedent:
    """Query facade over a Precedent store (a Relate ``.rl`` file)."""

    def __init__(self, store: Store | str | Path, lsa_path: str | Path | None = None, *, read_only: bool = True):
        self.store = store if isinstance(store, Store) else Store(store, read_only=read_only)
        path = Path(self.store.path)
        cand = Path(lsa_path) if lsa_path else path.with_suffix(".lsa.npz")
        self.lsa: LSA | None = LSA.load(cand) if cand.exists() else None

    def close(self) -> None:
        self.store.close()

    # ------------------------------------------------------------------ corpus
    def corpus(self) -> dict[str, Any]:
        info = self.store.one("MATCH (c:Corpus) RETURN c.name AS name, c.source_url AS source_url, c.commit AS commit, c.license AS license") or {}
        counts = self.store.run("MATCH (d:Decision) RETURN d.standing AS standing, count(*) AS n")
        info["decisions"] = sum(r["n"] for r in counts)
        info["standing"] = {r["standing"]: r["n"] for r in counts}
        info["clauses"] = self.store.one("MATCH (c:Clause) RETURN count(c) AS n")["n"]
        info["citations"] = self.store.one("MATCH ()-[r:CITES]->() RETURN count(r) AS n")["n"]
        info["treatments"] = {
            r["kind"]: r["n"]
            for r in self.store.run(f"MATCH ()-[t:{KINDS_CYPHER}]->() RETURN type(t) AS kind, count(t) AS n ORDER BY n DESC")
        }
        return info

    # ------------------------------------------------------------------ status
    def status(self, decision: str, *, max_dependents: int = 8) -> dict[str, Any]:
        did = canonical_id(decision)
        d = self.store.one(
            "MATCH (d:Decision {id: $id}) RETURN d.id AS id, d.title AS title, d.status AS declared, d.status_raw AS declared_raw, "
            "d.date AS date, d.path AS path, d.standing AS standing, d.out_clauses AS out_clauses, "
            "d.partial_unspecified AS partial_unspecified, d.controlled_by AS controlled_by, d.restored AS restored, "
            "d.n_clauses AS n_clauses, d.gist AS gist",
            {"id": did},
        )
        if d is None:
            raise KeyError(f"{did} is not in this store")
        clauses = self.store.run(
            "MATCH (:Decision {id: $id})-[:HAS_CLAUSE]->(c:Clause) RETURN c.n AS n, c.title AS title, c.standing AS standing, c.defeated_by AS defeated_by ORDER BY c.n",
            {"id": did},
        )
        incoming = self.store.run(
            f"MATCH (a:Decision)-[t:{KINDS_CYPHER}]->(:Decision {{id: $id}}) "
            "RETURN a.id AS actor, a.title AS actor_title, a.standing AS actor_standing, type(t) AS kind, t.scope AS scope, "
            "t.clauses AS clauses, t.affirmed AS affirmed, t.effective AS effective, t.confidence AS confidence, "
            "t.rule AS rule, t.evidence AS evidence ORDER BY a.num",
            {"id": did},
        )
        outgoing = self.store.run(
            f"MATCH (:Decision {{id: $id}})-[t:{KINDS_CYPHER}]->(b:Decision) "
            "RETURN b.id AS target, b.title AS target_title, type(t) AS kind, t.scope AS scope, t.clauses AS clauses, "
            "t.effective AS effective, t.confidence AS confidence, t.evidence AS evidence ORDER BY b.num",
            {"id": did},
        )
        deps = self.store.run(
            "MATCH (s:Decision)-[c:CITES]->(:Decision {id: $id}) WHERE c.section IN ['decision', 'consequences'] "
            "RETURN s.id AS id, s.title AS title, s.standing AS standing, s.num AS num, collect(c.clauses) AS clause_lists ORDER BY s.num",
            {"id": did},
        )
        out_set = set(d["out_clauses"] or [])
        dependents = []
        for r in deps:
            cited = sorted({n for lst in r["clause_lists"] for n in (lst or [])})
            dependents.append({"id": r["id"], "title": r["title"], "standing": r["standing"], "cites_clauses": cited,
                               "cites_out_of_force": sorted(set(cited) & out_set)})
        paths = self.store.run(
            "MATCH (:Decision {id: $id})-[r:REFERS_TO]->(p:CodePath) RETURN p.path AS path, p.exists AS exists, p.current AS current, r.section AS section ORDER BY r.section, p.path",
            {"id": did},
        )
        d["clauses"] = clauses
        d["treated_by"] = incoming
        d["treats"] = outgoing
        d["dependents"] = dependents[:max_dependents]
        d["dependent_count"] = len(dependents)
        d["code_paths"] = paths[:20]
        d["declared_vs_computed"] = _mismatch(d)
        d["verdict"] = _verdict(d)
        return d

    # ------------------------------------------------------------------ search
    def search(self, query: str, k: int = 8) -> list[dict[str, Any]]:
        """Hybrid retrieval: BM25 over decisions + BM25 over clauses + vector similarity, fused with RRF."""
        q = _sanitise_query(query)
        ranks: dict[str, dict[str, int]] = {}
        clause_hit: dict[str, tuple[int, str]] = {}

        def add(channel: str, ids: list[str]) -> None:
            for i, did in enumerate(ids):
                ranks.setdefault(did, {}).setdefault(channel, i + 1)

        if q:
            rows = self.store.run(
                "CALL db.index.fulltext.queryNodes('decision_text', $q) YIELD node, score "
                "RETURN node.id AS id, score ORDER BY score DESC LIMIT 25", {"q": q})
            add("fulltext", [r["id"] for r in rows])
            crows = self.store.run(
                "CALL db.index.fulltext.queryNodes('clause_text', $q) YIELD node, score "
                "RETURN node.decision AS id, node.n AS n, node.title AS title, score ORDER BY score DESC LIMIT 25", {"q": q})
            seen: list[str] = []
            for r in crows:
                if r["id"] not in clause_hit:
                    clause_hit[r["id"]] = (r["n"], r["title"])
                if r["id"] not in seen:
                    seen.append(r["id"])
            add("clause", seen)
        if self.lsa is not None and query.strip():
            vec = [float(x) for x in self.lsa.transform([query])[0]]
            vrows = self.store.run(
                "MATCH (d:Decision) SEARCH d IN (VECTOR INDEX decision_vec FOR vector($v, $k, FLOAT32) LIMIT 25) SCORE AS s "
                "RETURN d.id AS id, s", {"v": vec, "k": self.lsa.dim})
            add("vector", [r["id"] for r in vrows])
        scored = sorted(((sum(1.0 / (60 + r) for r in ch.values()), did, ch) for did, ch in ranks.items()), reverse=True)[:k]
        if not scored:
            return []
        info = {r["id"]: r for r in self.store.run(
            "MATCH (d:Decision) WHERE d.id IN $ids RETURN d.id AS id, d.title AS title, d.standing AS standing, d.status AS declared, d.gist AS gist, d.controlled_by AS controlled_by",
            {"ids": [s[1] for s in scored]})}
        out = []
        for score, did, ch in scored:
            row = {**info[did], "score": round(score * 60, 3), "matched_by": sorted(ch)}
            if did in clause_hit:
                row["matched_clause"] = {"n": clause_hit[did][0], "title": clause_hit[did][1]}
            out.append(row)
        return out

    # ------------------------------------------------------------------ preflight
    def paths_to_decisions(self, path: str) -> list[dict[str, Any]]:
        """Decisions that talk about ``path`` (exact, renamed, or under a directory)."""
        x = path.strip().removeprefix("./")
        is_dir = x.endswith("/")
        rows = self.store.run(
            "MATCH (d:Decision)-[r:REFERS_TO]->(p:CodePath) "
            "WHERE p.path = $x OR p.current = $x OR ($dir AND (p.current STARTS WITH $x OR p.path STARTS WITH $x)) "
            "RETURN d.id AS id, r.section AS section, p.path AS path, p.current AS current",
            {"x": x, "dir": is_dir},
        )
        if not is_dir and "/" in x:  # also decisions about the enclosing directory, at lower weight
            parent = x.rsplit("/", 1)[0] + "/"
            rows += [dict(r, parent=True) for r in self.store.run(
                "MATCH (d:Decision)-[r:REFERS_TO]->(p:CodePath) WHERE p.path = $x OR p.current = $x "
                "RETURN d.id AS id, r.section AS section, p.path AS path, p.current AS current", {"x": parent})]
        return rows

    def preflight(self, task: str = "", paths: list[str] | None = None, *, budget_tokens: int = 1800, k: int = 6) -> dict[str, Any]:
        """Which decisions must an agent respect before doing ``task`` / touching ``paths``?

        Returns *good-law-aware* context: stale decisions are flagged, and the decisions that
        replaced them are pulled in as the controlling authority.
        """
        cand: dict[str, dict[str, Any]] = {}

        def bump(did: str, score: float, reason: str) -> None:
            c = cand.setdefault(did, {"score": 0.0, "why": []})
            c["score"] += score
            if reason not in c["why"]:
                c["why"].append(reason)

        for p in paths or []:
            for r in self.paths_to_decisions(p):
                base = 3.0 if not r.get("parent") else 1.2
                w = SECTION_WEIGHT.get(r["section"], 0.4)
                where = r["path"] if r["path"] == p else f"{r['path']} (now {r['current']})" if r.get("current") and r["current"] != r["path"] else r["path"]
                bump(r["id"], base * w, f"{r['section']} refers to `{where}`" + (" (enclosing directory)" if r.get("parent") else ""))
        if task.strip():
            for i, h in enumerate(self.search(task, k=12)):
                bump(h["id"], 2.0 * h["score"] / 1.0 / (1 + 0.15 * i), f"matches task ({'+'.join(h['matched_by'])})")

        if not cand:
            return {"task": task, "paths": paths or [], "decisions": [], "warnings": ["no decision matches; nothing recorded constrains this"], "tokens": 1}

        info = self._info(list(cand))
        # standing-aware re-ranking + pull in the controlling authority of stale decisions
        for did in list(cand):
            s = info[did]["standing"]
            if s == "out":
                cand[did]["score"] *= 0.35
            elif s in ("partial", "contested"):
                cand[did]["score"] *= 0.85
            for ctrl in info[did]["controlled_by"] or []:
                bump(ctrl, cand[did]["score"] * 0.9, f"controls {did} ({_ranges(info[did]['out_clauses'] or []) or 'part'})")
        info.update(self._info([d for d in cand if d not in info]))

        ranked = sorted(cand, key=lambda d: -cand[d]["score"])[: max(k * 2, 8)]
        cards: list[dict[str, Any]] = []
        warnings: list[str] = []
        used = 0
        for did in ranked:
            card = self._card(did, info[did], cand[did])
            cost = est_tokens(card)
            if cards and (used + cost > budget_tokens or len(cards) >= k):
                break
            cards.append(card)
            used += cost
            if card["standing"] != "in_force":
                warnings.append(f"{did} is {STATE_WORD[card['standing']].lower()}: " + (card["stale_clauses"][0]["note"] if card["stale_clauses"] else "see status"))
        return {
            "task": task, "paths": paths or [], "decisions": cards, "warnings": warnings,
            "omitted": max(0, len(cand) - len(cards)), "tokens": used,
            "how_to_read": "live_clauses are good law; stale_clauses were taken out of force by the decision named in `by` - follow that decision instead.",
        }

    def _info(self, ids: list[str]) -> dict[str, dict[str, Any]]:
        if not ids:
            return {}
        rows = self.store.run(
            "MATCH (d:Decision) WHERE d.id IN $ids RETURN d.id AS id, d.title AS title, d.standing AS standing, d.status AS declared, "
            "d.gist AS gist, d.path AS path, d.out_clauses AS out_clauses, d.controlled_by AS controlled_by, d.partial_unspecified AS partial_unspecified, d.date AS date",
            {"ids": ids},
        )
        return {r["id"]: r for r in rows}

    def _card(self, did: str, info: dict[str, Any], c: dict[str, Any]) -> dict[str, Any]:
        clauses = self.store.run(
            "MATCH (:Decision {id: $id})-[:HAS_CLAUSE]->(c:Clause) RETURN c.n AS n, c.title AS title, c.standing AS standing, c.defeated_by AS by ORDER BY c.n",
            {"id": did},
        )
        live = [{"n": x["n"], "title": x["title"]} for x in clauses if x["standing"] == "in_force"][:8]
        stale = []
        for x in clauses:
            if x["standing"] == "out":
                stale.append({"n": x["n"], "title": x["title"], "by": x["by"], "note": f"§{x['n']} {x['title']!r} superseded by {', '.join(x['by'] or [])}"})
        ev = self.store.run(
            f"MATCH (a:Decision)-[t:{NEG_CYPHER} {{effective: true}}]->(:Decision {{id: $id}}) RETURN a.id AS actor, type(t) AS kind, t.evidence AS evidence, t.clauses AS clauses ORDER BY t.confidence DESC LIMIT 2",
            {"id": did},
        )
        if info["partial_unspecified"] and not stale:
            for e in ev:
                stale.append({"n": None, "title": "(part not itemised)", "by": [e["actor"]], "note": f"a part is {PARTICIPLE.get(e['kind'], e['kind'].lower())} by {e['actor']}"})
        card = {
            "id": did, "title": info["title"], "standing": info["standing"], "declared_status": info["declared"],
            "path": info["path"], "gist": info["gist"], "why": c["why"][:3],
            "live_clauses": live, "stale_clauses": stale,
        }
        if ev:
            card["evidence"] = [{"by": e["actor"], "treatment": e["kind"], "clauses": e["clauses"], "quote": e["evidence"]} for e in ev]
        return card

    # ------------------------------------------------------------------ explain
    def explain(self, a: str, b: str, max_hops: int = 6) -> dict[str, Any]:
        a, b = canonical_id(a), canonical_id(b)
        row = self.store.one(
            f"MATCH (x:Decision {{id: $a}}), (y:Decision {{id: $b}}) MATCH p = shortestPath((x)-[:CITES|{KINDS_CYPHER}*..{int(max_hops)}]-(y)) "
            "RETURN [n IN nodes(p) | n.id] AS ids, [n IN nodes(p) | n.title] AS titles, [r IN relationships(p) | type(r)] AS kinds, "
            "[r IN relationships(p) | startNode(r).id] AS froms",
            {"a": a, "b": b},
        )
        if not row:
            return {"from": a, "to": b, "connected": False, "hops": []}
        hops = [{"from": row["froms"][i], "to": row["ids"][i + 1] if row["froms"][i] == row["ids"][i] else row["ids"][i], "kind": row["kinds"][i]} for i in range(len(row["kinds"]))]
        return {"from": a, "to": b, "connected": True, "length": len(hops), "decisions": [{"id": i, "title": t} for i, t in zip(row["ids"], row["titles"], strict=True)], "hops": hops}


def _mismatch(d: dict[str, Any]) -> str | None:
    if d["standing"] in ("partial", "out", "contested") and d["declared"] in ("accepted", "proposed", "unknown"):
        return f"declared '{d['declared_raw'] or d['declared']}' but computed {STATE_WORD[d['standing']].lower()}"
    return None


def _verdict(d: dict[str, Any]) -> str:
    s = d["standing"]
    head = f"{d['id']} is {STATE_WORD.get(s, s)}"
    out = d["out_clauses"] or []
    if s == "in_force":
        extra = " (restored after being reversed)" if d.get("restored") else ""
        return f"{head}{extra}: no later decision has taken any clause out of force."
    by = ", ".join(d["controlled_by"] or [])
    if s == "out":
        return f"{head}: superseded by {by}. Follow {by or 'the later decision'} instead."
    if s == "contested":
        return f"{head}: mutually conflicting treatments - needs a human ruling."
    live = [c["n"] for c in d["clauses"] if c["standing"] == "in_force"]
    if out:
        txt = f"{head}: {_ranges(out)} out of force (by {by})"
        return txt + (f"; {_ranges(live)} still good law." if live else ".")
    return f"{head}: a part of it is out of force (by {by}), but the text does not say which clause."
