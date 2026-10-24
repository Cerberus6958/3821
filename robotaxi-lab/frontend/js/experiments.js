// Experiments view: many random days, or a sweep over one parameter.
import { api, waitForJob } from "./api.js";
import { chart, lineSet } from "./charts.js";
import { emit, enabledHeuristics, exactSettings, heuristicPayload, on } from "./state.js";
import { download, el, fmt, fmtSeconds, formData, intOr, seriesColor, store, toCSV, toast } from "./util.js";

let mode = "batch";
let jobId = null;
let last = null;          // { mode, result, slots }

const VAR_LABEL = { n: "Trips", cars: "Cars", horizon: "Requests within (min)", width: "Grid size" };

export function initExperiments() {
  const form = document.getElementById("exp-form");
  const saved = store.get("exp-form", null);
  if (saved) for (const [k, v] of Object.entries(saved)) if (form.elements[k]) form.elements[k].value = v;
  setMode(store.get("exp-mode", "batch"));
  for (const b of document.querySelectorAll("#view-experiments [data-mode]")) b.addEventListener("click", () => setMode(b.dataset.mode));
  form.addEventListener("submit", (e) => { e.preventDefault(); run(); });
  document.getElementById("exp-cancel").addEventListener("click", () => jobId && api.cancel(jobId));
  on("theme-changed", () => last && renderResult());
  on("tab-shown", (t) => { if (t === "experiments" && last) renderResult(); });
}

function setMode(m) {
  mode = m;
  store.set("exp-mode", m);
  for (const b of document.querySelectorAll("#view-experiments [data-mode]")) b.setAttribute("aria-checked", String(b.dataset.mode === m));
  for (const n of document.querySelectorAll("#exp-form [data-sweep]")) n.hidden = m !== "sweep";
  for (const n of document.querySelectorAll("#exp-form [data-batch]")) n.hidden = m !== "batch";
}

export function setProgress(id, done, total, message) {
  const box = document.getElementById(id);
  box.hidden = false;
  box.querySelector(".bar span").style.width = `${Math.round((100 * done) / Math.max(total, 1))}%`;
  box.querySelector("p").textContent = message ? `${message} (${done} of ${total})` : "";
}

async function run() {
  const hs = enabledHeuristics();
  if (!hs.length) return toast("Tick at least one heuristic in the sidebar.", "error");
  const form = document.getElementById("exp-form");
  const f = formData(form);
  store.set("exp-form", f);
  const config = {
    n: intOr(f.n, 8), cars: intOr(f.cars, 2), width: intOr(f.width, 10), horizon: intOr(f.horizon, 40),
    instances: intOr(f.instances, 50), seed: intOr(f.seed, 3821), reference: f.reference,
  };
  if (mode === "sweep") {
    config.variable = f.variable;
    config.values = String(f.values).split(/[\s,]+/).filter(Boolean).map((v) => parseInt(v, 10)).filter(Number.isFinite);
    if (!config.values.length) return toast("Enter at least one value to sweep, separated by commas.", "error");
    if (config.values.length > 25) return toast("Sweep at most 25 values at a time.", "error");
  }
  const exact = { ...exactSettings(), enabled: true };
  const submit = form.querySelector("button[type=submit]");
  const cancel = document.getElementById("exp-cancel");
  submit.disabled = true;
  cancel.hidden = false;
  setProgress("exp-progress", 0, 1, "Starting");
  try {
    const { job } = await api.startJob(mode === "sweep" ? "sweep" : "batch", { config, heuristics: hs.map(heuristicPayload), exact });
    jobId = job;
    const result = await waitForJob(job, (d, t, m) => setProgress("exp-progress", d, t, m));
    if (!result) { toast("Experiment cancelled."); return; }
    last = { mode, result, slots: hs.map((h) => h.slot) };
    renderResult();
  } catch (err) {
    toast(err.message, "error");
  } finally {
    jobId = null;
    submit.disabled = false;
    cancel.hidden = true;
    document.getElementById("exp-progress").hidden = true;
  }
}

function section(title, ...kids) {
  return el("section", { class: "result-section" }, el("h3", {}, title), ...kids);
}

function nameCell(name, slot) {
  return el("span", { class: "name-cell" }, el("span", { class: "swatch", style: { background: seriesColor(slot) } }), name);
}

function figure(caption, canvasId, note) {
  return el("figure", { class: "chart-block" },
    el("figcaption", {}, caption),
    el("div", { class: "chart-box" }, el("canvas", { id: canvasId })),
    note ? el("p", { class: "chart-note" }, note) : null);
}

function renderResult() {
  if (!last) return;
  if (last.mode === "sweep") renderSweep(last.result, last.slots);
  else renderBatch(last.result, last.slots);
}

// ------------------------------------------------------------------ batch

