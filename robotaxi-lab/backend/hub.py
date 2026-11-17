"""Simplified (hub) problem and its online version.

Simplified problem: a car serves trip i by leaving the depot at a time S_i >= t_i,
driving to s_i, carrying the passenger to w_i and driving back to the depot, and it
must be back before starting another trip. With

    a_i = d(o, s_i) + d(s_i, w_i)     (depot to drop-off)
    b_i = d(w_i, o)                   (drive home)
    p_i = a_i + b_i                   (time the car is busy)

the passenger is dropped off at S_i + a_i, and the objective is the largest
completion time G_i = S_i + a_i - t_i (request to drop-off).

Online problem: the same model, but trips are revealed only at their request
times. Days are generated with Poisson arrivals and demand hotspots, and are
usually too large to solve exactly, so heuristics are measured against a max-flow
lower bound (Horn, 1974) instead of the optimum.

Heuristics here are dispatch rules: whenever a car is free at the depot and some
trip has been requested but not started, the car starts the waiting trip with the
smallest key. The key is a user formula (see KEY_VARIABLES). A rule marked
`lookahead` may instead commit a car to a trip that has not been requested yet and
wait for it, as our original Max-min heuristic does; such rules need to know the
future, so they are only allowed in the simplified (offline) mode.
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .expr import FormulaError, compile_formula
from .model import Instance, Trip, dist

try:
    from ortools.graph.python import max_flow as _ortools_max_flow
    HAVE_MAXFLOW = True
except Exception:  # pragma: no cover - optional dependency
    HAVE_MAXFLOW = False

HUB_EXACT_LIMIT = 9

KEY_VARIABLES = {
    "t": "Request time of the trip",
    "a": "Depot to pickup to drop-off: the shortest possible completion time",
    "b": "Drive from the drop-off back to the depot",
    "p": "Time the car is busy with the trip, a + b",
    "ride": "Pickup to drop-off distance",
    "depot_dist": "Depot to pickup distance",
    "now": "Time the free car makes its choice",
    "waited": "now - t: how long the trip has been waiting (negative if not requested yet)",
    "start": "Time the car would leave the depot for this trip, max(t, now)",
    "completion": "Completion time if this trip is started now, start + a - t",
    "i": "Trip index",
    "n_left": "Number of trips not started yet (including this one)",
}

HUB_PRESETS = [
    {
        "id": "fifo",
        "name": "FIFO",
        "key_formula": "t",
        "lookahead": False,
        "description": "Serve the waiting trip that was requested first. Proven (5 - 1/m)-approximation.",
    },
    {
        "id": "epd",
        "name": "EPD",
        "key_formula": "t + a",
        "lookahead": False,
        "description": "Earliest possible drop-off first. Proven (6 - 1/m)-approximation.",
    },
    {
        "id": "adjmaxmin",
        "name": "Adjusted Max-min",
        "key_formula": "t - a",
        "lookahead": False,
        "description": "Max-min restricted to trips already requested: serve the one that would finish latest. "
                       "Proven (6 - 1/m)-approximation.",
    },
    {
        "id": "spt",
        "name": "Shortest trip first",
        "key_formula": "a, t",
        "lookahead": False,
        "description": "Serve the shortest waiting trip. No constant bound: long trips can starve.",
    },
    {
        "id": "maxmin_orig",
        "name": "Max-min (original)",
        "key_formula": "-completion, t",
        "lookahead": True,
        "description": "Our original heuristic: may commit a car to a trip that is not requested yet. "
                       "No constant bound, and offline only.",
    },
]

ONLINE_PRESETS = [p for p in HUB_PRESETS if not p["lookahead"]]


def trip_parts(inst: Instance, tr: Trip) -> Tuple[int, int, int]:
    a = dist(inst.depot, tr.s) + tr.ride
    b = dist(tr.w, inst.depot)
    return a, b, a + b


# ------------------------------------------------------------------ schedules

@dataclass
class HubOutcome:
    car: int
    position: int
    depart: int       # S_i: car leaves the depot
    arrive: int       # reaches the pickup
    pickup: int       # equals arrive, since S_i >= t_i
    dropoff: int      # S_i + a_i
    back: int         # S_i + p_i: car is back at the depot
    wait: int         # pickup - t_i
    completion: int   # dropoff - t_i (the objective)
    empty: int        # empty driving: depot to pickup plus drive home


@dataclass
class HubSchedule:
    routes: List[List[int]]
    outcomes: Dict[int, HubOutcome]

    @property
    def objective(self) -> int:
        return max((o.completion for o in self.outcomes.values()), default=0)

    @property
    def max_wait(self) -> int:
        """Kept so code written for the base problem can compare schedules generically."""
        return self.objective

    def metrics(self, inst: Instance) -> dict:
        outs = list(self.outcomes.values())
        n = len(outs)
        return {
            "objective": self.objective,
            "max_completion": self.objective,
            "mean_completion": (sum(o.completion for o in outs) / n) if n else 0.0,
            "max_wait": max((o.wait for o in outs), default=0),
            "mean_wait": (sum(o.wait for o in outs) / n) if n else 0.0,
            "zero_wait_trips": sum(1 for o in outs if o.wait == 0),
            "empty_distance": sum(o.empty for o in outs),
            "ride_distance": sum(inst.trips[i].ride for i in self.outcomes),
            "last_dropoff": max((o.back for o in outs), default=0),
            "cars_used": sum(1 for r in self.routes if r),
        }

    def to_dict(self, inst: Instance) -> dict:
        legs = []
        for route in self.routes:
            car_legs = []
            for i in route:
                o = self.outcomes[i]
                tr = inst.trips[i]
                if o.arrive > o.depart:
                    car_legs.append({"kind": "empty", "start": o.depart, "end": o.arrive,
                                     "from": list(inst.depot), "to": list(tr.s), "trip": i})
                car_legs.append({"kind": "ride", "start": o.pickup, "end": o.dropoff,
                                 "from": list(tr.s), "to": list(tr.w), "trip": i})
                if o.back > o.dropoff:
                    car_legs.append({"kind": "return", "start": o.dropoff, "end": o.back,
                                     "from": list(tr.w), "to": list(inst.depot), "trip": i})
            legs.append(car_legs)
        return {
            "routes": self.routes,
            "trips": {str(i): o.__dict__ for i, o in self.outcomes.items()},
            "legs": legs,
            "metrics": self.metrics(inst),
        }


def hub_simulate(inst: Instance, routes: List[List[int]]) -> HubSchedule:
    """Each car serves its trips in order, leaving the depot as early as allowed."""
    seen = [i for r in routes for i in r]
    if sorted(seen) != list(range(inst.n)):
        raise ValueError("Routes must contain every trip exactly once.")
    outcomes: Dict[int, HubOutcome] = {}
    for c, route in enumerate(routes):
        free = 0
        for pos, i in enumerate(route):
            tr = inst.trips[i]
            a, b, p = trip_parts(inst, tr)
            S = max(tr.t, free)
            arrive = S + dist(inst.depot, tr.s)
            outcomes[i] = HubOutcome(car=c, position=pos, depart=S, arrive=arrive, pickup=arrive,
                                     dropoff=S + a, back=S + p, wait=arrive - tr.t,
                                     completion=S + a - tr.t, empty=dist(inst.depot, tr.s) + b)
            free = S + p
    return HubSchedule(routes=[list(r) for r in routes], outcomes=outcomes)


# ------------------------------------------------------------------ dispatch rules

@dataclass
class DispatchRule:
    name: str
    key_formula: str
    lookahead: bool = False
    id: str = ""

    def __post_init__(self):
        try:
            self._key = compile_formula(self.key_formula, KEY_VARIABLES)
        except FormulaError as exc:
            raise FormulaError(f"Key formula: {exc}") from None

    @staticmethod
    def from_dict(d: dict) -> "DispatchRule":
        return DispatchRule(name=str(d.get("name", "Rule"))[:40], key_formula=str(d.get("key_formula") or ""),
                            lookahead=bool(d.get("lookahead", False)), id=str(d.get("id", "")))

    def run(self, inst: Instance) -> HubSchedule:
        m, trips = inst.cars, inst.trips
        parts = [trip_parts(inst, tr) for tr in trips]
        free = [0] * m
        routes: List[List[int]] = [[] for _ in range(m)]
        left = set(range(inst.n))
        while left:
            c = min(range(m), key=lambda k: (free[k], k))
            if self.lookahead:
                now = free[c]
                pool = left
            else:
                now = max(free[c], min(trips[j].t for j in left))
                pool = [j for j in left if trips[j].t <= now]
            n_left = len(left)
            best = None
            for j in pool:
                tr = trips[j]
                a, b, p = parts[j]
                start = max(tr.t, now)
                env = {"t": tr.t, "a": a, "b": b, "p": p, "ride": tr.ride,
                       "depot_dist": dist(inst.depot, tr.s), "now": now, "waited": now - tr.t,
                       "start": start, "completion": start + a - tr.t, "i": j, "n_left": n_left}
                key = self._key(env) + (tr.t, j)
                if best is None or key < best[0]:
                    best = (key, j, start)
            _, j, start = best
            routes[c].append(j)
            free[c] = start + parts[j][2]
            left.remove(j)
        return hub_simulate(inst, routes)


def run_rule_timed(rule: DispatchRule, inst: Instance):
    t0 = time.perf_counter()
    sched = rule.run(inst)
    return sched, (time.perf_counter() - t0) * 1000.0


# ------------------------------------------------------------------ exact optimum

def hub_optimal(inst: Instance) -> HubSchedule:
    """Exact minimum of the maximum completion time, by exhaustive search (small days only).

    For every subset of trips, the best order on a single car is found by depth-first
    search over orders; the subsets are then split between the m cars by dynamic
    programming, as in the base problem's exhaustive search.
    """
    n, m, trips = inst.n, inst.cars, inst.trips
    if n > HUB_EXACT_LIMIT:
        raise ValueError(f"Exact search for the simplified problem is limited to {HUB_EXACT_LIMIT} trips.")
    parts = [trip_parts(inst, tr) for tr in trips]
    INF = float("inf")
    size = 1 << n
    g = [INF] * size
    g_order: List[Optional[tuple]] = [None] * size
    g[0], g_order[0] = 0, ()

    def dfs(mask, free, cur, order):
        if cur < g[mask]:
            g[mask], g_order[mask] = cur, order
        for i in range(n):
            if not mask & (1 << i):
                t = trips[i].t
                a, _, p = parts[i]
                S = max(t, free)
                dfs(mask | (1 << i), S + p, max(cur, S + a - t), order + (i,))

    dfs(0, 0, 0, ())
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
    return hub_simulate(inst, routes)


# ------------------------------------------------------------------ max-flow lower bound

def _max_flow(n_nodes: int, arcs: List[Tuple[int, int, int]], src: int, sink: int) -> int:
    if HAVE_MAXFLOW:
        smf = _ortools_max_flow.SimpleMaxFlow()
        for u, v, c in arcs:
            smf.add_arc_with_capacity(u, v, c)
        status = smf.solve(src, sink)
        if status != smf.OPTIMAL:
            raise RuntimeError("The max-flow solver failed.")
        return smf.optimal_flow()
    return _dinic(n_nodes, arcs, src, sink)


def _dinic(n_nodes, arcs, src, sink) -> int:
    """Plain-Python max flow, used only if OR-Tools is missing."""
    graph = [[] for _ in range(n_nodes)]
    to, cap = [], []
    for u, v, c in arcs:
        graph[u].append(len(to)); to.append(v); cap.append(c)
        graph[v].append(len(to)); to.append(u); cap.append(0)
    flow = 0
    while True:
        level = [-1] * n_nodes
        level[src] = 0
        queue = [src]
        for u in queue:
            for e in graph[u]:
                if cap[e] > 0 and level[to[e]] < 0:
                    level[to[e]] = level[u] + 1
                    queue.append(to[e])
        if level[sink] < 0:
            return flow
        it = [0] * n_nodes

        def push(u, f):
            if u == sink:
                return f
            while it[u] < len(graph[u]):
                e = graph[u][it[u]]
                v = to[e]
                if cap[e] > 0 and level[v] == level[u] + 1:
                    got = push(v, min(f, cap[e]))
                    if got:
                        cap[e] -= got
                        cap[e ^ 1] += got
                        return got
                it[u] += 1
            return 0

        while True:
            f = push(src, math.inf)
            if not f:
                break
            flow += f


def _flow_feasible(inst: Instance, F: int) -> bool:
    """Relaxation: trips may be paused and resumed, even on another car (Horn, 1974).

    Trip i must do its a_i units of driving within [t_i, t_i + F] and its b_i units
    of driving home within [t_i + a_i, t_i + F + b_i]. Every real schedule with value
    F satisfies this, so if the relaxation is infeasible then OPT > F.
    """
    pieces = []
    for tr in inst.trips:
        a, b, _ = trip_parts(inst, tr)
        if a > F:
            return False
        pieces.append((a, tr.t, tr.t + F))
        if b > 0:
            pieces.append((b, tr.t + a, tr.t + F + b))
    bounds = sorted({x for _, lo, hi in pieces for x in (lo, hi)})
    index = {x: k for k, x in enumerate(bounds)}
    P, K = len(pieces), len(bounds) - 1
    src, sink = 0, 1 + P + K
    arcs = []
    for i, (size, lo, hi) in enumerate(pieces):
        arcs.append((src, 1 + i, size))
        for k in range(index[lo], index[hi]):
            arcs.append((1 + i, 1 + P + k, bounds[k + 1] - bounds[k]))
    for k in range(K):
        arcs.append((1 + P + k, sink, inst.cars * (bounds[k + 1] - bounds[k])))
    total = sum(size for size, _, _ in pieces)
    return _max_flow(sink + 1, arcs, src, sink) == total


def flow_lower_bound(inst: Instance, upper: Optional[int] = None) -> dict:
    """Smallest integer F feasible for the relaxation: a lower bound on OPT, in polynomial time."""
    t0 = time.perf_counter()
    if inst.n == 0:
        return {"value": 0, "seconds": 0.0, "longest_trip": 0}
    longest = max(trip_parts(inst, tr)[0] for tr in inst.trips)
    lo = longest
    hi = upper if upper is not None else FIFO.run(inst).objective
    while lo < hi:
        mid = (lo + hi) // 2
        if _flow_feasible(inst, mid):
            hi = mid
        else:
            lo = mid + 1
    return {"value": lo, "seconds": time.perf_counter() - t0, "longest_trip": longest}


FIFO = DispatchRule(name="FIFO", key_formula="t")


# ------------------------------------------------------------------ online days

def hotspot_count(width: int) -> int:
    """A d x d town has sqrt(d) hotspots, rounded to the nearest whole number (4 for the report's 20 x 20 town)."""
    return max(1, round(math.sqrt(width)))


def _hot_point(rng: random.Random, inst_w: int, inst_h: int, hotspots, spread: float, share: float):
    if hotspots and rng.random() < share:
        hx, hy = rng.choice(hotspots)
        x = round(rng.gauss(hx, spread))
        y = round(rng.gauss(hy, spread))
        return (min(inst_w, max(0, x)), min(inst_h, max(0, y)))
    return (rng.randint(0, inst_w), rng.randint(0, inst_h))


def online_instance(rng: random.Random, n: int, cars: int, width: int = 20, load: float = 0.85,
                    hotspots: Optional[int] = None, spread: Optional[float] = None, share: float = 0.7,
                    seed: Optional[int] = None) -> Instance:
    """Poisson arrivals with demand hotspots.

    A d x d town has round(sqrt(d)) hotspots, placed uniformly at random for each day.
    Each pickup and drop-off is drawn, with probability `share`, from a normal
    distribution around one of the hotspots, and otherwise uniformly from the grid.
    The arrival rate is set so that the load rho = rate * E[p] / m, the fraction of
    fleet capacity demanded, equals `load`.
    """
    height = width
    depot = (width // 2, height // 2)
    count = hotspot_count(width) if hotspots is None else max(0, hotspots)
    spots = [(rng.randint(0, width), rng.randint(0, height)) for _ in range(count)]
    spread = spread if spread is not None else max(1.0, width / 10)

    def draw_trip(r):
        s = _hot_point(r, width, height, spots, spread, share)
        w = _hot_point(r, width, height, spots, spread, share)
        while w == s:
            w = _hot_point(r, width, height, spots, spread, share)
        return s, w

    # Mean busy time per trip, estimated from a separate stream so the day itself is unaffected.
    est = random.Random(12345)
    sample = 4000
    total_p = 0
    for _ in range(sample):
        s, w = draw_trip(est)
        total_p += dist(depot, s) + dist(s, w) + dist(w, depot)
    mean_p = total_p / sample
    rate = max(1e-9, load) * cars / mean_p

    trips, t = [], 0.0
    for _ in range(n):
        t += rng.expovariate(rate)
        s, w = draw_trip(rng)
        trips.append(Trip(s=s, w=w, t=int(t)))
    inst = Instance(width=width, height=height, depot=depot, cars=cars, trips=trips, seed=seed)
    inst.hotspots = [list(p) for p in spots]
    inst.load = load
    inst.mean_busy = round(mean_p, 2)
    return inst
