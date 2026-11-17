"""Online experiment, simplified problem (Table 4): dispatch rules against the max-flow lower bound of flow_lb.py."""
import random, statistics
from hub_exp import dispatch
from online_exp_days import day, hub_jobs, mean_busy
from flow_lb import lower_bound

rng = random.Random(9801)
m, n, DAYS = 10, 400, 200
lams = [-1, 0, 1]
Ep = mean_busy(rng)
print("E[p] =", round(Ep, 2))
for rho in (0.7, 0.85, 0.95, 1.05):
    rate = rho * m / Ep
    mx = {l: [] for l in lams}; mean = {l: [] for l in lams}; ratio = {l: [] for l in lams}; lbs = []; longest = []
    for _ in range(DAYS):
        J = hub_jobs(day(rng, n, rate))
        res = {l: dispatch(J, m, lambda x, l=l: x[0] + l * x[1]) for l in lams}
        lb = lower_bound(J, m, int(min(r[0] for r in res.values())))
        lbs.append(lb); longest.append(max(j[1] for j in J))
        for l in lams:
            mx[l].append(res[l][0]); mean[l].append(res[l][1]); ratio[l].append(res[l][0] / lb)
    print(f"rho={rho} longest trip {statistics.mean(longest):.1f} flow bound {statistics.mean(lbs):.1f} | " + " | ".join(
        f"lam{l}: max {statistics.mean(mx[l]):.1f} ratio {statistics.mean(ratio[l]):.3f} worst {max(ratio[l]):.2f} mean {statistics.mean(mean[l]):.1f}" for l in lams), flush=True)
