#!/usr/bin/env python3
"""Do models lean on overruled clauses less when Precedent's `preflight` is in their context?

    uv run python scripts/agent_eval.py build            # write the prompts (data/agent-eval/prompts/)
    uv run python scripts/agent_eval.py run --reps 2     # give each prompt to a model (needs the `claude` CLI), save the answers
    uv run python scripts/agent_eval.py score            # compare the two conditions

`run` starts the model with no tools, no project settings, no memory and an empty working directory, so it sees
exactly the prompt and nothing else.  To try another model, feed the same prompt files to it and save its JSON
arrays as data/agent-eval/responses/r1/<prompt name>.json.

Design (see docs/evaluation.md section 8)
  * 24 tasks, each about an area where a decision is *partly* overruled.  The decisions were drawn at random
    (seed 11) from the 35 whose every overruling edge was hand-audited as correct and which have at least one
    dead and one live clause, so extractor mistakes cannot be blamed on the model.
  * condition `docs`: the five best matches of a plain full-text search, as written (header + Decision section).
  * condition `docs+warning` (control): the same documents plus one generic sentence saying later decisions may have
    overruled parts of them, with no information about which.  Does a nudge to be careful already do the job?
  * condition `docs+precedent`: the same five documents plus the `preflight` result for the task.
  * the model lists the numbered clauses its plan must respect or build on.  We count how often that list
    contains a clause the graph says is out of force.
Prompts, raw answers and this scorer are committed, so any model can be tried by feeding it the same files.
Nothing in `build` or `score` calls a model or the network.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import re
from pathlib import Path

from precedent.api import Precedent, _sanitise_query

ROOT = Path("data/agent-eval")
CONDITIONS = ("docs", "docs+warning", "docs+precedent")
WARNING = ("Note: decision records are never edited, so some of these decisions may have been partly overruled by later decisions "
           "that are not shown here. Take care not to rely on a clause that is no longer in force.")
BATCH = 6
DOC_CAP, HEADER_CAP = 3500, 700

INSTRUCTIONS = """\
You are a coding agent in a repository that keeps architecture decision records (ADRs). Below are {n} independent tasks.
For each task you get context retrieved for it. Decide which numbered decision clauses your plan for the task must
respect or build on (ADR number and clause number), at most 8, most important first. Use only the context in this
file: do not read any other file, search the repository or run commands.

Answer with a single JSON array, one object per task, in this exact shape and nothing else:

[{{"task_id": "T01", "relies_on": [{{"adr": "ADR-0046", "clause": 2}}], "note": "one sentence on your plan"}}]

