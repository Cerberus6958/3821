# Robotaxi dispatch lab

A local web tool for the COMP3821 robotaxi project: write greedy dispatch heuristics as formulas, compare them with the true optimal schedule, and watch every algorithm's cars drive the same day side by side.

## The model

- Manhattan grid of `width × height` blocks, depot `o` at the centre.
- `m` identical cars start at the depot at time 0 and carry one passenger at a time.
- Trip `r_i = (s_i, w_i, t_i)`: pickup point, drop-off point, request time.
- Driving one block takes one minute. A car that finishes at `e` at point `w'` picks up trip `i` at `p_i = max(t_i, e + d(w', s_i))`.
- Wait of trip `i` is `p_i − t_i`. The objective is the **longest wait** `W = max_i (p_i − t_i)`, known in advance (offline).

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

1. **Day** (sidebar): generate a random day from a seed, or import one as JSON. Export the current day to share it with the group.
2. **Heuristics**: FIFO, Max-min and Regret are loaded to start with. Add presets or a blank formula with *Add heuristic*, and untick any you want to leave out. Up to 8 can be compared at once.
3. **Dispatch this day** (or Ctrl/Cmd + Enter) runs every ticked heuristic and the exact solver.
4. Views:
   - **Replay**: one map per algorithm (or all overlaid on one map). Play, pause, step one minute back or forward, jump to the start or end, drag the scrubber, or click a request on the timeline. Keyboard: Space, Left, Right, Home, End. The table underneath shows every trip's status at the current minute.
   - **Compare**: optimum (proven or best found plus a lower bound), each heuristic's longest wait and ratio to the optimum, other metrics, and the wait of every trip. Downloads as CSV and PNG.
   - **Experiments**: run many random days and get mean, median and worst ratios, a head-to-head win matrix and each heuristic's worst day (which opens in the replay). Or sweep one parameter (trips, cars, request window, grid size) and plot the ratio, the longest wait and the exact solver's run time against it.
   - **Counterexamples**: hill-climbs small days (up to 7 trips, solved exactly) to make a chosen heuristic look as bad as possible against the optimum or another heuristic. Useful for checking a claimed approximation ratio before trying to prove it.

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

## Layout

```
backend/   model, formula parser, heuristics, exact solvers, experiments, FastAPI app
frontend/  static site (plain ES modules, no build step)
tests/     pytest checks: solvers agree with brute force, presets, worked example
run.py     starts the server
```

## Credits

- [OR-Tools](https://developers.google.com/optimization) (Apache 2.0) for CP-SAT.
- [Chart.js](https://www.chartjs.org/) 4.4.4 (MIT), bundled in `frontend/vendor`.
- [Barlow](https://github.com/jpt/barlow) by Jeremy Tribby (SIL Open Font License), bundled in `frontend/vendor/fonts`.
- Built with help from Claude (Anthropic). See the project's "Use of AI tools" statement.
