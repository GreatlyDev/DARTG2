// Single-page UI for the base2 sweep viewer.
//
// Tabs (driven by sidebar nav): dashboard, families, table, reader, prompts.
// Charts via Chart.js (loaded as a global `Chart` from CDN).

const $  = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

// ─────────────────── tooltip definitions ───────────────────
// Central source of truth for hover-help text. Every stat / column / chart /
// filter in the UI references a key here so the wording stays consistent.
const TOOLTIPS = {
  // Headline / overall
  records:            "Total number of rewrite records loaded from the JSONL file.",
  ok_rate:            "Fraction of records with generation_status='ok'. Failures are model_fail, parse_error, or api_error (rare; the runner retries transient API errors up to 8 times).",
  dialect_pass_rate:  "Fraction of OK records that satisfy the composite gate: cosine ≥ 0.85 AND (applied_feature_count ≥ 3 OR new_inventory_hits ≥ 1). Defined in lib/dialect_scoring.py:dialect_pass. Switched from a token-change criterion because token-change systematically undercounts dialect rewrites (dialect work clusters in a few high-signal words).",
  total_cost:         "Total USD spend across all records. Computed from per-record tokens_in/tokens_out × the per-million price in lib/pricing.py.",

  // Similarity / change measures
  cosine:             "Sentence-embedding cosine similarity between anchor and rewrite. Encoder: sentence-transformers/all-MiniLM-L6-v2. Range 0–1; 1.0 = identical meaning, lower = more semantic drift. Sentinel value -1 means uncomputed (e.g. --no-embed run or empty rewrite).",
  token_change_pct:   "Fraction of anchor word tokens NOT preserved in the rewrite, ×100. The base2 prompt targets a 5–25% surface-variation band. Below 5% the rewrite barely changed; above 25% it starts to paraphrase instead of dialect-rewrite.",
  difflib_ratio:      "Python's difflib.SequenceMatcher.ratio() over the character sequences. 1.0 = identical text, 0 = totally different.",
  levenshtein_norm:   "Levenshtein edit distance divided by the longer string's length. 0 = identical, 1 = maximum distance.",
  char_3gram_j:       "Jaccard similarity over 3-character shingles. Catches sub-word changes (e.g. 'going' → 'gonna') that token-level metrics miss.",
  token_jaccard:      "Jaccard similarity over lowercase word tokens. High = same vocabulary, low = many different words.",
  length_ratio:       "len(rewrite) / len(anchor). 1.0 = same length.",
  composite_change:   "1 − difflib_ratio. Convenience top-level field; rises with surface change.",

  // Features
  feature_count:      "Number of distinct {feature, realization} entries the model reported in its applied_features array. Range typically 2–5; the prompt asks for ≥2 on short anchors and 3–5 on longer ones.",
  declared_count:     "feature_count value the model self-reported in its JSON output. model_notes is populated when this disagrees with len(applied_features).",
  grounding_rate:     "Of the {realization} substrings the model claimed it produced, what fraction actually appear in rewrite_text? 100% = the model is honest; below 100% = at least one claim is hallucinated. Computed by lib/dialect_scoring.py:feature_realization_grounding.",
  new_inv_hits:       "Independent scan: how many concrete inventory feature names appear in the rewrite but NOT in the anchor. Confirms dialect change without trusting the model's self-report. Abstract syntactic features (e.g. 'double modals') aren't string-matchable and are skipped — only lexical patterns count here.",
  inv_hits_rewrite:   "All inventory patterns matched anywhere in the rewrite (including ones already present in the anchor).",
  inv_hits_anchor:    "Inventory patterns already present in the anchor — background noise we subtract to compute new_inv_hits.",

  // Operational
  attempts:           "Runner-level attempts on this record. 1 = first call succeeded. >1 = the response came back as parse_error / model_fail / api_error and was re-tried. Caps at --max-attempts (default 2).",
  cost_usd:           "Estimated USD cost for this single record. tokens_in × input_price + tokens_out × output_price.",
  tokens_in:          "Input tokens the model billed for this call (prompt + system).",
  tokens_out:         "Output tokens the model produced.",
  refused:            "Heuristic: True if exact_match (model returned anchor verbatim) OR generation failed OR applied_features was an empty list.",
  retried:            "Number of records that needed >1 attempt to succeed.",
  multi_attempt:      "Number of records that needed >1 attempt to succeed (synonym for retried).",

  // Dialect pass detail
  dialect_pass:       "Per-record composite gate. PASS iff cosine ≥ 0.85 AND (applied_feature_count ≥ 3 OR new_inventory_hits ≥ 1). None when cosine wasn't computed. See lib/dialect_scoring.py:dialect_pass for the source of truth.",

  // Status pills
  status_ok:          "Model returned a valid JSON rewrite that parsed successfully.",
  status_fail:        "Model returned 'FAIL' (couldn't satisfy constraints), produced invalid JSON, or the API errored out after all retries.",
  status_uncomputed:  "Couldn't decide pass/fail because cosine wasn't computed for this record.",

  // Per-family
  fam_n:              "Anchor count for this family.",
  fam_ok:             "OK records and OK rate within this family.",

  // Word-count / length analysis
  anchor_word_count:  "Whitespace-tokenized word count of the anchor essay. Anchors in this dataset range 50–142 words.",
  rewrite_word_count: "Whitespace-tokenized word count of the rewrite. A meaningful drop or spike vs anchor_word_count is a sign of paraphrase rather than dialect-rewriting.",
  length_band:        "Anchor length bucket — short (≤60 words), medium (61–120), long (>120). Used to test whether token-change behavior is driven by anchor length.",
  score_band:         "Original essay score band carried through from the anchor CSV (LOW / MID / HIGH). Used to test whether the model rewrites LOW-scored anchors more aggressively.",
  tokens_changed_absolute: "Absolute count of anchor word-tokens that did NOT survive into the rewrite. Computed as round(anchor_word_count × token_change_ratio). Pairs with min/max_change_budget_words to show the absolute budget visually.",
  min_change_budget_words: "Words the 5% lower bound buys you on this anchor — round(anchor_word_count × 0.05). On a 50-word anchor that's just 2.5 words; on a 150-word anchor it's 7.5.",
  max_change_budget_words: "Words the 25% upper bound buys you on this anchor — round(anchor_word_count × 0.25). The original token-change gate would cap a rewrite at this many changed words.",
  feature_density_per_100w: "applied_feature_count per 100 anchor words. Density makes feature counts comparable across short and long anchors.",
};

