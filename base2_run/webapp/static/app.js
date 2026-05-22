// Single-page UI for the base2 sweep viewer.
//
// Tabs (driven by sidebar nav): dashboard, families, table, reader, prompts.
// Charts via Chart.js (loaded as a global `Chart` from CDN).

const $  = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

// ─────────────────── helpers ───────────────────
function fmtNum(v, digits = 2) {
  if (v === null || v === undefined) return "—";
  const n = Number(v);
  if (Number.isNaN(n)) return String(v);
  return n.toFixed(digits);
}
function fmtPct(v, digits = 1) {
  if (v === null || v === undefined) return "—";
  return (Number(v) * 100).toFixed(digits) + "%";
}
function fmtMoney(v) {
  if (v === null || v === undefined) return "—";
  return "$" + Number(v).toFixed(4);
}
function fmtInt(v) {
  if (v === null || v === undefined) return "—";
  return Number(v).toLocaleString();
}
function safeText(s) {
  if (s === null || s === undefined) return "";
  return String(s).replace(/[&<>"]/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[ch]));
}

// ─────────────────── sidebar toggle ───────────────────
$("#sidebar-toggle").addEventListener("click", () => {
  document.querySelector(".app").classList.toggle("collapsed");
  // Charts need a resize tick after width change.
  setTimeout(() => Object.values(CHARTS).forEach(c => c && c.resize()), 220);
});

// ─────────────────── tab switching ───────────────────
function activateTab(name) {
  $$(".navlink").forEach(b => b.classList.toggle("active", b.dataset.tab === name));
  $$(".tab-panel").forEach(p => p.classList.toggle("active", p.id === "tab-" + name));
  if (name === "dashboard") loadDashboard();
  if (name === "families")  loadFamilyStats();
  if (name === "table")     loadTable();
  if (name === "reader" && !readerState.currentId) loadRandomRecord();
  if (name === "prompts")   loadPrompts();
}
$$(".navlink").forEach(b => b.addEventListener("click", () => activateTab(b.dataset.tab)));

// ─────────────────── chart palette ───────────────────
const CHART_COLORS = {
  ok:     "rgba(93, 211, 161, 0.85)",
  fail:   "rgba(255, 122, 138, 0.85)",
  warn:   "rgba(255, 184, 107, 0.85)",
  accent: "rgba(125, 166, 255, 0.85)",
  accent2:"rgba(93, 211, 161, 0.85)",
  accent3:"rgba(198, 164, 255, 0.85)",
  muted:  "rgba(140, 147, 163, 0.5)",
  grid:   "rgba(255, 255, 255, 0.06)",
  axis:   "rgba(230, 232, 238, 0.7)",
};
const FAMILY_COLORS = {
  aae:          "rgba(125, 166, 255, 0.85)",
  southern:     "rgba(93, 211, 161, 0.85)",
  appalachian:  "rgba(255, 184, 107, 0.85)",
  midwestern:   "rgba(198, 164, 255, 0.85)",
  northeastern: "rgba(255, 122, 138, 0.85)",
  western:      "rgba(110, 220, 220, 0.85)",
};

if (window.Chart) {
  Chart.defaults.color = CHART_COLORS.axis;
  Chart.defaults.borderColor = CHART_COLORS.grid;
  Chart.defaults.font.family = '-apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif';
}

const CHARTS = {};
function destroyChart(key) { if (CHARTS[key]) { CHARTS[key].destroy(); delete CHARTS[key]; } }

// ─────────────────── dashboard ───────────────────
async function loadDashboard() {
  const [overall, families, dists] = await Promise.all([
    fetch("/api/stats/overall").then(r => r.json()),
    fetch("/api/stats/families").then(r => r.json()),
    fetch("/api/stats/distributions").then(r => r.json()),
  ]);

  // Headline stat cards.
  const card = (label, value, sub="") => `
    <div class="stat-card">
      <div class="label">${label}</div>
      <div class="value">${value}</div>
      ${sub ? `<div class="sub">${sub}</div>` : ""}
    </div>`;
  $("#headline-stats").innerHTML = [
    card("Records",          fmtInt(overall.records)),
    card("OK rate",          fmtPct(overall.ok_rate), `${overall.ok}/${overall.records} ok`),
    card("Dialect-pass",     fmtPct(overall.dialect_pass_rate, 1), "cosine ≥ 0.85 AND 5–25% token Δ"),
    card("Median cosine",    fmtNum(overall.median_cosine, 4), "meaning preservation"),
    card("Median token Δ %", fmtNum(overall.median_token_change_pct, 2) + "%", "surface variation"),
    card("Median features",  fmtNum(overall.median_feature_count, 1), "applied per rewrite"),
    card("Grounding rate",   fmtPct(overall.median_grounding_rate, 1), "realizations found in rewrite"),
    card("Total cost",       fmtMoney(overall.cost_usd_total), `${fmtInt(overall.tokens_in_total)} in / ${fmtInt(overall.tokens_out_total)} out`),
  ].join("");

  // Pie 1: status breakdown
  drawPie("chart-status", overall.statuses);
  // Pie 2: dialect_pass distribution (pass/fail/uncomputed across all records)
  const passCounts = {pass: 0, fail: 0, uncomputed: 0};
  Object.values(dists.family_pass).forEach(v => {
    passCounts.pass += v.pass; passCounts.fail += v.fail; passCounts.uncomputed += v.uncomputed;
  });
  drawPie("chart-pass", passCounts, {pass: CHART_COLORS.ok, fail: CHART_COLORS.fail, uncomputed: CHART_COLORS.warn});

  // Per-family bars
  const fams = Object.keys(families);
  const passRates  = fams.map(f => (families[f].dialect_pass_rate ?? 0) * 100);
  const cosMedians = fams.map(f => families[f].median_cosine ?? 0);
  const tcrMedians = fams.map(f => families[f].median_token_change_pct ?? 0);
  const featMedians= fams.map(f => families[f].median_feature_count ?? 0);
  const colors     = fams.map(f => FAMILY_COLORS[f] || CHART_COLORS.accent);

  drawBar("chart-fam-pass", fams, passRates,  colors, "% pass", "%");
  drawBar("chart-fam-cos",  fams, cosMedians, colors, "median cosine", "", {yMin: 0.85, yMax: 1.0});
  drawBar("chart-fam-tcr",  fams, tcrMedians, colors, "median token Δ %", "%");
  drawBar("chart-fam-feat", fams, featMedians,colors, "median features");

  // Histograms
  drawHistogram("chart-hist-cos", dists.cosine, {bins: 20, min: 0.5, max: 1.0,
    color: CHART_COLORS.accent2, label: "cosine", refLine: 0.85, refLabel: "0.85 floor"});
  drawHistogram("chart-hist-tcr", dists.token_change.map(v => v * 100), {bins: 20, min: 0, max: 40,
    color: CHART_COLORS.accent, label: "token Δ %", band: [5, 25], bandLabel: "5–25% pass band"});
  drawHistogram("chart-hist-feat", dists.feature_counts, {bins: 8, min: 0, max: 8,
    color: CHART_COLORS.accent3, label: "feature count"});
  drawHistogram("chart-hist-inv", dists.new_inventory_hits, {bins: 8, min: 0, max: 8,
    color: CHART_COLORS.warn, label: "new inv hits"});
}

function drawPie(canvasId, counts, colorOverrides = null) {
  destroyChart(canvasId);
  const labels = Object.keys(counts);
  const data = labels.map(k => counts[k]);
  const colors = labels.map(k => {
    if (colorOverrides && colorOverrides[k]) return colorOverrides[k];
    if (k === "ok") return CHART_COLORS.ok;
    if (k === "model_fail" || k === "api_error" || k === "parse_error" || k === "fail") return CHART_COLORS.fail;
    return CHART_COLORS.warn;
  });
  CHARTS[canvasId] = new Chart($("#" + canvasId), {
    type: "doughnut",
    data: { labels, datasets: [{ data, backgroundColor: colors, borderColor: "rgba(0,0,0,0)" }] },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { position: "right", labels: { color: CHART_COLORS.axis, boxWidth: 12 } },
        tooltip: { callbacks: { label: ctx => `${ctx.label}: ${ctx.parsed}` } }
      }
    }
  });
}

