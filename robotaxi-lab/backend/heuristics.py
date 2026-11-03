"""Generic greedy dispatcher driven by two user formulas.

At every step, for each unassigned trip:
  1. Score every car with the *car formula* and keep the car with the smallest score.
  2. Score the trip with the *trip formula*, which can use statistics of its best
     car (for example its waiting time) and its second-best car.
The trip with the smallest trip score is appended to the end of its best car's
route. Repeat until every trip is assigned.

Formulas are comma-separated tuples compared lexicographically, so later parts
break ties in earlier ones. To *maximise* something, minimise its negative.
Remaining ties go to the lower car index and the lower trip index.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from .expr import FormulaError, compile_formula
from .model import Instance, ScheduleResult, dist, simulate

CAR_VARIABLES = {
    "wait": "Waiting time if this car serves the trip next",
    "pickup": "Pickup time if this car serves the trip next",
    "arrive": "Time this car would reach the pickup (before any idling)",
    "idle": "Time the car would sit at the pickup waiting for the request",
    "empty": "Empty driving distance from the car's position to the pickup",
    "finish": "Drop-off time if this car serves the trip next",
    "free_at": "Time the car finishes its current route",
    "car": "Car index (0, 1, 2, ...)",
    "car_trips": "Number of trips already assigned to this car",
    "t": "Request time of the trip",
    "ride": "Ride distance of the trip (pickup to drop-off)",
    "depot_dist": "Distance from the depot to the pickup",
}

TRIP_VARIABLES = {
    "t": "Request time of the trip",
    "ride": "Ride distance of the trip",
    "i": "Trip index",
    "best_wait": "Waiting time with the best car",
    "second_wait": "Smallest waiting time among the other cars (equals best_wait with one car)",
    "regret": "second_wait - best_wait: how much worse it gets if the best car is taken",
    "worst_wait": "Largest waiting time over all cars",
    "mean_wait": "Average waiting time over all cars",
    "best_pickup": "Pickup time with the best car",
    "best_empty": "Empty driving distance for the best car",
    "best_finish": "Drop-off time with the best car",
    "depot_dist": "Distance from the depot to the pickup",
    "n_left": "Number of trips still unassigned (including this one)",
}

PRESETS = [
    {
        "id": "fifo",
        "name": "FIFO",
        "car_formula": "wait, empty",
        "trip_formula": "t",
        "description": "Take trips in request order; give each to the car that can pick it up soonest.",
    },
    {
        "id": "maxmin",
        "name": "Max-min",
        "car_formula": "wait, empty",
        "trip_formula": "-best_wait, t",
        "description": "Our proposed heuristic: assign the trip whose minimum wait over all cars is largest.",
    },
    {
        "id": "regret",
        "name": "Regret",
        "car_formula": "wait, empty",
        "trip_formula": "-regret, -best_wait, t",
        "description": "Assign the trip that loses the most if its best car is taken by someone else.",
    },
    {
        "id": "nearest",
        "name": "Nearest car",
        "car_formula": "empty, wait",
        "trip_formula": "t",
        "description": "Take trips in request order; send the car that is closest, regardless of when it is free.",
    },
]


@dataclass
class Heuristic:
    name: str
    car_formula: str
    trip_formula: str
    id: str = ""

    def __post_init__(self):
        try:
            self._car = compile_formula(self.car_formula, CAR_VARIABLES)
        except FormulaError as exc:
            raise FormulaError(f"Car formula: {exc}") from None
        try:
            self._trip = compile_formula(self.trip_formula, TRIP_VARIABLES)
        except FormulaError as exc:
            raise FormulaError(f"Trip formula: {exc}") from None

    @staticmethod
    def from_dict(d: dict) -> "Heuristic":
        return Heuristic(name=str(d.get("name", "Heuristic"))[:40], car_formula=str(d.get("car_formula", "")),
                         trip_formula=str(d.get("trip_formula", "")), id=str(d.get("id", "")))

    def run(self, inst: Instance) -> ScheduleResult:
        m = inst.cars
        trips = inst.trips
        cars = [(0, inst.depot, 0)] * m      # (free_at, location, trips assigned)
        routes: List[List[int]] = [[] for _ in range(m)]
        left = set(range(inst.n))

        while left:
            chosen = None
            n_left = len(left)
            for i in sorted(left):
                tr = trips[i]
                ride = tr.ride
                depot_dist = dist(inst.depot, tr.s)
                per_car = []
                for c, (free_at, loc, k) in enumerate(cars):
                    empty = dist(loc, tr.s)
                    arrive = free_at + empty
                    pickup = max(tr.t, arrive)
                    env = {
                        "wait": pickup - tr.t, "pickup": pickup, "arrive": arrive,
                        "idle": max(0, tr.t - arrive), "empty": empty, "finish": pickup + ride,
                        "free_at": free_at, "car": c, "car_trips": k, "t": tr.t, "ride": ride,
                        "depot_dist": depot_dist,
                    }
                    per_car.append((self._car(env) + (c,), env))
                per_car.sort(key=lambda x: x[0])
                best_env = per_car[0][1]
                waits = [env["wait"] for _, env in per_car]
                # second_wait: smallest wait among the cars other than the chosen one
                second = min(waits[1:]) if m > 1 else best_env["wait"]
                tenv = {
                    "t": tr.t, "ride": ride, "i": i,
                    "best_wait": best_env["wait"], "second_wait": second,
                    "regret": second - best_env["wait"],
                    "worst_wait": max(waits), "mean_wait": sum(waits) / m,
                    "best_pickup": best_env["pickup"], "best_empty": best_env["empty"],
                    "best_finish": best_env["finish"], "depot_dist": depot_dist, "n_left": n_left,
                }
                key = self._trip(tenv) + (i,)
                if chosen is None or key < chosen[0]:
                    chosen = (key, i, best_env)

            _, i, env = chosen
            c = env["car"]
            free_at, loc, k = cars[c]
            cars[c] = (env["finish"], trips[i].w, k + 1)
            routes[c].append(i)
            left.remove(i)

        return simulate(inst, routes)


def run_timed(h: Heuristic, inst: Instance):
    start = time.perf_counter()
    res = h.run(inst)
    return res, (time.perf_counter() - start) * 1000.0
