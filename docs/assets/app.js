// Precedent explorer. The graph is loaded into Relate compiled to WebAssembly and
// *every* list, card and chart below is answered by a Cypher query executed in this tab.
import init, { RelateDb } from "./relate/relate.js";

const REPO_URL = ""; // filled in at publish time
const RELATE_WASM_VERSION = "1.0.1"; // keep in sync with scripts/vendor-web.sh
const NEG = new Set(["SUPERSEDES", "REVERSES", "WITHDRAWS"]);
const STATES = {
  in_force: { label: "in force", short: "in force", varName: "--ok" },
  partial: { label: "partly superseded", short: "partly", varName: "--warn" },
  out: { label: "out of force", short: "out", varName: "--bad" },
  contested: { label: "contested", short: "contested", varName: "--mag" },
};
const EXAMPLES = [
  ["Accepted on paper, partly superseded", `MATCH (d:Decision)
WHERE d.status = 'accepted' AND d.standing = 'partial'
RETURN d.id AS id, d.title AS title, d.out_clauses AS out_clauses, d.controlled_by AS by
ORDER BY size(d.out_clauses) DESC LIMIT 15`],
  ["Who took clauses from ADR-0116?", `MATCH (a:Decision)-[t:SUPERSEDES|REVERSES|WITHDRAWS {effective: true}]->(d:Decision {id: 'ADR-0116'})
RETURN a.id AS decision, type(t) AS treatment, t.clauses AS clauses, t.evidence AS evidence`],
  ["Still relying on a dead clause", `MATCH (s:Decision)-[c:CITES]->(d:Decision)
WHERE c.section IN ['decision', 'consequences'] AND size(c.clauses) > 0
  AND any(n IN c.clauses WHERE n IN d.out_clauses)
  AND NOT s.id IN d.controlled_by
RETURN s.id AS relies, d.id AS on, [n IN c.clauses WHERE n IN d.out_clauses] AS dead_clauses, d.controlled_by AS replaced_by
ORDER BY s.num DESC LIMIT 15`],
  ["Chains of overruling", `MATCH (a:Decision)-[:SUPERSEDES|REVERSES|WITHDRAWS]->(b:Decision)-[:SUPERSEDES|REVERSES|WITHDRAWS]->(c:Decision)
RETURN a.id AS latest, b.id AS middle, c.id AS earliest LIMIT 15`],
  ["More like ADR-0116 (vector index)", `MATCH (d:Decision {id: 'ADR-0116'})
WITH d.embedding AS e
MATCH (x:Decision) SEARCH x IN (VECTOR INDEX decision_vec FOR e LIMIT 8) SCORE AS similarity
RETURN x.id AS id, x.title AS title, x.standing AS standing, round(similarity * 100) / 100 AS similarity`],
  ["Path between two decisions", `MATCH (a:Decision {id: 'ADR-0116'}), (b:Decision {id: 'ADR-0472'})
MATCH p = shortestPath((a)-[:CITES|SUPERSEDES|REVERSES|WITHDRAWS|AMENDS*..6]-(b))
RETURN [n IN nodes(p) | n.id] AS path, length(p) AS hops`],
];

const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const cssVar = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const stateColor = (s) => cssVar(STATES[s]?.varName || "--muted");

let db, doc, fg, emptyHtml = "";
let selected = null, hovered = null, hl = null, showAll = false;
const filters = new Set(Object.keys(STATES));
const timing = { last: 0, count: 0 };
let nodeIndex = new Map();
let fitPending = true;

// ----------------------------------------------------------------------------- Relate
function q(cypher, params) {
  const t0 = performance.now();
  const env = JSON.parse(db.execute(cypher, params ? JSON.stringify(params) : null));
  if (env.error) throw new Error(env.error);
  timing.last = env.elapsed_ms ?? performance.now() - t0;
  timing.count += 1;
  $("#foot-q").textContent = `last query ${timing.last.toFixed(1)} ms · ${timing.count} queries this session`;
  return env;
}
const rows = (cypher, params) => q(cypher, params).rows;
const chunk = (arr, n) => Array.from({ length: Math.ceil(arr.length / n) }, (_, i) => arr.slice(i * n, i * n + n));

