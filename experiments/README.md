# Experiments for the final report

Standalone Python scripts that produce every table and figure in the report. Each uses a fixed random seed, so rerunning it gives the same numbers.

```bash
cd experiments
pip install numpy scipy        # only flow_lb.py and online_lb.py need these
python3 base_exp.py
```

| Script | What it produces | Report |
|---|---|---|
| `base_exp.py` | Base problem: FIFO, Max-min, EPD and batch matching against the exact optimum, plus zero-wait counts (150 days per setting, n = 8) | Table 1, Section 5.4 |
| `hub_exp.py` | Simplified problem: FIFO, EPD, adjusted Max-min, shortest trip first and the original Max-min against the exact optimum | Table 3 |
| `sweep.py` | Dispatch rules with key `t + λ·a` for λ from −2 to 2 | Figure 2, Appendix D |
| `verify_bounds.py` | Checks the dispatch-rule bound against the exact optimum on 7,000 random days | Section 6.2 |
| `online_exp.py` | Simplified problem online: Poisson arrivals around √d random hotspots, 400 trips, 10 cars, 200 days per load, with the flow bound and each rule's ratio to it | Table 4 |
| `online_base.py` | Base problem online on the same days: Commit and the pool rules (FIFO, EPD, Max-min, Nearest) | Table 5 |
| `flow_lb.py` | The max-flow lower bound (Horn, 1974), and its check against the exact optimum on 900 days | Section 7.1, Appendix C |
| `robotaxi_sim.py` | Base-problem model and exact solver used by `base_exp.py` | |
| `online_exp_days.py` | The day generator shared by `online_exp.py` and `online_base.py` | |

The interactive simulator in `robotaxi-lab/` implements the same three problems; its tests check that its solvers and rules agree with brute force and with these scripts.