// Apply title attributes (and a help cursor) to elements that have a
// data-tooltip key — used for static HTML labels in the template.
function applyStaticTooltips() {
  $$("[data-tooltip]").forEach(el => {
    const key = el.dataset.tooltip;
    const text = TOOLTIPS[key];
    if (text) { el.title = text; el.classList.add("has-tooltip"); }
  });
}

// Build an inline title="..." attribute from a tooltip key.
function tipAttr(key) {
  const t = TOOLTIPS[key];
  return t ? ` title="${String(t).replace(/"/g, "&quot;")}"` : "";
}

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
  if (name === "length")    loadLengthAnalysis();
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
  const card = (label, value, sub="", tipKey=null) => `
    <div class="stat-card${tipKey ? " has-tooltip" : ""}"${tipAttr(tipKey)}>
      <div class="label">${label}${tipKey ? ' <span class="help">ⓘ</span>' : ""}</div>
      <div class="value">${value}</div>
      ${sub ? `<div class="sub">${sub}</div>` : ""}
    </div>`;
  $("#headline-stats").innerHTML = [
    card("Records",          fmtInt(overall.records),                                                  "",                                                 "records"),
    card("OK rate",          fmtPct(overall.ok_rate),                                                  `${overall.ok}/${overall.records} ok`,              "ok_rate"),
    card("Dialect-pass",     fmtPct(overall.dialect_pass_rate, 1),                                     "cosine ≥ 0.85 AND (feat ≥ 3 OR new inv hit)",      "dialect_pass_rate"),
    card("Median cosine",    fmtNum(overall.median_cosine, 4),                                         "meaning preservation",                             "cosine"),
    card("Median token Δ %", fmtNum(overall.median_token_change_pct, 2) + "%",                         "surface variation",                                "token_change_pct"),
    card("Median features",  fmtNum(overall.median_feature_count, 1),                                  "applied per rewrite",                              "feature_count"),
    card("Grounding rate",   fmtPct(overall.median_grounding_rate, 1),                                 "realizations found in rewrite",                    "grounding_rate"),
    card("Total cost",       fmtMoney(overall.cost_usd_total),                                         `${fmtInt(overall.tokens_in_total)} in / ${fmtInt(overall.tokens_out_total)} out`, "total_cost"),
  ].join("");

  // Decorate chart titles with tooltips for their underlying metric.
  const chartTips = {
    "chart-status":   "status_ok",
    "chart-pass":     "dialect_pass",
    "chart-fam-pass": "dialect_pass_rate",
    "chart-fam-cos":  "cosine",
    "chart-fam-tcr":  "token_change_pct",
    "chart-fam-feat": "feature_count",
    "chart-hist-cos": "cosine",
    "chart-hist-tcr": "token_change_pct",
    "chart-hist-feat":"feature_count",
    "chart-hist-inv": "new_inv_hits",
  };
  Object.entries(chartTips).forEach(([canvasId, key]) => {
    const card = $("#" + canvasId)?.closest(".chart-card");
    const title = card?.querySelector(".chart-title");
    if (title && TOOLTIPS[key]) { card.title = TOOLTIPS[key]; card.classList.add("has-tooltip"); }
  });

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
    color: CHART_COLORS.accent, label: "token Δ %"});
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
  const mini = (lbl, val, tipKey=null) => `
    <div class="mini-stat${tipKey ? " has-tooltip" : ""}"${tipAttr(tipKey)}>
      <div class="lbl">${lbl}</div>
      <div class="val">${val}</div>
    </div>`;
  const html = Object.entries(stats).map(([fam, s]) => {
    const passBar = (s.dialect_pass_rate ?? 0) * 100;
    return `<div class="family-card">
      <h3>${fam} — ${safeText(s.title)}</h3>
      <div class="bar${"" /*"" pad */}"><div style="width:${passBar.toFixed(0)}%"></div></div>
      <div class="muted small has-tooltip"${tipAttr("dialect_pass_rate")} style="margin:4px 0 10px">dialect_pass rate: ${fmtPct(s.dialect_pass_rate, 1)}</div>
      <div class="mini-grid">
        ${mini("n",              fmtInt(s.records),                                "fam_n")}
        ${mini("ok",             `${fmtInt(s.ok)} (${fmtPct(s.ok_rate, 0)})`,       "fam_ok")}
        ${mini("med cosine",     fmtNum(s.median_cosine, 4),                       "cosine")}
        ${mini("med token Δ%",   fmtNum(s.median_token_change_pct, 2) + "%",       "token_change_pct")}
        ${mini("med feat #",     fmtNum(s.median_feature_count, 1),                "feature_count")}
        ${mini("ground rate",    fmtPct(s.median_grounding_rate, 0),               "grounding_rate")}
        ${mini("new inv hits",   fmtNum(s.median_new_inventory_hits, 1),           "new_inv_hits")}
        ${mini("refused",        fmtInt(s.refused_count),                          "refused")}
        ${mini("retried",        fmtInt(s.multi_attempt_count),                    "retried")}
        ${mini("cost",           fmtMoney(s.cost_usd_total),                       "total_cost")}
      </div>
    </div>`;
  }).join("");
  $("#family-stats").innerHTML = html;
}

