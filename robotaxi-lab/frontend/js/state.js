// Shared application state with a tiny publish/subscribe helper.
import { store } from "./util.js";

const listeners = {};

export const state = {
  mode: "base",        // "base" | "simplified" | "online"
  meta: null,
  heuristics: [],      // base: {uid, slot, name, car_formula, trip_formula, ...}; others: {..., key_formula, lookahead}
  instance: null,      // current day
  result: null,        // last /api/compare response
};

export const MODE_INFO = {
  base: {
    label: "Base problem",
    tagline: "Compare dispatch heuristics against the optimal schedule for the longest passenger wait",
  },
  simplified: {
    label: "Simplified",
    tagline: "Cars return to the depot after every trip. Compare dispatch rules on the longest completion time (request to drop-off)",
  },
  online: {
    label: "Online",
    tagline: "Trips arrive over the day (Poisson, with demand hotspots). Dispatch rules against a max-flow lower bound",
  },
};

export const isHub = () => state.mode !== "base";

// Storage key for settings kept separately per problem (the base problem keeps the original keys).
export const modeKey = (name) => (state.mode === "base" ? name : `${name}-${state.mode}`);

// The objective being minimised, for labels: "longest wait" or "longest completion time".
export const objLabel = () => (state.mode === "base" ? "longest wait" : "longest completion time");

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
  store.set(modeKey("heuristics"), state.heuristics);
}

export function enabledHeuristics() {
  return state.heuristics.filter((h) => h.enabled);
}

export function heuristicPayload(h) {
  if (isHub()) return { id: h.uid, name: h.name, key_formula: h.key_formula, lookahead: !!h.lookahead && state.mode === "simplified" };
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
