"""Simplified (hub) problem: exact optimum vs dispatch rules with key t + lam*a, n = 8 trips."""
import random, statistics, sys
INF = float("inf")
d = lambda u, v: abs(u[0] - v[0]) + abs(u[1] - v[1])

def make(rng, n, T, depot=(5, 5), grid=10):
    jobs = []
    for _ in range(n):
        s = (rng.randint(0, grid), rng.randint(0, grid)); w = (rng.randint(0, grid), rng.randint(0, grid))
        a = d(depot, s) + d(s, w)
        jobs.append((rng.randint(0, T), a, a + d(w, depot)))
    return jobs

def opt(jobs, m):
    n = len(jobs)
    g = [INF] * (1 << n); g[0] = 0
    def dfs(mask, free, cur):
        if cur < g[mask]:
            g[mask] = cur
        for i in range(n):
            if not mask & (1 << i):
                t, a, p = jobs[i]
                S = max(t, free)
                dfs(mask | (1 << i), S + p, max(cur, S + a - t))
    dfs(0, 0, 0)
    prev = [INF] * (1 << n); prev[0] = 0
    for _ in range(m):
        cur = [INF] * (1 << n); cur[0] = 0
        for mask in range(1, 1 << n):
            low = mask & -mask; rest = mask ^ low; sub = rest; best = INF
            while True:
                part = sub | low
                v = max(g[part], prev[mask ^ part])
                if v < best: best = v
                if sub == 0: break
                sub = (sub - 1) & rest
            cur[mask] = best
        prev = cur
    return prev[(1 << n) - 1]

def dispatch(jobs, m, key):
    free = [0] * m; left = set(range(len(jobs))); comp = []
    while left:
        c = min(range(m), key=lambda c: free[c])
        tau = max(free[c], min(jobs[j][0] for j in left))
        j = min((j for j in left if jobs[j][0] <= tau), key=lambda j: (key(jobs[j]), jobs[j][0], j))
        t, a, p = jobs[j]
        comp.append(tau + a - t); free[c] = tau + p; left.remove(j)
    return max(comp), statistics.mean(comp)

def planning_maxmin(jobs, m):
    """The original Max-min: looks at every unassigned trip, including ones not yet requested."""
    free = [0] * m; left = set(range(len(jobs))); comp = []
    while left:
        c = min(range(m), key=lambda c: free[c])
        j = max(left, key=lambda j: (max(jobs[j][0], free[c]) + jobs[j][1] - jobs[j][0], -jobs[j][0], -j))
        t, a, p = jobs[j]; S = max(t, free[c])
        comp.append(S + a - t); free[c] = S + p; left.remove(j)
    return max(comp), statistics.mean(comp)

RULES = [("FIFO", lambda J, m: dispatch(J, m, lambda x: x[0])),
         ("EPD0.5", lambda J, m: dispatch(J, m, lambda x: x[0] + 0.5 * x[1])),
         ("EPD", lambda J, m: dispatch(J, m, lambda x: x[0] + x[1])),
         ("EPD2", lambda J, m: dispatch(J, m, lambda x: x[0] + 2 * x[1])),
         ("AdjMM", lambda J, m: dispatch(J, m, lambda x: x[0] - x[1])),
         ("SPT", lambda J, m: dispatch(J, m, lambda x: x[1])),
         ("PlanMM", planning_maxmin)]

if __name__ == "__main__":
    rng = random.Random(3821)
    n = 8
    for m in (2, 3):
        for T, lab in ((15, "Heavy"), (40, "Moderate"), (100, "Light")):
            res = {r: [] for r, _ in RULES}; means = {r: [] for r, _ in RULES}
            for _ in range(150):
                J = make(rng, n, T); o = opt(J, m)
                for r, fn in RULES:
                    mx, mean = fn(J, m)
                    assert mx >= o
                    res[r].append(mx / o); means[r].append(mean)
            fm = statistics.mean(means["FIFO"])
            print(f"m={m} {lab:<8} " + " | ".join(
                f"{r}: {statistics.mean(res[r]):.3f} {max(res[r]):.2f} {100*sum(x==1 for x in res[r])/150:.1f}% avg{statistics.mean(means[r])/fm:.3f}"
                for r, _ in RULES), flush=True)
