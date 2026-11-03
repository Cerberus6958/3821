// Compare view: headline facts, per-algorithm table and per-trip wait chart.
import { chart, chartPNG, lineSet } from "./charts.js";
import { on, resultSeries, state } from "./state.js";
import { download, el, fmt, fmtSeconds, seriesColor, toCSV, toast } from "./util.js";

export function initCompare() {
  on("result-changed", render);
  on("theme-changed", () => { if (isVisible()) render(); });
  on("tab-shown", (t) => { if (t === "compare") render(); });
  document.getElementById("compare-csv").addEventListener("click", exportCSV);
  document.getElementById("compare-png").addEventListener("click", () => {
    const png = chartPNG("chart-waits");
    if (!png) return toast("Nothing to download yet.", "error");
    const a = el("a", { href: png, download: "trip-waits.png" });
    document.body.append(a); a.click(); a.remove();
  });
}

function isVisible() {
  return !document.getElementById("view-compare").hidden;
}

export function ratioText(ratio, opt, value) {
  if (!opt) return "–";
  if (ratio === null || ratio === undefined) return value > 0 && opt.value === 0 ? "∞" : "–";
  return `${opt.proven ? "" : "≥ "}${ratio.toFixed(2)}×`;
}

function render() {
  const r = state.result;
  document.getElementById("compare-empty").hidden = !!r;
  document.getElementById("compare").hidden = !r;
  if (!r || !isVisible()) return;
  renderFacts(r);
  renderTable(r);
  renderChart(r);
}

function fact(value, label) {
  return el("div", { class: "fact" }, el("span", { class: "fact-value" }, value), el("span", { class: "fact-label" }, label));
}

function renderFacts(r) {
  const opt = r.optimal;
  const best = r.heuristics.reduce((a, b) => (b.metrics.max_wait < a.metrics.max_wait ? b : a), r.heuristics[0]);
  const items = [];
  if (opt) {
    items.push(fact(`${fmt(opt.value)} min`, opt.proven
      ? `Optimal longest wait, proven by ${opt.method === "enumeration" ? "exhaustive search" : "CP-SAT"} in ${fmtSeconds(opt.seconds)}`
      : `Best longest wait CP-SAT found in ${fmtSeconds(opt.seconds)}. The optimum is at least ${fmt(opt.bound)} min`));
  } else {
    items.push(fact("Off", "The optimum wasn't computed for this run, so there are no ratios"));
  }
  items.push(fact(`${fmt(best.metrics.max_wait)} min`, `Best heuristic longest wait, from ${best.name}`));
  items.push(fact(`${fmt(r.lower_bound)} min`, "Simple lower bound: the worst trip if every car drove straight from the depot to it"));
  const z = r.zero_wait;
  if (z.min_fleet === null) {
    items.push(fact("None", "Fleet size that lets nobody wait. Some trip can't be reached from the depot by its request time, so any fleet makes someone wait"));
  } else {
    items.push(fact(`${z.min_fleet} car${z.min_fleet === 1 ? "" : "s"}`,
      `Smallest fleet that lets nobody wait. This day has ${r.instance.cars}, so zero wait is ${z.feasible_with_fleet ? "achievable" : "out of reach"}`));
  }
  document.getElementById("compare-facts").replaceChildren(...items);
}