function loadGraph(d) {
  const t0 = performance.now();
  const dim = d.meta.embedding_dim || 0;
  for (const ddl of [
    "CREATE CONSTRAINT decision_id IF NOT EXISTS FOR (d:Decision) REQUIRE d.id IS UNIQUE",
    "CREATE CONSTRAINT clause_key IF NOT EXISTS FOR (c:Clause) REQUIRE c.key IS UNIQUE",
    "CREATE FULLTEXT INDEX decision_text IF NOT EXISTS FOR (d:Decision) ON EACH [d.title, d.text]",
  ]) q(ddl);
  if (dim) q(`CREATE VECTOR INDEX decision_vec IF NOT EXISTS FOR (d:Decision) ON (d.embedding) OPTIONS {indexConfig: {\`vector.dimensions\`: ${dim}, \`vector.similarity_function\`: 'cosine'}}`);

  for (const part of chunk(d.decisions, 150)) {
    q(`UNWIND $rows AS r CREATE (d:Decision {id: r.id, num: r.num, title: r.title, status: r.status, status_raw: r.status_raw, date: r.date,
        standing: r.standing, out_clauses: r.out_clauses, controlled_by: r.controlled_by, attackers: r.attackers, restored: r.restored,
        n_clauses: r.n_clauses, gist: r.gist, text: r.text, path: r.path${dim ? ", embedding: vector(r.emb, $dim, FLOAT32)" : ""}})`, { rows: part, dim });
  }
  for (const part of chunk(d.clauses, 500)) {
    q(`UNWIND $rows AS r MATCH (d:Decision {id: r.decision}) CREATE (d)-[:HAS_CLAUSE]->(:Clause {key: r.key, decision: r.decision, n: r.n, title: r.title, standing: r.standing, defeated_by: r.defeated_by})`, { rows: part });
  }
  for (const part of chunk(d.cites, 800)) {
    q(`UNWIND $rows AS r MATCH (a:Decision {id: r.src}), (b:Decision {id: r.dst}) CREATE (a)-[:CITES {section: r.section, clauses: r.clauses}]->(b)`, { rows: part });
  }
  for (const kind of ["SUPERSEDES", "REVERSES", "WITHDRAWS", "AMENDS", "REINSTATES", "AFFIRMS"]) {
    const part = d.treatments.filter((t) => t.kind === kind);
    if (!part.length) continue;
    q(`UNWIND $rows AS r MATCH (a:Decision {id: r.actor}), (b:Decision {id: r.target}) CREATE (a)-[:${kind} {scope: r.scope, clauses: r.clauses, evidence: r.evidence, confidence: r.confidence, rule: r.rule, effective: r.effective}]->(b)`, { rows: part });
  }
  const uniquePaths = [...new Map(d.paths.map((p) => [p.path, p])).values()];
  for (const part of chunk(uniquePaths, 600)) q(`UNWIND $rows AS r CREATE (:CodePath {path: r.path, exists: r.exists, current: r.current})`, { rows: part });
  for (const part of chunk(d.paths, 800)) q(`UNWIND $rows AS r MATCH (d:Decision {id: r.decision}), (p:CodePath {path: r.path}) CREATE (d)-[:REFERS_TO]->(p)`, { rows: part });
  return performance.now() - t0;
}

// ----------------------------------------------------------------------------- helpers
function ranges(nums) {
  const n = [...new Set(nums)].sort((a, b) => a - b);
  const out = [];
  for (let i = 0; i < n.length; ) {
    let j = i;
    while (j + 1 < n.length && n[j + 1] === n[j] + 1) j++;
    out.push(i === j ? `§${n[i]}` : `§${n[i]}–${n[j]}`);
    i = j + 1;
  }
  return out.join(", ");
}
const pill = (s) => `<span class="pill ${s}">${STATES[s]?.short ?? s}</span>`;
const goto = (id) => `<span class="goto" data-goto="${esc(id)}">${esc(id)}</span>`;
const flat = (lists) => [...new Set((lists || []).flat(2))].filter((x) => Number.isInteger(x));

