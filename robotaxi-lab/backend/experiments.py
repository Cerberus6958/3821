"""Comparisons, batch experiments, parameter sweeps and counterexample search."""

from __future__ import annotations

import math
import random
import statistics
import threading
import time
import traceback
import uuid
from typing import Callable, Dict, List, Optional

from .exact import ENUMERATION_LIMIT, enumerate_optimal, solve_exact
from .heuristics import Heuristic, run_timed
from .model import Instance, Trip, lower_bound, random_instance
from .zero_wait import zero_wait_analysis

Progress = Callable[[int, int, str], None]


class Cancelled(Exception):
    pass


# ------------------------------------------------------------------ single instance

def compare(inst: Instance, heuristics: List[Heuristic], exact: dict) -> dict:
    results = []
    best_heur = None
    for h in heuristics:
        sched, ms = run_timed(h, inst)
        results.append({"id": h.id, "name": h.name, "ms": round(ms, 2), **sched.to_dict(inst)})
        if best_heur is None or sched.max_wait < best_heur.max_wait:
            best_heur = sched

    optimal = None
    if exact.get("enabled", True) and inst.n > 0:
        res = solve_exact(inst, time_limit=float(exact.get("time_limit", 20)), hint=best_heur,
                          workers=int(exact.get("workers", 4)))
        optimal = res.to_dict(inst)

    ref = optimal["value"] if optimal and optimal["value"] is not None else None
    for r in results:
        mw = r["metrics"]["max_wait"]
        r["ratio"] = (mw / ref) if ref else (1.0 if ref == 0 and mw == 0 else None)
    return {
        "instance": inst.to_dict(),
        "heuristics": results,
        "optimal": optimal,
        "lower_bound": lower_bound(inst),
        "zero_wait": zero_wait_analysis(inst),
    }


# ------------------------------------------------------------------ batch

def _evaluate(inst, heuristics, exact, reference):
    values, times = [], []
    best_sched = None
    for h in heuristics:
        sched, ms = run_timed(h, inst)
        values.append(sched.max_wait)
        times.append(ms)
        if best_sched is None or sched.max_wait < best_sched.max_wait:
            best_sched = sched
    row = {"heuristics": values, "heuristic_ms": times, "opt": None, "bound": None,
           "proven": None, "opt_seconds": None}
    if reference == "optimal":
        res = solve_exact(inst, time_limit=float(exact.get("time_limit", 10)), hint=best_sched,
                          workers=int(exact.get("workers", 4)))
        opt = res.value if res.value is not None else min(values)
        row.update(opt=min(opt, min(values)), bound=res.bound, proven=res.proven,
                   opt_seconds=round(res.seconds, 3))
    else:
        row.update(opt=min(values), bound=None, proven=None)
    return row


def _summarise(rows: List[dict], names: List[str]) -> dict:
    k = len(names)
    per = []
    for h in range(k):
        vals = [r["heuristics"][h] for r in rows]
        ratios = [r["heuristics"][h] / r["opt"] for r in rows if r["opt"]]
        zero_cases = [r for r in rows if r["opt"] == 0]
        per.append({
            "name": names[h],
            "mean_max_wait": statistics.mean(vals) if vals else None,
            "mean_ratio": statistics.mean(ratios) if ratios else None,
            "median_ratio": statistics.median(ratios) if ratios else None,
            "worst_ratio": max(ratios) if ratios else None,
            "pct_matching_reference": 100 * sum(r["heuristics"][h] == r["opt"] for r in rows) / len(rows) if rows else None,
            "zero_reference_cases": len(zero_cases),
            "zero_found": sum(r["heuristics"][h] == 0 for r in zero_cases),
            "mean_ms": statistics.mean(r["heuristic_ms"][h] for r in rows) if rows else None,
            "ratios": ratios,
        })
    wins = [[sum(r["heuristics"][a] < r["heuristics"][b] for r in rows) for b in range(k)] for a in range(k)]
    proven = [r for r in rows if r["proven"] is not None]
    return {
        "per_heuristic": per,
        "wins": wins,
        "instances": len(rows),
        "proven": sum(1 for r in proven if r["proven"]),
        "mean_reference": statistics.mean(r["opt"] for r in rows) if rows else None,
        "mean_solver_seconds": statistics.mean(r["opt_seconds"] for r in proven) if proven else None,
    }