function drawBar(canvasId, labels, values, colors, label, unit = "", opts = {}) {
  destroyChart(canvasId);
  CHARTS[canvasId] = new Chart($("#" + canvasId), {
    type: "bar",
    data: { labels, datasets: [{ label, data: values, backgroundColor: colors, borderColor: "rgba(0,0,0,0)" }] },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: ctx => `${ctx.parsed.y.toFixed(3)}${unit}` } }
      },
      scales: {
        x: { grid: { color: CHART_COLORS.grid }, ticks: { color: CHART_COLORS.axis } },
        y: { grid: { color: CHART_COLORS.grid }, ticks: { color: CHART_COLORS.axis,
             callback: v => v + unit }, beginAtZero: opts.yMin === undefined,
             min: opts.yMin, max: opts.yMax },
      }
    }
  });
}

function drawHistogram(canvasId, values, opts) {
  destroyChart(canvasId);
  const { bins = 20, min = 0, max = 1, color = CHART_COLORS.accent,
          label = "count", band = null, refLine = null, refLabel = "" } = opts;
  const range = max - min;
  const width = range / bins;
  const counts = new Array(bins).fill(0);
  values.forEach(v => {
    if (v == null) return;
    if (v < min || v > max) return;
    let idx = Math.floor((v - min) / width);
    if (idx >= bins) idx = bins - 1;
    counts[idx]++;
  });
  const labels = Array.from({length: bins}, (_, i) => {
    const lo = (min + i * width);
    return lo.toFixed(width < 1 ? 2 : 0);
  });
  const colors = counts.map((_, i) => {
    if (band) {
      const lo = min + i * width;
      const hi = lo + width;
      if (hi > band[0] && lo < band[1]) return CHART_COLORS.accent2;
    }
    return color;
  });
  CHARTS[canvasId] = new Chart($("#" + canvasId), {
    type: "bar",
    data: { labels, datasets: [{ label, data: counts, backgroundColor: colors,
                                  borderColor: "rgba(0,0,0,0)", barPercentage: 1.0, categoryPercentage: 0.95 }] },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: {
          title: items => {
            const i = items[0].dataIndex;
            const lo = (min + i * width);
            return `${lo.toFixed(width < 1 ? 2 : 0)} – ${(lo + width).toFixed(width < 1 ? 2 : 0)}`;
          },
          label: ctx => `${ctx.parsed.y} records`
        }}
      },
      scales: {
        x: { grid: { display: false }, ticks: { color: CHART_COLORS.axis, maxRotation: 0, autoSkip: true } },
        y: { beginAtZero: true, grid: { color: CHART_COLORS.grid }, ticks: { color: CHART_COLORS.axis } }
      }
    }
  });
}