// ─────────────────── anchor length / score band ───────────────────
async function loadLengthAnalysis() {
  const [scatter, bands] = await Promise.all([
    fetch("/api/stats/length_scatter").then(r => r.json()),
    fetch("/api/stats/length_bands").then(r => r.json()),
  ]);

  // Headline takeaways: pass rate by length / score band, total n.
  const byLen = bands.by_length || {};
  const byScore = bands.by_score || {};
  const card = (label, value, sub="", tipKey=null) => `
    <div class="stat-card${tipKey ? " has-tooltip" : ""}"${tipAttr(tipKey)}>
      <div class="label">${label}${tipKey ? ' <span class="help">ⓘ</span>' : ""}</div>
      <div class="value">${value}</div>
      ${sub ? `<div class="sub">${sub}</div>` : ""}
    </div>`;
  $("#length-headline").innerHTML = [
    card("OK records",                     fmtInt(scatter.points.length),                                      "with valid token-change", "anchor_word_count"),
    card("Short anchors (≤60w)",           `${fmtInt((byLen.short || {}).n || 0)} · ${fmtPct((byLen.short || {}).dialect_pass_rate, 0)} pass`,  "", "length_band"),
    card("Medium anchors (61–120w)",       `${fmtInt((byLen.medium || {}).n || 0)} · ${fmtPct((byLen.medium || {}).dialect_pass_rate, 0)} pass`, "", "length_band"),
    card("Long anchors (>120w)",           `${fmtInt((byLen.long || {}).n || 0)} · ${fmtPct((byLen.long || {}).dialect_pass_rate, 0)} pass`,    "", "length_band"),
  ].join("");

  // Scatter — anchor word count vs token change %, dotted ref lines at 5% and 25%.
  drawScatter("chart-length-scatter", scatter.points, scatter.band);

  // Bar charts per band.
  const lenKeys = Object.keys(byLen);
  const lenColors = lenKeys.map(k => ({short: CHART_COLORS.accent3, medium: CHART_COLORS.accent, long: CHART_COLORS.warn, unknown: CHART_COLORS.muted})[k] || CHART_COLORS.muted);
  drawBar("chart-length-pass", lenKeys, lenKeys.map(k => (byLen[k].dialect_pass_rate ?? 0) * 100), lenColors, "% pass", "%", {yMin: 0, yMax: 100});
  drawBar("chart-length-tcr",  lenKeys, lenKeys.map(k => byLen[k].median_token_change_pct ?? 0),  lenColors, "median token Δ %", "%");

  const scoreKeys = Object.keys(byScore);
  const scoreColors = scoreKeys.map(k => ({LOW: CHART_COLORS.fail, MID: CHART_COLORS.warn, HIGH: CHART_COLORS.ok, unknown: CHART_COLORS.muted})[String(k).toUpperCase()] || CHART_COLORS.muted);
  drawBar("chart-score-pass", scoreKeys, scoreKeys.map(k => (byScore[k].dialect_pass_rate ?? 0) * 100), scoreColors, "% pass", "%", {yMin: 0, yMax: 100});
  drawBar("chart-score-tcr",  scoreKeys, scoreKeys.map(k => byScore[k].median_token_change_pct ?? 0),  scoreColors, "median token Δ %", "%");

  // Tables.
  const cols = [
    {key: "band",                          label: "band"},
    {key: "n",                             label: "n",                    num: true},
    {key: "dialect_pass_rate",             label: "pass",                 num: true, render: v => v==null?"—":(v*100).toFixed(1)+"%"},
    {key: "median_anchor_words",           label: "med anchor words",     num: true},
    {key: "median_tokens_changed",         label: "med tokens changed",   num: true},
    {key: "median_token_change_pct",       label: "med token Δ%",         num: true, render: v => v==null?"—":v.toFixed(2)+"%"},
    {key: "median_feature_count",          label: "med features",         num: true},
    {key: "median_feature_density_per_100w", label: "feat/100w",          num: true},
    {key: "median_cosine",                 label: "med cosine",           num: true, render: v => v==null?"—":v.toFixed(4)},
  ];
  function bandTable(tableSel, groups) {
    const thead = $(tableSel + " thead");
    const tbody = $(tableSel + " tbody");
    thead.innerHTML = "<tr>" + cols.map(c => `<th class="${c.num?'num':''}">${c.label}</th>`).join("") + "</tr>";
    tbody.innerHTML = Object.entries(groups).map(([band, s]) => {
      return "<tr>" + cols.map(c => {
        if (c.key === "band") return `<td><strong>${safeText(band)}</strong></td>`;
        const v = s[c.key];
        const cell = c.render ? c.render(v) : (v == null ? "—" : safeText(String(v)));
        return `<td class="${c.num?'num':''}">${cell}</td>`;
      }).join("") + "</tr>";
    }).join("");
  }
  bandTable("#length-band-table", byLen);
  bandTable("#score-band-table",  byScore);
}