Use `"clause": null` for a decision that has no numbered clauses.
"""


def sections(text: str) -> tuple[str, str]:
    head = re.split(r"^##\s", text, maxsplit=1, flags=re.MULTILINE)[0]
    m = re.search(r"^##\s+Decision\s*$(.*?)(?=^##\s|\Z)", text, re.MULTILINE | re.DOTALL)
    return head.strip()[:HEADER_CAP], (m.group(1).strip() if m else text[len(head) :].strip())[:DOC_CAP]


def plain_top5(api: Precedent, task: str) -> list[dict]:
    q = _sanitise_query(task)
    return api.store.run(
        "CALL db.index.fulltext.queryNodes('decision_text', $q) YIELD node, score RETURN node.id AS id, node.title AS title, node.text AS text ORDER BY score DESC LIMIT 5",
        {"q": q})


def render_docs(rows: list[dict]) -> str:
    out = []
    for r in rows:
        head, decision = sections(r["text"])
        out.append(f"--- {r['id']} ---\n{head}\n\n## Decision\n{decision}")
    return "\n\n".join(out)


def build() -> None:
    api = Precedent("data/relate-adr.rl")
    tasks = json.loads((ROOT / "tasks.json").read_text())
    order = tasks[:]
    random.Random(5).shuffle(order)
    batches = [order[i : i + BATCH] for i in range(0, len(order), BATCH)]
    (ROOT / "prompts").mkdir(exist_ok=True)
    (ROOT / "responses").mkdir(exist_ok=True)
    ctx = {}
    for t in tasks:
        ctx[t["id"]] = {
            "docs": render_docs(plain_top5(api, t["task"])),
            "preflight": json.dumps(api.preflight(t["task"], k=5), ensure_ascii=False, separators=(",", ":")),
        }
    for cond in CONDITIONS:
        for k, batch in enumerate(batches, 1):
            parts = [INSTRUCTIONS.format(n=len(batch))]
            for t in batch:
                c = ctx[t["id"]]
                parts.append(f"\n\n==================== TASK {t['id']} ====================\nTask: {t['task']}\n\nContext retrieved for this task: the decision records of the repository, as written.\n\n{c['docs']}")
                if cond == "docs+warning":
                    parts.append(f"\n\n{WARNING}")
                if cond == "docs+precedent":
                    parts.append(f"\n\nPrecedent `preflight` for this task (a tool that tracks which decisions are still in force):\n{c['preflight']}")
            name = f"{cond.replace('+', '-plus-')}-batch{k}.md"
            (ROOT / "prompts" / name).write_text("".join(parts), encoding="utf-8")
    (ROOT / "batches.json").write_text(json.dumps([[t["id"] for t in b] for b in batches]))
    print(f"wrote {len(CONDITIONS) * len(batches)} prompt files for {len(tasks)} tasks in {ROOT / 'prompts'}")


def _array(text: str) -> list[dict]:
    """The JSON array in a model answer, tolerating a code fence or a sentence around it."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    i, j = text.find("["), text.rfind("]")
    return json.loads(text[i : j + 1])


def run(reps: int, jobs: int, model: str) -> None:
    import concurrent.futures as cf
    import subprocess
    import tempfile

    work = Path(tempfile.mkdtemp(prefix="precedent-agent-eval-"))  # empty: nothing for the model to find
    cmd = ["claude", "-p", "--model", model, "--tools", "", "--no-session-persistence", "--setting-sources", "", "--disable-slash-commands",
           "--strict-mcp-config", "--output-format", "json"]
    meta_dir = ROOT / "meta"
    meta_dir.mkdir(exist_ok=True)

    def one(prompt: Path, rep: int) -> str:
        out = ROOT / "responses" / f"r{rep}" / f"{prompt.stem}.json"
        if out.exists():
            return f"skip {out.name} r{rep}"
        out.parent.mkdir(parents=True, exist_ok=True)
        done = subprocess.run(cmd, input=prompt.read_text(encoding="utf-8"), capture_output=True, text=True, cwd=work, timeout=1500)
        env = json.loads(done.stdout)
        out.write_text(json.dumps(_array(env["result"]), indent=1), encoding="utf-8")
        (meta_dir / f"r{rep}-{prompt.stem}.json").write_text(json.dumps({k: env.get(k) for k in ("modelUsage", "usage", "total_cost_usd", "duration_ms", "num_turns")}, indent=1))
        return f"ok {out.name} r{rep}"

    jobs_list = [(p, r) for r in range(1, reps + 1) for p in sorted((ROOT / "prompts").glob("*.md"))]
    with cf.ThreadPoolExecutor(max_workers=jobs) as ex:
        for msg in ex.map(lambda a: one(*a), jobs_list):
            print(msg, flush=True)


def paired(res: dict[str, dict[str, dict]], common: list[str], x: str, y: str) -> dict:
    """Tasks where only one of two conditions relied on an overruled clause, and the sign test on them."""
    only_x = [t for t in common if res[x][t]["stale_any"] and not res[y][t]["stale_any"]]
    only_y = [t for t in common if res[y][t]["stale_any"] and not res[x][t]["stale_any"]]
    return {f"relied_with_{x}_only": len(only_x), f"relied_with_{y}_only": len(only_y), "sign_test_p": round(sign_test_p(len(only_x), len(only_y)), 4)}