// ─────────────────── families ───────────────────
async function loadFamilyStats() {
  const stats = await fetch("/api/stats/families").then(r => r.json());
  const html = Object.entries(stats).map(([fam, s]) => {
    const passBar = (s.dialect_pass_rate ?? 0) * 100;
    const mini = (lbl, val) => `<div class="mini-stat"><div class="lbl">${lbl}</div><div class="val">${val}</div></div>`;
    return `<div class="family-card">
      <h3>${fam} — ${safeText(s.title)}</h3>
      <div class="bar"><div style="width:${passBar.toFixed(0)}%"></div></div>
      <div class="muted small" style="margin:4px 0 10px">dialect_pass rate: ${fmtPct(s.dialect_pass_rate, 1)}</div>
      <div class="mini-grid">
        ${mini("n", fmtInt(s.records))}
        ${mini("ok", `${fmtInt(s.ok)} (${fmtPct(s.ok_rate, 0)})`)}
        ${mini("med cosine", fmtNum(s.median_cosine, 4))}
        ${mini("med token Δ%", fmtNum(s.median_token_change_pct, 2) + "%")}
        ${mini("med feat #", fmtNum(s.median_feature_count, 1))}
        ${mini("ground rate", fmtPct(s.median_grounding_rate, 0))}
        ${mini("new inv hits", fmtNum(s.median_new_inventory_hits, 1))}
        ${mini("refused", fmtInt(s.refused_count))}
        ${mini("retried", fmtInt(s.multi_attempt_count))}
        ${mini("cost", fmtMoney(s.cost_usd_total))}
      </div>
    </div>`;
  }).join("");
  $("#family-stats").innerHTML = html;
}

