"""Base problem, same seed and instances as the progression-check table, with batch bottleneck matching added."""
import random, statistics, itertools
from robotaxi_sim import dist, pick_car, fifo, maxmin, optimal_max_wait, random_instance, serve

def epd(trips, m, depot):
    cars = [(0, depot)] * m; worst = 0
    for i in sorted(range(len(trips)), key=lambda i: (trips[i][2] + dist(trips[i][0], trips[i][1]), trips[i][2], i)):
        _, c, wait, e2, loc2 = pick_car(cars, trips[i]); cars[c] = (e2, loc2); worst = max(worst, wait)
    return worst

def batch(trips, m, depot):
    """Take the next m trips in request order; assign them to distinct cars minimising the largest wait."""
    cars = [(0, depot)] * m; worst = 0
    order = sorted(range(len(trips)), key=lambda i: (trips[i][2], i))
    for k in range(0, len(order), m):
        B = order[k:k + m]; best = None
        for perm in itertools.permutations(range(m), len(B)):
            out = [serve(cars[c], trips[i]) for i, c in zip(B, perm)]
            key = (max(o[0] for o in out), sum(o[3] for o in out))
            if best is None or key < best[0]:
                best = (key, perm, out)
        _, perm, out = best
        for c, o in zip(perm, out):
            cars[c] = (o[1], o[2]); worst = max(worst, o[0])
    return worst

rng = random.Random(3821); grid, depot = 10, (5, 5)
for _ in range(60):
    n, m = rng.randint(2, 5), rng.randint(1, 3)
    random_instance(rng, n, grid, rng.choice([5, 20, 50]))
rules = [("FIFO", fifo), ("Max-min", maxmin), ("EPD", epd), ("Batch", batch)]
for m, n in [(2, 8), (3, 8)]:
    for T, lab in ((15, "Heavy"), (40, "Moderate"), (100, "Light")):
        opts = []; vals = {r: [] for r, _ in rules}
        for _ in range(150):
            tr = random_instance(rng, n, grid, T); o = optimal_max_wait(tr, m, depot); opts.append(o)
            for r, fn in rules:
                v = fn(tr, m, depot); assert v >= o; vals[r].append(v)
        zero = sum(o == 0 for o in opts)
        parts = []
        for r, _ in rules:
            pos = [v / o for v, o in zip(vals[r], opts) if o > 0]
            parts.append(f"{r}: {statistics.mean(pos):.2f} {max(pos):.2f} {100*sum(v==o for v,o in zip(vals[r],opts))/150:.1f}% z{sum(v==0 for v,o in zip(vals[r],opts) if o==0)}")
        print(f"m={m} {lab:<8} OPT0={zero} | " + " | ".join(parts), flush=True)
