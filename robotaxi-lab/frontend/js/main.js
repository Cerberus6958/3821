// Entry point: wires the sidebar, tabs and views together.
import { api } from "./api.js";
import { initCompare } from "./compare.js";
import { initCounter } from "./counter.js";
import { initExperiments } from "./experiments.js";
import { initHeuristics, loadHeuristics } from "./heuristics.js";
import { initInstance, loadInstanceForMode, setInstance } from "./instance.js";
import { initReplay } from "./replay.js";
import { MODE_INFO, emit, enabledHeuristics, exactSettings, heuristicPayload, on, state } from "./state.js";
import { fmtSeconds, store, toast } from "./util.js";

const TABS = ["replay", "compare", "experiments", "counter"];

export function showTab(name) {
  for (const t of TABS) {
    const btn = document.getElementById(`tab-${t}`);
    const view = document.getElementById(`view-${t}`);
    const on_ = t === name;
    btn.setAttribute("aria-selected", String(on_));
    btn.tabIndex = on_ ? 0 : -1;
    view.hidden = !on_;
  }
  store.set("tab", name);
  emit("tab-shown", name);
}

function initTabs() {
  for (const t of TABS) document.getElementById(`tab-${t}`).addEventListener("click", () => showTab(t));
  document.querySelector(".tabs").addEventListener("keydown", (e) => {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    const tabs = TABS.filter((t) => !document.getElementById(`tab-${t}`).hidden);
    const cur = tabs.findIndex((t) => document.getElementById(`tab-${t}`).getAttribute("aria-selected") === "true");
    const next = tabs[(cur + (e.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length];
    showTab(next);
    document.getElementById(`tab-${next}`).focus();
  });
  showTab(store.get("tab", "replay"));
}

function initTheme() {
  const saved = store.get("theme", null);
  if (saved) document.documentElement.dataset.theme = saved;
  document.getElementById("theme-toggle").addEventListener("click", () => {
    const dark = document.documentElement.dataset.theme
      ? document.documentElement.dataset.theme === "dark"
      : window.matchMedia("(prefers-color-scheme: dark)").matches;
    const next = dark ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    store.set("theme", next);
    emit("theme-changed");
  });
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    if (!document.documentElement.dataset.theme) emit("theme-changed");
  });
}

function solverNote() {
  const note = document.getElementById("solver-note");
  const m = state.meta;
  const n = state.instance ? state.instance.trips.length : null;
  document.getElementById("exact-label").textContent = state.mode === "base"
    ? "Compute the true optimum" : "Compute the optimum or a lower bound";
  if (!document.getElementById("exact-enabled").checked) {
    note.textContent = "Ratios are left blank while the optimum is switched off.";
    return;
  }
  if (state.mode !== "base") {
    const lim = m.hub_exact_limit;
    const flow = "a max-flow lower bound (Horn, 1974): trips may pause and change cars, so it never exceeds the optimum and true ratios are at most the ones shown";
    if (n !== null && n <= lim) note.textContent = `${n} trips: solved exactly by exhaustive search. The lab also reports ${flow.split(":")[0]}.`;
    else if (n !== null) note.textContent = `${n} trips is too many to solve exactly (limit ${lim}), so heuristics are measured against ${flow}.`;
    else note.textContent = `Days with up to ${lim} trips are solved exactly; bigger days use ${flow}.`;
    return;
  }
  if (!m.have_ortools) {
    note.textContent = `OR-Tools isn't installed, so the optimum is only available for up to ${m.enumeration_limit} trips (exhaustive search). Run pip install ortools for larger days.`;
    return;
  }
  if (n === null) note.textContent = "Small days use exhaustive search; larger days use the CP-SAT solver.";
  else if (n <= 7) note.textContent = `${n} trips: solved exactly by exhaustive search.`;
  else note.textContent = `${n} trips: solved with CP-SAT. If it hits the time limit you get the best schedule found and a lower bound.`;
}