function renderBatch(res, slots) {
  const s = res.summary;
  const refName = res.reference === "optimal" ? "optimum" : "best heuristic";
  const out = document.getElementById("exp-results");
  const facts = el("div", { class: "facts" },
    fact(String(s.instances), `Random days${res.cancelled ? " (stopped early)" : ""}`),
    res.reference === "optimal" ? fact(`${s.proven} of ${s.instances}`, "Optimum proven within the time limit") : null,
    fact(`${fmt(s.mean_reference)} min`, `Mean ${refName} longest wait`),
    s.mean_solver_seconds !== null ? fact(fmtSeconds(s.mean_solver_seconds), "Mean solver time per day") : null);

  const table = el("table", { class: "data" },
    el("thead", {}, el("tr", {}, ["Heuristic", "Mean longest wait", "Mean ratio", "Median ratio", "Worst ratio",
      `Days matching ${refName}`, "Zero-wait days found", "Mean run time"].map((c) => el("th", {}, c)))),
    el("tbody", {}, s.per_heuristic.map((p, h) => el("tr", {},
      el("td", {}, nameCell(p.name, slots[h])),
      el("td", {}, `${fmt(p.mean_max_wait)} min`),
      el("td", {}, p.mean_ratio === null ? "–" : `${p.mean_ratio.toFixed(3)}×`),
      el("td", {}, p.median_ratio === null ? "–" : `${p.median_ratio.toFixed(3)}×`),
      el("td", {}, p.worst_ratio === null ? "–" : `${p.worst_ratio.toFixed(2)}×`),
      el("td", {}, `${fmt(p.pct_matching_reference, 1)}%`),
      el("td", {}, p.zero_reference_cases ? `${p.zero_found} of ${p.zero_reference_cases}` : "none possible"),
      el("td", {}, `${fmt(p.mean_ms, 2)} ms`)))));

  const names = s.per_heuristic.map((p) => p.name);
  const matrix = el("table", { class: "data matrix" },
    el("thead", {}, el("tr", {}, el("th", {}, "Days where the row beats the column"), ...names.map((nm, j) => el("th", {}, nameCell(nm, slots[j]))))),
    el("tbody", {}, s.wins.map((row, i) => el("tr", {},
      el("td", {}, nameCell(names[i], slots[i])),
      ...row.map((w, j) => el("td", { class: i !== j && w > s.wins[j][i] ? "best" : null }, i === j ? "–" : String(w)))))));

  const worst = el("div", { class: "worst-days" }, s.per_heuristic.map((p, h) => {
    let bestIdx = -1, bestRatio = -1;
    res.rows.forEach((r, k) => {
      const ratio = r.opt ? r.heuristics[h] / r.opt : (r.heuristics[h] > 0 ? Infinity : 1);
      if (ratio > bestRatio) { bestRatio = ratio; bestIdx = k; }
    });
    const row = res.rows[bestIdx];
    return el("div", { class: "worst-day" },
      nameCell(p.name, slots[h]),
      el("span", {}, row ? `longest wait ${row.heuristics[h]} min against ${row.opt} min` : ""),
      row ? el("button", { type: "button", class: "text-btn", onclick: () => openInReplay(row.instance) }, "Open this day in the replay") : null);
  }));

  out.replaceChildren(
    facts,
    section("Summary", el("div", { class: "table-wrap card" }, table),
      el("p", { class: "note" }, `Ratio is the heuristic's longest wait divided by the ${refName}'s, over days where the ${refName} is above zero.`)),
    figure(`Ratio on every day, sorted from worst to best`, "chart-batch-profile",
      "A flat line at 1 means the heuristic always matched. The further a line sits above 1, the more often it fell short."),
    section("Head to head", el("div", { class: "table-wrap card" }, matrix)),
    section("Worst day for each heuristic", worst),
    el("div", { class: "link-row" }, el("button", { type: "button", class: "text-btn", onclick: () => exportBatch(res) }, "Download every day (CSV)")),
  );

  const maxLen = Math.max(0, ...s.per_heuristic.map((p) => p.ratios.length));
  chart("chart-batch-profile", {
    type: "line",
    data: {
      labels: Array.from({ length: maxLen }, (_, i) => i + 1),
      datasets: s.per_heuristic.map((p, h) => lineSet(p.name, seriesColor(slots[h]), [...p.ratios].sort((a, b) => b - a),
        { pointRadius: maxLen > 60 ? 0 : 3, stepped: false })),
    },
    options: {
      interaction: { mode: "index", intersect: false },
      plugins: { tooltip: { callbacks: { title: (c) => `Rank ${c[0].label}`, label: (c) => ` ${c.dataset.label}: ${c.parsed.y.toFixed(3)}×` } } },
      scales: {
        x: { title: { display: true, text: "Days, ranked by ratio" }, ticks: { autoSkip: true, maxTicksLimit: 12 } },
        y: { title: { display: true, text: `Ratio to ${refName}` }, suggestedMin: 1 },
      },
    },
  });
}

function fact(value, label) {
  return el("div", { class: "fact" }, el("span", { class: "fact-value" }, value), el("span", { class: "fact-label" }, label));
}

function openInReplay(instance) {
  emit("load-instance", instance);
}

function exportBatch(res) {
  const rows = [["day", "reference", "proven", ...res.names, "trips_json"]];
  res.rows.forEach((r, k) => rows.push([k + 1, r.opt, r.proven ?? "", ...r.heuristics, JSON.stringify(r.instance.trips)]));
  download("robotaxi-batch.csv", toCSV(rows), "text/csv");
}

