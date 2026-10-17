#!/usr/bin/env python3
"""
Taxi town simulation: minimise the MAXIMUM passenger wait over a whole day.

Model
-----
* Town: 2D plane (km). One depot, H homes, W workplaces.
* Trips: (s, w, t) = start location, destination, request time (minutes from 00:00).
  The full day's schedule is known in advance.
* K cars, all start at the depot at time 0, constant speed, unlimited fuel.
* One passenger per trip. A car serves its assigned trips in request-time order.
* Wait time = pickup time - request time (a car cannot pick up before t).

Two dispatchers are compared:
  1. fcfs      - online baseline: trips in time order, each goes to the car that
                 can reach the pickup earliest.
  2. optimised - offline local search (the schedule is known up front) that
                 moves trips between cars to minimise (max wait, total wait).

Usage:
  python3 taxi_sim.py                       # defaults
  python3 taxi_sim.py --cars 5 --trips 300 --seed 7 --csv out.csv
  python3 taxi_sim.py --trips-file trips.csv   # columns: home_x,home_y,work_x,work_y,time_min
"""
import argparse
import csv
import math
import random
from dataclasses import dataclass


@dataclass
class Trip:
    id: int
    s: tuple          # start (x, y)
    w: tuple          # destination (x, y)
    t: float          # request time, minutes


# ---------------------------------------------------------------- town setup
def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def build_town(args, rng):
    size = args.size
    depot = (size / 2, size / 2)
    homes = [(rng.uniform(0, size), rng.uniform(0, size)) for _ in range(args.homes)]
    works = [(rng.uniform(0, size), rng.uniform(0, size)) for _ in range(args.workplaces)]
    return depot, homes, works


def make_schedule(args, rng, homes, works):
    """Random day with morning and evening commute peaks plus background trips."""
    trips = []
    for i in range(args.trips):
        r = rng.random()
        if r < 0.35:
            t = rng.gauss(8 * 60, 60); to_work = True       # morning peak
        elif r < 0.70:
            t = rng.gauss(17.5 * 60, 70); to_work = False   # evening peak
        else:
            t = rng.uniform(6 * 60, 22 * 60); to_work = rng.random() < 0.5
        t = min(max(t, 0), 24 * 60 - 1)
        h, w = rng.choice(homes), rng.choice(works)
        s, d = (h, w) if to_work else (w, h)
        trips.append((s, d, t))
    trips.sort(key=lambda x: x[2])
    return [Trip(i, s, d, t) for i, (s, d, t) in enumerate(trips)]


def load_trips(path):
    trips = []
    with open(path) as f:
        for row in csv.DictReader(f):
            trips.append((
                (float(row["home_x"]), float(row["home_y"])),
                (float(row["work_x"]), float(row["work_y"])),
                float(row["time_min"]),
            ))
    trips.sort(key=lambda x: x[2])
    return [Trip(i, s, d, t) for i, (s, d, t) in enumerate(trips)]


# ---------------------------------------------------------------- simulation
def run_car(seq, trips, depot, speed_km_min):
    """Simulate one car through its ordered trip ids. Returns (max, sum, log)."""
    pos, free = depot, 0.0
    mx, total, log = 0.0, 0.0, []
    for tid in seq:
        tr = trips[tid]
        arrive = free + dist(pos, tr.s) / speed_km_min
        pickup = max(arrive, tr.t)
        wait = pickup - tr.t
        drop = pickup + dist(tr.s, tr.w) / speed_km_min
        log.append((tid, tr.t, pickup, drop, wait))
        mx, total = max(mx, wait), total + wait
        pos, free = tr.w, drop
    return mx, total, log


def evaluate(plan, trips, depot, speed):
    stats = [run_car(seq, trips, depot, speed)[:2] for seq in plan]
    return max(s[0] for s in stats), sum(s[1] for s in stats), stats


def fcfs(trips, k, depot, speed):
    plan = [[] for _ in range(k)]
    pos = [depot] * k
    free = [0.0] * k
    for tr in trips:
        best, best_pick = None, math.inf
        for c in range(k):
            pick = max(free[c] + dist(pos[c], tr.s) / speed, tr.t)
            if pick < best_pick:
                best, best_pick = c, pick
        plan[best].append(tr.id)
        free[best] = best_pick + dist(tr.s, tr.w) / speed
        pos[best] = tr.w
    return plan


