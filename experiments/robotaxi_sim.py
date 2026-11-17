"""
Robotaxi max-wait simulation: exact optimum vs FIFO greedy vs max-min greedy.

Model (matches the proposal's problem statement):
  - Town is an integer grid; travel time between points is Manhattan distance.
  - m identical cars start at the depot o at time 0.
  - n trips r_i = (s_i, w_i, t_i): pick up at s_i, drop off at w_i, requested at t_i.
  - Each car carries one passenger at a time and serves its trips in order.
    If a car finished its previous trip at w' at time e, it picks up trip i at
        p_i = max(t_i, e + d(w', s_i))
    and finishes at p_i + d(s_i, w_i).
  - Waiting time of trip i is p_i - t_i. Objective: minimise the maximum wait.

Rules compared:
  OPT     exact optimum (exponential: tries every split of trips into cars and
          every order on each car).
  FIFO    take trips in order of request time; give each to the car that can
          pick it up soonest.
  MAXMIN  our heuristic: for every unassigned trip, find the car giving it the
          minimum wait; assign the trip whose minimum wait is LARGEST to that car.

Tie-breaking (same for both greedies): when choosing a car, prefer smaller wait,
then smaller empty driving distance, then lower car index. MAXMIN breaks ties
between trips by earlier request time, then lower trip index.
"""

import itertools
import random
import statistics
import csv
import sys

INF = float("inf")