// ─────────────────── table ───────────────────
const TABLE_COLUMNS = [
  { key: "dialect_family",       label: "family" },
  { key: "anchor_id",            label: "anchor" },
  { key: "generation_status",    label: "status", render: v => `<span class="pill ${v==='ok'?'ok':'fail'}">${v}</span>` },
  { key: "applied_feature_count",label: "feat", num: true },
  { key: "token_change_ratio",   label: "tok Δ%", num: true, render: v => v==null?"—":(v*100).toFixed(1)+"%" },
  { key: "cosine_similarity",    label: "cosine", num: true, render: v => (v==null||v===-1)?"—":Number(v).toFixed(4) },
  { key: "dialect_pass",         label: "pass", render: v => v===true?'<span class="pill ok">pass</span>':v===false?'<span class="pill fail">fail</span>':'<span class="pill warn">—</span>' },
  { key: "feature_realization_rate", label: "ground", num: true, render: v => v==null?"—":(v*100).toFixed(0)+"%" },
  { key: "new_inventory_hits",   label: "inv new", num: true },
  { key: "attempts",             label: "tries", num: true },
  { key: "cost_usd",             label: "cost", num: true, render: v => v==null?"—":"$"+Number(v).toFixed(4) },
  { key: "anchor_preview",       label: "anchor preview", cls: "preview" },
  { key: "rewrite_preview",      label: "rewrite preview", cls: "preview" },
];

let tableSort = { key: "record_id", dir: 1 };
let tableRows = [];

function buildFilterQuery() {
  const fams = [...$("#f-family").selectedOptions].map(o => o.value);
  const stats = [...$("#f-status").selectedOptions].map(o => o.value);
  const params = new URLSearchParams();
  if (fams.length) params.set("family", fams.join(","));
  if (stats.length) params.set("status", stats.join(","));
  const dp = $("#f-pass").value; if (dp && dp !== "any") params.set("dialect_pass", dp);
  const refused = $("#f-refused").value; if (refused && refused !== "any") params.set("refused", refused);
  const mf = $("#f-min-feat").value; if (mf) params.set("min_feature_count", mf);
  const tcmin = $("#f-tc-min").value; if (tcmin) params.set("min_token_change", (Number(tcmin)/100));
  const tcmax = $("#f-tc-max").value; if (tcmax) params.set("max_token_change", (Number(tcmax)/100));
  const cmin = $("#f-cos-min").value; if (cmin) params.set("min_cosine", cmin);
  const cmax = $("#f-cos-max").value; if (cmax) params.set("max_cosine", cmax);
  const s = $("#f-search").value.trim(); if (s) params.set("search", s);
  return params;
}