function drawScatter(canvasId, points, band) {
  destroyChart(canvasId);
  const grouped = { pass: [], fail: [], uncomputed: [] };
  for (const p of points) {
    const k = p.dialect_pass === true ? "pass" : p.dialect_pass === false ? "fail" : "uncomputed";
    grouped[k].push({ x: p.anchor_word_count, y: p.token_change_pct, recordId: p.record_id,
                      family: p.dialect_family, scoreBand: p.score_band, feat: p.applied_feature_count });
  }
  const datasets = [
    { label: "pass", data: grouped.pass, backgroundColor: CHART_COLORS.ok,   borderColor: "rgba(0,0,0,0)", pointRadius: 3 },
    { label: "fail", data: grouped.fail, backgroundColor: CHART_COLORS.fail, borderColor: "rgba(0,0,0,0)", pointRadius: 3 },
  ];
  if (grouped.uncomputed.length) {
    datasets.push({ label: "uncomputed", data: grouped.uncomputed, backgroundColor: CHART_COLORS.muted, borderColor: "rgba(0,0,0,0)", pointRadius: 3 });
  }
  CHARTS[canvasId] = new Chart($("#" + canvasId), {
    type: "scatter",
    data: { datasets },
    options: {
      responsive: true, maintainAspectRatio: false,
      onClick: (evt, items) => {
        const item = items?.[0];
        if (!item) return;
        const p = datasets[item.datasetIndex].data[item.index];
        if (p?.recordId) openInReader(p.recordId);
      },
      plugins: {
        legend: { position: "bottom", labels: { color: CHART_COLORS.axis, boxWidth: 12 } },
        tooltip: { callbacks: {
          label: ctx => {
            const d = ctx.raw;
            return `${d.recordId}  ·  ${d.family}  ·  score=${d.scoreBand ?? '?'}  ·  feat=${d.feat}  ·  (${d.x}w, ${d.y.toFixed(1)}%)`;
          }
        }}
      },
      scales: {
        x: { type: "linear", title: { display: true, text: "anchor word count", color: CHART_COLORS.axis },
             grid: { color: CHART_COLORS.grid }, ticks: { color: CHART_COLORS.axis } },
        y: { title: { display: true, text: "token change %", color: CHART_COLORS.axis },
             grid: { color: CHART_COLORS.grid }, ticks: { color: CHART_COLORS.axis },
             beginAtZero: true, suggestedMax: 35 },
      },
    },
    // Simple inline plugin that draws 5% and 25% reference lines on the scatter
    // — Chart.js' annotation plugin isn't loaded, so this is the lightest option.
    plugins: [{
      id: "refLines",
      afterDatasetsDraw(chart) {
        const { ctx, chartArea, scales: { y } } = chart;
        if (!chartArea) return;
        const refs = [
          { v: band?.low ?? 5,  color: CHART_COLORS.warn, label: `${band?.low ?? 5}% floor` },
          { v: band?.high ?? 25, color: CHART_COLORS.warn, label: `${band?.high ?? 25}% ceiling` },
        ];
        ctx.save();
        ctx.lineWidth = 1;
        ctx.setLineDash([4, 4]);
        ctx.font = "11px sans-serif";
        for (const r of refs) {
          const yPix = y.getPixelForValue(r.v);
          if (yPix < chartArea.top || yPix > chartArea.bottom) continue;
          ctx.strokeStyle = r.color;
          ctx.beginPath();
          ctx.moveTo(chartArea.left, yPix);
          ctx.lineTo(chartArea.right, yPix);
          ctx.stroke();
          ctx.fillStyle = r.color;
          ctx.fillText(r.label, chartArea.left + 6, yPix - 4);
        }
        ctx.restore();
      }
    }],
  });
}

