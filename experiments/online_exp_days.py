"""Online days: Poisson arrivals, with pickups and drop-offs drawn around demand hotspots.

A d x d town has round(sqrt(d)) hotspots, placed uniformly at random for each day. Each pickup and
drop-off is drawn, with probability SHARE, from a normal distribution (standard deviation SD blocks)
around a random hotspot, and otherwise uniformly from the grid.
"""
import math, random, statistics

GRID, DEPOT = 20, (10, 10)
K = round(math.sqrt(GRID))          # number of hotspots: 4 for a 20 x 20 town
SHARE, SD = 0.7, 2.0
d = lambda u, v: abs(u[0] - v[0]) + abs(u[1] - v[1])


def hotspots(rng):
    return [(rng.randint(0, GRID), rng.randint(0, GRID)) for _ in range(K)]


def point(rng, hot):
    if rng.random() < SHARE:
        h = rng.choice(hot)
        return (min(GRID, max(0, round(rng.gauss(h[0], SD)))), min(GRID, max(0, round(rng.gauss(h[1], SD)))))
    return (rng.randint(0, GRID), rng.randint(0, GRID))


def day(rng, n, rate):
    """Returns a list of trips (s, w, t) with integer request times."""
    hot = hotspots(rng)
    t, trips = 0.0, []
    for _ in range(n):
        t += rng.expovariate(rate)
        s, w = point(rng, hot), point(rng, hot)
        while w == s:
            w = point(rng, hot)
        trips.append((s, w, int(t)))
    return trips


def hub_jobs(trips):
    """(t, a, p) for the simplified problem."""
    return [(t, d(DEPOT, s) + d(s, w), d(DEPOT, s) + d(s, w) + d(w, DEPOT)) for s, w, t in trips]


def mean_busy(rng, layouts=2000, per=10):
    """Mean time a trip occupies a car in the simplified problem, over random hotspot layouts."""
    tot = 0
    for _ in range(layouts):
        for s, w, _ in day(rng, per, 1.0):
            tot += d(DEPOT, s) + d(s, w) + d(w, DEPOT)
    return tot / (layouts * per)