async function loadTable() {
  const params = buildFilterQuery();
  const data = await fetch("/api/records?" + params.toString()).then(r => r.json());
  tableRows = data.records;
  $("#table-meta").innerHTML = `${data.count} record(s) match — click any row to open in Reader.`;
  renderTable();
}
function renderTable() {
  const thead = $("#records-table thead");
  thead.innerHTML = "<tr>" + TABLE_COLUMNS.map(c =>
    `<th data-key="${c.key}">${c.label}${tableSort.key===c.key ? (tableSort.dir>0?" ▲":" ▼") : ""}</th>`
  ).join("") + "</tr>";
  $$("#records-table thead th").forEach(th => th.addEventListener("click", () => {
    const k = th.dataset.key;
    if (tableSort.key === k) tableSort.dir = -tableSort.dir;
    else { tableSort.key = k; tableSort.dir = 1; }
    renderTable();
  }));
  const sorted = [...tableRows].sort((a, b) => {
    const av = a[tableSort.key], bv = b[tableSort.key];
    if (av == null && bv == null) return 0;
    if (av == null) return 1;
    if (bv == null) return -1;
    if (typeof av === "number" && typeof bv === "number") return (av - bv) * tableSort.dir;
    return String(av).localeCompare(String(bv)) * tableSort.dir;
  });
  $("#records-table tbody").innerHTML = sorted.map(r =>
    `<tr data-id="${safeText(r.record_id)}">` +
    TABLE_COLUMNS.map(c => {
      const v = r[c.key];
      const cell = c.render ? c.render(v) : (v == null ? "—" : safeText(String(v)));
      return `<td class="${c.num?'num':''} ${c.cls||''}">${cell}</td>`;
    }).join("") + "</tr>"
  ).join("");
  $$("#records-table tbody tr").forEach(tr => tr.addEventListener("click", () => {
    openInReader(tr.dataset.id);
  }));
}

$("#apply-filters").addEventListener("click", loadTable);
$("#reset-filters").addEventListener("click", () => { $("#filters").reset(); loadTable(); });
$("#dl-jsonl").addEventListener("click", () => {
  const p = buildFilterQuery(); p.set("full", "true");
  window.location = "/api/download.jsonl?" + p.toString();
});
$("#dl-csv").addEventListener("click", () => {
  window.location = "/api/download.csv?" + buildFilterQuery().toString();
});

// ─────────────────── reader ───────────────────
const readerState = { currentId: null, family: null };

function openInReader(recordId) {
  readerState.currentId = recordId;
  activateTab("reader");
  loadRecord(recordId);
}

async function loadRecord(recordId) {
  $("#reader-card").classList.add("loading");
  $("#reader-card").innerHTML = "loading…";
  const data = await fetch("/api/record/" + encodeURIComponent(recordId)).then(r => r.json());
  $("#reader-card").classList.remove("loading");
  renderReader(data);
  readerState.currentId = data.record.record_id;
  readerState.family = data.record.dialect_family;
  $("#reader-family-select").value = readerState.family || "";
  const n = data.neighbors;
  $("#reader-position").textContent =
    `record ${n.global_index + 1} / ${n.global_total}  ·  family ${data.record.dialect_family} ${n.family_index + 1}/${n.family_total}`;
  $("#reader-prev-global").disabled = !n.global_prev;
  $("#reader-next-global").disabled = !n.global_next;
  $("#reader-prev-family").disabled = !n.family_prev;
  $("#reader-next-family").disabled = !n.family_next;
  readerState.neighbors = n;
}