function verdict(d, clauses) {
  const by = (d.controlled_by || []).join(", ");
  const out = d.out_clauses || [];
  if (d.standing === "in_force") return `${d.id} is <b>in force</b>${d.restored ? " (restored after being reversed)" : ""}: no later decision has taken any clause out of force.`;
  if (d.standing === "out") return `${d.id} is <b>out of force</b>: superseded by ${esc(by)}. Follow ${esc(by || "the later decision")} instead.`;
  if (d.standing === "contested") return `${d.id} is <b>contested</b>: mutually conflicting treatments need a human ruling.`;
  const live = clauses.filter((c) => c.standing === "in_force").map((c) => c.n);
  if (out.length) return `${d.id} is <b>partly superseded</b>: ${ranges(out)} out of force (by ${esc(by)})${live.length ? `; ${ranges(live)} still good law` : ""}.`;
  return `${d.id} is <b>partly superseded</b> by ${esc(by)}, but the text does not say which clause.`;
}

// ----------------------------------------------------------------------------- list + search
function sanitise(s) { return (s.match(/[A-Za-z0-9_]{2,}/g) || []).slice(0, 24).join(" "); }

function renderList() {
  const text = $("#q").value.trim();
  let list;
  if (text.length >= 2) {
    const query = sanitise(text);
    const m = /^(?:ADR[-\s]?)?0*(\d{1,4})$/i.exec(text);
    if (m) {
      const id = `ADR-${String(m[1]).padStart(4, "0")}`;
      list = rows("MATCH (d:Decision {id: $id}) RETURN d.id AS id, d.title AS title, d.standing AS standing, d.out_clauses AS out", { id });
    } else if (query) {
      list = rows("CALL db.index.fulltext.queryNodes('decision_text', $q) YIELD node, score RETURN node.id AS id, node.title AS title, node.standing AS standing, node.out_clauses AS out ORDER BY score DESC LIMIT 60", { q: query });
    } else list = [];
    $("#listmeta").textContent = `${list.length} match${list.length === 1 ? "" : "es"} · full-text index in Relate`;
  } else {
    list = rows("MATCH (d:Decision) RETURN d.id AS id, d.title AS title, d.standing AS standing, d.out_clauses AS out ORDER BY CASE d.standing WHEN 'out' THEN 0 WHEN 'contested' THEN 1 WHEN 'partial' THEN 2 ELSE 3 END, size(d.out_clauses) DESC, d.num LIMIT 400");
    $("#listmeta").textContent = "Most affected first. Search to filter.";
  }
  list = list.filter((r) => filters.has(r.standing)).slice(0, 150);
  $("#list").innerHTML = list.map((r) => `<li><button class="row" data-id="${esc(r.id)}" ${r.id === selected ? 'aria-current="true"' : ""}>
      <span class="id">${esc(r.id)} ${pill(r.standing)}${r.out?.length ? `<span class="muted">${esc(ranges(r.out))}</span>` : ""}</span>
      <span class="ttl">${esc(r.title)}</span></button></li>`).join("") || `<li class="listmeta">No decision matches.</li>`;
}

function renderChips() {
  $("#chips").innerHTML = Object.entries(STATES).map(([k, v]) =>
    `<button class="chip" data-chip="${k}" aria-pressed="${filters.has(k)}"><i class="dot" style="--c:var(${v.varName})"></i>${v.short}</button>`).join("");
}

// ----------------------------------------------------------------------------- graph
function graphData() {
  const links = rows("MATCH (a:Decision)-[t:SUPERSEDES|REVERSES|WITHDRAWS|AMENDS]->(b:Decision) RETURN a.id AS source, b.id AS target, type(t) AS kind, t.effective AS effective, t.clauses AS clauses");
  const nodes = rows("MATCH (d:Decision) RETURN d.id AS id, d.num AS num, d.title AS title, d.standing AS standing, d.status AS declared, d.out_clauses AS out");
  const deg = new Map();
  for (const l of links) { deg.set(l.source, (deg.get(l.source) || 0) + 1); deg.set(l.target, (deg.get(l.target) || 0) + 1); }
  const keep = nodes.filter((n) => showAll || deg.has(n.id) || n.id === selected);
  for (const n of keep) n.r = 3 + Math.sqrt(deg.get(n.id) || 0) * 1.7;
  const ids = new Set(keep.map((n) => n.id));
  const ls = links.filter((l) => ids.has(l.source) && ids.has(l.target)).map((l) => ({ ...l }));
  return { nodes: keep, links: ls };
}