async function runDay() {
  const status = document.getElementById("run-status");
  const btn = document.getElementById("run-day");
  if (!state.instance) return toast("Generate or import a day first.", "error");
  const hs = enabledHeuristics();
  if (!hs.length) return toast("Tick at least one heuristic to dispatch.", "error");
  btn.disabled = true;
  status.textContent = "Dispatching…";
  const t0 = performance.now();
  try {
    const mode = state.mode;
    const res = await api.compare({ mode, instance: state.instance, heuristics: hs.map(heuristicPayload), exact: exactSettings() });
    if (mode !== state.mode) return;   // the problem was switched while this ran
    // Remember which sidebar heuristic produced each result so colours follow the heuristic.
    for (const r of res.heuristics) {
      const h = hs.find((x) => x.uid === r.id);
      r.slot = h ? h.slot : 1;
    }
    state.result = res;
    const secs = (performance.now() - t0) / 1000;
    const opt = res.optimal;
    status.textContent = opt
      ? `${opt.proven ? "Optimum proven" : "Best found, not proven"} in ${fmtSeconds(opt.seconds)}. Total ${fmtSeconds(secs)}.`
      : res.reference && res.reference.kind === "flow_bound"
        ? `Flow lower bound ${res.reference.value} min. Done in ${fmtSeconds(secs)}.`
        : `Done in ${fmtSeconds(secs)}.`;
    emit("result-changed");
  } catch (err) {
    status.textContent = "";
    toast(err.message, "error");
  } finally {
    btn.disabled = false;
  }
}

// Show only the controls that belong to the current problem.
function applyModeVisibility() {
  const mode = state.mode;
  document.documentElement.dataset.problem = mode;
  for (const b of document.querySelectorAll("[data-problem]")) b.setAttribute("aria-checked", String(b.dataset.problem === mode));
  for (const n of document.querySelectorAll("[data-modes]")) {
    const ok = n.dataset.modes.split(" ").includes(mode);
    n.hidden = !ok;
    if (n.tagName === "OPTION") n.disabled = !ok;
    for (const input of n.querySelectorAll("input")) input.disabled = !ok;
  }
  document.getElementById("tagline").textContent = MODE_INFO[mode].tagline;
  const select = document.querySelector("#exp-form select[name=variable]");
  if (select.selectedOptions[0] && select.selectedOptions[0].disabled) select.value = "n";
}

function setMode(mode) {
  if (mode === state.mode || !MODE_INFO[mode]) return;
  state.mode = mode;
  store.set("mode", mode);
  state.result = null;
  applyModeVisibility();
  loadHeuristics();
  loadInstanceForMode();
  document.getElementById("run-status").textContent = "";
  emit("mode-changed", mode);
  emit("result-changed");
  if (mode === "online" && document.getElementById("tab-counter").getAttribute("aria-selected") === "true") showTab("replay");
  solverNote();
}

async function boot() {
  initTheme();
  const savedMode = store.get("mode", "base");
  state.mode = MODE_INFO[savedMode] ? savedMode : "base";
  try {
    state.meta = await api.meta();
  } catch (err) {
    document.getElementById("run-status").textContent = err.message;
    toast(err.message, "error");
    return;
  }
  initHeuristics();
  initReplay();
  initCompare();
  initExperiments();
  initCounter();
  initInstance();
  applyModeVisibility();
  initTabs();
  if (state.mode === "online" && store.get("tab", "replay") === "counter") showTab("replay");
  solverNote();
  for (const b of document.querySelectorAll("[data-problem]")) b.addEventListener("click", () => setMode(b.dataset.problem));

  const exactBox = document.getElementById("exact-enabled");
  const limit = document.getElementById("exact-limit");
  const savedExact = store.get("exact", null);
  if (savedExact) { exactBox.checked = savedExact.enabled; limit.value = savedExact.time_limit; }
  const saveExact = () => { store.set("exact", { enabled: exactBox.checked, time_limit: limit.value }); solverNote(); };
  exactBox.addEventListener("change", saveExact);
  limit.addEventListener("change", saveExact);
  solverNote();

  on("instance-changed", () => {
    solverNote();
    if (!state.result) emit("result-changed");
  });
  on("load-instance", (inst) => {
    setInstance(inst);
    showTab("replay");
    runDay();
  });
  document.getElementById("run-day").addEventListener("click", runDay);
  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); runDay(); }
  });
}

boot();