function renderReader(data) {
  const r = data.record;
  const ss = r.similarity_scores || {};
  const applied = Array.isArray(r.applied_features) ? r.applied_features : [];
  const groundingMissing = (r.feature_realization && r.feature_realization.missing) || [];
  const missingSet = new Set(groundingMissing.map(m => (m.feature || "") + "||" + (m.realization || "")));
  const newHits = (r.inventory_pattern_hits && r.inventory_pattern_hits.new_hits) || [];

  const passBadge = r.dialect_pass === true
    ? '<span class="pill ok">dialect_pass</span>'
    : r.dialect_pass === false
    ? '<span class="pill fail">dialect_fail</span>'
    : '<span class="pill warn">pass uncomputed</span>';

  const meta = [
    ["family",            safeText(r.dialect_family + " · " + (r.dialect_title || ""))],
    ["anchor_id",         safeText(r.anchor_id)],
    ["status",            safeText(r.generation_status)],
    ["attempts",          fmtInt(r.attempts)],
    ["cosine",            (r.cosine_similarity == null || r.cosine_similarity === -1) ? "—" : fmtNum(r.cosine_similarity, 4)],
    ["token Δ %",         ss.token_change_ratio == null ? "—" : fmtPct(ss.token_change_ratio, 1)],
    ["difflib ratio",     fmtNum(ss.difflib_ratio, 4)],
    ["Levenshtein norm",  fmtNum(ss.levenshtein_normalized, 4)],
    ["char 3-gram J",     fmtNum(ss.char_3gram_jaccard, 4)],
    ["token Jaccard",     fmtNum(ss.token_jaccard, 4)],
    ["feature_count",     `${fmtInt(r.applied_feature_count)} (declared ${fmtInt(r.declared_feature_count)})`],
    ["grounding rate",    (r.feature_realization && r.feature_realization.rate != null) ? fmtPct(r.feature_realization.rate, 0) : "—"],
    ["new inv hits",      fmtInt(r.inventory_pattern_hits && r.inventory_pattern_hits.count_new)],
    ["anchor words",      fmtInt(r.anchor_word_count)],
    ["rewrite words",     fmtInt(r.rewrite_word_count)],
    ["cost",              fmtMoney(r.cost_usd)],
    ["tokens in / out",   `${fmtInt(r.tokens_in)} / ${fmtInt(r.tokens_out)}`],
    ["model",             safeText(r.model)],
  ];

  $("#reader-card").innerHTML = `
    <div style="display:flex; align-items:baseline; gap:12px; flex-wrap:wrap; margin-bottom:14px">
      <strong style="font-size:16px">${safeText(r.record_id)}</strong>
      ${passBadge}
      ${r.refused ? '<span class="pill fail">refused</span>' : ""}
    </div>

    <div class="reader-grid">
      <div class="reader-pane">
        <h4>Anchor</h4>
        <div class="text">${data.diff.anchor_html}</div>
      </div>
      <div class="reader-pane">
        <h4>Rewrite (${safeText(r.dialect_family)})</h4>
        <div class="text">${data.diff.rewrite_html}</div>
      </div>
    </div>

    <div class="reader-meta">
      ${meta.map(([k,v]) => `<div class="mini-stat"><div class="lbl">${k}</div><div class="val">${v}</div></div>`).join("")}
    </div>

    <div class="reader-features">
      <h4>Applied features (model self-report) — grounding ${
        (r.feature_realization && r.feature_realization.rate != null)
        ? fmtPct(r.feature_realization.rate, 0) : "—"
      }</h4>
      <div class="feat-list">
        ${applied.length === 0 ? '<div class="muted small">none</div>' :
          applied.map(f => {
            const isMissing = missingSet.has((f.feature || "") + "||" + (f.realization || ""));
            return `<div class="feat-item">
              <span class="feat-name">${safeText(f.feature || f.id || "(unnamed)")}</span>
              <span class="realization">→ "${safeText(f.realization || "")}"</span>
              ${isMissing ? '<span class="missing"> (not found in rewrite — likely hallucinated)</span>' : ""}
            </div>`;
          }).join("")}
      </div>
      ${newHits.length > 0 ? `
        <h4 style="margin-top:16px">Inventory hits in rewrite (independent of self-report)</h4>
        <div class="feat-list">
          ${newHits.map(h => `<div class="feat-item">
            <span class="feat-name">${safeText(h.feature)}</span>
            <span class="realization">pattern: <code>${safeText(h.pattern)}</code> · id: ${safeText(h.id)}</span>
          </div>`).join("")}
        </div>` : ""}
    </div>
  `;
}

async function loadRandomRecord(family = null) {
  const url = family ? `/api/records/random?family=${encodeURIComponent(family)}` : "/api/records/random";
  const d = await fetch(url).then(r => r.json());
  loadRecord(d.record_id);
}