def dist(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def serve(car, trip):
    """Return (wait, new_end_time, new_location, empty_distance) if `car` serves `trip` next."""
    e, loc = car
    s, w, t = trip
    empty = dist(loc, s)
    pickup = max(t, e + empty)
    return pickup - t, pickup + dist(s, w), w, empty


# ---------------------------------------------------------------- exact optimum

def best_single_car(trips, depot):
    """g[mask] = minimum over orders of the max wait when ONE car serves exactly the trips in mask.
    Enumerates every ordered sequence once via DFS (about e * n! nodes)."""
    n = len(trips)
    g = [INF] * (1 << n)
    g[0] = 0

    def dfs(mask, e, loc, cur_max):
        if cur_max < g[mask]:
            g[mask] = cur_max
        for i in range(n):
            if not mask & (1 << i):
                wait, e2, loc2, _ = serve((e, loc), trips[i])
                dfs(mask | (1 << i), e2, loc2, max(cur_max, wait))

    dfs(0, 0, depot, 0)
    return g


def optimal_max_wait(trips, m, depot):
    """Split trips among m identical cars, each using its best order."""
    n = len(trips)
    g = best_single_car(trips, depot)
    full = (1 << n) - 1
    # F[k][mask] = best max wait covering `mask` with at most k cars
    prev = [INF] * (1 << n)
    prev[0] = 0
    for _ in range(m):
        cur = [INF] * (1 << n)
        cur[0] = 0
        for mask in range(1, 1 << n):
            low = mask & -mask
            rest = mask ^ low
            sub = rest
            best = INF
            while True:
                part = sub | low  # part always contains the lowest trip, avoids double counting
                val = max(g[part], prev[mask ^ part])
                if val < best:
                    best = val
                if sub == 0:
                    break
                sub = (sub - 1) & rest
            cur[mask] = best
        prev = cur
    return prev[full]


def brute_force_check(trips, m, depot):
    """Independent naive exact solver for tiny instances: every assignment, every order per car."""
    n = len(trips)
    best = INF
    for assign in itertools.product(range(m), repeat=n):
        groups = [[i for i in range(n) if assign[i] == c] for c in range(m)]
        worst = 0
        for grp in groups:
            gbest = INF
            for order in itertools.permutations(grp):
                car = (0, depot)
                mx = 0
                for i in order:
                    wait, e2, loc2, _ = serve(car, trips[i])
                    car = (e2, loc2)
                    mx = max(mx, wait)
                gbest = min(gbest, mx)
            worst = max(worst, gbest if grp else 0)
        best = min(best, worst)
    return best


# ---------------------------------------------------------------- greedies

def pick_car(cars, trip):
    best = None
    for c, car in enumerate(cars):
        wait, e2, loc2, empty = serve(car, trip)
        key = (wait, empty, c)
        if best is None or key < best[0]:
            best = (key, c, wait, e2, loc2)
    return best


def fifo(trips, m, depot, log=None):
    cars = [(0, depot)] * m
    worst = 0
    for i in sorted(range(len(trips)), key=lambda i: (trips[i][2], i)):
        _, c, wait, e2, loc2 = pick_car(cars, trips[i])
        cars[c] = (e2, loc2)
        worst = max(worst, wait)
        if log is not None:
            log.append((i, c, wait))
    return worst


def maxmin(trips, m, depot, log=None):
    cars = [(0, depot)] * m
    left = set(range(len(trips)))
    worst = 0
    while left:
        choice = None
        for i in left:
            _, c, wait, e2, loc2 = pick_car(cars, trips[i])
            # largest min-wait first; ties -> earlier request, lower index
            key = (-wait, trips[i][2], i)
            if choice is None or key < choice[0]:
                choice = (key, i, c, wait, e2, loc2)
        _, i, c, wait, e2, loc2 = choice
        cars[c] = (e2, loc2)
        left.remove(i)
        worst = max(worst, wait)
        if log is not None:
            log.append((i, c, wait))
    return worst


# ---------------------------------------------------------------- experiments

def random_instance(rng, n, grid, horizon):
    pt = lambda: (rng.randint(0, grid), rng.randint(0, grid))
    return [(pt(), pt(), rng.randint(0, horizon)) for _ in range(n)]


def summarise(name, opts, vals):
    pos = [(v / o) for v, o in zip(vals, opts) if o > 0]
    zero = [v for v, o in zip(vals, opts) if o == 0]
    return {
        "rule": name,
        "mean_max_wait": statistics.mean(vals),
        "pct_optimal": 100 * sum(v == o for v, o in zip(vals, opts)) / len(opts),
        "mean_ratio": statistics.mean(pos) if pos else float("nan"),
        "worst_ratio": max(pos) if pos else float("nan"),
        "opt_zero_cases": len(zero),
        "zero_found": sum(v == 0 for v in zero),
    }


def main():
    rng = random.Random(3821)
    grid, depot = 10, (5, 5)

    # 1. sanity check the exact solver against the naive one
    for _ in range(60):
        n, m = rng.randint(2, 5), rng.randint(1, 3)
        tr = random_instance(rng, n, grid, rng.choice([5, 20, 50]))
        a, b = optimal_max_wait(tr, m, depot), brute_force_check(tr, m, depot)
        assert a == b, (tr, m, a, b)
    print("Exact solver agrees with naive brute force on 60 small instances.\n")

    configs = [(m, n, T) for (m, n) in [(2, 8), (3, 8)] for T in (15, 40, 100)]
    instances = 150
    rows = []
    worst_example = None

    for m, n, T in configs:
        opts, fifos, mms = [], [], []
        for _ in range(instances):
            tr = random_instance(rng, n, grid, T)
            o = optimal_max_wait(tr, m, depot)
            f, mm = fifo(tr, m, depot), maxmin(tr, m, depot)
            assert o <= f and o <= mm
            opts.append(o); fifos.append(f); mms.append(mm)
            if o > 0:
                r = mm / o
                if worst_example is None or r > worst_example[0]:
                    worst_example = (r, tr, m, o, f, mm)
        for name, vals in (("OPT", opts), ("FIFO", fifos), ("MAXMIN", mms)):
            row = {"m": m, "n": n, "T": T, **summarise(name, opts, vals)}
            rows.append(row)
        print(f"done m={m} n={n} T={T}", file=sys.stderr)

    with open("results.csv", "w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        wr.writeheader()
        wr.writerows(rows)

    hdr = f"{'m':>2} {'n':>2} {'T':>4} {'rule':>7} {'mean W':>8} {'%opt':>6} {'mean r':>7} {'worst r':>8} {'OPT=0':>6} {'found0':>7}"
    print(hdr)
    for r in rows:
        print(f"{r['m']:>2} {r['n']:>2} {r['T']:>4} {r['rule']:>7} {r['mean_max_wait']:>8.2f} "
              f"{r['pct_optimal']:>6.1f} {r['mean_ratio']:>7.2f} {r['worst_ratio']:>8.2f} "
              f"{r['opt_zero_cases']:>6} {r['zero_found']:>7}")

    # worst MAXMIN instance, with traces
    r, tr, m, o, f, mm = worst_example
    print(f"\nWorst MAXMIN/OPT ratio found: {r:.2f}  (m={m}, OPT={o}, FIFO={f}, MAXMIN={mm})")
    for i, (s, w, t) in enumerate(tr):
        print(f"  trip {i}: s={s} w={w} t={t}")
    for name, fn in (("FIFO", fifo), ("MAXMIN", maxmin)):
        log = []
        fn(tr, m, depot, log)
        print(f"  {name} assignment order (trip, car, wait): {log}")


if __name__ == "__main__":
    main()