// ------------------------------------------------------------------ sweep

function renderSweep(res, slots) {
  const v = res.config.variable;
  const label = VAR_LABEL[v] || v;
  const refName = res.reference === "optimal" ? "optimum" : "best heuristic";
  const pts = res.points;
  const names = res.names;
  const hasSolver = pts.some((p) => p.solver_mean_seconds !== null);
  const out = document.getElementById("exp-results");

  const table = el("table", { class: "data" },
    el("thead", {}, el("tr", {}, el("th", {}, label), el("th", {}, `Mean ${refName}`),
      ...names.map((nm, h) => el("th", {}, nameCell(`${nm} mean ratio`, slots[h]))),
      hasSolver ? el("th", {}, "Proven") : null, hasSolver ? el("th", {}, "Mean solver time") : null)),
    el("tbody", {}, pts.map((p) => el("tr", {},
      el("td", {}, String(p.value)), el("td", {}, `${fmt(p.mean_reference)} min`),
      ...p.per_heuristic.map((q) => el("td", {}, q.mean_ratio === null ? "–" : `${q.mean_ratio.toFixed(3)}×`)),
      hasSolver ? el("td", {}, `${p.proven} of ${p.instances}`) : null,
      hasSolver ? el("td", {}, fmtSeconds(p.solver_mean_seconds)) : null))));

  out.replaceChildren(
    el("div", { class: "chart-grid" },
      figure(`Mean ratio to the ${refName} as ${label.toLowerCase()} changes`, "chart-sweep-ratio"),
      figure(`Mean longest wait as ${label.toLowerCase()} changes`, "chart-sweep-wait")),
    hasSolver ? figure("Time to solve exactly", "chart-sweep-solver",
      "Log scale. Exhaustive search handles up to 7 trips; beyond that CP-SAT runs until it proves the optimum or hits the time limit, so a flat top means the limit is binding.") : null,
    section("Results", el("div", { class: "table-wrap card" }, table)),
    el("div", { class: "link-row" }, el("button", { type: "button", class: "text-btn", onclick: () => exportSweep(res) }, "Download sweep (CSV)")),
  );

  const labels = pts.map((p) => String(p.value));
  const xTitle = { title: { display: true, text: label } };
  chart("chart-sweep-ratio", {
    type: "line",
    data: { labels, datasets: names.map((nm, h) => lineSet(nm, seriesColor(slots[h]), pts.map((p) => p.per_heuristic[h].mean_ratio))) },
    options: { scales: { x: xTitle, y: { title: { display: true, text: "Mean ratio" }, suggestedMin: 1 } } },
  });
  chart("chart-sweep-wait", {
    type: "line",
    data: {
      labels,
      datasets: [
        ...names.map((nm, h) => lineSet(nm, seriesColor(slots[h]), pts.map((p) => p.per_heuristic[h].mean_max_wait))),
        lineSet(res.reference === "optimal" ? "Optimum" : "Best heuristic", seriesColor("opt"), pts.map((p) => p.mean_reference), { borderDash: [5, 4] }),
      ],
    },
    options: { scales: { x: xTitle, y: { beginAtZero: true, title: { display: true, text: "Minutes" } } } },
  });
  if (hasSolver) {
    chart("chart-sweep-solver", {
      type: "line",
      data: {
        labels,
        datasets: [
          lineSet("Mean", seriesColor("opt"), pts.map((p) => Math.max(p.solver_mean_seconds ?? 0, 1e-4))),
          lineSet("Slowest", seriesColor(7), pts.map((p) => Math.max(p.solver_max_seconds ?? 0, 1e-4)), { borderDash: [5, 4] }),
        ],
      },
      options: {
        plugins: { tooltip: { callbacks: { label: (c) => ` ${c.dataset.label}: ${fmtSeconds(c.parsed.y)}` } } },
        scales: { x: xTitle, y: { type: "logarithmic", title: { display: true, text: "Seconds" },
          ticks: { callback: (val) => (Number.isInteger(Math.round(Math.log10(val) * 1e6) / 1e6) ? tickSeconds(val) : "") } } },
      },
    });
  }
}

function exportSweep(res) {
  const rows = [[res.config.variable, "mean_reference", "proven", "instances", "solver_mean_s", "solver_max_s",
    ...res.names.flatMap((n) => [`${n} mean_ratio`, `${n} worst_ratio`, `${n} mean_max_wait`])]];
  for (const p of res.points) {
    rows.push([p.value, p.mean_reference, p.proven, p.instances, p.solver_mean_seconds ?? "", p.solver_max_seconds ?? "",
      ...p.per_heuristic.flatMap((q) => [q.mean_ratio ?? "", q.worst_ratio ?? "", q.mean_max_wait])]);
  }
  download("robotaxi-sweep.csv", toCSV(rows), "text/csv");
}

function tickSeconds(v) {
  if (v >= 1) return `${v} s`;
  const ms = v * 1000;
  return ms >= 1 ? `${Math.round(ms)} ms` : `${Math.round(ms * 1000)} µs`;
}
