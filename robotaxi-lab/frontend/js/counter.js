// Counterexample search: hill-climb small days to make one heuristic look as bad as possible.
import { api, waitForJob } from "./api.js";
import { setProgress } from "./experiments.js";
import { emit, heuristicPayload, on, state } from "./state.js";
import { el, fmt, formData, intOr, seriesColor, store, toast } from "./util.js";

let jobId = null;

export function initCounter() {
  const form = document.getElementById("ce-form");
  const saved = store.get("ce-form", null);
  if (saved) for (const [k, v] of Object.entries(saved)) if (form.elements[k] && k !== "target" && k !== "opponent") form.elements[k].value = v;
  fillSelects();
  on("heuristics-changed", fillSelects);
  form.addEventListener("submit", (e) => { e.preventDefault(); run(); });
  document.getElementById("ce-cancel").addEventListener("click", () => jobId && api.cancel(jobId));
}

function fillSelects() {
  const target = document.getElementById("ce-target");
  const opp = document.getElementById("ce-opponent");
  const keepT = target.value, keepO = opp.value;
  const opts = () => state.heuristics.map((h) => el("option", { value: h.uid }, h.name));
  target.replaceChildren(...opts());
  opp.replaceChildren(el("option", { value: "" }, "True optimum"), ...opts());
  const has = (v) => state.heuristics.some((h) => h.uid === v);
  if (has(keepT)) target.value = keepT;
  else {
    const mm = state.heuristics.find((h) => /max.?min/i.test(h.name));
    if (mm) target.value = mm.uid;
  }
  opp.value = has(keepO) ? keepO : "";
}

async function run() {
  const form = document.getElementById("ce-form");
  const f = formData(form);
  store.set("ce-form", f);
  const target = state.heuristics.find((h) => h.uid === f.target);
  if (!target) return toast("Pick a heuristic to test.", "error");
  const opponent = f.opponent ? state.heuristics.find((h) => h.uid === f.opponent) : null;
  if (opponent && opponent.uid === target.uid) return toast("Pick two different heuristics, or compare against the true optimum.", "error");
  const config = {
    n: intOr(f.n, 5), cars: intOr(f.cars, 2), width: intOr(f.width, 10), horizon: intOr(f.horizon, 20),
    iterations: intOr(f.iterations, 1500), seed: intOr(f.seed, 1), objective: f.objective,
  };
  const submit = form.querySelector("button[type=submit]");
  const cancel = document.getElementById("ce-cancel");
  submit.disabled = true;
  cancel.hidden = false;
  setProgress("ce-progress", 0, 1, "Starting");
  try {
    const { job } = await api.startJob("counterexample", {
      config, target: heuristicPayload(target), opponent: opponent ? heuristicPayload(opponent) : null,
    });
    jobId = job;
    const res = await waitForJob(job, (d, t, m) => setProgress("ce-progress", d, t, m));
    if (!res) { toast("Search stopped before it found anything."); return; }
    render(res, target, opponent);
  } catch (err) {
    toast(err.message, "error");
  } finally {
    jobId = null;
    submit.disabled = false;
    cancel.hidden = true;
    document.getElementById("ce-progress").hidden = true;
  }
}

function render(res, target, opponent) {
  const refName = opponent ? opponent.name : "the optimum";
  const ratio = res.reference_value > 0 ? res.heuristic_value / res.reference_value : null;
  const headline = res.objective === "gap"
    ? `${res.heuristic_value - res.reference_value} min longer`
    : ratio === null ? (res.heuristic_value > 0 ? "unboundedly worse" : "1.00×") : `${ratio.toFixed(2)}×`;
  const lead = res.objective === "gap" ? `${target.name}'s longest wait is ` : `${target.name}'s longest wait is `;
  const tail = res.objective === "gap" ? ` than ${refName}'s on this day: ` : ` ${refName === "the optimum" ? "the optimum's" : `${refName}'s`} on this day: `;
  const inst = res.instance;
  const rows = inst.trips.map((t, i) => el("tr", {},
    el("td", {}, `Trip ${i}`), el("td", {}, String(t.t)), el("td", {}, `(${t.s.join(", ")})`), el("td", {}, `(${t.w.join(", ")})`)));
  const json = JSON.stringify(inst, null, 2);
  document.getElementById("ce-results").replaceChildren(
    el("p", { class: "ce-summary" },
      el("span", { class: "swatch inline", style: { background: seriesColor(target.slot) } }),
      lead, el("strong", {}, headline), tail,
      `${fmt(res.heuristic_value)} min against ${fmt(res.reference_value)} min.`,
      res.cancelled ? " The search was stopped early, so a worse day may exist." : ""),
    el("p", { class: "note" }, `Depot (${inst.depot.join(", ")}), ${inst.cars} car${inst.cars === 1 ? "" : "s"}, ${inst.width} × ${inst.height} grid.`),
    el("div", { class: "table-wrap card ce-table" }, el("table", { class: "data" },
      el("thead", {}, el("tr", {}, el("th", {}, "Trip"), el("th", {}, "Requested"), el("th", {}, "Pickup"), el("th", {}, "Drop-off"))),
      el("tbody", {}, rows))),
    el("div", { class: "link-row" },
      el("button", { type: "button", class: "btn primary", onclick: () => emit("load-instance", inst) }, "Open this day in the replay"),
      el("button", {
        type: "button", class: "text-btn",
        onclick: async () => {
          try { await navigator.clipboard.writeText(json); toast("Copied the day as JSON."); }
          catch { toast("Couldn't reach the clipboard. Use Export JSON in the sidebar after opening the day.", "error"); }
        },
      }, "Copy as JSON")),
  );
}
