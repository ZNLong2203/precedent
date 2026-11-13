// Precedent: is this decision still good law?
// The decision graph lives in Relate compiled to WebAssembly; every number, list and diagram on this
// page is the answer to a Cypher query run in this tab.
import init, { RelateDb } from "./relate/relate.js";

const REPO_URL = "https://github.com/ZNLong2203/precedent";
const RELATE_WASM_VERSION = "1.0.1"; // keep in sync with scripts/vendor-web.sh
const START_ID = "ADR-0116";
const ASSET_VERSION = "4"; // bump with index.html when graph.json or the app changes (Pages caches for minutes)
const NEG = new Set(["SUPERSEDES", "REVERSES", "WITHDRAWS"]);
const KIND = { SUPERSEDES: "overrules", REVERSES: "reverses", WITHDRAWS: "withdraws", AMENDS: "amends", REINSTATES: "reinstates", AFFIRMS: "confirms" };
const CHANGES = "SUPERSEDES|REVERSES|WITHDRAWS|AMENDS";
const STATE_WORD = { in_force: "Still valid", partial: "Partly overruled", out: "Overruled", contested: "Contested" };
const STATE_TONE = { in_force: "ok", partial: "part", out: "bad", contested: "bad" };
const TONE = { ok: "ok", part: "part", most: "bad", out: "bad", cont: "bad" }; // verdict key -> text colour
const COLOR = { in_force: "#3fb27f", partial: "#e0a526", out: "#ef6a5f", contested: "#ef6a5f" };
const VIEWS = ["decision", "browse", "network", "query", "about"];
const LEGACY = { documents: "decision", explore: "decision", graph: "network", overview: "about", ask: "query" };
const OPEN_STATUS = ["accepted", "proposed", "unknown"];

const EXAMPLES = [
  ["How many decisions are in each state?", `MATCH (d:Decision)
RETURN d.standing AS state, count(*) AS decisions
ORDER BY decisions DESC`],
  ["Decisions that say “Accepted” but are partly overruled", `MATCH (d:Decision)
WHERE d.status = 'accepted' AND d.standing = 'partial'
RETURN d.id AS id, d.title AS title, d.out_clauses AS overruled_clauses, d.controlled_by AS replaced_by
ORDER BY size(d.out_clauses) DESC LIMIT 15`],
  ["Who overruled ADR-0116, and which clauses?", `MATCH (a:Decision)-[t:SUPERSEDES|REVERSES|WITHDRAWS {effective: true}]->(d:Decision {id: 'ADR-0116'})
RETURN a.id AS decision, type(t) AS how, t.clauses AS clauses, t.evidence AS the_sentence`],
  ["Decisions still leaning on an overruled clause", `MATCH (s:Decision)-[c:CITES]->(d:Decision)
WHERE c.section IN ['decision', 'consequences'] AND size(c.clauses) > 0
  AND any(n IN c.clauses WHERE n IN d.out_clauses)
  AND NOT s.id IN d.controlled_by
RETURN s.id AS relies_on_it, d.id AS decision, [n IN c.clauses WHERE n IN d.out_clauses] AS overruled_clauses, d.controlled_by AS replaced_by
ORDER BY s.num DESC LIMIT 15`],
  ["Chains: A overruled B, which overruled C", `MATCH (a:Decision)-[:SUPERSEDES|REVERSES|WITHDRAWS]->(b:Decision)-[:SUPERSEDES|REVERSES|WITHDRAWS]->(c:Decision)
RETURN a.id AS latest, b.id AS middle, c.id AS earliest LIMIT 15`],
  ["Decisions closest in meaning to ADR-0116 (vector index)", `MATCH (d:Decision {id: 'ADR-0116'})
WITH d.embedding AS e
MATCH (x:Decision) SEARCH x IN (VECTOR INDEX decision_vec FOR e LIMIT 8) SCORE AS similarity
RETURN x.id AS id, x.title AS title, x.standing AS state, round(similarity * 100) / 100 AS similarity`],
  ["How are two decisions connected?", `MATCH (a:Decision {id: 'ADR-0116'}), (b:Decision {id: 'ADR-0472'})
MATCH p = shortestPath((a)-[:CITES|SUPERSEDES|REVERSES|WITHDRAWS|AMENDS*..6]-(b))
RETURN [n IN nodes(p) | n.id] AS path, length(p) AS hops`],
];

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const clip = (s, n) => (s.length > n ? s.slice(0, n - 1).trimEnd() + "…" : s);
const uniq = (a) => [...new Set(a)];
const fmt = (n) => Number(n).toLocaleString("en-US");
/** minimal inline markdown for clause text: escape first, then `code` and **bold** */
const mdInline = (s) => esc(s).replace(/`([^`]+)`/g, "<code>$1</code>").replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>");
const fmtDate = (iso) => {
  const t = iso ? new Date(`${iso}T00:00:00Z`) : null;
  return t && !isNaN(t) ? t.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }) : "";
};

let db, doc, fg;
let view = "decision", selected = null, hl = null, hovered = null, queryStarted = false, netData = null;
let bFilter = "attention", bLimit = 60;
let sugg = [], suggIdx = -1;
const nodeIndex = new Map();
const timing = { last: 0, count: 0 };

// ----------------------------------------------------------------------------- Relate
function q(cypher, params) {
  const t0 = performance.now();
  const env = JSON.parse(db.execute(cypher, params ? JSON.stringify(params) : null));
  if (env.error) throw new Error(env.error);
  timing.last = env.elapsed_ms ?? performance.now() - t0;
  timing.count += 1;
  $("#foot-q").textContent = `last query ${timing.last.toFixed(1)} ms · ${timing.count} this session`;
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
        partial_unspecified: r.partial_unspecified, n_clauses: r.n_clauses, gist: r.gist, text: r.text, path: r.path${dim ? ", embedding: vector(r.emb, $dim, FLOAT32)" : ""}})`, { rows: part, dim });
  }
  for (const part of chunk(d.clauses, 400)) {
    q(`UNWIND $rows AS r MATCH (d:Decision {id: r.decision}) CREATE (d)-[:HAS_CLAUSE]->(:Clause {key: r.key, decision: r.decision, n: r.n, title: r.title, body: r.body, standing: r.standing, defeated_by: r.defeated_by})`, { rows: part });
  }
  for (const part of chunk(d.cites, 800)) {
    q(`UNWIND $rows AS r MATCH (a:Decision {id: r.src}), (b:Decision {id: r.dst}) CREATE (a)-[:CITES {section: r.section, clauses: r.clauses}]->(b)`, { rows: part });
  }
  for (const kind of Object.keys(KIND)) {
    const part = d.treatments.filter((t) => t.kind === kind);
    if (!part.length) continue;
    q(`UNWIND $rows AS r MATCH (a:Decision {id: r.actor}), (b:Decision {id: r.target}) CREATE (a)-[:${kind} {scope: r.scope, clauses: r.clauses, evidence: r.evidence, confidence: r.confidence, rule: r.rule, effective: r.effective}]->(b)`, { rows: part });
  }
  const uniquePaths = [...new Map(d.paths.map((p) => [p.path, p])).values()];
  for (const part of chunk(uniquePaths, 600)) q(`UNWIND $rows AS r CREATE (:CodePath {path: r.path, exists: r.exists, current: r.current})`, { rows: part });
  for (const part of chunk(d.paths, 800)) q(`UNWIND $rows AS r MATCH (d:Decision {id: r.decision}), (p:CodePath {path: r.path}) CREATE (d)-[:REFERS_TO]->(p)`, { rows: part });
  return performance.now() - t0;
}

