// Sidebar: generate, import and export the current day.
import { api } from "./api.js";
import { emit, modeKey, state } from "./state.js";
import { download, el, formData, intOr, store, toast } from "./util.js";

// Starting values for the Day form in each problem.
const DAY_DEFAULTS = {
  base: { n: 10, cars: 3, width: 10, horizon: 30, load: 85, seed: "" },
  simplified: { n: 8, cars: 2, width: 10, horizon: 30, load: 85, seed: "" },
  online: { n: 120, cars: 6, width: 20, horizon: 30, load: 85, seed: "" },
};

function restoreForm() {
  const form = document.getElementById("instance-form");
  const values = { ...DAY_DEFAULTS[state.mode], ...(store.get(modeKey("instance-form"), null) || {}) };
  for (const [k, v] of Object.entries(values)) if (form.elements[k]) form.elements[k].value = v;
}

// Called when the problem changes: restore that problem's form and last day.
export function loadInstanceForMode() {
  restoreForm();
  const last = store.get(modeKey("instance"), null);
  state.instance = null;
  if (last && Array.isArray(last.trips)) setInstance(last, false);
  else { renderSummary(); emit("instance-changed"); }
}

export function initInstance() {
  const form = document.getElementById("instance-form");
  restoreForm();

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = formData(form);
    store.set(modeKey("instance-form"), f);
    const mode = state.mode;
    try {
      const inst = await api.randomDay({
        mode, n: intOr(f.n, 10), cars: intOr(f.cars, 3), width: intOr(f.width, 10),
        horizon: intOr(f.horizon, 30), load: Number(f.load) || 85, seed: f.seed === "" ? null : intOr(f.seed, null),
      });
      if (mode !== state.mode) return;
      setInstance(inst);
      toast(`Generated a day with ${inst.trips.length} trips (seed ${inst.seed}).`);
    } catch (err) {
      toast(err.message, "error");
    }
  });

  document.getElementById("export-json").addEventListener("click", () => {
    if (!state.instance) return toast("Generate or import a day first.", "error");
    download(`robotaxi-day-${state.instance.seed ?? "custom"}.json`, JSON.stringify(state.instance, null, 2), "application/json");
  });

  const file = document.getElementById("import-file");
  document.getElementById("import-json").addEventListener("click", () => file.click());
  file.addEventListener("change", async () => {
    const f = file.files[0];
    if (!f) return;
    try {
      const inst = JSON.parse(await f.text());
      if (!Array.isArray(inst.trips)) throw new Error("The file needs a \"trips\" list.");
      setInstance(inst);
      toast(`Imported ${inst.trips.length} trips.`);
    } catch (err) {
      toast(`Couldn't import that file: ${err.message}`, "error");
    }
    file.value = "";
  });

  const tripsBtn = document.getElementById("show-trips");
  tripsBtn.addEventListener("click", () => {
    const wrap = document.getElementById("trip-table-wrap");
    wrap.hidden = !wrap.hidden;
    tripsBtn.textContent = wrap.hidden ? "Show trips" : "Hide trips";
  });

  const last = store.get(modeKey("instance"), null);
  if (last && Array.isArray(last.trips)) setInstance(last, false);
}

export function setInstance(inst, clearResult = true) {
  state.instance = inst;
  store.set(modeKey("instance"), inst);
  if (clearResult) state.result = null;
  renderSummary();
  emit("instance-changed");
}

function renderSummary() {
  const inst = state.instance;
  const p = document.getElementById("instance-summary");
  if (!inst) { p.textContent = "No day loaded yet."; return; }
  const ts = inst.trips.map((t) => t.t);
  const last = ts.length ? Math.max(...ts) : 0;
  const base = `${inst.trips.length} trips and ${inst.cars} car${inst.cars === 1 ? "" : "s"} on a ${inst.width} × ${inst.height} grid, requests from minute 0 to ${last}. Depot at (${inst.depot.join(", ")}).`;
  const online = inst.load
    ? ` Poisson arrivals at ${Math.round(inst.load * 100)}% load${inst.hotspots && inst.hotspots.length ? `, ${inst.hotspots.length} demand hotspot${inst.hotspots.length === 1 ? "" : "s"}` : ""}.`
    : "";
  p.textContent = base + online;
  const rows = inst.trips
    .map((t, i) => ({ ...t, i }))
    .sort((a, b) => a.t - b.t || a.i - b.i)
    .map((t) => el("tr", {}, el("td", {}, `Trip ${t.i}`), el("td", {}, t.t), el("td", {}, `(${t.s.join(", ")})`), el("td", {}, `(${t.w.join(", ")})`)));
  document.getElementById("trip-table-wrap").replaceChildren(
    el("table", { class: "data" },
      el("thead", {}, el("tr", {}, el("th", {}, "Trip"), el("th", {}, "Requested"), el("th", {}, "Pickup"), el("th", {}, "Drop-off"))),
      el("tbody", {}, rows)),
  );
}
