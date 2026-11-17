"""Simplified problem: dispatch rules with key t + lambda*a for lambda from -2 to 2 (Figure 2 and Appendix C)."""
import random, statistics
from hub_exp import make, opt, dispatch
rng = random.Random(2026)
lams = [-2, -1.5, -1, -0.5, 0, 0.5, 1, 1.5, 2]
keys = {f"lam{l}": (lambda x, l=l: x[0] + l * x[1]) for l in lams}
keys["t+b"] = lambda x: x[0] + (x[2] - x[1])
keys["t+b-a"] = lambda x: x[0] + (x[2] - x[1]) - x[1]
for m, T in ((2, 15), (3, 15), (2, 40), (3, 40)):
    R = {k: [] for k in keys}; M = {k: [] for k in keys}
    for _ in range(300):
        J = make(rng, 8, T); o = opt(J, m)
        for k, f in keys.items():
            mx, mean = dispatch(J, m, f); R[k].append(mx / o); M[k].append(mean)
    fm = statistics.mean(M["lam0"])
    print(m, T, " ".join(f"{k}:{statistics.mean(R[k]):.3f}/{max(R[k]):.2f}/{statistics.mean(M[k])/fm:.3f}" for k in keys), flush=True)
