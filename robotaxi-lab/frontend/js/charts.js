// Chart.js helpers that read colours from the CSS theme tokens.
import { cssVar } from "./util.js";

const charts = new Map();

function theme() {
  const Chart = window.Chart;
  Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
  Chart.defaults.font.size = 12;
  Chart.defaults.color = cssVar("--ink-2");
  Chart.defaults.borderColor = cssVar("--hair");
  Chart.defaults.animation = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? false : { duration: 250 };
}

export function chart(canvasId, config) {
  if (!window.Chart) return null;
  theme();
  const old = charts.get(canvasId);
  if (old) old.destroy();
  const canvas = document.getElementById(canvasId);
  if (!canvas) return null;
  const grid = { color: cssVar("--hair"), drawTicks: false };
  const base = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: "nearest", intersect: false },
    plugins: {
      legend: {
        display: (config.data.datasets || []).length > 1,
        position: "top",
        align: "start",
        labels: { boxWidth: 10, boxHeight: 10, usePointStyle: true, pointStyle: "rectRounded", color: cssVar("--ink-2") },
      },
      tooltip: {
        backgroundColor: cssVar("--ink"),
        titleColor: cssVar("--surface"),
        bodyColor: cssVar("--surface"),
        padding: 8,
        cornerRadius: 6,
        boxPadding: 4,
      },
    },
    scales: {
      x: { grid: { ...grid, display: false }, border: { color: cssVar("--hair-strong") }, ticks: { color: cssVar("--muted"), padding: 6 } },
      y: { grid, border: { display: false }, ticks: { color: cssVar("--muted"), padding: 6 } },
    },
  };
  const merged = deepMerge(base, config.options || {});
  const c = new window.Chart(canvas, { ...config, options: merged });
  charts.set(canvasId, c);
  return c;
}

export function chartPNG(canvasId) {
  const c = charts.get(canvasId);
  return c ? c.toBase64Image("image/png", 1) : null;
}

function deepMerge(a, b) {
  const out = { ...a };
  for (const [k, v] of Object.entries(b)) {
    out[k] = v && typeof v === "object" && !Array.isArray(v) && a[k] && typeof a[k] === "object" ? deepMerge(a[k], v) : v;
  }
  return out;
}

// Line-chart dataset styled to the spec: 2px line, 8px markers with a surface ring.
export function lineSet(label, color, data, extra = {}) {
  return {
    label, data, borderColor: color, backgroundColor: color, borderWidth: 2,
    pointRadius: 4, pointHoverRadius: 6, pointBorderColor: cssVar("--surface"), pointBorderWidth: 2,
    tension: 0, ...extra,
  };
}
