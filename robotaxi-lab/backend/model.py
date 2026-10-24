"""Problem model: instances, distances and schedule simulation.

A town is an integer grid. Travel time between two points is their Manhattan
distance (one minute per block). There are m identical cars, all at the depot at
time 0, and n trip requests (s, w, t): pick up at s, drop off at w, requested at t.

A schedule gives each car an ordered list of trips. A car that finished its
previous trip at w' at time e picks up trip i at

    p_i = max(t_i, e + d(w', s_i))

and finishes at p_i + d(s_i, w_i). The waiting time of trip i is p_i - t_i, and
the objective is the maximum waiting time over all trips.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

Point = Tuple[int, int]


def dist(a: Sequence[int], b: Sequence[int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


@dataclass
class Trip:
    s: Point
    w: Point
    t: int

    @property
    def ride(self) -> int:
        return dist(self.s, self.w)

    def to_dict(self) -> dict:
        return {"s": list(self.s), "w": list(self.w), "t": self.t}


@dataclass
class Instance:
    width: int
    height: int
    depot: Point
    cars: int
    trips: List[Trip] = field(default_factory=list)
    seed: Optional[int] = None

    @property
    def n(self) -> int:
        return len(self.trips)

    def to_dict(self) -> dict:
        return {
            "width": self.width,
            "height": self.height,
            "depot": list(self.depot),
            "cars": self.cars,
            "seed": self.seed,
            "trips": [tr.to_dict() for tr in self.trips],
        }

    @staticmethod
    def from_dict(d: dict) -> "Instance":
        width = int(d.get("width", 10))
        height = int(d.get("height", width))
        depot = tuple(int(v) for v in d.get("depot", [width // 2, height // 2]))
        trips = []
        for raw in d.get("trips", []):
            s = tuple(int(v) for v in raw["s"])
            w = tuple(int(v) for v in raw["w"])
            trips.append(Trip(s=s, w=w, t=int(raw["t"])))
        inst = Instance(width=width, height=height, depot=depot,
                        cars=int(d.get("cars", 2)), trips=trips, seed=d.get("seed"))
        inst.validate()
        return inst

    def validate(self) -> None:
        if self.cars < 1:
            raise ValueError("There must be at least one car.")
        if self.width < 1 or self.height < 1:
            raise ValueError("The grid must be at least 1 x 1.")
        for k, p in enumerate([self.depot] + [x for tr in self.trips for x in (tr.s, tr.w)]):
            if not (0 <= p[0] <= self.width and 0 <= p[1] <= self.height):
                raise ValueError(f"Point {list(p)} lies outside the {self.width} x {self.height} grid.")
        for k, tr in enumerate(self.trips):
            if tr.t < 0:
                raise ValueError(f"Trip {k} has a negative request time.")


def random_instance(rng: random.Random, n: int, cars: int, width: int = 10, height: Optional[int] = None,
                    horizon: int = 40, depot: Optional[Point] = None, min_ride: int = 1,
                    seed: Optional[int] = None) -> Instance:
    """Uniform random pickups, drop-offs and request times in [0, horizon]."""
    height = width if height is None else height
    depot = depot if depot is not None else (width // 2, height // 2)
    trips = []
    for _ in range(n):
        while True:
            s = (rng.randint(0, width), rng.randint(0, height))
            w = (rng.randint(0, width), rng.randint(0, height))
            if dist(s, w) >= min_ride:
                break
        trips.append(Trip(s=s, w=w, t=rng.randint(0, horizon)))
    return Instance(width=width, height=height, depot=depot, cars=cars, trips=trips, seed=seed)


# --------------------------------------------------------------------- schedules

@dataclass
class TripOutcome:
    car: int
    position: int     # index within the car's route
    depart: int       # time the car leaves for the pickup
    arrive: int       # time the car reaches the pickup
    pickup: int
    dropoff: int
    wait: int
    empty: int        # empty driving distance to reach the pickup


@dataclass
class ScheduleResult:
    routes: List[List[int]]
    outcomes: Dict[int, TripOutcome]

    @property
    def max_wait(self) -> int:
        return max((o.wait for o in self.outcomes.values()), default=0)

    def metrics(self, inst: Instance) -> dict:
        waits = [o.wait for o in self.outcomes.values()]
        n = len(waits)
        return {
            "max_wait": self.max_wait,
            "mean_wait": (sum(waits) / n) if n else 0.0,
            "zero_wait_trips": sum(1 for w in waits if w == 0),
            "empty_distance": sum(o.empty for o in self.outcomes.values()),
            "ride_distance": sum(inst.trips[i].ride for i in self.outcomes),
            "last_dropoff": max((o.dropoff for o in self.outcomes.values()), default=0),
            "cars_used": sum(1 for r in self.routes if r),
        }

    def to_dict(self, inst: Instance) -> dict:
        legs = []
        for c, route in enumerate(self.routes):
            car_legs = []
            loc, e = inst.depot, 0
            for i in route:
                o = self.outcomes[i]
                tr = inst.trips[i]
                if o.arrive > o.depart:
                    car_legs.append({"kind": "empty", "start": o.depart, "end": o.arrive,
                                     "from": list(loc), "to": list(tr.s), "trip": i})
                if o.pickup > o.arrive:
                    car_legs.append({"kind": "idle", "start": o.arrive, "end": o.pickup,
                                     "from": list(tr.s), "to": list(tr.s), "trip": i})
                car_legs.append({"kind": "ride", "start": o.pickup, "end": o.dropoff,
                                 "from": list(tr.s), "to": list(tr.w), "trip": i})
                loc, e = tr.w, o.dropoff
            legs.append(car_legs)
        return {
            "routes": self.routes,
            "trips": {str(i): o.__dict__ for i, o in self.outcomes.items()},
            "legs": legs,
            "metrics": self.metrics(inst),
        }


def simulate(inst: Instance, routes: List[List[int]]) -> ScheduleResult:
    """Earliest-possible timing for a set of car routes."""
    seen = [i for r in routes for i in r]
    if sorted(seen) != list(range(inst.n)):
        raise ValueError("Routes must contain every trip exactly once.")
    outcomes: Dict[int, TripOutcome] = {}
    for c, route in enumerate(routes):
        loc, e = inst.depot, 0
        for pos, i in enumerate(route):
            tr = inst.trips[i]
            empty = dist(loc, tr.s)
            arrive = e + empty
            pickup = max(tr.t, arrive)
            dropoff = pickup + tr.ride
            outcomes[i] = TripOutcome(car=c, position=pos, depart=e, arrive=arrive, pickup=pickup,
                                      dropoff=dropoff, wait=pickup - tr.t, empty=empty)
            loc, e = tr.w, dropoff
    return ScheduleResult(routes=[list(r) for r in routes], outcomes=outcomes)


def lower_bound(inst: Instance) -> int:
    """Every car starts at the depot at time 0, so trip j cannot be picked up before d(o, s_j)."""
    return max((max(0, dist(inst.depot, tr.s) - tr.t) for tr in inst.trips), default=0)