def run_batch(cfg: dict, heuristics: List[Heuristic], exact: dict, progress: Progress) -> dict:
    rng = random.Random(int(cfg.get("seed", 3821)))
    count = int(cfg["instances"])
    reference = cfg.get("reference", "optimal")
    rows = []
    for k in range(count):
        progress(k, count, f"Instance {k + 1} of {count}")
        inst = random_instance(rng, int(cfg["n"]), int(cfg["cars"]), width=int(cfg.get("width", 10)),
                               horizon=int(cfg["horizon"]))
        row = _evaluate(inst, heuristics, exact, reference)
        row["instance"] = inst.to_dict()
        rows.append(row)
    progress(count, count, "Done")
    return {"config": cfg, "names": [h.name for h in heuristics], "rows": rows,
            "summary": _summarise(rows, [h.name for h in heuristics]), "reference": reference}


def run_sweep(cfg: dict, heuristics: List[Heuristic], exact: dict, progress: Progress) -> dict:
    variable = cfg["variable"]
    values = [int(v) for v in cfg["values"]]
    per_value = int(cfg["instances"])
    reference = cfg.get("reference", "optimal")
    rng = random.Random(int(cfg.get("seed", 3821)))
    total = len(values) * per_value
    points = []
    done = 0
    for v in values:
        params = {"n": int(cfg["n"]), "cars": int(cfg["cars"]), "horizon": int(cfg["horizon"]),
                  "width": int(cfg.get("width", 10))}
        params[variable] = v
        rows = []
        for k in range(per_value):
            progress(done, total, f"{variable} = {v}: instance {k + 1} of {per_value}")
            inst = random_instance(rng, params["n"], params["cars"], width=params["width"],
                                   horizon=params["horizon"])
            rows.append(_evaluate(inst, heuristics, exact, reference))
            done += 1
        summ = _summarise(rows, [h.name for h in heuristics])
        secs = [r["opt_seconds"] for r in rows if r["opt_seconds"] is not None]
        points.append({
            "value": v,
            "per_heuristic": [{k2: v2 for k2, v2 in p.items() if k2 != "ratios"} for p in summ["per_heuristic"]],
            "proven": summ["proven"],
            "instances": len(rows),
            "solver_mean_seconds": statistics.mean(secs) if secs else None,
            "solver_max_seconds": max(secs) if secs else None,
            "mean_reference": summ["mean_reference"],
        })
    progress(total, total, "Done")
    return {"config": cfg, "names": [h.name for h in heuristics], "points": points, "reference": reference}


# ------------------------------------------------------------------ counterexamples

def _mutate(rng: random.Random, inst: Instance, horizon: int) -> Instance:
    trips = [Trip(s=tr.s, w=tr.w, t=tr.t) for tr in inst.trips]
    j = rng.randrange(len(trips))
    tr = trips[j]
    clamp = lambda v, hi: max(0, min(hi, v))
    choice = rng.random()
    step = lambda: rng.choice([-2, -1, 1, 2])
    if choice < 0.3:
        tr.s = (clamp(tr.s[0] + step(), inst.width), clamp(tr.s[1] + step(), inst.height))
    elif choice < 0.6:
        tr.w = (clamp(tr.w[0] + step(), inst.width), clamp(tr.w[1] + step(), inst.height))
    elif choice < 0.9:
        tr.t = clamp(tr.t + rng.choice([-4, -2, -1, 1, 2, 4]), horizon)
    else:
        tr.s = (rng.randint(0, inst.width), rng.randint(0, inst.height))
        tr.w = (rng.randint(0, inst.width), rng.randint(0, inst.height))
        tr.t = rng.randint(0, horizon)
    if tr.s == tr.w:
        tr.w = (clamp(tr.w[0] + 1, inst.width) if tr.w[0] < inst.width else tr.w[0] - 1, tr.w[1])
    return Instance(inst.width, inst.height, inst.depot, inst.cars, trips)


