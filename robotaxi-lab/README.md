# Robotaxi dispatch lab

A local web tool for the COMP3821 robotaxi project: write greedy dispatch heuristics as formulas, compare them with the true optimal schedule, and watch every algorithm's cars drive the same day side by side.

The switch at the top of the page chooses one of three problems. Each keeps its own heuristics, day and experiment settings.

| Problem | Model | Objective | Measured against |
|---|---|---|---|
| **Base problem** | Cars drive straight from one trip to the next | Longest wait (request to pickup) | True optimum (exhaustive search or CP-SAT) |
| **Simplified** | Cars return to the depot after every trip and can't leave before the request | Longest completion time (request to drop-off) | True optimum (exhaustive search, up to 9 trips), or the max-flow lower bound |
| **Online** | Simplified model, trips arriving over the day as a Poisson process around demand hotspots | Longest completion time | Max-flow lower bound (true optimum for days up to 9 trips) |

## The base problem

- Manhattan grid of `width × height` blocks, depot `o` at the centre.
- `m` identical cars start at the depot at time 0 and carry one passenger at a time.
- Trip `r_i = (s_i, w_i, t_i)`: pickup point, drop-off point, request time.
- Driving one block takes one minute. A car that finishes at `e` at point `w'` picks up trip `i` at `p_i = max(t_i, e + d(w', s_i))`.
- Wait of trip `i` is `p_i − t_i`. The objective is the **longest wait** `W = max_i (p_i − t_i)`, known in advance (offline).

## The simplified and online problems

- A car serves trip `i` by leaving the depot at `S_i ≥ t_i`, driving to `s_i`, carrying the passenger to `w_i` and driving home. With `a_i = d(o, s_i) + d(s_i, w_i)` and `b_i = d(w_i, o)`, the passenger is dropped off at `S_i + a_i` and the car is free again at `S_i + a_i + b_i`.
- Completion time of trip `i` is `S_i + a_i − t_i`; the objective is the **longest completion time**.
- Heuristics are **dispatch rules**: whenever a car is free, it starts the waiting trip with the smallest key. You write the key. The key `t + λ·a` gives the family from the report: `t` is FIFO, `t + a` is EPD and `t − a` is adjusted Max-min, each provably within `5 + |λ| − 1/m` of optimal.
- In the simplified problem a rule can tick **Look ahead**, letting a free car commit to a trip that hasn't been requested yet and wait for it, as our original Max-min does. That needs the future, so it isn't allowed online.
- **Online days** have Poisson arrivals. A `d × d` town has `√d` hotspots (rounded, so 4 on a 20 × 20 grid), placed at random for each day and drawn on the map. Each pickup and drop-off comes, with probability 0.7, from a normal distribution around one of them, and otherwise uniformly from the grid. The arrival rate is set by the **load**, the share of the fleet's capacity the requests demand: `rate × E[busy time per trip] / cars`.
- **Max-flow lower bound** (Horn, 1974). If trips could be paused and resumed, even on another car, checking whether a longest completion time `F` is achievable is a maximum-flow problem: each trip's `a_i` units of driving must fit in `[t_i, t_i + F]` and its drive home in `[t_i + a_i, t_i + F + b_i]`. A binary search finds the smallest feasible `F`, which is a lower bound on the optimum computed in polynomial time. Ratios against it are marked `≤`, because the true ratio is at most that.

| Rule | Key | Bound |
|---|---|---|
| FIFO | `t` | 5 − 1/m |
| EPD | `t + a` | 6 − 1/m |
| Adjusted Max-min | `t - a` | 6 − 1/m |
| Shortest trip first | `a, t` | none (long trips starve) |
| Max-min (original, looks ahead) | `-completion, t` | none, offline only |

Key variables: `t`, `a`, `b`, `p`, `ride`, `depot_dist`, `now`, `waited`, `start`, `completion`, `i`, `n_left` (descriptions under *Formula reference* in the app).

## Running it