// ----------------------------------------------------------------------------- small helpers
function ranges(nums) {
  const n = [...new Set(nums || [])].sort((a, b) => a - b);
  const out = [];
  for (let i = 0; i < n.length; ) {
    let j = i;
    while (j + 1 < n.length && n[j + 1] === n[j] + 1) j++;
    out.push(i === j ? `§${n[i]}` : `§${n[i]}–${n[j]}`);
    i = j + 1;
  }
  return out.join(", ");
}
const goto = (id) => `<a class="goto" href="?id=${esc(id)}" data-goto="${esc(id)}">${esc(id)}</a>`;
const flat = (lists) => [...new Set((lists || []).flat(2))].filter((x) => Number.isInteger(x));
const declared = (d) => d.declared_raw || d.declared || d.status_raw || d.status || "";
const isStale = (d) => d.standing !== "in_force" && OPEN_STATUS.includes(d.status);

/** The one-line answer to "is it still good law?", shared by the page, the panel and the table. */
function verdictOf(d) {
  const out = d.out_clauses || [], o = out.length, n = d.n_clauses || 0, by = d.controlled_by || [];
  if (d.standing === "in_force") return { key: "ok", word: "Still valid", line: d.restored ? "It was overruled once, then restored." : "No later decision overrules any part of it.", short: "Still valid" };
  if (d.standing === "contested") return { key: "cont", word: "Contested", line: "Later decisions overrule each other here.", short: "Contested" };
  if (d.standing === "out" || (o && n && o >= n)) {
    const line = n > 1 && o >= n ? `All ${n} clauses no longer hold.` : by.length ? `Replaced by ${by.map(goto).join(", ")}.` : "A later decision replaced it.";
    return { key: "out", word: "Overruled", line, short: "Overruled" };
  }
  if (o && n) {
    const most = o / n >= 0.5;
    return { key: most ? "most" : "part", word: most ? "Mostly overruled" : "Partly overruled", line: `${o} of ${n} clause${n === 1 ? "" : "s"} no longer ${o === 1 ? "holds" : "hold"}`, short: `${o} of ${n} clauses overruled` };
  }
  return { key: "part", word: "Partly overruled", line: "A later decision replaced part of it but does not say which clause.", short: "Partly overruled" };
}
/** standing as shown on a dot: a "partial" decision whose every clause is overruled counts as overruled */
const stateOf = (d) => (d.standing === "partial" && d.n_clauses && (d.out_clauses || []).length >= d.n_clauses ? "out" : d.standing);
function cells(d, one = false) {
  const n = d.n_clauses || 0, out = d.out_clauses || [];
  if (!n) return [d.standing === "out" ? "no" : d.standing === "in_force" ? "" : "pt"];
  if (!out.length && d.standing === "out") return Array(Math.min(n, one ? 28 : 60)).fill("no");
  if (!out.length && d.standing !== "in_force") return one ? [...Array(Math.min(n, 28)).fill(""), "pt"] : Array(Math.min(n, 60)).fill("pt");
  return Array.from({ length: Math.min(n, one ? 28 : 60) }, (_, i) => (out.includes(i + 1) ? "no" : ""));
}
const barHtml = (d, cls = "bar") => {
  const n = d.n_clauses || 0, o = (d.out_clauses || []).length;
  const label = n ? `${n - o} of ${n} clauses still hold` : STATE_WORD[d.standing];
  return `<div class="${cls}" role="img" aria-label="${esc(label)}">${cells(d).map((c) => `<i class="${c}"></i>`).join("")}</div>`;
};

