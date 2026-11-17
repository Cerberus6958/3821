"""Replays the days of online_exp.py (same seed and draws) and adds the max-flow lower bound."""
import random, statistics, time
from hub_exp import dispatch
from online_exp_days import day
from flow_lb import lower_bound

rng = random.Random(9801)
m, n = 10, 400
lams = [-1, 0, 1]
Ep = statistics.mean(j[2] for j in day(rng, 20000, 1.0))
print("E[p] =", round(Ep, 2))
for rho in (0.7, 0.85, 0.95, 1.05):
    rate = rho * m / Ep
    mx = {l: [] for l in lams}; ratio = {l: [] for l in lams}; lbs = []; maxa = []
    t0 = time.time()
    for _ in range(200):
        J = day(rng, n, rate)
        res = {l: dispatch(J, m, lambda x, l=l: x[0] + l * x[1])[0] for l in lams}
        lb = lower_bound(J, m, int(min(res.values())))
        lbs.append(lb); maxa.append(max(j[1] for j in J))
        for l in lams:
            mx[l].append(res[l]); ratio[l].append(res[l] / lb)
    print(f"rho={rho} maxa {statistics.mean(maxa):.1f} flowLB {statistics.mean(lbs):.1f} | " + " | ".join(
        f"lam{l}: max {statistics.mean(mx[l]):.1f} ratio {statistics.mean(ratio[l]):.3f} worst {max(ratio[l]):.3f}" for l in lams),
        f"| {time.time()-t0:.0f}s", flush=True)