function renderTable(r) {
  const series = resultSeries();
  const opt = r.optimal;
  const cols = [
    ["Algorithm", null],
    ["Longest wait", (s) => s.sched.metrics.max_wait],
    ["Ratio to optimum", null],
    ["Mean wait", (s) => s.sched.metrics.mean_wait],
    ["Trips with no wait", (s) => s.sched.metrics.zero_wait_trips],
    ["Empty driving", (s) => s.sched.metrics.empty_distance],
    ["Last drop-off", (s) => s.sched.metrics.last_dropoff],
    ["Cars used", (s) => s.sched.metrics.cars_used],
    ["Run time", null],
  ];
  const minWait = Math.min(...series.map((s) => s.sched.metrics.max_wait));
  const head = el("thead", {}, el("tr", {}, cols.map(([c]) => el("th", { scope: "col" }, c))));
  const body = el("tbody", {}, series.map((s) => {
    const m = s.sched.metrics;
    return el("tr", {},
      el("td", {}, el("span", { class: "name-cell" },
        el("span", { class: "swatch", style: { background: seriesColor(s.slot) } }), s.name)),
      el("td", { class: m.max_wait === minWait ? "best" : null }, `${fmt(m.max_wait)} min`),
      el("td", {}, s.isOpt ? (opt.proven ? "1.00×" : "reference") : ratioText(s.ratio, opt, m.max_wait)),
      el("td", {}, `${fmt(m.mean_wait)} min`),
      el("td", {}, `${m.zero_wait_trips} of ${r.instance.trips.length}`),
      el("td", {}, `${fmt(m.empty_distance)} blocks`),
      el("td", {}, `minute ${fmt(m.last_dropoff)}`),
      el("td", {}, `${m.cars_used} of ${r.instance.cars}`),
      el("td", {}, s.isOpt ? fmtSeconds(opt.seconds) : `${fmt(s.ms)} ms`));
  }));
  const caption = opt && !opt.proven
    ? el("caption", { class: "table-note" }, "The solver hit its time limit, so ratios are against the best schedule found. True ratios are at least this large.")
    : null;
  document.getElementById("compare-table").replaceChildren(...[caption, head, body].filter(Boolean));
}

function renderChart(r) {
  const series = resultSeries();
  const order = r.instance.trips.map((t, i) => ({ t: t.t, i })).sort((a, b) => a.t - b.t || a.i - b.i);
  const labels = order.map(({ i, t }) => [`Trip ${i}`, `min ${t}`]);
  const many = order.length > 18;
  const datasets = series.map((s) => {
    const data = order.map(({ i }) => s.sched.trips[String(i)].wait);
    const color = seriesColor(s.slot);
    if (many) return lineSet(s.name, color, data, { showLine: false, pointRadius: 4 });
    return { label: s.name, data, backgroundColor: color, borderRadius: { topLeft: 4, topRight: 4 }, borderSkipped: "bottom",
      borderColor: getComputedStyle(document.documentElement).getPropertyValue("--surface").trim(), borderWidth: { left: 1, right: 1 } };
  });
  chart("chart-waits", {
    type: many ? "line" : "bar",
    data: { labels: many ? order.map(({ i }) => `Trip ${i}`) : labels, datasets },
    options: {
      interaction: { mode: "index", intersect: false },
      plugins: { tooltip: { callbacks: { label: (c) => ` ${c.dataset.label}: ${c.parsed.y} min` } } },
      scales: {
        y: { beginAtZero: true, title: { display: true, text: "Wait (min)" } },
        x: { ticks: { autoSkip: many, maxRotation: 0 } },
      },
      datasets: { bar: { categoryPercentage: 0.8, barPercentage: 0.92 } },
    },
  });
}

function exportCSV() {
  const r = state.result;
  if (!r) return toast("Dispatch a day first.", "error");
  const series = resultSeries();
  const rows = [["trip", "requested", "pickup_x", "pickup_y", "dropoff_x", "dropoff_y",
    ...series.flatMap((s) => [`${s.name} car`, `${s.name} pickup`, `${s.name} wait`])]];
  r.instance.trips.forEach((t, i) => {
    rows.push([i, t.t, ...t.s, ...t.w, ...series.flatMap((s) => {
      const o = s.sched.trips[String(i)];
      return [o.car, o.pickup, o.wait];
    })]);
  });
  rows.push([]);
  rows.push(["algorithm", "longest_wait", "ratio", "mean_wait", "empty_distance", "last_dropoff"]);
  for (const s of series) {
    const m = s.sched.metrics;
    rows.push([s.name, m.max_wait, s.ratio ?? "", m.mean_wait, m.empty_distance, m.last_dropoff]);
  }
  download(`robotaxi-compare-${r.instance.seed ?? "custom"}.csv`, toCSV(rows), "text/csv");
}
