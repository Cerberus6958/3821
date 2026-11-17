// Sidebar: list, edit and add heuristics.
import { api } from "./api.js";
import { emit, isHub, modeKey, nextSlot, saveHeuristics, state, MAX_HEURISTICS } from "./state.js";
import { el, seriesColor, store, toast } from "./util.js";

let openUid = null;

function uid() {
  return Math.random().toString(36).slice(2, 10);
}

// Heuristics loaded the first time each problem is opened.
const STARTERS = {
  base: ["fifo", "maxmin", "epd"],
  simplified: ["fifo", "epd", "adjmaxmin", "maxmin_orig"],
  online: ["fifo", "epd", "adjmaxmin"],
};

const presets = () => state.meta.modes[state.mode].presets;

export function initHeuristics() {
  bindAddMenu();
  loadHeuristics();
}

// Load the saved list for the current problem (each problem keeps its own list).
export function loadHeuristics() {
  const saved = store.get(modeKey("heuristics"), null);
  const valid = (h) => h && h.slot && (isHub() ? typeof h.key_formula === "string" : h.car_formula !== undefined);
  openUid = null;
  if (Array.isArray(saved) && saved.length && saved.every(valid)) {
    state.heuristics = saved.slice(0, MAX_HEURISTICS);
  } else {
    state.heuristics = [];
    for (const id of STARTERS[state.mode]) {
      const p = presets().find((x) => x.id === id);
      if (p) addFromPreset(p, false);
    }
  }
  renderReference();
  buildAddMenu();
  render();
  emit("heuristics-changed");
}

export function addFromPreset(p, announce = true) {
  const slot = nextSlot();
  if (!slot) {
    toast(`You can compare up to ${MAX_HEURISTICS} heuristics. Remove one to add another.`, "error");
    return null;
  }
  const h = isHub()
    ? { uid: uid(), slot, name: p.name, key_formula: p.key_formula, lookahead: !!p.lookahead,
        description: p.description || "", enabled: true }
    : { uid: uid(), slot, name: p.name, car_formula: p.car_formula, trip_formula: p.trip_formula,
        description: p.description || "", enabled: true };
  state.heuristics.push(h);
  saveHeuristics();
  if (announce) {
    openUid = h.uid;
    render();
    emit("heuristics-changed");
  }
  return h;
}

function closeMenu() {
  document.getElementById("add-menu").hidden = true;
  document.getElementById("add-heuristic").setAttribute("aria-expanded", "false");
}

function buildAddMenu() {
  const menu = document.getElementById("add-menu");
  const blank = isHub()
    ? { name: "My rule", key_formula: "t", lookahead: false, description: "" }
    : { name: "My heuristic", car_formula: "wait, empty", trip_formula: "t", description: "" };
  menu.replaceChildren(
    ...presets().map((p) =>
      el("button", { type: "button", onclick: () => { closeMenu(); addFromPreset(p); } },
        p.name, el("span", { class: "menu-desc" }, p.description))),
    el("button", { type: "button", onclick: () => { closeMenu(); addFromPreset(blank); } },
      "Blank formula", el("span", { class: "menu-desc" }, "Start from FIFO's formula and edit it.")),
  );
}

function bindAddMenu() {
  const btn = document.getElementById("add-heuristic");
  const menu = document.getElementById("add-menu");
  const close = closeMenu;
  btn.addEventListener("click", (e) => {
    e.stopPropagation();
    menu.hidden = !menu.hidden;
    btn.setAttribute("aria-expanded", String(!menu.hidden));
    if (!menu.hidden) menu.querySelector("button")?.focus();
  });
  document.addEventListener("click", (e) => { if (!menu.contains(e.target)) close(); });
  menu.addEventListener("keydown", (e) => { if (e.key === "Escape") { close(); btn.focus(); } });
}

function renderReference() {
  const m = state.meta;
  const list = (vars) => el("dl", {}, ...Object.entries(vars).flatMap(([k, v]) => [el("dt", {}, k), el("dd", {}, v)]));
  if (isHub()) {
    document.getElementById("formula-reference").replaceChildren(
      el("p", {}, "Whenever a car is free at the depot, it starts the waiting trip with the smallest key. Ties go to the earlier request, then the lower trip number."),
      el("p", {}, "The key ", el("code", {}, "t + λ·a"), " gives the family from the report: λ = 0 is FIFO, λ = 1 is EPD and λ = −1 is adjusted Max-min, each within (5 + |λ| − 1/m) of optimal."),
      el("p", {}, "Separate expressions with commas to break ties, e.g. ", el("code", {}, "a, t"), ". To prefer larger values, minimise the negative, e.g. ", el("code", {}, "-completion"), "."),
      state.mode === "simplified"
        ? el("p", {}, "Tick ", el("em", {}, "Look ahead"), " to let a free car commit to a trip that hasn't been requested yet and wait for it, as the original Max-min does. That needs the future, so it isn't available online.")
        : null,
      el("h3", {}, "Key variables"), list(m.modes[state.mode].key_variables),
      el("h3", {}, "Functions"), el("p", {}, m.functions.join(", ") + ", plus a if condition else b."),
    );
    return;
  }
  document.getElementById("formula-reference").replaceChildren(
    el("p", {}, "Each step, every unassigned trip picks the car with the smallest car score, then the trip with the smallest trip score is added to the end of that car's route."),
    el("p", {}, "Separate expressions with commas to break ties, e.g. ", el("code", {}, "wait, empty"), ". To prefer larger values, minimise the negative, e.g. ", el("code", {}, "-best_wait"), "."),
    el("h3", {}, "Car formula variables"), list(m.car_variables),
    el("h3", {}, "Trip formula variables"), list(m.trip_variables),
    el("h3", {}, "Functions"), el("p", {}, m.functions.join(", ") + ", plus a if condition else b."),
  );
}