$("#reader-prev-global").addEventListener("click", () => readerState.neighbors?.global_prev && loadRecord(readerState.neighbors.global_prev));
$("#reader-next-global").addEventListener("click", () => readerState.neighbors?.global_next && loadRecord(readerState.neighbors.global_next));
$("#reader-prev-family").addEventListener("click", () => readerState.neighbors?.family_prev && loadRecord(readerState.neighbors.family_prev));
$("#reader-next-family").addEventListener("click", () => readerState.neighbors?.family_next && loadRecord(readerState.neighbors.family_next));
$("#reader-random").addEventListener("click", () => loadRandomRecord());
$("#reader-random-family").addEventListener("click", () => loadRandomRecord(readerState.family));
$("#reader-family-select").addEventListener("change", e => {
  const fam = e.target.value;
  if (fam) loadRandomRecord(fam);
});

window.addEventListener("keydown", e => {
  const onReader = document.getElementById("tab-reader").classList.contains("active");
  if (!onReader) return;
  if (e.target.tagName === "INPUT" || e.target.tagName === "SELECT" || e.target.tagName === "TEXTAREA") return;
  if (e.key === "ArrowLeft") {
    const id = e.shiftKey ? readerState.neighbors?.family_prev : readerState.neighbors?.global_prev;
    if (id) loadRecord(id);
  } else if (e.key === "ArrowRight") {
    const id = e.shiftKey ? readerState.neighbors?.family_next : readerState.neighbors?.global_next;
    if (id) loadRecord(id);
  } else if (e.key === "r" || e.key === "R") {
    loadRandomRecord(e.shiftKey ? readerState.family : null);
  }
});

// ─────────────────── prompts ───────────────────
let promptItems = [];
async function loadPrompts() {
  if (promptItems.length === 0) {
    const data = await fetch("/api/prompts").then(r => r.json());
    promptItems = data.items;
    // Group by kind for the sidebar list.
    const groups = [
      { key: "template", label: "Template" },
      { key: "rendered", label: "Actual prompts (per family)" },
      { key: "inventory", label: "Feature inventories" },
    ];
    const html = [];
    groups.forEach(g => {
      const items = promptItems
        .map((it, i) => ({ it, i }))
        .filter(({ it }) => it.kind === g.key);
      if (items.length === 0) return;
      html.push(`<div class="group">${g.label}</div>`);
      items.forEach(({ it, i }) => {
        html.push(`<button data-i="${i}">${safeText(it.name)}</button>`);
      });
    });
    $("#prompt-list").innerHTML = html.join("");
    $$("#prompt-list button").forEach(b =>
      b.addEventListener("click", () => showPrompt(Number(b.dataset.i)))
    );
  }
  // Default to the first item.
  showPrompt(0);
}

function showPrompt(i) {
  $$("#prompt-list button").forEach(b => b.classList.toggle("active", Number(b.dataset.i) === i));
  const it = promptItems[i];
  if (!it) { $("#prompt-body").innerHTML = "<div class='muted'>nothing to show</div>"; return; }
  $("#prompt-body").innerHTML = renderProvenance(it) + renderMarkdown(it.markdown);
}

