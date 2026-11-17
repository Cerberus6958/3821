"""Online experiment, base problem: cars drive straight from one trip to the next, objective = longest wait.

Every rule is online: it only uses trips that have already been requested, and a car only starts
driving to a pickup once the trip has been requested. Days are generated exactly as in online_exp.py
(same seed, so the same days), so the load rho is the simplified problem's load.
"""
import random, statistics
from online_exp_days import DEPOT, d, day, mean_busy


def commit_fifo(trips, m):
    """On request, commit the trip to the car that will reach it soonest (cars keep a queue)."""
    cars = [(0, DEPOT)] * m; waits = []
    for s, w, t in trips:
        c = min(range(m), key=lambda c: (max(cars[c][0], t) + d(cars[c][1], s), d(cars[c][1], s), c))
        pickup = max(cars[c][0], t) + d(cars[c][1], s)
        waits.append(pickup - t); cars[c] = (pickup + d(s, w), w)
    return waits


def pool(trips, m, choose):
    """Requested trips wait in a pool. Whenever a car is free it takes the trip picked by `choose`."""
    free = [0] * m; loc = [DEPOT] * m; left = list(range(len(trips))); waits = []
    while left:
        now = max(min(free), trips[left[0]][2])
        idle = [c for c in range(m) if free[c] <= now]
        waiting = [i for i in left if trips[i][2] <= now]
        near = {i: min(idle, key=lambda c: (d(loc[c], trips[i][0]), c)) for i in waiting}
        i = choose(waiting, lambda i: d(loc[near[i]], trips[i][0]), now)
        c = near[i]; s, w, t = trips[i]
        pickup = now + d(loc[c], s)
        waits.append(pickup - t); free[c] = pickup + d(s, w); loc[c] = w; left.remove(i)
    return waits


def run(trips, m):
    T = trips
    return {
        "FIFO (commit)": commit_fifo(T, m),
        "FIFO": pool(T, m, lambda W, e, now: min(W, key=lambda i: (T[i][2], i))),
        "EPD": pool(T, m, lambda W, e, now: min(W, key=lambda i: (T[i][2] + d(T[i][0], T[i][1]), T[i][2], i))),
        "Max-min": pool(T, m, lambda W, e, now: max(W, key=lambda i: (now + e(i) - T[i][2], -T[i][2], -i))),
        "Nearest": pool(T, m, lambda W, e, now: min(W, key=lambda i: (e(i), T[i][2], i))),
    }


if __name__ == "__main__":
    rng = random.Random(9801)
    m, n, DAYS = 10, 400, 200
    Ep = mean_busy(rng)
    for rho in (0.7, 0.85, 0.95, 1.05):
        rate = rho * m / Ep
        mx, mean, comp = {}, {}, []
        for _ in range(DAYS):
            T = day(rng, n, rate)
            res = run(T, m)
            for k, w in res.items():
                mx.setdefault(k, []).append(max(w)); mean.setdefault(k, []).append(statistics.mean(w))
            # longest request-to-drop-off time under FIFO (commit), to compare with the simplified problem
            comp.append(max(w + d(s, e) for w, (s, e, t) in zip(res["FIFO (commit)"], T)))
        print(f"rho={rho} | " + " | ".join(f"{k}: max {statistics.mean(mx[k]):.1f} mean {statistics.mean(mean[k]):.1f}" for k in mx)
              + f" | FIFO (commit) longest completion {statistics.mean(comp):.1f}", flush=True)
