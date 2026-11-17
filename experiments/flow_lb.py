"""Max-flow lower bound for the simplified (hub) problem.

Relaxation: a car may pause a trip and resume it later, possibly on another car (preemption with
migration). Trip i must do its a_i units of driving (to the pickup and then to the drop-off) inside
[t_i, t_i + F], and its b_i units of driving home inside [t_i + a_i, t_i + F + b_i]. Every real
schedule with maximum completion time F satisfies this, so the smallest feasible F is a lower bound
on OPT. Feasibility for a fixed F is a max-flow problem (Horn, 1974):
source -> piece (capacity = its length) -> time interval inside its window (capacity = interval
length) -> sink (capacity = m * interval length). F is feasible iff the max flow saturates the source.
"""
import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import maximum_flow


def feasible(jobs, m, F):
    pieces = []
    for t, a, p in jobs:
        if a > F:
            return False
        b = p - a
        pieces.append((a, t, t + F))
        if b > 0:
            pieces.append((b, t + a, t + F + b))
    bounds = sorted({x for _, lo, hi in pieces for x in (lo, hi)})
    idx = {x: k for k, x in enumerate(bounds)}
    P, K = len(pieces), len(bounds) - 1
    src, sink = 0, 1 + P + K
    rows, cols, caps = [], [], []
    for i, (size, lo, hi) in enumerate(pieces):
        rows.append(src); cols.append(1 + i); caps.append(size)
        for k in range(idx[lo], idx[hi]):
            rows.append(1 + i); cols.append(1 + P + k); caps.append(bounds[k + 1] - bounds[k])
    for k in range(K):
        rows.append(1 + P + k); cols.append(sink); caps.append(m * (bounds[k + 1] - bounds[k]))
    n = sink + 1
    G = csr_matrix((np.array(caps, dtype=np.int32), (rows, cols)), shape=(n, n))
    total = sum(size for size, _, _ in pieces)
    return maximum_flow(G, src, sink).flow_value == total


def lower_bound(jobs, m, hi):
    """Smallest integer F that the relaxation can achieve. `hi` must be achievable (e.g. a heuristic's value)."""
    lo = max(a for _, a, _ in jobs)
    while lo < hi:
        mid = (lo + hi) // 2
        if feasible(jobs, m, mid):
            hi = mid
        else:
            lo = mid + 1
    return lo


if __name__ == "__main__":
    import random, statistics
    from hub_exp import make, opt, dispatch
    rng = random.Random(3821)
    for m in (2, 3):
        for name, T in (("Heavy", 15), ("Moderate", 40), ("Light", 100)):
            r_lb, r_max, gain, bad, exact = [], [], [], 0, 0
            for _ in range(150):
                J = make(rng, 8, T)
                o = opt(J, m)
                fifo = dispatch(J, m, lambda x: x[0])[0]
                lb = lower_bound(J, m, int(fifo))
                ma = max(a for _, a, _ in J)
                bad += lb > o; exact += lb == o
                r_lb.append(lb / o); r_max.append(ma / o)
            print(f"m={m} {name:8s} LB/OPT mean {statistics.mean(r_lb):.3f} min {min(r_lb):.3f} | maxa/OPT mean {statistics.mean(r_max):.3f} | LB=OPT {100*exact/150:.1f}% | violations {bad}")