Needs Python 3.10 or newer.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python run.py                    # opens http://127.0.0.1:8000
```

Options: `python run.py --port 8080 --no-browser`.

`ortools` provides the CP-SAT solver used for days with more than 7 trips. If it fails to install, the app still runs and computes the optimum by exhaustive search for up to 9 trips.

Run the tests with:

```bash
pip install pytest
python -m pytest -q
```

## Using it

1. **Problem** (top right): base, simplified or online.
2. **Day** (sidebar): generate a random day from a seed, or import one as JSON. Export the current day to share it with the group. Online days are set by trips, cars, grid size and load instead of a request window.
3. **Heuristics**: three or four presets are loaded the first time you open each problem (for the base problem FIFO, Max-min and EPD). Add presets or a blank formula with *Add heuristic*, and untick any you want to leave out. Up to 8 can be compared at once.
4. **Dispatch this day** (or Ctrl/Cmd + Enter) runs every ticked heuristic and the exact solver (or the flow bound).
5. Views:
   - **Replay**: one map per algorithm (or all overlaid on one map). Play, pause, step one minute back or forward, jump to the start or end, drag the scrubber, or click a request on the timeline. Keyboard: Space, Left, Right, Home, End. The table underneath shows every trip's status at the current minute.
   - **Compare**: optimum (proven or best found plus a lower bound), each heuristic's longest wait and ratio to the optimum, other metrics, and the wait of every trip. Downloads as CSV and PNG.
   - **Experiments**: run many random days and get mean, median and worst ratios, a head-to-head win matrix and each heuristic's worst day (which opens in the replay). Or sweep one parameter (trips, cars, request window, grid size) and plot the ratio, the longest wait and the exact solver's run time against it.
   - **Counterexamples** (base and simplified problems): hill-climbs small days (up to 7 trips, solved exactly) to make a chosen heuristic look as bad as possible against the optimum or another heuristic. Useful for checking a claimed approximation ratio before trying to prove it.

## Writing a heuristic

Every heuristic here is the same greedy loop:

```
while trips remain:
    for each remaining trip, find the car with the smallest CAR score
    assign the trip with the smallest TRIP score to that car (end of its route)
```

You write the two scores. Separate several expressions with commas to break ties in order, and minimise a negative to prefer large values.

| Heuristic | Car formula | Trip formula |
|---|---|---|
| FIFO | `wait, empty` | `t` |
| Max-min (largest minimum wait first) | `wait, empty` | `-best_wait, t` |
| Regret | `wait, empty` | `-regret, -best_wait, t` |
| Nearest car | `empty, wait` | `t` |

Car formula variables (this trip on this car): `wait`, `pickup`, `arrive`, `idle`, `empty`, `finish`, `free_at`, `car`, `car_trips`, `t`, `ride`, `depot_dist`.

Trip formula variables (this trip's best and second-best cars): `t`, `ride`, `i`, `best_wait`, `second_wait`, `regret`, `worst_wait`, `mean_wait`, `best_pickup`, `best_empty`, `best_finish`, `depot_dist`, `n_left`.

Functions: `min`, `max`, `abs`, `sqrt`, `log`, `floor`, `ceil`, and `a if condition else b`. The full descriptions are under *Formula reference* in the app. Formulas are parsed with a restricted expression checker, so only arithmetic on these names is allowed.

## How the optimum is computed

- Up to 7 trips: exhaustive search over trip orders and car assignments (exact).
- More trips: Google OR-Tools CP-SAT, modelled as a multi-vehicle path cover with `AddMultipleCircuit`, seeded with the best heuristic schedule. If it hits the time limit, the app reports the best schedule found and the solver's lower bound, and ratios are shown as "at least".
- Also reported: a simple lower bound (`max_j d(o, s_j) − t_j`) and the smallest fleet that makes every wait zero (minimum path cover via bipartite matching).
- Simplified and online problems: exhaustive search up to 9 trips, and the max-flow lower bound above for every day (OR-Tools' max-flow solver, or a plain-Python fallback if OR-Tools is missing).

## Layout

```
backend/   model, formula parser, heuristics, exact solvers, experiments, FastAPI app
           hub.py: simplified and online problems (dispatch rules, exact search, flow bound, online days)
frontend/  static site (plain ES modules, no build step)
tests/     pytest checks: solvers agree with brute force, presets, worked example, dispatch-rule bounds, flow bound
run.py     starts the server
```

## Credits

- [OR-Tools](https://developers.google.com/optimization) (Apache 2.0) for CP-SAT.
- [Chart.js](https://www.chartjs.org/) 4.4.4 (MIT), bundled in `frontend/vendor`.
- [Barlow](https://github.com/jpt/barlow) by Jeremy Tribby (SIL Open Font License), bundled in `frontend/vendor/fonts`.
- Built with help from Claude (Anthropic). See the project's "Use of AI tools" statement.