// ─────────────────── table ───────────────────
const TABLE_COLUMNS = [
  { key: "dialect_family",       label: "family",                 tip: null },
  { key: "anchor_id",            label: "anchor",                 tip: null },
  { key: "generation_status",    label: "status",                 tip: "ok_rate",
    render: v => `<span class="pill ${v==='ok'?'ok':'fail'}">${v}</span>` },
  { key: "applied_feature_count",label: "feat",   num: true,      tip: "feature_count" },
  { key: "anchor_word_count",    label: "anc w",  num: true,      tip: "anchor_word_count" },
  { key: "rewrite_word_count",   label: "rew w",  num: true,      tip: "rewrite_word_count" },
  { key: "tokens_changed_absolute", label: "Δw", num: true,       tip: "tokens_changed_absolute" },
  { key: "min_change_budget_words", label: "5%w", num: true,      tip: "min_change_budget_words" },
  { key: "max_change_budget_words", label: "25%w", num: true,     tip: "max_change_budget_words" },
  { key: "token_change_ratio",   label: "tok Δ%", num: true,      tip: "token_change_pct",
    render: v => v==null?"—":(v*100).toFixed(1)+"%" },
  { key: "cosine_similarity",    label: "cosine", num: true,      tip: "cosine",
    render: v => (v==null||v===-1)?"—":Number(v).toFixed(4) },
  { key: "dialect_pass",         label: "pass",                   tip: "dialect_pass",
    render: v => v===true?'<span class="pill ok">pass</span>':v===false?'<span class="pill fail">fail</span>':'<span class="pill warn">—</span>' },
  { key: "feature_realization_rate", label: "ground", num: true,  tip: "grounding_rate",
    render: v => v==null?"—":(v*100).toFixed(0)+"%" },
  { key: "new_inventory_hits",   label: "inv new", num: true,     tip: "new_inv_hits" },
  { key: "attempts",             label: "tries",   num: true,     tip: "attempts" },
  { key: "cost_usd",             label: "cost",    num: true,     tip: "cost_usd",
    render: v => v==null?"—":"$"+Number(v).toFixed(4) },
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
    `<th data-key="${c.key}" class="${c.tip ? "has-tooltip" : ""}"${tipAttr(c.tip)}>${c.label}${tableSort.key===c.key ? (tableSort.dir>0?" ▲":" ▼") : ""}</th>`
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
    ["family",            safeText(r.dialect_family + " · " + (r.dialect_title || "")), null],
    ["anchor_id",         safeText(r.anchor_id),                                          null],
    ["status",            safeText(r.generation_status),                                  "ok_rate"],
    ["attempts",          fmtInt(r.attempts),                                             "attempts"],
    ["cosine",            (r.cosine_similarity == null || r.cosine_similarity === -1) ? "—" : fmtNum(r.cosine_similarity, 4), "cosine"],
    ["token Δ %",         ss.token_change_ratio == null ? "—" : fmtPct(ss.token_change_ratio, 1), "token_change_pct"],
    ["difflib ratio",     fmtNum(ss.difflib_ratio, 4),                                    "difflib_ratio"],
    ["Levenshtein norm",  fmtNum(ss.levenshtein_normalized, 4),                           "levenshtein_norm"],
    ["char 3-gram J",     fmtNum(ss.char_3gram_jaccard, 4),                               "char_3gram_j"],
    ["token Jaccard",     fmtNum(ss.token_jaccard, 4),                                    "token_jaccard"],
    ["feature_count",     `${fmtInt(r.applied_feature_count)} (declared ${fmtInt(r.declared_feature_count)})`, "feature_count"],
    ["grounding rate",    (r.feature_realization && r.feature_realization.rate != null) ? fmtPct(r.feature_realization.rate, 0) : "—", "grounding_rate"],
    ["new inv hits",      fmtInt(r.inventory_pattern_hits && r.inventory_pattern_hits.count_new), "new_inv_hits"],
    ["anchor words",      fmtInt(r.anchor_word_count),                                    "anchor_word_count"],
    ["rewrite words",     fmtInt(r.rewrite_word_count),                                   "rewrite_word_count"],
    ["length band",       safeText(r.length_band || "—"),                                 "length_band"],
    ["score band",        safeText((r.anchor_extras || {}).score_band || "—"),            "score_band"],
    ["tokens changed",    fmtInt(r.tokens_changed_absolute),                              "tokens_changed_absolute"],
    ["change budget",     `${fmtInt(r.min_change_budget_words)}–${fmtInt(r.max_change_budget_words)} words`, "max_change_budget_words"],
    ["feat / 100w",       fmtNum(r.feature_density_per_100w, 2),                          "feature_density_per_100w"],
    ["cost",              fmtMoney(r.cost_usd),                                           "cost_usd"],
    ["tokens in / out",   `${fmtInt(r.tokens_in)} / ${fmtInt(r.tokens_out)}`,             "tokens_in"],
    ["model",             safeText(r.model),                                              null],
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
      ${meta.map(([k,v,tip]) => `<div class="mini-stat${tip ? " has-tooltip" : ""}"${tipAttr(tip)}><div class="lbl">${k}</div><div class="val">${v}</div></div>`).join("")}
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

// ─────────────────── dataset switcher ───────────────────
// Populates the sidebar <select> with every JSONL the server can see, and
// hot-swaps the in-memory dataset on change.

function _fmtMtime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d)) return "";
  const now = new Date();
  const sameDay = d.toDateString() === now.toDateString();
  return sameDay
    ? d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    : d.toLocaleDateString([], { month: "short", day: "numeric" });
}