def find_counterexample(cfg: dict, target: Heuristic, opponent: Optional[Heuristic], progress: Progress,
                        should_stop: Callable[[], bool]) -> dict:
    n = int(cfg["n"])
    if n > 7:
        raise ValueError("Counterexample search uses exhaustive search, so it is limited to 7 trips.")
    rng = random.Random(int(cfg.get("seed", 1)))
    iterations = int(cfg["iterations"])
    horizon = int(cfg["horizon"])
    objective = cfg.get("objective", "ratio")

    def score(inst):
        h = target.run(inst).max_wait
        ref = opponent.run(inst).max_wait if opponent else enumerate_optimal(inst).value
        if objective == "gap":
            return h - ref, h, ref
        return h / max(ref, 1), h, ref

    best = None
    current = None
    stale = 0
    for it in range(iterations):
        if should_stop():
            break
        if it % 25 == 0:
            progress(it, iterations, f"Best so far: {best[0]:.2f}" if best else "Searching")
        if current is None or stale > 150:
            inst = random_instance(rng, n, int(cfg["cars"]), width=int(cfg.get("width", 10)), horizon=horizon)
            current = (score(inst), inst)
            stale = 0
        cand = _mutate(rng, current[1], horizon)
        sc = score(cand)
        if sc[0] >= current[0][0]:
            stale = 0 if sc[0] > current[0][0] else stale + 1
            current = (sc, cand)
        else:
            stale += 1
        if best is None or current[0][0] > best[0]:
            best = (current[0][0], current[0][1], current[0][2], current[1])
    progress(iterations, iterations, "Done")
    if best is None:
        raise ValueError("The search stopped before evaluating any instance.")
    return {"score": best[0], "heuristic_value": best[1], "reference_value": best[2],
            "objective": objective, "reference": opponent.name if opponent else "Optimal",
            "instance": best[3].to_dict()}


# ------------------------------------------------------------------ jobs

class JobManager:
    def __init__(self):
        self.jobs: Dict[str, dict] = {}
        self.lock = threading.Lock()

    def start(self, kind: str, fn: Callable[[Progress, Callable[[], bool]], dict]) -> str:
        job_id = uuid.uuid4().hex[:10]
        job = {"id": job_id, "kind": kind, "status": "running", "done": 0, "total": 1,
               "message": "Starting", "result": None, "error": None, "cancel": False,
               "started": time.time()}
        with self.lock:
            self.jobs[job_id] = job

        def progress(done, total, message):
            if job["cancel"]:
                raise Cancelled()
            job.update(done=done, total=max(total, 1), message=message)

        def worker():
            try:
                job["result"] = fn(progress, lambda: job["cancel"])
                job["status"] = "cancelled" if job["cancel"] else "done"
            except Cancelled:
                job["status"] = "cancelled"
            except Exception as exc:  # report to the UI
                job["status"] = "error"
                job["error"] = str(exc) or type(exc).__name__
                traceback.print_exc()

        threading.Thread(target=worker, daemon=True).start()
        return job_id

    def get(self, job_id: str) -> Optional[dict]:
        job = self.jobs.get(job_id)
        if job is None:
            return None
        return {k: v for k, v in job.items() if k != "cancel"}

    def cancel(self, job_id: str) -> bool:
        job = self.jobs.get(job_id)
        if job is None:
            return False
        job["cancel"] = True
        return True