export function render() {
  const ul = document.getElementById("heuristic-list");
  ul.replaceChildren(...state.heuristics.map(itemView));
}

function itemView(h) {
  const open = openUid === h.uid;
  const checkbox = el("input", {
    type: "checkbox", checked: h.enabled, "aria-label": `Include ${h.name}`,
    onchange: (e) => { h.enabled = e.target.checked; saveHeuristics(); emit("heuristics-changed"); },
  });
  const row = el("div", { class: "h-row" },
    checkbox,
    el("span", { class: "swatch", style: { background: seriesColor(h.slot) }, "aria-hidden": "true" }),
    el("span", { class: "h-name", title: h.name }, h.name),
    el("span", { class: "h-actions" },
      el("button", { type: "button", class: "text-btn", "aria-expanded": String(open),
        onclick: () => { openUid = open ? null : h.uid; render(); } }, open ? "Close" : "Edit")),
    isHub()
      ? el("span", { class: "h-formulas", title: `key: ${h.key_formula}` },
        `key: ${h.key_formula}${h.lookahead && state.mode === "simplified" ? "  (looks ahead)" : ""}`)
      : el("span", { class: "h-formulas", title: `car: ${h.car_formula} | trip: ${h.trip_formula}` },
        `car: ${h.car_formula};  trip: ${h.trip_formula}`),
  );
  const item = el("li", { class: "h-item" }, row);
  if (open) item.append(editorView(h));
  return item;
}

function hubEditorView(h) {
  const name = el("input", { type: "text", value: h.name, maxlength: 40 });
  const key = el("textarea", { rows: 1, spellcheck: "false" }, h.key_formula);
  const look = el("input", { type: "checkbox", checked: !!h.lookahead });
  const error = el("p", { class: "h-error", role: "alert" });
  const save = async () => {
    const candidate = { id: h.uid, name: name.value.trim() || "Rule", key_formula: key.value.trim(),
      lookahead: state.mode === "simplified" && look.checked };
    try {
      const res = await api.validate({ ...candidate, mode: state.mode });
      if (!res.ok) { error.textContent = res.error; return; }
    } catch (e) {
      error.textContent = e.message;
      return;
    }
    Object.assign(h, { name: candidate.name, key_formula: candidate.key_formula, lookahead: candidate.lookahead });
    saveHeuristics();
    openUid = null;
    render();
    emit("heuristics-changed");
    toast(`Saved ${h.name}.`);
  };
  const remove = () => {
    state.heuristics = state.heuristics.filter((x) => x !== h);
    saveHeuristics();
    openUid = null;
    render();
    emit("heuristics-changed");
  };
  return el("div", { class: "h-editor" },
    h.description ? el("p", { class: "h-desc" }, h.description) : null,
    el("label", {}, "Name", name),
    el("label", {}, "When a car is free, start the waiting trip that minimises", key),
    state.mode === "simplified"
      ? el("label", { class: "check small" }, look, "Look ahead at trips not requested yet (offline only)")
      : null,
    error,
    el("div", { class: "editor-actions" },
      el("button", { type: "button", class: "btn primary", onclick: save }, "Save rule"),
      el("button", { type: "button", class: "btn", onclick: remove }, "Remove")),
  );
}

function editorView(h) {
  if (isHub()) return hubEditorView(h);
  const name = el("input", { type: "text", value: h.name, maxlength: 40 });
  const car = el("textarea", { rows: 1, spellcheck: "false" }, h.car_formula);
  const trip = el("textarea", { rows: 1, spellcheck: "false" }, h.trip_formula);
  const error = el("p", { class: "h-error", role: "alert" });
  const save = async () => {
    const candidate = { id: h.uid, name: name.value.trim() || "Heuristic", car_formula: car.value.trim(), trip_formula: trip.value.trim() };
    try {
      const res = await api.validate({ ...candidate, mode: "base" });
      if (!res.ok) { error.textContent = res.error; return; }
    } catch (e) {
      error.textContent = e.message;
      return;
    }
    Object.assign(h, { name: candidate.name, car_formula: candidate.car_formula, trip_formula: candidate.trip_formula });
    saveHeuristics();
    openUid = null;
    render();
    emit("heuristics-changed");
    toast(`Saved ${h.name}.`);
  };
  const remove = () => {
    state.heuristics = state.heuristics.filter((x) => x !== h);
    saveHeuristics();
    openUid = null;
    render();
    emit("heuristics-changed");
  };
  return el("div", { class: "h-editor" },
    h.description ? el("p", { class: "h-desc" }, h.description) : null,
    el("label", {}, "Name", name),
    el("label", {}, "Choose the car that minimises", car),
    el("label", {}, "Then assign the trip that minimises", trip),
    error,
    el("div", { class: "editor-actions" },
      el("button", { type: "button", class: "btn primary", onclick: save }, "Save heuristic"),
      el("button", { type: "button", class: "btn", onclick: remove }, "Remove")),
  );
}