function buildGraph() {
  const el = $("#graph");
  const data = graphData();
  nodeIndex = new Map(data.nodes.map((n) => [n.id, n]));
  $("#graphmeta").textContent = `${data.nodes.length} decisions · ${data.links.length} treatments`;
  if (!fg) {
    fg = ForceGraph()(el)
      .backgroundColor("rgba(0,0,0,0)")
      .nodeId("id")
      .nodeLabel((n) => `<b>${esc(n.id)}</b> · ${esc(n.title)}<br><span style="opacity:.8">${esc(STATES[n.standing]?.label || n.standing)}</span>`)
      .nodeCanvasObject((n, ctx, scale) => {
        const dim = hl && !hl.has(n.id);
        ctx.globalAlpha = dim ? 0.18 : 1;
        ctx.beginPath(); ctx.arc(n.x, n.y, n.r, 0, 2 * Math.PI); ctx.fillStyle = stateColor(n.standing); ctx.fill();
        if (n.id === selected || n.id === hovered) {
          ctx.lineWidth = 2 / scale; ctx.strokeStyle = cssVar("--text"); ctx.stroke();
        }
        if (n.id === selected || n.id === hovered || (scale > 2.4 && !dim)) {
          const fs = Math.max(3.2, 11 / scale);
          ctx.font = `${n.id === selected ? "600 " : ""}${fs}px ${cssVar("--mono") || "monospace"}`;
          ctx.fillStyle = cssVar("--text"); ctx.textAlign = "center"; ctx.textBaseline = "top";
          ctx.fillText(n.id.replace("ADR-", ""), n.x, n.y + n.r + 1.5);
        }
        ctx.globalAlpha = 1;
      })
      .nodePointerAreaPaint((n, color, ctx) => { ctx.fillStyle = color; ctx.beginPath(); ctx.arc(n.x, n.y, n.r + 2, 0, 2 * Math.PI); ctx.fill(); })
      .linkColor((l) => {
        const dim = hl && !(hl.has(l.source.id ?? l.source) && hl.has(l.target.id ?? l.target));
        const c = NEG.has(l.kind) ? cssVar("--bad") : cssVar("--amend");
        return dim ? c + "30" : c;
      })
      .linkWidth((l) => (l.effective ? 1.6 : 0.8))
      .linkLineDash((l) => (NEG.has(l.kind) && !l.effective ? [3, 2] : null))
      .linkDirectionalArrowLength((l) => (NEG.has(l.kind) ? 4.5 : 3))
      .linkDirectionalArrowRelPos(0.93)
      .onNodeHover((n) => { hovered = n ? n.id : null; el.style.cursor = n ? "pointer" : "default"; })
      .onNodeClick((n) => select(n.id, { center: false }))
      .onBackgroundClick(() => select(null))
      .cooldownTicks(200)
      .d3VelocityDecay(0.32)
      .onEngineStop(() => {
        if (!fitPending) return;
        fitPending = false;
        fg.zoomToFit(450, 36);
        const n = selected && nodeIndex.get(selected);
        if (n) setTimeout(() => { fg.centerAt(n.x, n.y, 600); fg.zoom(2.6, 600); }, 520);
      });
    fg.d3Force("charge").strength(-46);
    fg.d3Force("link").distance(34);
    // pull detached components toward the centre so the whole case-law network stays in view
    let simNodes = [];
    const gravity = (alpha) => { for (const n of simNodes) { n.vx -= n.x * 0.06 * alpha; n.vy -= n.y * 0.06 * alpha; } };
    gravity.initialize = (ns) => { simNodes = ns; };
    fg.d3Force("gravity", gravity);
    new ResizeObserver(() => fg.width(el.clientWidth).height(el.clientHeight)).observe(el);
  }
  fitPending = true;
  fg.graphData(data);
}