def optimise(plan, trips, depot, speed, iters, rng):
    """Hill-climb: move one trip to another car; accept if (max, total) doesn't worsen."""
    k = len(plan)
    plan = [list(p) for p in plan]
    stats = [run_car(p, trips, depot, speed)[:2] for p in plan]

    def score(st):
        return (max(s[0] for s in st), sum(s[1] for s in st))

    cur = score(stats)
    owner = {tid: c for c, p in enumerate(plan) for tid in p}
    ids = list(owner)
    for _ in range(iters):
        tid = rng.choice(ids)
        a, b = owner[tid], rng.randrange(k)
        if a == b:
            continue
        new_a = [x for x in plan[a] if x != tid]
        new_b = sorted(plan[b] + [tid], key=lambda x: trips[x].t)
        sa = run_car(new_a, trips, depot, speed)[:2]
        sb = run_car(new_b, trips, depot, speed)[:2]
        trial = list(stats)
        trial[a], trial[b] = sa, sb
        new = score(trial)
        if new <= cur:
            plan[a], plan[b], stats, cur = new_a, new_b, trial, new
            owner[tid] = b
    return plan


# ---------------------------------------------------------------- reporting
def hhmm(m):
    return f"{int(m // 60) % 24:02d}:{int(m % 60):02d}"


def report(name, plan, trips, depot, speed):
    waits, per_car = [], []
    worst = (-1, None)
    for c, seq in enumerate(plan):
        _, _, log = run_car(seq, trips, depot, speed)
        per_car.append((c, len(log), sum(r[3] - r[2] for r in log)))
        for r in log:
            waits.append(r[4])
            if r[4] > worst[0]:
                worst = (r[4], r[0], c, r[1])
    waits.sort()
    n = len(waits)
    print(f"\n=== {name} ===")
    print(f"  max wait     : {waits[-1]:7.2f} min   (trip #{worst[1]}, car {worst[2]}, requested {hhmm(worst[3])})")
    print(f"  mean wait    : {sum(waits)/n:7.2f} min")
    print(f"  95th pct wait: {waits[int(0.95*(n-1))]:7.2f} min")
    print(f"  trips served : {n}")
    print("  car  trips  busy_driving_time")
    for c, cnt, busy in per_car:
        print(f"  {c:>3}  {cnt:>5}  {busy:8.1f} min")


def write_csv(path, name, plan, trips, depot, speed):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["dispatcher", "car", "trip_id", "request_time", "pickup_time", "dropoff_time", "wait_min"])
        for c, seq in enumerate(plan):
            for tid, t, pick, drop, wait in run_car(seq, trips, depot, speed)[2]:
                w.writerow([name, c, tid, hhmm(t), hhmm(pick), hhmm(drop), round(wait, 2)])


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--cars", type=int, default=10)
    p.add_argument("--homes", type=int, default=30)
    p.add_argument("--workplaces", type=int, default=6)
    p.add_argument("--trips", type=int, default=200)
    p.add_argument("--size", type=float, default=20.0, help="town side length, km")
    p.add_argument("--speed", type=float, default=40.0, help="car speed, km/h")
    p.add_argument("--iters", type=int, default=20000, help="local-search iterations")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--trips-file", help="CSV of trips instead of a random schedule")
    p.add_argument("--csv", help="write optimised per-trip results to this CSV")
    args = p.parse_args()

    rng = random.Random(args.seed)
    depot, homes, works = build_town(args, rng)
    trips = load_trips(args.trips_file) if args.trips_file else make_schedule(args, rng, homes, works)
    speed = args.speed / 60.0  # km per minute

    print(f"Town {args.size}x{args.size} km | depot {depot} | {args.cars} cars @ {args.speed} km/h | {len(trips)} trips")

    base = fcfs(trips, args.cars, depot, speed)
    report("FCFS nearest-available (baseline)", base, trips, depot, speed)

    opt = optimise(base, trips, depot, speed, args.iters, rng)
    report(f"Optimised min-max ({args.iters} iterations)", opt, trips, depot, speed)

    b, o = evaluate(base, trips, depot, speed)[0], evaluate(opt, trips, depot, speed)[0]
    print(f"\nMax wait: {b:.2f} -> {o:.2f} min  ({(b-o)/b*100 if b else 0:.1f}% reduction)")

    if args.csv:
        write_csv(args.csv, "optimised", opt, trips, depot, speed)
        print(f"Wrote {args.csv}")


if __name__ == "__main__":
    main()