def sign_test_p(b: int, c: int) -> float:
    """Exact two-sided sign test on the discordant pairs."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2**n)


def score() -> None:
    api = Precedent("data/relate-adr.rl")
    tasks = {t["id"]: t for t in json.loads((ROOT / "tasks.json").read_text())}
    clause = {(r["d"], r["n"]): r["s"] for r in api.store.run("MATCH (c:Clause) RETURN c.decision AS d, c.n AS n, c.standing AS s")}
    decision = {r["id"]: r for r in api.store.run("MATCH (d:Decision) RETURN d.id AS id, d.standing AS standing, d.controlled_by AS by")}

    def load(rep_dir: Path, cond: str) -> dict[str, dict]:
        res: dict[str, dict] = {}
        for f in sorted(rep_dir.glob(f"{cond.replace('+', '-plus-')}-batch*.json")):
            for item in json.loads(f.read_text()):
                tid = item["task_id"]
                target = tasks[tid]["decision"]
                stale = live = unknown = 0
                cited = set()
                for r in item.get("relies_on", [])[:8]:
                    adr, n = r.get("adr"), r.get("clause")
                    cited.add(adr)
                    if adr not in decision:
                        unknown += 1
                    elif n is None:
                        stale += decision[adr]["standing"] == "out"
                        live += decision[adr]["standing"] != "out"
                    elif (adr, n) not in clause:
                        unknown += 1
                    elif clause[(adr, n)] == "out":
                        stale += 1
                    else:
                        live += 1
                res[tid] = {"stale": stale, "live": live, "unknown": unknown, "stale_any": stale > 0,
                            "cites_controller": bool(cited & set(decision[target]["by"] or [])), "cites_target": target in cited}
        return res

    def agg(res: dict[str, dict], common: list[str]) -> dict:
        rows = [res[t] for t in common]
        n = len(rows)
        return {
            "tasks": n, "tasks_relying_on_an_overruled_clause": sum(r["stale_any"] for r in rows),
            "pct_tasks_relying_on_an_overruled_clause": round(100 * sum(r["stale_any"] for r in rows) / n, 1),
            "overruled_clauses_per_task": round(sum(r["stale"] for r in rows) / n, 2),
            "live_clauses_per_task": round(sum(r["live"] for r in rows) / n, 2),
            "pct_citing_a_controlling_decision": round(100 * sum(r["cites_controller"] for r in rows) / n, 1),
            "pct_citing_the_partly_overruled_decision": round(100 * sum(r["cites_target"] for r in rows) / n, 1),
            "unknown_citations": sum(r["unknown"] for r in rows),
        }

    out: dict = {}
    for rep_dir in sorted((ROOT / "responses").glob("r*")):
        res = {c: load(rep_dir, c) for c in CONDITIONS}
        common = sorted(set.intersection(*(set(r) for r in res.values())))
        if not common:
            continue

        out[rep_dir.name] = {
            **{c: agg(res[c], common) for c in CONDITIONS},
            "paired": {"docs_vs_precedent": paired(res, common, "docs", "docs+precedent"), "warning_vs_precedent": paired(res, common, "docs+warning", "docs+precedent"),
                       "docs_vs_warning": paired(res, common, "docs", "docs+warning")},
            "per_task_overruled_clauses": {t: [res[c][t]["stale"] for c in CONDITIONS] for t in common},
        }
    if not out:
        raise SystemExit("no paired responses yet: run `agent_eval.py run` or save model answers in data/agent-eval/responses/r1/")
    (ROOT / "results.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build", "run", "score"])
    ap.add_argument("--reps", type=int, default=1, help="run: independent repetitions of every prompt")
    ap.add_argument("--jobs", type=int, default=4, help="run: parallel model calls")
    ap.add_argument("--model", default="sonnet", help="run: model alias for the claude CLI")
    a = ap.parse_args()
    if a.cmd == "run":
        run(a.reps, a.jobs, a.model)
    else:
        {"build": build, "score": score}[a.cmd]()
