// Sidebar: list, edit and add heuristics.
import { api } from "./api.js";
import { emit, nextSlot, saveHeuristics, state, MAX_HEURISTICS } from "./state.js";
import { el, seriesColor, store, toast } from "./util.js";

let openUid = null;

function uid() {
  return Math.random().toString(36).slice(2, 10);
}

export function initHeuristics() {
  const saved = store.get("heuristics", null);
  if (Array.isArray(saved) && saved.length) {
    state.heuristics = saved.filter((h) => h && h.slot && h.car_formula !== undefined).slice(0, MAX_HEURISTICS);
  } else {
    state.heuristics = [];
    for (const p of state.meta.presets.slice(0, 3)) addFromPreset(p, false);
  }
  renderReference();
  buildAddMenu();
  render();
}

export function addFromPreset(p, announce = true) {
  const slot = nextSlot();
  if (!slot) {
    toast(`You can compare up to ${MAX_HEURISTICS} heuristics. Remove one to add another.`, "error");
    return null;
  }
  const h = {
    uid: uid(), slot, name: p.name, car_formula: p.car_formula, trip_formula: p.trip_formula,
    description: p.description || "", enabled: true,
  };
  state.heuristics.push(h);
  saveHeuristics();
  if (announce) {
    openUid = h.uid;
    render();
    emit("heuristics-changed");
  }
  return h;
}

function buildAddMenu() {
  const btn = document.getElementById("add-heuristic");
  const menu = document.getElementById("add-menu");
  const close = () => { menu.hidden = true; btn.setAttribute("aria-expanded", "false"); };
  menu.replaceChildren(
    ...state.meta.presets.map((p) =>
      el("button", { type: "button", onclick: () => { close(); addFromPreset(p); } },
        p.name, el("span", { class: "menu-desc" }, p.description))),
    el("button", {
      type: "button",
      onclick: () => {
        close();
        addFromPreset({ name: "My heuristic", car_formula: "wait, empty", trip_formula: "t", description: "" });
      },
    }, "Blank formula", el("span", { class: "menu-desc" }, "Start from FIFO's formulas and edit them.")),
  );
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
    el("span", { class: "h-formulas", title: `car: ${h.car_formula} | trip: ${h.trip_formula}` },
      `car: ${h.car_formula};  trip: ${h.trip_formula}`),
  );
  const item = el("li", { class: "h-item" }, row);
  if (open) item.append(editorView(h));
  return item;
}

function editorView(h) {
  const name = el("input", { type: "text", value: h.name, maxlength: 40 });
  const car = el("textarea", { rows: 1, spellcheck: "false" }, h.car_formula);
  const trip = el("textarea", { rows: 1, spellcheck: "false" }, h.trip_formula);
  const error = el("p", { class: "h-error", role: "alert" });
  const save = async () => {
    const candidate = { id: h.uid, name: name.value.trim() || "Heuristic", car_formula: car.value.trim(), trip_formula: trip.value.trim() };
    try {
      const res = await api.validate(candidate);
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
