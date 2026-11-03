"""Exact minimum maximum waiting time.

Two methods:
  * `enumerate_optimal`: exhaustive search over every split of trips between cars
    and every order on each car. Exact, but exponential; used for small instances
    (up to about 9 trips) and as an independent check.
  * `solve_cpsat`: a constraint-programming model solved with Google OR-Tools
    CP-SAT. Handles larger instances; with a time limit it returns the best schedule
    found together with a proven lower bound.

CP-SAT model: node 0 is the depot and nodes 1..n are trips. A Boolean x[i,j] says a
car serves trip j directly after i (or starts with j when i = 0). AddMultipleCircuit
makes the chosen arcs form depot-to-depot routes covering every trip once, and at
most m routes leave the depot. Pickup times satisfy
    p_j >= t_j,  p_j >= d(o, s_j) if the route starts with j,
    p_j >= p_i + d(s_i, w_i) + d(w_i, s_j) if j directly follows i,
and we minimise W >= p_j - t_j. Any feasible pickup times are at least the
earliest possible ones, so the optimum equals the true minimum maximum wait.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List, Optional

from .model import Instance, ScheduleResult, dist, lower_bound, simulate

try:
    from ortools.sat.python import cp_model
    HAVE_ORTOOLS = True
except Exception:  # pragma: no cover - optional dependency
    HAVE_ORTOOLS = False

ENUMERATION_LIMIT = 9


@dataclass
class ExactResult:
    schedule: Optional[ScheduleResult]
    value: Optional[int]
    bound: int
    proven: bool
    method: str
    seconds: float

    def to_dict(self, inst: Instance) -> dict:
        return {
            "value": self.value,
            "bound": self.bound,
            "proven": self.proven,
            "method": self.method,
            "seconds": round(self.seconds, 3),
            "schedule": self.schedule.to_dict(inst) if self.schedule else None,
        }


# ------------------------------------------------------------------ enumeration

def enumerate_optimal(inst: Instance) -> ExactResult:
    start = time.perf_counter()
    n, m, trips = inst.n, inst.cars, inst.trips
    if n > ENUMERATION_LIMIT + 2:
        raise ValueError("Exhaustive search is limited to 11 trips.")
    INF = float("inf")
    size = 1 << n
    g = [INF] * size              # best max wait for one car serving exactly `mask`
    g_order: List[Optional[tuple]] = [None] * size
    g[0], g_order[0] = 0, ()

    def dfs(mask, e, loc, cur_max, order):
        if cur_max < g[mask]:
            g[mask], g_order[mask] = cur_max, order
        for i in range(n):
            if not mask & (1 << i):
                tr = trips[i]
                pickup = max(tr.t, e + dist(loc, tr.s))
                dfs(mask | (1 << i), pickup + tr.ride, tr.w, max(cur_max, pickup - tr.t), order + (i,))

    dfs(0, 0, inst.depot, 0, ())

    # F[k][mask]: best max wait covering mask with at most k cars
    prev = [INF] * size
    prev[0] = 0
    choices = []
    for _ in range(m):
        cur = [INF] * size
        choice = [0] * size
        cur[0] = 0
        for mask in range(1, size):
            low = mask & -mask
            rest = mask ^ low
            sub = rest
            best, best_part = INF, 0
            while True:
                part = sub | low
                val = max(g[part], prev[mask ^ part])
                if val < best:
                    best, best_part = val, part
                if sub == 0:
                    break
                sub = (sub - 1) & rest
            cur[mask], choice[mask] = best, best_part
        choices.append(choice)
        prev = cur

    routes: List[List[int]] = []
    mask = size - 1
    for k in range(m - 1, -1, -1):
        if mask == 0:
            break
        part = choices[k][mask]
        routes.append(list(g_order[part]))
        mask ^= part
    while len(routes) < m:
        routes.append([])
    sched = simulate(inst, routes)
    return ExactResult(schedule=sched, value=sched.max_wait, bound=sched.max_wait, proven=True,
                       method="exhaustive search", seconds=time.perf_counter() - start)


# ------------------------------------------------------------------ CP-SAT

def solve_cpsat(inst: Instance, time_limit: float = 20.0, hint: Optional[ScheduleResult] = None,
                workers: int = 4) -> ExactResult:
    if not HAVE_ORTOOLS:
        raise RuntimeError("OR-Tools is not installed; run `pip install ortools`.")
    start = time.perf_counter()
    n, m, trips = inst.n, inst.cars, inst.trips
    model = cp_model.CpModel()
    ride = [tr.ride for tr in trips]
    span = max((tr.t for tr in trips), default=0) + sum(ride) \
        + n * (inst.width + inst.height) + inst.width + inst.height + 1

    p = [model.NewIntVar(tr.t, span, f"p{j}") for j, tr in enumerate(trips)]
    W = model.NewIntVar(lower_bound(inst), span, "W")
    arcs, out_depot = [], []
    lits = {}
    for j, tr in enumerate(trips):
        lit = model.NewBoolVar(f"x0_{j}")
        arcs.append((0, j + 1, lit))
        out_depot.append(lit)
        lits[(0, j + 1)] = lit
        model.Add(p[j] >= dist(inst.depot, tr.s)).OnlyEnforceIf(lit)
        end = model.NewBoolVar(f"x{j}_0")
        arcs.append((j + 1, 0, end))
        lits[(j + 1, 0)] = end
        model.Add(W >= p[j] - tr.t)
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            lit = model.NewBoolVar(f"x{i}_{j}")
            arcs.append((i + 1, j + 1, lit))
            lits[(i + 1, j + 1)] = lit
            model.Add(p[j] >= p[i] + ride[i] + dist(trips[i].w, trips[j].s)).OnlyEnforceIf(lit)
    model.AddMultipleCircuit(arcs)
    model.Add(sum(out_depot) <= m)
    model.Minimize(W)

    if hint is not None:
        used = set()
        for route in hint.routes:
            prev = 0
            for i in route:
                used.add((prev, i + 1))
                prev = i + 1
            if route:
                used.add((prev, 0))
        for key, lit in lits.items():
            model.AddHint(lit, 1 if key in used else 0)
        for j, o in hint.outcomes.items():
            model.AddHint(p[j], o.pickup)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max(0.5, float(time_limit))
    solver.parameters.num_workers = max(1, int(workers))
    status = solver.Solve(model)
    seconds = time.perf_counter() - start
    bound = int(solver.BestObjectiveBound()) if status in (cp_model.OPTIMAL, cp_model.FEASIBLE) else lower_bound(inst)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return ExactResult(None, None, bound, False, "CP-SAT (no solution in time)", seconds)

    succ = {}
    for (a, b), lit in lits.items():
        if solver.Value(lit):
            succ.setdefault(a, []).append(b)
    routes = []
    for first in succ.get(0, []):
        route, node = [], first
        while node != 0:
            route.append(node - 1)
            node = succ[node][0]
        routes.append(route)
    while len(routes) < m:
        routes.append([])
    sched = simulate(inst, routes)
    proven = status == cp_model.OPTIMAL
    value = sched.max_wait
    return ExactResult(sched, value, value if proven else min(bound, value), proven,
                       "CP-SAT" + ("" if proven else " (time limit reached)"), seconds)


def solve_exact(inst: Instance, time_limit: float = 20.0, hint: Optional[ScheduleResult] = None,
                workers: int = 4) -> ExactResult:
    """Exhaustive search for small instances, CP-SAT otherwise."""
    if inst.n <= ENUMERATION_LIMIT and (inst.n <= 7 or not HAVE_ORTOOLS):
        return enumerate_optimal(inst)
    if not HAVE_ORTOOLS:
        raise RuntimeError(f"Instances with more than {ENUMERATION_LIMIT} trips need OR-Tools (pip install ortools).")
    return solve_cpsat(inst, time_limit=time_limit, hint=hint, workers=workers)