// ----------------------------------------------------------------------------- routing
function parseUrl() {
  const p = new URL(location.href).searchParams;
  let v = p.get("view") || "decision";
  v = LEGACY[v] || v;
  if (!VIEWS.includes(v)) v = "decision";
  return { v, id: (p.get("id") || "").toUpperCase() || null };
}
function urlFor(v, id) {
  const u = new URL(location.href);
  u.search = "";
  if (v !== "decision") u.searchParams.set("view", v);
  if (id && (v === "decision" || v === "network")) u.searchParams.set("id", id);
  return u;
}
function go(v, id, { push = true } = {}) {
  if (id) selected = id;
  if (!selected) selected = START_ID;
  view = v;
  const u = urlFor(v, selected);
  if (u.href !== location.href) history[push ? "pushState" : "replaceState"](null, "", u);
  show();
  window.scrollTo(0, 0);
}
function show() {
  $$(".view").forEach((el) => (el.hidden = el.id !== `v-${view}`));
  $$(".nav a").forEach((a) => (a.dataset.view === view ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current")));
  document.title = view === "decision" && selected ? `${selected} · Precedent` : "Precedent — is this decision still good law?";
  if (view === "decision") { renderDecision(selected); syncFinder(); }
  if (view === "browse") renderBrowse();
  if (view === "network") { buildNetwork(); selectNode(selected, { recentre: false }); }
  if (view === "query" && !queryStarted) { queryStarted = true; pickExample(0); }
}

// ----------------------------------------------------------------------------- search
const sanitise = (s) => (s.match(/[A-Za-z0-9_]{2,}/g) || []).slice(0, 24).join(" ");
const COLS = "d.id AS id, d.num AS num, d.title AS title, d.status AS status, d.standing AS standing, d.out_clauses AS out_clauses, d.n_clauses AS n_clauses, d.controlled_by AS controlled_by, d.restored AS restored";

function findDecisions(text, limit) {
  const m = /^(?:ADR[-\s]?)?(\d{1,4})$/i.exec(text);
  if (m) {
    const exact = `ADR-${m[1].padStart(4, "0")}`;
    const list = rows(`MATCH (d:Decision) WHERE d.id = $exact OR d.id STARTS WITH $prefix RETURN ${COLS} ORDER BY num LIMIT ${limit}`, { exact, prefix: `ADR-${m[1]}` });
    return list.sort((a, b) => (b.id === exact) - (a.id === exact));
  }
  const s = sanitise(text);
  if (!s) return [];
  return rows(`CALL db.index.fulltext.queryNodes('decision_text', $q) YIELD node AS d, score RETURN ${COLS} ORDER BY score DESC LIMIT ${limit}`, { q: s });
}

function syncFinder() {
  const input = $("#q");
  if (document.activeElement !== input) input.value = selected || "";
}
function closeSuggest() {
  sugg = []; suggIdx = -1;
  $("#suggest").hidden = true;
  $("#q").setAttribute("aria-expanded", "false");
}
function updateSuggest() {
  const text = $("#q").value.trim();
  if (text.length < 2 || text.toUpperCase() === selected) return closeSuggest();
  sugg = findDecisions(text, 8);
  suggIdx = sugg.length ? 0 : -1;
  const ul = $("#suggest");
  ul.innerHTML = sugg.length
    ? sugg.map((r, i) => `<li role="presentation"><a role="option" href="?id=${esc(r.id)}" data-goto="${esc(r.id)}" aria-selected="${i === suggIdx}"><span class="id">${esc(r.id)}</span><span class="ttl">${esc(r.title)}</span><span class="st t-${STATE_TONE[stateOf(r)]}">${esc(STATE_WORD[stateOf(r)])}</span></a></li>`).join("")
    : `<li class="none">No decision matches “${esc(text)}”.</li>`;
  ul.hidden = false;
  $("#q").setAttribute("aria-expanded", "true");
}
function moveSuggest(delta) {
  if (!sugg.length) return;
  suggIdx = (suggIdx + delta + sugg.length) % sugg.length;
  $$("#suggest a").forEach((a, i) => a.setAttribute("aria-selected", String(i === suggIdx)));
  $$("#suggest a")[suggIdx]?.scrollIntoView({ block: "nearest" });
}

// ----------------------------------------------------------------------------- the decision page
const KIND_PASSIVE = { SUPERSEDES: "Overruled", REVERSES: "Reversed", WITHDRAWS: "Withdrawn", AMENDS: "Amended", REINSTATES: "Reinstated", AFFIRMS: "Confirmed" };
const quoteHtml = (t, soft) => `<blockquote class="quote ${soft ? "soft" : ""}"><span class="by">${KIND_PASSIVE[t.kind] || "Changed"} by ${goto(t.id)}</span>${mdInline(clip(t.evidence || "", 320))}</blockquote>`;

/** Group edges to one neighbour into a single arrow: which clauses, and whether it really overrules. */
function groupLinks(list) {
  const m = new Map();
  for (const r of list) {
    const g = m.get(r.id) || { id: r.id, title: r.title, num: r.num, state: stateOf(r), neg: false, weak: false, whole: false, clauses: new Set() };
    m.set(r.id, g);
    if (NEG.has(r.kind) && r.effective) { g.neg = true; (r.clauses || []).forEach((n) => g.clauses.add(n)); if (r.scope === "whole") g.whole = true; }
    else if (NEG.has(r.kind)) g.weak = true;
  }
  return [...m.values()].sort((a, b) => b.neg - a.neg || a.num - b.num);
}
const tookOf = (g) => (g.neg ? (g.clauses.size ? ranges([...g.clauses]) : g.whole ? "all of it" : "part") : g.weak ? "no longer in force" : "amends");

function mapSvg(d, ups, downs) {
  const W = 760, cx = 380, R0 = 30, r = 14, cap = 6, gap = 68;
  const U = ups.slice(0, cap), D = downs.slice(0, cap);
  const m = Math.max(U.length, D.length, 1);
  const half = ((m - 1) * gap) / 2;
  const H = Math.max(230, half * 2 + 122), cy = H / 2 + 14;
  const place = (list, side) => list.map((g, i) => {
    const dy = (i - (list.length - 1) / 2) * gap, t = half ? dy / half : 0;
    return { ...g, x: cx + side * (112 + 54 * (1 - t * t)), y: cy + dy };
  });
  const L = place(D, -1), Rt = place(U, 1);
  let body = "", nodes = "";
  const edge = (p, from, to) => {
    const dx = to.x - from.x, dy = to.y - from.y, len = Math.hypot(dx, dy) || 1, ux = dx / len, uy = dy / len;
    const r1 = from.r + 3, r2 = to.r + 7;
    const a = { x: from.x + ux * r1, y: from.y + uy * r1 }, b = { x: to.x - ux * r2, y: to.y - uy * r2 };
    const cls = p.neg ? "neg" : "soft";
    body += `<line class="e ${cls}" x1="${a.x.toFixed(1)}" y1="${a.y.toFixed(1)}" x2="${b.x.toFixed(1)}" y2="${b.y.toFixed(1)}" marker-end="url(#ah-${cls})"/>`;
    if (p.neg) body += `<text class="elab" x="${((a.x + b.x) / 2).toFixed(1)}" y="${((a.y + b.y) / 2 - 5).toFixed(1)}">${esc(tookOf(p))}</text>`;
  };
  const me = { x: cx, y: cy, r: R0 };
  for (const p of Rt) edge(p, { x: p.x, y: p.y, r }, me);
  for (const p of L) edge(p, me, { x: p.x, y: p.y, r });
  const node = (p, side) => {
    const lx = p.x + side * (r + 9), anchor = side < 0 ? " end" : "";
    return `<a class="mnode" href="?id=${esc(p.id)}" data-goto="${esc(p.id)}"><title>${esc(p.id)} · ${esc(p.title)} — ${esc(STATE_WORD[p.state])}</title>
      <circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="${r}" fill="${COLOR[p.state]}"/>
      <text class="nid${anchor}" x="${lx.toFixed(1)}" y="${(p.y - 2).toFixed(1)}">${esc(p.id)}</text>
      <text class="ntt${anchor}" x="${lx.toFixed(1)}" y="${(p.y + 14).toFixed(1)}">${esc(clip(p.title.replace(/`/g, ""), 30))}</text></a>`;
  };
  nodes += Rt.map((p) => node(p, 1)).join("") + L.map((p) => node(p, -1)).join("");
  const heads = (D.length ? `<text class="colh" x="150" y="30">Earlier — it changed</text>` : "") + (U.length ? `<text class="colh" x="610" y="30">Later — changed it</text>` : "");
  const more = (ups.length > cap ? `<text class="more" x="${W - 16}" y="${H - 14}" text-anchor="end">+${ups.length - cap} more later decisions, listed below</text>` : "") + (downs.length > cap ? `<text class="more" x="16" y="${H - 14}">+${downs.length - cap} more earlier decisions</text>` : "");
  const center = `<g class="center"><circle cx="${cx}" cy="${cy}" r="${R0}" fill="${COLOR[stateOf(d)]}"/><text class="mid" x="${cx}" y="${cy + 5}">${esc(String(d.num).padStart(4, "0"))}</text></g>`;
  return `<svg viewBox="0 0 ${W} ${H.toFixed(0)}" role="group" aria-label="${esc(d.id)} at the centre, with the later decisions that changed it on the right and the earlier decisions it changed on the left. Each decision is a link.">
    <defs><marker id="ah-neg" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path class="ah-neg" d="M0 0L10 5L0 10z"/></marker><marker id="ah-soft" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path class="ah-soft" d="M0 0L10 5L0 10z"/></marker></defs>
    ${heads}${body}${center}${nodes}${more}</svg>`;
}
function mapList(ups, downs) {
  const row = (g, prefix) => `<a class="mrow" href="?id=${esc(g.id)}" data-goto="${esc(g.id)}"><i class="dot" style="--c:${COLOR[g.state]}"></i><span class="who"><b>${esc(g.id)}</b><span>${esc(g.title.replace(/`/g, ""))}</span></span><span class="took ${g.neg ? "" : "soft"}">${prefix}${esc(tookOf(g))}</span></a>`;
  return `<div class="maplist">${ups.length ? `<h3 class="muted" style="font-size:13px;font-weight:600;margin:14px 0 2px">Later decisions that changed it</h3>${ups.map((g) => row(g, "")).join("")}` : ""}${downs.length ? `<h3 class="muted" style="font-size:13px;font-weight:600;margin:18px 0 2px">Earlier decisions it changed</h3>${downs.map((g) => row(g, "")).join("")}` : ""}</div>`;
}

function renderDecision(id) {
  const el = $("#doc");
  const d = rows(`MATCH (d:Decision {id: $id}) RETURN ${COLS}, d.status_raw AS declared_raw, d.date AS date, d.gist AS gist, d.path AS path`, { id })[0];
  if (!d) { el.innerHTML = `<p class="empty">${esc(id)} is not in this graph. Try the search above.</p>`; return; }
  const clauses = rows("MATCH (:Decision {id: $id})-[:HAS_CLAUSE]->(c:Clause) RETURN c.n AS n, c.title AS title, c.body AS body, c.standing AS standing, c.defeated_by AS by ORDER BY n", { id });
  const treated = rows(`MATCH (a:Decision)-[t:${CHANGES}]->(:Decision {id: $id}) RETURN a.id AS id, a.title AS title, a.num AS num, a.standing AS standing, a.out_clauses AS out_clauses, a.n_clauses AS n_clauses, type(t) AS kind, t.clauses AS clauses, t.scope AS scope, t.effective AS effective, t.evidence AS evidence ORDER BY num`, { id });
  const changed = rows(`MATCH (:Decision {id: $id})-[t:${CHANGES}]->(b:Decision) RETURN b.id AS id, b.title AS title, b.num AS num, b.standing AS standing, b.out_clauses AS out_clauses, b.n_clauses AS n_clauses, type(t) AS kind, t.clauses AS clauses, t.scope AS scope, t.effective AS effective ORDER BY num`, { id });
  const deps = rows("MATCH (s:Decision)-[c:CITES]->(:Decision {id: $id}) WHERE c.section IN ['decision', 'consequences'] RETURN s.id AS id, s.title AS title, s.num AS num, collect(c.clauses) AS cl ORDER BY num", { id });
  const paths = rows("MATCH (:Decision {id: $id})-[:REFERS_TO]->(p:CodePath) RETURN p.path AS path, p.exists AS exists, p.current AS current LIMIT 8", { id });
  let similar = [];
  try { similar = rows("MATCH (d:Decision {id: $id}) WITH d.embedding AS e MATCH (x:Decision) SEARCH x IN (VECTOR INDEX decision_vec FOR e LIMIT 7) SCORE AS s RETURN x.id AS id, x.title AS title, x.standing AS standing, s", { id }).filter((r) => r.id !== id).slice(0, 4); } catch { /* no vector index */ }

  const dd = { ...d, n_clauses: clauses.length || d.n_clauses };
  const v = verdictOf(dd);
  const negs = treated.filter((t) => NEG.has(t.kind) && t.effective);
  const softs = treated.filter((t) => t.kind === "AMENDS");
  const forClause = (list, n) => list.filter((t) => (t.clauses || []).includes(n));
  const headNegs = negs.filter((t) => !(t.clauses || []).length);
  const ups = groupLinks(treated), downs = groupLinks(changed);
  const outSet = new Set(d.out_clauses || []);
  const src = d.path && doc.meta.source_url ? `${doc.meta.source_url}/blob/${doc.meta.commit}/${d.path}` : "";

  const clauseHtml = clauses.map((c) => {
    const dead = c.standing === "out", ns = forClause(negs, c.n), ss = forClause(softs, c.n);
    const by = uniq(dead ? ((c.by || []).length ? c.by : ns.map((t) => t.id)) : []);
    const status = dead
      ? `<span class="st bad">Overruled by ${by.map(goto).join(", ")}</span>`
      : `<span class="st ok">Still holds${ss.length ? ` <span class="sub">· amended by ${uniq(ss.map((t) => t.id)).map(goto).join(", ")}</span>` : ""}</span>`;
    const detail = (c.body ? `<p class="body">${mdInline(c.body)}</p>` : "") + (dead ? ns : []).filter((t) => t.evidence).map((t) => quoteHtml(t, false)).join("") + ss.filter((t) => t.evidence).map((t) => quoteHtml(t, true)).join("");
    return `<details class="cl ${dead ? "dead" : ""} ${detail ? "" : "bare"}"><summary><span class="n">§${c.n}</span><span class="t">${mdInline(c.title)}</span>${status}</summary>${detail ? `<div class="cd">${detail}</div>` : ""}</details>`;
  }).join("");

  const unspecified = headNegs.length && clauses.length
    ? `<section class="sec"><h2>Overruled, but no clause is named</h2>${headNegs.map((t) => quoteHtml(t, false)).join("")}</section>` : "";
  const noClauses = !clauses.length
    ? `<section class="sec"><h2>What it says</h2><p class="gist">${mdInline(clip(d.gist || "", 420))}</p>${negs.map((t) => quoteHtml(t, false)).join("")}</section>` : "";

  const lst = (items) => `<table class="lst">${items.join("")}</table>`;
  const li = (id2, title2, extra) => `<tr><td>${goto(id2)}</td><td class="t">${esc(clip(title2.replace(/`/g, ""), 70))}</td><td>${extra || ""}</td></tr>`;
  const depRows = deps.slice(0, 8).map((x) => {
    const stale = flat(x.cl).filter((n) => outSet.has(n));
    return li(x.id, x.title, stale.length ? `<span class="warn">leans on overruled ${esc(ranges(stale))}</span>` : "");
  });
  const connected = [
    deps.length ? `<h3>Relied on by ${deps.length} later decision${deps.length > 1 ? "s" : ""}</h3>${lst(depRows)}${deps.length > 8 ? `<p class="faint">and ${deps.length - 8} more</p>` : ""}` : "",
    similar.length ? `<h3>Closest in meaning (vector index)</h3>${lst(similar.map((s) => li(s.id, s.title, `<span class="faint">${esc(STATE_WORD[s.standing])}</span>`)))}` : "",
    paths.length ? `<h3>Code it mentions</h3><ul class="paths">${paths.map((p) => `<li>${esc(p.path)}${p.exists ? "" : p.current ? ` <span class="faint">→ now ${esc(p.current)}</span>` : ' <span class="faint">(gone)</span>'}</li>`).join("")}</ul>` : "",
  ].join("");

  el.innerHTML = `
    <div class="meta">${esc(d.id)}${d.date ? ` · ${esc(fmtDate(d.date))}` : ""} · header says <b>${esc(declared(d))}</b>${src ? ` · <a href="${esc(src)}" target="_blank" rel="noopener">original</a>` : ""}</div>
    <h1>${mdInline(d.title)}</h1>
    <section class="verdict v-${v.key}" aria-label="Verdict">
      <div class="row"><div class="word">${v.word}</div><div class="sub">${v.line}</div></div>
      ${barHtml(dd)}
      ${isStale(d) ? `<p class="note">Its own header still says “${esc(declared(d))}”.</p>` : ""}
    </section>

    <section class="sec">
      <div class="sec-head"><h2>How it connects</h2>
        <p class="legend"><span><i class="dot g"></i>valid</span><span><i class="dot a"></i>partly overruled</span><span><i class="dot r"></i>overruled</span><span><i class="ln"></i>overrules</span><span><i class="ln dash"></i>amends</span></p></div>
      ${ups.length || downs.length
        ? `<div class="map">${mapSvg(dd, ups, downs)}</div>${mapList(ups, downs)}<p class="mapcap">Click any dot to open that decision. Arrows point at the decision that was overruled.</p>`
        : `<div class="alone">No later decision changes this one, and it changes no earlier decision. It stands on its own.</div>`}
    </section>

    ${clauses.length ? `<section class="sec"><h2>Clause by clause</h2><div style="margin-top:6px">${clauseHtml}</div></section>` : ""}
    ${noClauses}${unspecified}

    ${connected ? `<details class="more" ${ups.length || downs.length ? "" : "open"}><summary>Also connected</summary>${connected}</details>` : ""}`;
}

// ----------------------------------------------------------------------------- browse
function renderBrowse() {
  const s = doc.meta.standing, total = doc.decisions.length, need = (s.partial || 0) + (s.out || 0) + (s.contested || 0);
  const stale = doc.decisions.filter((d) => ["partial", "out"].includes(d.standing) && OPEN_STATUS.includes(d.status)).length;
  $("#browse-sum").innerHTML = `<b>${fmt(total)}</b> decisions in ${esc(doc.meta.name)}. <b style="color:var(--red-ink)">${need}</b> have been overruled in whole or in part, and <b style="color:var(--red-ink)">${stale}</b> of those still say Accepted or Proposed in their own header.`;
  const tabs = [["attention", `Need attention · ${need}`], ["in_force", `Still valid · ${s.in_force || 0}`], ["all", `All · ${total}`]];
  $("#seg").innerHTML = tabs.map(([k, label]) => `<button data-filter="${k}" aria-pressed="${bFilter === k}">${label}</button>`).join("");
  drawBrowse();
}
function drawBrowse() {
  const text = $("#bq").value.trim();
  let list = text.length >= 2 ? findDecisions(text, 200) : rows(`MATCH (d:Decision) RETURN ${COLS} ORDER BY num`);
  if (bFilter === "attention") list = list.filter((r) => r.standing !== "in_force");
  if (bFilter === "in_force") list = list.filter((r) => r.standing === "in_force");
  if (!text && bFilter === "attention") {
    const score = (r) => (r.standing === "out" ? 1e6 : 0) + (r.out_clauses || []).length * 100 + (r.n_clauses ? ((r.out_clauses || []).length / r.n_clauses) * 10 : 0);
    list.sort((a, b) => score(b) - score(a) || a.num - b.num);
  }
  const shown = list.slice(0, bLimit);
  $("#bmeta").textContent = text ? `${list.length} match${list.length === 1 ? "" : "es"}` : bFilter === "attention" ? "Most clauses overruled first" : "Oldest first";
  $("#btable").innerHTML = shown.map((r) => {
    const v = verdictOf(r), o = (r.out_clauses || []).length;
    const today = r.standing === "partial" && o && r.n_clauses ? `${o} of ${r.n_clauses} overruled` : STATE_WORD[r.standing];
    const by = (r.controlled_by || []);
    return `<tr><td>${goto(r.id)}</td><td class="ttl"><a href="?id=${esc(r.id)}" data-goto="${esc(r.id)}">${mdInline(r.title)}</a></td><td class="hdr">${esc(r.status.replace(/_/g, " "))}</td>
      <td class="today t-${TONE[v.key]}" title="${esc(v.word)}">${esc(today)}</td>
      <td class="c-bar"><div class="mini">${cells(r, true).map((c) => `<i class="${c}"></i>`).join("")}</div></td>
      <td class="by">${by.slice(0, 3).map(goto).join(", ")}${by.length > 3 ? ` +${by.length - 3}` : ""}</td></tr>`;
  }).join("") || `<tr><td colspan="6" class="empty">No decision matches.</td></tr>`;
  const more = $("#bmore");
  more.hidden = list.length <= bLimit;
  more.textContent = `Show ${Math.min(60, list.length - bLimit)} more (${shown.length} of ${list.length})`;
}

// ----------------------------------------------------------------------------- whole network
function graphData() {
  const links = rows(`MATCH (a:Decision)-[t:${CHANGES}]->(b:Decision) RETURN a.id AS source, b.id AS target, type(t) AS kind, t.effective AS effective`);
  const nodes = rows("MATCH (d:Decision) RETURN d.id AS id, d.num AS num, d.title AS title, d.standing AS standing, d.out_clauses AS out_clauses, d.n_clauses AS n_clauses");
  const deg = new Map(), nb = new Map();
  for (const l of links) {
    deg.set(l.source, (deg.get(l.source) || 0) + 1); deg.set(l.target, (deg.get(l.target) || 0) + 1);
    (nb.get(l.source) || nb.set(l.source, new Set()).get(l.source)).add(l.target);
    (nb.get(l.target) || nb.set(l.target, new Set()).get(l.target)).add(l.source);
  }
  const keep = nodes.filter((n) => deg.has(n.id));
  for (const n of keep) { n.state = stateOf(n); n.r = 3.2 + Math.sqrt(deg.get(n.id)) * 1.7; n.nb = nb.get(n.id); }
  const ids = new Set(keep.map((n) => n.id));
  return { nodes: keep, links: links.filter((l) => ids.has(l.source) && ids.has(l.target)).map((l) => ({ ...l })) };
}
const rgba = (hex, a) => { const n = parseInt(hex.slice(1), 16); return `rgba(${n >> 16},${(n >> 8) & 255},${n & 255},${a})`; };
const CALLOUT_INK = { ok: "#14502f", part: "#6b4a05", most: "#6b1a14", out: "#6b1a14", cont: "#6b1a14" };

function buildNetwork() {
  const el = $("#graph");
  if (!el.clientWidth) return;
  if (!netData) {
    netData = graphData();
    nodeIndex.clear();
    netData.nodes.forEach((n) => nodeIndex.set(n.id, n));
  }
  $("#net-title").textContent = `Every decision that overrules, or is overruled by, another · ${netData.nodes.length}`;
  if (!fg) {
    fg = ForceGraph()(el).backgroundColor("rgba(0,0,0,0)").nodeId("id").autoPauseRedraw(false)
      .nodeLabel((n) => `<b>${esc(n.id)}</b> · ${esc(clip(n.title.replace(/`/g, ""), 80))}<br><span style="color:#9aa6b6">${esc(verdictOf(n).short)}</span>`)
      .nodeCanvasObject((n, ctx, scale) => {
        const dim = hl && !hl.has(n.id);
        ctx.globalAlpha = dim ? 0.2 : 1;
        ctx.beginPath(); ctx.arc(n.x, n.y, n.id === selected ? n.r + 1.5 : n.r, 0, 2 * Math.PI);
        ctx.fillStyle = COLOR[n.state]; ctx.fill();
        if (n.id === hovered) { ctx.lineWidth = 1.8 / scale; ctx.strokeStyle = "#e8ecf1"; ctx.stroke(); }
        if (!dim && hl && n.id !== selected && scale > 1.4) {
          ctx.font = `${11 / scale}px ui-monospace, Menlo, monospace`; ctx.fillStyle = "#c9d2de";
          ctx.textAlign = "center"; ctx.textBaseline = "top"; ctx.fillText(n.id.replace("ADR-", ""), n.x, n.y + n.r + 2 / scale);
        }
        ctx.globalAlpha = 1;
      })
      .nodePointerAreaPaint((n, c, ctx) => { ctx.fillStyle = c; ctx.beginPath(); ctx.arc(n.x, n.y, n.r + 2, 0, 2 * Math.PI); ctx.fill(); })
      .linkColor((l) => {
        const a = l.source.id ?? l.source, b = l.target.id ?? l.target;
        const lit = hl && (a === selected || b === selected), dim = hl && !lit;
        const red = NEG.has(l.kind) && l.effective;
        return red ? rgba("#ef6a5f", dim ? 0.1 : lit ? 1 : 0.55) : rgba("#8795a8", dim ? 0.07 : lit ? 0.9 : 0.35);
      })
      .linkWidth((l) => { const a = l.source.id ?? l.source, b = l.target.id ?? l.target; return hl && (a === selected || b === selected) ? 1.9 : 0.8; })
      .linkDirectionalArrowLength((l) => (NEG.has(l.kind) ? 4.2 : 2.8)).linkDirectionalArrowRelPos(0.94)
      .onNodeHover((n) => { hovered = n ? n.id : null; el.style.cursor = n ? "pointer" : "grab"; })
      .onNodeClick((n) => selectNode(n.id))
      .onRenderFramePost((ctx, scale) => drawCallout(ctx, scale))
      .cooldownTicks(220).d3VelocityDecay(0.32)
      .onEngineStop(() => { if (fg._fit) { fg._fit = false; fg.zoomToFit(450, 40); } });
    fg.d3Force("charge").strength(-46); fg.d3Force("link").distance(34);
    let simNodes = [];
    const gravity = (a) => { for (const n of simNodes) { n.vx -= n.x * 0.06 * a; n.vy -= n.y * 0.06 * a; } };
    gravity.initialize = (ns) => { simNodes = ns; };
    fg.d3Force("gravity", gravity);
    fg._fit = true;
    fg.graphData(netData);
    new ResizeObserver(() => { if (el.clientWidth) fg.width(el.clientWidth).height(el.clientHeight); }).observe(el);
  }
  fg.width(el.clientWidth).height(el.clientHeight);
}

function drawCallout(ctx, scale) {
  const n = nodeIndex.get(selected);
  if (!n || n.x == null) return;
  const v = verdictOf(n), k = 1 / scale;
  ctx.lineWidth = 1.6 * k; ctx.strokeStyle = "#ffffff";
  ctx.beginPath(); ctx.arc(n.x, n.y, n.r + 4 * k, 0, 2 * Math.PI); ctx.stroke();
  const f1 = `700 ${13 * k}px system-ui, sans-serif`, f2 = `500 ${11.5 * k}px system-ui, sans-serif`;
  ctx.font = f1; const w1 = ctx.measureText(n.id).width;
  ctx.font = f2; const w2 = ctx.measureText(v.short).width;
  const w = Math.max(w1, w2) + 22 * k, h = 42 * k, bx = n.x + 22 * k, by = n.y - 54 * k;
  ctx.beginPath(); ctx.moveTo(n.x + (n.r + 4 * k) * 0.7, n.y - (n.r + 4 * k) * 0.7); ctx.lineTo(bx, by + h); ctx.lineWidth = 1 * k; ctx.strokeStyle = "rgba(255,255,255,0.8)"; ctx.stroke();
  ctx.fillStyle = "#ffffff"; ctx.beginPath(); ctx.roundRect(bx, by, w, h, 7 * k); ctx.fill();
  ctx.textAlign = "left"; ctx.textBaseline = "alphabetic";
  ctx.font = f1; ctx.fillStyle = "#0e1319"; ctx.fillText(n.id, bx + 11 * k, by + 17 * k);
  ctx.font = f2; ctx.fillStyle = CALLOUT_INK[v.key]; ctx.fillText(v.short, bx + 11 * k, by + 33 * k);
}

function selectNode(id, { recentre = true } = {}) {
  if (!id) return;
  selected = id;
  const n = nodeIndex.get(id);
  hl = n ? new Set([id, ...(n.nb || [])]) : null;
  const u = urlFor("network", id);
  if (u.href !== location.href) history.replaceState(null, "", u);
  if (n && recentre && fg && n.x != null) fg.centerAt(n.x, n.y, 500);
  renderPanel(id, !!n);
}

function renderPanel(id, drawn) {
  const el = $("#panel");
  const d = rows(`MATCH (d:Decision {id: $id}) RETURN ${COLS}, d.status_raw AS declared_raw, d.date AS date`, { id })[0];
  if (!d) { el.innerHTML = `<p class="empty">${esc(id)} is not in this graph.</p>`; return; }
  const v = verdictOf(d);
  const by = groupLinks(rows(`MATCH (a:Decision)-[t:${CHANGES}]->(:Decision {id: $id}) RETURN a.id AS id, a.title AS title, a.num AS num, a.standing AS standing, a.out_clauses AS out_clauses, a.n_clauses AS n_clauses, type(t) AS kind, t.clauses AS clauses, t.scope AS scope, t.effective AS effective ORDER BY num`, { id }));
  const to = groupLinks(rows(`MATCH (:Decision {id: $id})-[t:${CHANGES}]->(b:Decision) RETURN b.id AS id, b.title AS title, b.num AS num, b.standing AS standing, b.out_clauses AS out_clauses, b.n_clauses AS n_clauses, type(t) AS kind, t.clauses AS clauses, t.scope AS scope, t.effective AS effective ORDER BY num`, { id }));
  const list = (items) => items.slice(0, 8).map((g) => `<a class="mrow" href="?id=${esc(g.id)}" data-pick="${esc(g.id)}"><i class="dot" style="--c:${COLOR[g.state]}"></i><span class="who"><b>${esc(g.id)}</b><span>${esc(clip(g.title.replace(/`/g, ""), 80))}</span></span><span class="took ${g.neg ? "" : "soft"}">${esc(tookOf(g))}</span></a>`).join("") + (items.length > 8 ? `<p class="faint" style="margin-top:8px">and ${items.length - 8} more</p>` : "");
  el.innerHTML = `
    <div class="mono">${esc(d.id)}${d.date ? ` · ${esc(fmtDate(d.date))}` : ""}</div>
    <h2>${mdInline(d.title)}</h2>
    <div class="pills"><span>Header says</span><span class="pill">${esc(declared(d))}</span><span>→</span><span class="pill v-${v.key}">${v.word}</span></div>
    <div class="big">${v.key === "ok" ? "Still valid" : v.line}</div>
    ${v.key === "ok" ? `<p class="lead">${v.line}</p>` : ""}
    ${barHtml(d)}
    ${by.length ? `<h3>Changed by</h3>${list(by)}` : ""}
    ${to.length ? `<h3>Changes earlier decisions</h3>${list(to)}` : ""}
    ${!drawn ? `<p class="lead" style="margin-top:20px">Not linked to any other decision, so it is not drawn on the map.</p>` : ""}
    <a class="btn" href="?id=${esc(id)}" data-goto="${esc(id)}">Read the full decision</a>`;
}

// ----------------------------------------------------------------------------- query
function runConsole() {
  const cy = $("#cypher").value.trim();
  const box = $("#result");
  if (!cy) return;
  try {
    const env = q(cy);
    const cols = env.columns || (env.rows[0] ? Object.keys(env.rows[0]) : []);
    const cell = (v) => {
      if (v === null || v === undefined) return '<span class="faint">null</span>';
      if (typeof v === "string") return /^ADR-\d{4}$/.test(v) ? goto(v) : esc(v.length > 180 ? v.slice(0, 180) + "…" : v);
      if (typeof v === "object") return esc(JSON.stringify(v));
      return esc(v);
    };
    box.innerHTML = `<div class="meta">${env.rows.length} row${env.rows.length === 1 ? "" : "s"} · answered by Relate in ${Number(env.elapsed_ms ?? timing.last).toFixed(2)} ms${env.rows.length > 100 ? " · showing 100" : ""}</div>
      <table><thead><tr>${cols.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead><tbody>${env.rows.slice(0, 100).map((r) => `<tr>${cols.map((c) => `<td>${cell(r[c])}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
  } catch (e) {
    box.innerHTML = `<div class="err">${esc(e.message)}</div>`;
  }
}
function pickExample(i) {
  $$("#examples button").forEach((b, k) => b.setAttribute("aria-pressed", String(k === i)));
  $("#cypher").value = EXAMPLES[i][1];
  runConsole();
}

// ----------------------------------------------------------------------------- about
function renderAbout() {
  const s = doc.meta.standing, total = doc.decisions.length;
  const stale = doc.decisions.filter((d) => ["partial", "out"].includes(d.standing) && OPEN_STATUS.includes(d.status)).length;
  $("#facts").innerHTML = [
    ["Decisions in the log", fmt(total)],
    ["Numbered clauses", fmt(doc.clauses.length)],
    ["Later decisions that change an earlier one (edges)", fmt(doc.treatments.length)],
    ["Still valid", fmt(s.in_force || 0)],
    ["Partly overruled", fmt(s.partial || 0)],
    ["Overruled", fmt(s.out || 0)],
    ["…of the overruled ones, still say Accepted or Proposed", fmt(stale)],
    ["Plain searches that surface an overruled decision in the top 5", "74.5%"],
  ].map(([a, b]) => `<tr><td>${a}</td><td>${b}</td></tr>`).join("");
  $("#eval-link").href = `${REPO_URL}/blob/main/docs/evaluation.md`;
  $("#more-links").innerHTML = `<a href="${REPO_URL}/blob/main/docs/agent-integration.md" target="_blank" rel="noopener">Agent guide</a> · <a href="${REPO_URL}/blob/main/docs/methodology.md" target="_blank" rel="noopener">Method</a> · <a href="${REPO_URL}" target="_blank" rel="noopener">Source</a>.`;
}

// ----------------------------------------------------------------------------- wiring
function bind() {
  const input = $("#q");
  input.addEventListener("input", updateSuggest);
  input.addEventListener("focus", () => { input.select(); });
  input.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); if ($("#suggest").hidden) updateSuggest(); else moveSuggest(1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); moveSuggest(-1); }
    else if (e.key === "Escape") { closeSuggest(); input.blur(); }
    else if (e.key === "Enter") {
      e.preventDefault();
      if (!sugg.length) updateSuggest();
      const pick = sugg[Math.max(suggIdx, 0)];
      if (pick) { closeSuggest(); input.blur(); go("decision", pick.id); }
    }
  });
  $("#bq").addEventListener("input", () => { bLimit = 60; drawBrowse(); });
  $("#bmore").addEventListener("click", () => { bLimit += 60; drawBrowse(); });
  document.addEventListener("keydown", (e) => {
    const tag = document.activeElement.tagName;
    if (e.key === "/" && tag !== "TEXTAREA" && tag !== "INPUT") {
      e.preventDefault();
      if (view !== "decision") go("decision");
      $("#q").focus();
    }
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter" && view === "query") runConsole();
  });
  document.addEventListener("click", (e) => {
    const t = e.target;
    let el;
    if (!t.closest(".finder")) closeSuggest();
    if ((el = t.closest("[data-pick]"))) { e.preventDefault(); selectNode(el.dataset.pick); return; }
    if ((el = t.closest("#random"))) {
      e.preventDefault();
      const pool = doc.decisions.filter((d) => d.standing !== "in_force");
      go("decision", pool[Math.floor(Math.random() * pool.length)].id);
      return;
    }
    if ((el = t.closest("[data-goto]"))) { if (e.metaKey || e.ctrlKey || e.shiftKey) return; e.preventDefault(); closeSuggest(); go("decision", el.dataset.goto); return; }
    if ((el = t.closest("[data-view]"))) { if (e.metaKey || e.ctrlKey || e.shiftKey) return; e.preventDefault(); go(el.dataset.view); return; }
    if ((el = t.closest("[data-filter]"))) { bFilter = el.dataset.filter; bLimit = 60; renderBrowse(); return; }
    if ((el = t.closest("[data-ex]"))) pickExample(+el.dataset.ex);
  });
  window.addEventListener("popstate", () => { const { v, id } = parseUrl(); if (id) selected = id; view = v; show(); });
  $("#run").addEventListener("click", runConsole);
  $("#reset").addEventListener("click", () => {
    db.free?.(); db = new RelateDb(); loadGraph(doc); netData = null;
    if (fg) { buildNetwork(); fg.graphData(netData); }
    $("#result").innerHTML = '<div class="meta">Graph reloaded.</div>';
  });
  $("#examples").innerHTML = EXAMPLES.map((e, i) => `<li><button data-ex="${i}" aria-pressed="false">${esc(e[0])}</button></li>`).join("");
}

async function main() {
  const msg = (t) => ($("#boot-msg").textContent = t);
  try {
    await init();
    db = new RelateDb();
    msg("Fetching the decision graph…");
    doc = await (await fetch(`data/graph.json?v=${ASSET_VERSION}`)).json();
    msg(`Loading ${doc.decisions.length} decisions into Relate…`);
    const ms = loadGraph(doc);
    $("#engine").textContent = `Relate v${RELATE_WASM_VERSION} · WebAssembly · graph loaded in ${ms.toFixed(0)} ms`;
    $("#n-total").textContent = doc.decisions.length;
    const repo = $("#repo-link"); repo.href = REPO_URL; repo.hidden = false;
    renderAbout(); bind();
    const { v, id } = parseUrl();
    selected = id || START_ID;
    view = v;
    show();
    $("#boot").classList.add("done");
  } catch (e) {
    console.error(e);
    $("#boot-msg").innerHTML = `Could not start the explorer: <code>${esc(e.message)}</code><br><small>Serve this folder over http(s); WebAssembly cannot load from file://.</small>`;
  }
}
main();
