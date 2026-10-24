// Small DOM, formatting and download helpers.

export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === undefined || v === null || v === false) continue;
    if (k === "class") node.className = v;
    else if (k === "style" && typeof v === "object") Object.assign(node.style, v);
    else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v);
    else if (k === "html") node.innerHTML = v;
    else node.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) {
    if (c === undefined || c === null || c === false) continue;
    node.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return node;
}

const SVG_NS = "http://www.w3.org/2000/svg";
export function svg(tag, attrs = {}, ...children) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === undefined || v === null || v === false) continue;
    if (k === "text") node.textContent = v;
    else node.setAttribute(k, v);
  }
  for (const c of children.flat()) if (c) node.append(c);
  return node;
}

export function fmt(v, digits = 2) {
  if (v === null || v === undefined || Number.isNaN(v)) return "–";
  if (typeof v !== "number") return String(v);
  if (!Number.isFinite(v)) return "∞";
  if (Number.isInteger(v)) return String(v);
  return v.toFixed(digits);
}

export function fmtSeconds(s) {
  if (s === null || s === undefined) return "–";
  if (s < 0.01) return "<0.01 s";
  if (s < 10) return `${s.toFixed(2)} s`;
  return `${s.toFixed(1)} s`;
}

export function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

export function seriesColor(slot) {
  return slot === "opt" ? cssVar("--opt") : cssVar(`--s${slot}`);
}

export function download(filename, text, type = "text/plain") {
  const blob = new Blob([text], { type });
  const url = URL.createObjectURL(blob);
  const a = el("a", { href: url, download: filename });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function toCSV(rows) {
  const esc = (v) => {
    const s = v === null || v === undefined ? "" : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  return rows.map((r) => r.map(esc).join(",")).join("\n");
}

let toastTimer;
export function toast(message, kind = "info") {
  const t = document.getElementById("toast");
  t.textContent = message;
  t.className = `toast ${kind === "error" ? "error" : ""}`;
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.hidden = true), kind === "error" ? 7000 : 3500);
}

export const store = {
  get(key, fallback) {
    try {
      const raw = localStorage.getItem(`robotaxi-lab:${key}`);
      return raw ? JSON.parse(raw) : fallback;
    } catch {
      return fallback;
    }
  },
  set(key, value) {
    try {
      localStorage.setItem(`robotaxi-lab:${key}`, JSON.stringify(value));
    } catch {
      /* storage unavailable: settings simply are not remembered */
    }
  },
};

export function formData(form) {
  const out = {};
  for (const [k, v] of new FormData(form).entries()) out[k] = v;
  return out;
}

export function intOr(v, fallback) {
  const n = parseInt(v, 10);
  return Number.isFinite(n) ? n : fallback;
}