async function loadDatasetList() {
  const picker = $("#dataset-picker");
  if (!picker) return;
  let data;
  try {
    data = await fetch("/api/datasets").then(r => r.json());
  } catch (err) {
    picker.innerHTML = `<option disabled>error loading dataset list</option>`;
    return;
  }
  const current = data.current;
  picker.innerHTML = data.datasets.map(d => {
    const label = d.name.replace(/\.jsonl$/i, "");
    const selected = d.path === current ? " selected" : "";
    return `<option value="${d.path}"${selected}>${label}</option>`;
  }).join("");
  // If the current dataset isn't in the listed set (e.g. it lives outside the
  // configured roots), still surface it as a non-selectable first row.
  if (current && !data.datasets.some(d => d.path === current)) {
    const opt = document.createElement("option");
    opt.value = current;
    opt.selected = true;
    opt.textContent = `${data.current_name} · (current)`;
    picker.prepend(opt);
  }
}

async function switchDataset(path) {
  const meta = $("#dataset-record-count");
  const status = $("#dataset-status");
  const picker = $("#dataset-picker");
  if (status) status.textContent = "loading…";
  if (picker) picker.disabled = true;
  try {
    const res = await fetch("/api/load", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    const info = await res.json();
    if (meta) meta.textContent = info.records;
    if (status) status.textContent = info.model ? info.model : "";
    // Reset reader state — record_ids likely differ between datasets.
    if (typeof readerState !== "undefined") readerState.currentId = null;
    // Re-run whatever tab the user is on so the data refreshes immediately.
    const activeTab = document.querySelector(".navlink.active")?.dataset?.tab || "dashboard";
    activateTab(activeTab);
  } catch (err) {
    if (status) status.textContent = `error: ${err.message}`;
    if (picker) picker.value = picker.dataset.lastValue || "";
  } finally {
    if (picker) {
      picker.disabled = false;
      picker.dataset.lastValue = picker.value;
    }
  }
}

const _datasetPickerEl = document.getElementById("dataset-picker");
if (_datasetPickerEl) {
  _datasetPickerEl.addEventListener("change", (e) => switchDataset(e.target.value));
}

// ─────────────────── boot ───────────────────
applyStaticTooltips();
loadDatasetList();
activateTab("dashboard");