function renderProvenance(it) {
  if (!it.provenance) return "";
  const p = it.provenance;
  const vc = it.version_check;
  let rows = [];

  // For "rendered" items the provenance is a nested object covering template
  // + inventory + the lib function used. For "template"/"inventory" it's a
  // single file's worth of metadata.
  if (it.kind === "rendered") {
    rows.push(`<strong>Render source</strong> — built by <code>${safeText(p.build_input_function)}</code> from:`);
    rows.push(`&nbsp;&nbsp;template: <code>${safeText(p.template.path)}</code> · mtime ${safeText(p.template.mtime_utc)} · sha256 <code>${safeText(p.template.sha256?.slice(0,16) || "—")}…</code>`);
    rows.push(`&nbsp;&nbsp;inventory: <code>${safeText(p.inventory.path)}</code> · mtime ${safeText(p.inventory.mtime_utc)} · sha256 <code>${safeText(p.inventory.sha256?.slice(0,16) || "—")}…</code>`);
    rows.push(`<strong>Rendered SHA-256:</strong> <code>${safeText(p.rendered_sha256 || "—")}</code>`);
    rows.push(`<strong>prompt_version:</strong> <code>${safeText(p.prompt_version)}</code>`);
    if (p.note) rows.push(`<em class="muted">${safeText(p.note)}</em>`);
  } else if (p.path) {
    rows.push(`<strong>Source:</strong> <code>${safeText(p.path)}</code>`);
    if (p.mtime_utc) rows.push(`<strong>Modified:</strong> ${safeText(p.mtime_utc)}`);
    if (p.sha256) rows.push(`<strong>SHA-256:</strong> <code>${safeText(p.sha256.slice(0,32))}…</code>`);
    if (p.bytes != null) rows.push(`<strong>Size:</strong> ${p.bytes} bytes`);
  }

  // Version-match badge (applies to template + rendered; inventories are referenced indirectly).
  let badge = "";
  if (vc && (it.kind === "template" || it.kind === "rendered")) {
    if (vc.in_sync) {
      badge = `<span class="pill ok">prompt_version matches all ${vc.records_total} records (${vc.current_version})</span>`;
    } else {
      badge = `<span class="pill fail">prompt_version MISMATCH — current=${vc.current_version}, recorded=${(vc.recorded_versions || []).join(", ")}</span>`;
    }
  }
  return `<div class="provenance">
    ${badge ? `<div style="margin-bottom:8px">${badge}</div>` : ""}
    ${rows.map(r => `<div>${r}</div>`).join("")}
  </div>`;
}

// Tiny markdown subset renderer — enough for our prompts + inventories.
// Also highlights `[bracketed placeholder]` tokens that we inject in the
// template view so they look distinct from regular text.
function renderMarkdown(md) {
  const lines = md.split("\n");
  const out = [];
  let inCode = false, inList = false;
  for (let raw of lines) {
    if (raw.startsWith("```")) {
      if (!inCode) { out.push("<pre><code>"); inCode = true; }
      else { out.push("</code></pre>"); inCode = false; }
      continue;
    }
    if (inCode) { out.push(safeText(raw)); continue; }
    const line = raw.replace(/\r$/, "");
    if (line.startsWith("### ")) { closeList(); out.push("<h3>" + inlineMd(line.slice(4)) + "</h3>"); continue; }
    if (line.startsWith("## "))  { closeList(); out.push("<h2>" + inlineMd(line.slice(3)) + "</h2>"); continue; }
    if (line.startsWith("# "))   { closeList(); out.push("<h1>" + inlineMd(line.slice(2)) + "</h1>"); continue; }
    if (line.startsWith("- ") || /^\s{2,}- /.test(line)) {
      if (!inList) { out.push("<ul>"); inList = true; }
      out.push("<li>" + inlineMd(line.replace(/^\s*- /, "")) + "</li>");
      continue;
    }
    if (line.trim() === "") { closeList(); out.push(""); continue; }
    closeList();
    out.push("<p>" + inlineMd(line) + "</p>");
  }
  closeList();
  function closeList() { if (inList) { out.push("</ul>"); inList = false; } }
  return out.join("\n");
}
function inlineMd(s) {
  let t = safeText(s);
  // Highlight bracketed placeholders like "[anchor essay]" inserted by the
  // server's humanize step. Run before bold/italic so they don't fight.
  t = t.replace(/\[([a-z][^\]]{0,80})\]/g, '<span class="placeholder-token">[$1]</span>');
  t = t.replace(/`([^`]+)`/g, "<code>$1</code>");
  t = t.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  t = t.replace(/(^|\W)_([^_]+)_(?=\W|$)/g, "$1<em>$2</em>");
  return t;
}

// ─────────────────── boot ───────────────────
activateTab("dashboard");
