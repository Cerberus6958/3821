// Shared application state with a tiny publish/subscribe helper.
import { store } from "./util.js";

const listeners = {};

export const state = {
  meta: null,
  heuristics: [],      // {uid, slot, name, car_formula, trip_formula, enabled, description}
  instance: null,      // current day
  result: null,        // last /api/compare response
};

export function on(event, fn) {
  (listeners[event] ||= []).push(fn);
}

export function emit(event, payload) {
  for (const fn of listeners[event] || []) fn(payload);
}

export const MAX_HEURISTICS = 8;

export function nextSlot() {
  const used = new Set(state.heuristics.map((h) => h.slot));
  for (let s = 1; s <= MAX_HEURISTICS; s++) if (!used.has(s)) return s;
  return null;
}

export function saveHeuristics() {
  store.set("heuristics", state.heuristics);
}

export function enabledHeuristics() {
  return state.heuristics.filter((h) => h.enabled);
}

export function heuristicPayload(h) {
  return { id: h.uid, name: h.name, car_formula: h.car_formula, trip_formula: h.trip_formula };
}

// Every schedule in the last result, heuristics first then the optimum, in one shape.
export function resultSeries() {
  const r = state.result;
  if (!r) return [];
  const out = r.heuristics.map((h) => ({
    key: h.id, name: h.name, slot: h.slot, sched: h, ratio: h.ratio, ms: h.ms, isOpt: false,
  }));
  if (r.optimal && r.optimal.schedule) {
    out.push({
      key: "opt", name: r.optimal.proven ? "Optimal" : "Best found", slot: "opt",
      sched: r.optimal.schedule, ratio: 1, ms: r.optimal.seconds * 1000, isOpt: true,
    });
  }
  return out;
}

export function exactSettings() {
  return {
    enabled: document.getElementById("exact-enabled").checked,
    time_limit: Math.max(1, Number(document.getElementById("exact-limit").value) || 20),
    workers: 4,
  };
}