function setHighlight() {
  if (!selected || !fg) { hl = null; return; }
  hl = new Set([selected]);
  for (const l of fg.graphData().links) {
    const a = l.source.id ?? l.source, b = l.target.id ?? l.target;
    if (a === selected) hl.add(b);
    if (b === selected) hl.add(a);
  }
}

// ----------------------------------------------------------------------------- detail
function select(id, opts = {}) {
  selected = id;
  const url = new URL(location.href);
  if (id) url.searchParams.set("id", id); else url.searchParams.delete("id");
  history.replaceState(null, "", url);
  if (id && !nodeIndex.has(id)) { showAll = true; $("#showall").checked = true; buildGraph(); }
  setHighlight();
  for (const b of document.querySelectorAll(".row")) b.toggleAttribute("aria-current", b.dataset.id === id);
  if (id && fg && opts.center !== false) {
    const n = nodeIndex.get(id);
    if (n && Number.isFinite(n.x)) { fg.centerAt(n.x, n.y, 600); fg.zoom(3, 600); }
  }
  renderDetail(id);
}

function renderDetail(id) {
  const el = $("#detail");
  if (!id) { el.innerHTML = emptyHtml; return; }
  const d = rows("MATCH (d:Decision {id: $id}) RETURN d.id AS id, d.title AS title, d.status AS declared, d.status_raw AS declared_raw, d.date AS date, d.standing AS standing, d.out_clauses AS out_clauses, d.controlled_by AS controlled_by, d.restored AS restored, d.gist AS gist, d.path AS path", { id })[0];
  if (!d) { el.innerHTML = `<div class="empty"><h2>${esc(id)}</h2><p>Not in this graph.</p></div>`; return; }
  const clauses = rows("MATCH (:Decision {id: $id})-[:HAS_CLAUSE]->(c:Clause) RETURN c.n AS n, c.title AS title, c.standing AS standing, c.defeated_by AS by ORDER BY c.n", { id });
  const treated = rows("MATCH (a:Decision)-[t:SUPERSEDES|REVERSES|WITHDRAWS|AMENDS]->(:Decision {id: $id}) RETURN a.id AS actor, type(t) AS kind, t.clauses AS clauses, t.scope AS scope, t.effective AS effective, t.confidence AS conf, t.evidence AS evidence ORDER BY a.num", { id });
  const treats = rows("MATCH (:Decision {id: $id})-[t:SUPERSEDES|REVERSES|WITHDRAWS]->(b:Decision) RETURN b.id AS target, b.title AS title, type(t) AS kind, t.clauses AS clauses, t.effective AS effective ORDER BY b.num", { id });
  const deps = rows("MATCH (s:Decision)-[c:CITES]->(:Decision {id: $id}) WHERE c.section IN ['decision', 'consequences'] RETURN s.id AS id, s.title AS title, s.num AS num, collect(c.clauses) AS cl ORDER BY num", { id });
  const paths = rows("MATCH (:Decision {id: $id})-[:REFERS_TO]->(p:CodePath) RETURN p.path AS path, p.exists AS exists, p.current AS current LIMIT 8", { id });
  let similar = [];
  try {
    similar = rows("MATCH (d:Decision {id: $id}) WITH d.embedding AS e MATCH (x:Decision) SEARCH x IN (VECTOR INDEX decision_vec FOR e LIMIT 7) SCORE AS s RETURN x.id AS id, x.title AS title, x.standing AS standing, s", { id }).filter((r) => r.id !== id).slice(0, 5);
  } catch { /* vector index not available */ }

  const out = new Set(d.out_clauses || []);
  const mismatch = ["partial", "out", "contested"].includes(d.standing) && ["accepted", "proposed", "unknown"].includes(d.declared);
  el.innerHTML = `
    <div class="d-id">${esc(d.id)}${d.date ? " · " + esc(d.date) : ""}</div>
    <h2 class="d-title">${esc(d.title)}</h2>
    <div class="chiprow">
      <span>declared <b>${esc(d.declared_raw || d.declared)}</b></span><span class="arrow">→</span>
      <span>computed ${pill(d.standing)}</span>${mismatch ? `<span class="warnflag">⚠ header is out of date</span>` : ""}
    </div>
    <div class="verdict ${d.standing}">${verdict(d, clauses)}</div>
    ${clauses.length ? `<h3>Clauses</h3><table class="clauses">${clauses.map((c) => `<tr><td>§${c.n}</td><td>${esc(c.title)}</td>
        <td>${c.standing === "in_force" ? '<span class="ok">✓ good law</span>' : `<span class="no">✗ ${(c.by || []).map(goto).join(", ")}</span>`}</td></tr>`).join("")}</table>` : ""}
    ${treated.length ? `<h3>Treated by later decisions</h3>${treated.map((t) => `
      <div class="treat ${NEG.has(t.kind) ? "neg" : ""} ${t.effective ? "eff" : ""}">
        <div><span class="who">${goto(t.actor)} ${esc(t.kind.toLowerCase())}</span> ${t.clauses?.length ? esc(ranges(t.clauses)) : esc(t.scope === "whole" ? "the whole decision" : "an unspecified part")}
          ${NEG.has(t.kind) ? (t.effective ? "" : '<span class="muted">· no effect (its own authority is gone)</span>') : ""}</div>
        <blockquote>“${esc(t.evidence)}”</blockquote>
        <div class="meta">confidence ${Number(t.conf).toFixed(2)}</div>
      </div>`).join("")}` : ""}
    ${treats.length ? `<h3>What it changed</h3><ul>${treats.map((t) => `<li>${esc(t.kind.toLowerCase())} ${goto(t.target)} ${t.clauses?.length ? esc(ranges(t.clauses)) : ""} <span class="muted">${esc(t.title.slice(0, 50))}</span></li>`).join("")}</ul>` : ""}
    ${deps.length ? `<h3>${deps.length} later decision${deps.length > 1 ? "s" : ""} build on it</h3>${deps.slice(0, 8).map((x) => {
      const cited = flat(x.cl); const stale = cited.filter((n) => out.has(n));
      return `<div class="dep">${goto(x.id)}<span>${esc(x.title.slice(0, 44))}</span>${stale.length ? `<span class="warnflag">⚠ cites out-of-force ${esc(ranges(stale))}</span>` : ""}</div>`;
    }).join("")}${deps.length > 8 ? `<div class="muted">+${deps.length - 8} more</div>` : ""}` : ""}
    ${similar.length ? `<div class="sim"><h3>More like this · vector index</h3><ul>${similar.map((s) => `<li>${goto(s.id)} ${pill(s.standing)} <span class="muted">${esc(s.title.slice(0, 42))}</span></li>`).join("")}</ul></div>` : ""}
    ${paths.length ? `<div class="paths"><h3>Code it talks about</h3><ul>${paths.map((p) => `<li>${esc(p.path)}${p.exists ? "" : p.current ? ` <span class="muted">→ now ${esc(p.current)}</span>` : ' <span class="muted">(gone)</span>'}</li>`).join("")}</ul></div>` : ""}
    ${d.path && doc.meta.source_url ? `<h3>Source</h3><a href="${esc(doc.meta.source_url)}/blob/${esc(doc.meta.commit)}/${esc(d.path)}" target="_blank" rel="noopener">${esc(d.path)}</a>` : ""}`;
  el.scrollTop = 0;
}

