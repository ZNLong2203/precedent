"""`precedent` command line: index, status, search, preflight, lint, explain, propose, mcp, demo."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Annotated, Any

import typer
from rich import box
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

from . import __version__
from . import lint as lint_mod
from .api import STATE_WORD, Precedent, _ranges
from .graph import StoreLocked

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Case law for your codebase: is this decision still good law? Built on the Relate embedded graph database.",
)
console = Console(highlight=False)
err = Console(stderr=True, highlight=False)

DEFAULT_STORE = os.environ.get("PRECEDENT_STORE", "data/relate-adr.rl")
StoreOpt = Annotated[Path, typer.Option("--store", "-s", help="Precedent store (a Relate .rl file).", envvar="PRECEDENT_STORE", show_default=True)]
JsonOpt = Annotated[bool, typer.Option("--json", help="Machine-readable JSON output.")]

STYLE = {"in_force": "green", "partial": "yellow", "out": "red", "contested": "magenta"}
GLYPH = {"in_force": "✓", "partial": "◐", "out": "✗", "contested": "⚡"}


def _open(store: Path, *, read_only: bool = True) -> Precedent:
    if not store.exists():
        err.print(f"[red]No store at {store}.[/red] Build one with `precedent index <repo>` or pass --store.")
        raise typer.Exit(2)
    try:
        return Precedent(store, read_only=read_only)
    except StoreLocked as e:
        err.print(f"[red]{escape(str(e))}[/red]")
        raise typer.Exit(5) from e


def _emit(data: Any) -> None:
    typer.echo(json.dumps(data, indent=2, default=str, ensure_ascii=False))


def _chip(state: str) -> str:
    return f"[{STYLE.get(state, 'white')}]{GLYPH.get(state, '?')} {STATE_WORD.get(state, state)}[/]"


@app.callback()
def _root(version: Annotated[bool, typer.Option("--version", help="Show version.", is_eager=True)] = False) -> None:
    if version:
        typer.echo(f"precedent {__version__}")
        raise typer.Exit()


# --------------------------------------------------------------------------- index
@app.command()
def index(
    repo: Annotated[Path, typer.Argument(help="Repository containing the decision records.")],
    out: Annotated[Path, typer.Option("--out", "-o", help="Where to write the Relate store.")] = Path(DEFAULT_STORE),
    adr_dir: Annotated[str, typer.Option(help="Directory of NNNN-*.md records, relative to REPO.")] = "docs/adr",
    rename: Annotated[list[str], typer.Option(help="Historical path rename OLD=NEW (repeatable).")] = [],  # noqa: B006
    name: Annotated[str, typer.Option(help="Corpus name stored in the graph.")] = "",
    source_url: Annotated[str, typer.Option(help="Public URL of the corpus.")] = "",
    license_id: Annotated[str, typer.Option("--license", help="SPDX id of the corpus license.")] = "",
    commit: Annotated[str, typer.Option(help="Pin the commit recorded in the store (default: git HEAD).")] = "",
) -> None:
    """Build a Precedent store (single .rl file) from a directory of decision records."""
    from .indexer import index as run_index

    renames = dict(r.split("=", 1) for r in rename)
    with console.status("indexing decision records into Relate…"):
        corpus, report, stats = run_index(repo, out, adr_dir, name=name or None, source_url=source_url, license_id=license_id,
                                          commit=commit or None, lsa_path=out.with_suffix(".lsa.npz"), renames=renames)
    t = Table(box=box.SIMPLE_HEAD, show_header=False)
    for k, v in stats.items():
        t.add_row(k.replace("_", " "), str(v))
    console.print(Panel(t, title=f"[bold]indexed {escape(corpus.name)}[/] @ {corpus.commit[:7]}", subtitle=str(out), border_style="cyan"))
    c = report.counts()
    console.print(f"standing: [green]{c.get('in_force', 0)} in force[/], [yellow]{c.get('partial', 0)} partly superseded[/], "
                  f"[red]{c.get('out', 0)} out of force[/], [magenta]{c.get('contested', 0)} contested[/]")


# --------------------------------------------------------------------------- info
@app.command()
def info(store: StoreOpt = Path(DEFAULT_STORE), as_json: JsonOpt = False) -> None:
    """Describe the store: corpus, counts, standing."""
    api = _open(store)
    try:
        data = api.corpus()
    finally:
        api.close()
    if as_json:
        return _emit(data)
    s = data["standing"]
    console.print(Panel(
        f"[bold]{escape(str(data.get('name')))}[/]  {escape(str(data.get('source_url') or ''))}\n"
        f"commit {str(data.get('commit'))[:10]}  license {data.get('license')}\n\n"
        f"{data['decisions']} decisions · {data['clauses']} clauses · {data['citations']} citations\n"
        f"treatments: " + ", ".join(f"{k.lower()} {v}" for k, v in data["treatments"].items()) + "\n\n"
        f"[green]{s.get('in_force', 0)} in force[/]   [yellow]{s.get('partial', 0)} partly superseded[/]   "
        f"[red]{s.get('out', 0)} out of force[/]   [magenta]{s.get('contested', 0)} contested[/]",
        title="precedent store", border_style="cyan"))


# --------------------------------------------------------------------------- status
@app.command()
def status(decision: Annotated[str, typer.Argument(help="e.g. ADR-0116 or 116")], store: StoreOpt = Path(DEFAULT_STORE), as_json: JsonOpt = False) -> None:
    """Is this decision still good law? Shows clause-level standing and the evidence."""
    api = _open(store)
    try:
        d = api.status(decision)
    except (KeyError, ValueError) as e:
        err.print(f"[red]{escape(str(e))}[/red]")
        raise typer.Exit(2) from e
    finally:
        api.close()
    if as_json:
        return _emit(d)
    console.print(f"\n[bold]{d['id']}[/]  {escape(d['title'])}")
    console.print(f"declared: [bold]{escape(d['declared_raw'] or d['declared'])}[/]   →   computed: {_chip(d['standing'])}"
                  + ("   [dim](restored)[/]" if d.get("restored") else ""))
    console.print(Panel(escape(d["verdict"]), border_style=STYLE.get(d["standing"], "white")))
    if d["clauses"]:
        t = Table(box=box.SIMPLE_HEAD, title="clauses", title_justify="left")
        t.add_column("§")
        t.add_column("clause")
        t.add_column("standing")
        for c in d["clauses"]:
            t.add_row(str(c["n"]), escape(c["title"][:70]), "[green]✓ good law[/]" if c["standing"] == "in_force" else f"[red]✗ out[/] by {', '.join(c['defeated_by'] or [])}")
        console.print(t)
    if d["treated_by"]:
        console.print("[bold]treated by later decisions[/]")
        for t in d["treated_by"]:
            if t["kind"] == "AFFIRMS" and not t["affirmed"]:
                continue
            tag = "effective" if t["effective"] else "[dim]no effect[/]"
            scope = _ranges(t["clauses"]) if t["clauses"] else t["scope"]
            console.print(f"  [cyan]{t['actor']}[/] [bold]{t['kind'].lower()}[/] ({scope}) · {tag} · conf {t['confidence']:.2f} · {t['rule']}")
            console.print(f"     [dim]“{escape(t['evidence'][:240])}”[/]")
    if d["dependent_count"]:
        stale = [x for x in d["dependents"] if x["cites_out_of_force"]]
        console.print(f"\n[bold]{d['dependent_count']}[/] later decisions build on this one"
                      + (f" - [yellow]{len(stale)} of the shown cite clauses that are out of force[/]" if stale else ""))
        for x in d["dependents"][:5]:
            flag = f"  [yellow]⚠ cites out-of-force {_ranges(x['cites_out_of_force'])}[/]" if x["cites_out_of_force"] else ""
            console.print(f"  {x['id']}  {escape(x['title'][:60])}{flag}")
    if d["code_paths"]:
        console.print("\n[bold]code it talks about[/]")
        for p in d["code_paths"][:6]:
            now = "" if p["exists"] else (f" → now `{p['current']}`" if p["current"] else " [dim](gone)[/]")
            console.print(f"  {escape(p['path'])}{now}")


# --------------------------------------------------------------------------- search
@app.command()
def search(query: Annotated[str, typer.Argument()], limit: Annotated[int, typer.Option("--limit", "-n")] = 8, store: StoreOpt = Path(DEFAULT_STORE), as_json: JsonOpt = False) -> None:
    """Hybrid search (BM25 + clause BM25 + vector), fused with reciprocal-rank fusion."""
    api = _open(store)
    try:
        hits = api.search(query, limit)
    finally:
        api.close()
    if as_json:
        return _emit(hits)
    t = Table(box=box.SIMPLE_HEAD)
    t.add_column("decision")
    t.add_column("standing")
    t.add_column("title")
    t.add_column("matched by", style="dim")
    for h in hits:
        t.add_row(h["id"], _chip(h["standing"]), escape(h["title"][:62]), "+".join(h["matched_by"]))
    console.print(t)


# --------------------------------------------------------------------------- preflight
@app.command()
def preflight(
    task: Annotated[str, typer.Argument(help="What you are about to do, in plain language.")] = "",
    path: Annotated[list[str], typer.Option("--path", "-p", help="File or directory you are about to touch (repeatable).")] = [],  # noqa: B006
    budget: Annotated[int, typer.Option(help="Token budget for the answer.")] = 1800,
    limit: Annotated[int, typer.Option("--limit", "-n")] = 6,
    store: StoreOpt = Path(DEFAULT_STORE),
    as_json: JsonOpt = False,
) -> None:
    """Which decisions must be respected before doing TASK / touching PATH? (stale ones flagged)"""
    if not task and not path:
        err.print("[red]give a task and/or at least one --path[/red]")
        raise typer.Exit(2)
    api = _open(store)
    try:
        out = api.preflight(task, path, budget_tokens=budget, k=limit)
    finally:
        api.close()
    if as_json:
        return _emit(out)
    console.print(f"[dim]≈{out['tokens']} tokens · {out.get('omitted', 0)} more decisions omitted[/]")
    for w in out["warnings"]:
        console.print(f"[yellow]⚠ {escape(w)}[/]")
    for c in out["decisions"]:
        console.print(f"\n{GLYPH[c['standing']]} [bold]{c['id']}[/] {escape(c['title'][:80])}   {_chip(c['standing'])}")
        for why in c["why"][:2]:
            console.print(f"   [dim]why:[/] {escape(why)}")
        if c["live_clauses"]:
            console.print("   [green]good law:[/] " + "; ".join(f"§{x['n']} {escape(x['title'][:34])}" for x in c["live_clauses"][:4]))
        for x in c["stale_clauses"][:3]:
            console.print(f"   [red]stale:[/] {escape(x['note'])}")
        if not c["live_clauses"] and not c["stale_clauses"] and c["gist"]:
            console.print(f"   [dim]{escape(c['gist'][:200])}[/]")


# --------------------------------------------------------------------------- lint
@app.command("cite-check")
def cite_check(
    category: Annotated[list[str], typer.Option("--category", "-c", help="Only these categories (repeatable).")] = [],  # noqa: B006
    limit: Annotated[int, typer.Option(help="Findings shown per category.")] = 5,
    store: StoreOpt = Path(DEFAULT_STORE),
    as_json: JsonOpt = False,
    fail_on_warn: Annotated[bool, typer.Option(help="Exit 1 if any warning is found (CI).")] = False,
) -> None:
    """Find stale statuses, reliance on superseded clauses, ghost paths and more."""
    api = _open(store)
    try:
        res = lint_mod.run(api, categories=category or None, limit=limit)
    finally:
        api.close()
    if as_json:
        _emit(res)
    else:
        t = Table(box=box.SIMPLE_HEAD, title=f"{res['total']} findings", title_justify="left")
        t.add_column("category")
        t.add_column("count", justify="right")
        t.add_column("what it means", style="dim")
        for c, n in res["summary"].items():
            t.add_row(c, str(n), res["categories"][c])
        console.print(t)
        for f in res["findings"]:
            sev = "yellow" if f["severity"] == "warn" else "blue"
            console.print(f"[{sev}]{f['category']:<24}[/] {escape(f['message'])}")
    if fail_on_warn and any(f["severity"] == "warn" for f in res["findings"]):
        raise typer.Exit(1)


# --------------------------------------------------------------------------- explain
@app.command()
def explain(a: str, b: str, store: StoreOpt = Path(DEFAULT_STORE), as_json: JsonOpt = False) -> None:
    """How are two decisions connected? (shortest path over citations and treatments)"""
    api = _open(store)
    try:
        r = api.explain(a, b)
    finally:
        api.close()
    if as_json:
        return _emit(r)
    if not r["connected"]:
        console.print(f"{r['from']} and {r['to']} are not connected within 6 hops.")
        return
    titles = {d["id"]: d["title"] for d in r["decisions"]}
    console.print(f"[bold]{r['length']} hop(s)[/]")
    for h in r["hops"]:
        console.print(f"  [cyan]{h['from']}[/] ({escape(titles[h['from']][:40])}) ─[bold]{h['kind'].lower()}[/]→ [cyan]{h['to']}[/] ({escape(titles[h['to']][:40])})")


# --------------------------------------------------------------------------- propose
@app.command()
def propose(
    spec: Annotated[str, typer.Argument(help="JSON file describing the draft decision, or - for stdin.")],
    commit: Annotated[bool, typer.Option(help="Record the decision if the review passes (needs a writable store).")] = False,
    store: StoreOpt = Path(DEFAULT_STORE),
    as_json: JsonOpt = False,
) -> None:
    """Review a draft decision against the graph (what-if). Dry run by default."""
    from . import guard

    raw = json.loads(sys.stdin.read() if spec == "-" else Path(spec).read_text(encoding="utf-8"))
    api = _open(store, read_only=not commit)
    try:
        out = guard.propose(api, raw, commit=commit)
    finally:
        api.close()
    if as_json:
        return _emit(out)
    colour = {"committed": "green", "dry-run ok": "green", "rejected": "red"}[out["verdict"]]
    console.print(Panel(f"[bold]{out['id']}[/] {escape(out['title'])}\nverdict: [{colour}]{out['verdict']}[/]   (simulated in {out['simulated_in']})", border_style=colour))
    for e in out["errors"]:
        console.print(f"[red]✗ {e['code']}[/] {escape(e['message'])}\n   [dim]fix:[/] {escape(e['fix'])}")
    for w in out["warnings"]:
        console.print(f"[yellow]⚠ {w['code']}[/] {escape(w['message'])}\n   [dim]fix:[/] {escape(w['fix'])}")
    if out["standing_changes"]:
        t = Table(box=box.SIMPLE_HEAD, title="what changes if this lands", title_justify="left")
        t.add_column("decision")
        t.add_column("before")
        t.add_column("after")
        t.add_column("out of force")
        for c in out["standing_changes"]:
            t.add_row(c["decision"], _chip(c["before"]) if c["before"] in STYLE else c["before"], _chip(c["after"]), _ranges(c["out_clauses_after"]))
        console.print(t)
    if out["dependents"]:
        console.print("[bold]rely on what you are overruling:[/] " + ", ".join(f"{d['id']} ({d['relies_on']})" for d in out["dependents"][:8]))
    console.print(f"[dim]{out['note']}[/]")


# --------------------------------------------------------------------------- mcp
@app.command()
def mcp(
    store: StoreOpt = Path(DEFAULT_STORE),
    writable: Annotated[bool, typer.Option(help="Open the store writable so propose_decision(commit=true) can record decisions.")] = False,
) -> None:
    """Serve the Precedent tools to an AI agent over MCP (stdio)."""
    from .mcp_server import serve

    if not store.exists():
        err.print(f"[red]No store at {store}[/red]")
        raise typer.Exit(2)
    serve(store, writable=writable)


# --------------------------------------------------------------------------- export-web
@app.command("export-web")
def export_web(
    out: Annotated[Path, typer.Option("--out", "-o")] = Path("docs/data"),
    store: StoreOpt = Path(DEFAULT_STORE),
) -> None:
    """Export the graph for the in-browser explorer (Relate compiled to WebAssembly)."""
    from .webexport import export

    api = _open(store)
    try:
        stats = export(api, out)
    finally:
        api.close()
    console.print(f"exported {stats['decisions']} decisions, {stats['edges']} edges → {out}")


# --------------------------------------------------------------------------- demo
@app.command()
def demo(store: StoreOpt = Path(DEFAULT_STORE)) -> None:
    """A 20-second tour: the headline numbers, one real decision, one agent preflight."""
    api = _open(store)
    try:
        c = api.corpus()
        s = c["standing"]
        nonforce = s.get("partial", 0) + s.get("out", 0)
        stale = lint_mod.run(api, categories=["stale-status"], limit=0)["summary"]["stale-status"]
        console.print(Panel(
            f"[bold]{c['decisions']}[/] decision records in [bold]{escape(str(c['name']))}[/]\n"
            f"[bold yellow]{nonforce}[/] have been partly or wholly superseded by later decisions\n"
            f"[bold red]{stale}[/] of those still say [bold]Accepted[/] or [bold]Proposed[/] in their own header\n\n"
            "Status lives in prose, so a reader (or an agent) of the original record acts on dead clauses.\n"
            "Precedent reads the prose once, builds the citation graph in Relate, and computes standing.",
            title="the problem", border_style="red"))
        focus = "ADR-0116" if "ADR-0116" in {h["id"] for h in api.search("fixed namespaces database semantics", 5)} else api.search("database", 1)[0]["id"]
        d = api.status(focus)
        console.print(f"\n[bold]{d['id']}[/] {escape(d['title'])}\n  declared [bold]{escape(d['declared_raw'] or d['declared'])}[/]  →  {_chip(d['standing'])}\n  {escape(d['verdict'])}")
        for t in [x for x in d["treated_by"] if x["effective"] and x["kind"] in ("SUPERSEDES", "REVERSES", "WITHDRAWS")][:1]:
            console.print(f"  [dim]{t['actor']} {t['kind'].lower()}: “{escape(t['evidence'][:200])}”[/]")
        console.print("\n[bold]agent preflight[/]  (task: add support for multiple databases)")
        p = api.preflight("add support for creating and switching between multiple databases", [], k=3, budget_tokens=900)
        for w in p["warnings"][:3]:
            console.print(f"  [yellow]⚠ {escape(w)}[/]")
        console.print(f"  [dim]{len(p['decisions'])} decisions, ≈{p['tokens']} tokens, stale clauses flagged and the controlling decision pulled in[/]")
        console.print("\nTry:  [cyan]precedent status ADR-0116[/]   [cyan]precedent cite-check[/]   [cyan]precedent preflight \"…\" -p path/to/file[/]")
    finally:
        api.close()


if __name__ == "__main__":  # pragma: no cover
    app()