// ----------------------------------------------------------------------------- console
function runConsole() {
  const cy = $("#cypher").value.trim();
  const box = $("#result");
  if (!cy) return;
  try {
    const env = q(cy);
    const cols = env.columns || (env.rows[0] ? Object.keys(env.rows[0]) : []);
    const cell = (v) => {
      if (v === null || v === undefined) return '<span class="muted">null</span>';
      if (typeof v === "string") return /^ADR-\d{4}$/.test(v) ? goto(v) : esc(v.length > 160 ? v.slice(0, 160) + "…" : v);
      if (Array.isArray(v)) return esc(JSON.stringify(v));
      if (typeof v === "object") return esc(JSON.stringify(v));
      return esc(v);
    };
    box.innerHTML = `<div class="meta">${env.rows.length} row${env.rows.length === 1 ? "" : "s"} · ${Number(env.elapsed_ms ?? timing.last).toFixed(2)} ms in Relate${env.rows.length > 100 ? " · showing 100" : ""}${env.stats && Object.values(env.stats).some((x) => x) ? " · " + esc(JSON.stringify(env.stats)) : ""}</div>
      <table><thead><tr>${cols.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead><tbody>${env.rows.slice(0, 100).map((r) => `<tr>${cols.map((c) => `<td>${cell(r[c])}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
  } catch (e) {
    box.innerHTML = `<div class="err">${esc(e.message)}</div>`;
  }
}

// ----------------------------------------------------------------------------- boot
function renderStats() {
  const s = doc.meta.standing;
  const non = (s.partial || 0) + (s.out || 0);
  const stale = doc.decisions.filter((d) => ["partial", "out"].includes(d.standing) && ["accepted", "proposed", "unknown"].includes(d.status)).length;
  $("#stats").innerHTML = `
    <span class="stat"><b>${doc.decisions.length}</b> decisions in <b>${esc(doc.meta.name)}</b></span>
    <span class="stat warn"><b>${non}</b> partly or wholly superseded</span>
    <span class="stat bad"><b>${stale}</b> still say Accepted / Proposed</span>
    <span class="stat"><b>${doc.treatments.length}</b> treatments · <b>${doc.clauses.length}</b> clauses</span>`;
}

function bind() {
  $("#q").addEventListener("input", () => renderList());
  document.addEventListener("keydown", (e) => {
    if (e.key === "/" && document.activeElement.tagName !== "TEXTAREA" && document.activeElement.id !== "q") { e.preventDefault(); $("#q").focus(); }
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") runConsole();
  });
  document.addEventListener("click", (e) => {
    const g = e.target.closest("[data-goto]"); if (g) { select(g.dataset.goto); return; }
    const r = e.target.closest(".row"); if (r) { select(r.dataset.id); return; }
    const c = e.target.closest("[data-chip]");
    if (c) { const k = c.dataset.chip; filters.has(k) ? filters.delete(k) : filters.add(k); renderChips(); renderList(); }
    const x = e.target.closest("[data-ex]"); if (x) { $("#cypher").value = EXAMPLES[+x.dataset.ex][1]; runConsole(); }
  });
  $("#showall").addEventListener("change", (e) => { showAll = e.target.checked; buildGraph(); setHighlight(); });
  $("#run").addEventListener("click", runConsole);
  $("#reset").addEventListener("click", () => { db.free?.(); db = new RelateDb(); loadGraph(doc); buildGraph(); renderList(); renderDetail(selected); $("#result").innerHTML = '<div class="meta">graph reloaded</div>'; });
  $("#examples").innerHTML = EXAMPLES.map((e, i) => `<button class="ex" data-ex="${i}">${esc(e[0])}</button>`).join("");
  $("#cypher").value = EXAMPLES[0][1];
}

async function main() {
  const msg = (t) => ($("#boot-msg").textContent = t);
  try {
    await init();
    db = new RelateDb();
    msg("Fetching the decision graph…");
    doc = await (await fetch("data/graph.json")).json();
    msg(`Loading ${doc.decisions.length} decisions into the embedded graph…`);
    const ms = loadGraph(doc);
    $("#engine").textContent = `Relate v${RELATE_WASM_VERSION} · WebAssembly · graph loaded in ${ms.toFixed(0)} ms`;
    if (REPO_URL) { const a = $("#repo-link"); a.href = REPO_URL; a.hidden = false; }
    emptyHtml = $("#detail").innerHTML;
    renderStats(); renderChips(); bind();
    $("#app").hidden = false;
    renderList(); buildGraph();
    const initial = new URL(location.href).searchParams.get("id");
    if (initial) select(initial.toUpperCase());
    $("#boot").classList.add("done");
  } catch (e) {
    console.error(e);
    $("#boot-msg").innerHTML = `Could not start the explorer:<br><code>${esc(e.message)}</code><br><span class="muted">Serve this folder over http(s) (WebAssembly modules cannot load from file://).</span>`;
    $(".spinner").hidden = true;
  }
}
main();
