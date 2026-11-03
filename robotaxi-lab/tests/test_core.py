"""Correctness checks. Run with:  python -m pytest -q"""

import itertools
import random

import pytest

from backend.exact import HAVE_ORTOOLS, enumerate_optimal, solve_cpsat
from backend.expr import FormulaError, compile_formula
from backend.heuristics import PRESETS, Heuristic
from backend.model import Instance, Trip, dist, random_instance, simulate
from backend.zero_wait import zero_wait_analysis

PRESET = {p["id"]: Heuristic.from_dict(p) for p in PRESETS}


def naive_optimum(inst: Instance) -> int:
    """Independent brute force: every assignment, every order per car."""
    best = float("inf")
    for assign in itertools.product(range(inst.cars), repeat=inst.n):
        groups = [[i for i in range(inst.n) if assign[i] == c] for c in range(inst.cars)]
        worst = 0
        for grp in groups:
            gbest = min((simulate(Instance(inst.width, inst.height, inst.depot, 1,
                                           [inst.trips[i] for i in order]),
                                  [list(range(len(order)))]).max_wait
                         for order in itertools.permutations(grp)), default=0)
            worst = max(worst, gbest)
        best = min(best, worst)
    return best


# Reference implementations of the two greedies from the original experiment script.
def ref_pick(cars, tr):
    best = None
    for c, (e, loc) in enumerate(cars):
        empty = dist(loc, tr.s)
        pickup = max(tr.t, e + empty)
        key = (pickup - tr.t, empty, c)
        if best is None or key < best[0]:
            best = (key, c, pickup - tr.t, pickup + tr.ride, tr.w)
    return best


def ref_fifo(inst):
    cars = [(0, inst.depot)] * inst.cars
    worst = 0
    for i in sorted(range(inst.n), key=lambda i: (inst.trips[i].t, i)):
        _, c, wait, e2, loc2 = ref_pick(cars, inst.trips[i])
        cars[c] = (e2, loc2)
        worst = max(worst, wait)
    return worst


def ref_maxmin(inst):
    cars = [(0, inst.depot)] * inst.cars
    left = set(range(inst.n))
    worst = 0
    while left:
        choice = None
        for i in left:
            _, c, wait, e2, loc2 = ref_pick(cars, inst.trips[i])
            key = (-wait, inst.trips[i].t, i)
            if choice is None or key < choice[0]:
                choice = (key, i, c, wait, e2, loc2)
        _, i, c, wait, e2, loc2 = choice
        cars[c] = (e2, loc2)
        left.remove(i)
        worst = max(worst, wait)
    return worst


def test_enumeration_matches_naive_bruteforce():
    rng = random.Random(1)
    for _ in range(40):
        inst = random_instance(rng, rng.randint(1, 5), rng.randint(1, 3), horizon=rng.choice([5, 20, 60]))
        assert enumerate_optimal(inst).value == naive_optimum(inst)


@pytest.mark.skipif(not HAVE_ORTOOLS, reason="OR-Tools not installed")
def test_cpsat_matches_enumeration():
    rng = random.Random(2)
    for _ in range(25):
        inst = random_instance(rng, rng.randint(2, 8), rng.randint(1, 3), horizon=rng.choice([10, 30, 80]))
        res = solve_cpsat(inst, time_limit=20, workers=2)
        assert res.proven
        assert res.value == enumerate_optimal(inst).value


def test_presets_match_original_experiment():
    rng = random.Random(3)
    for _ in range(60):
        inst = random_instance(rng, rng.randint(1, 12), rng.randint(1, 4), horizon=rng.choice([10, 40, 100]))
        assert PRESET["fifo"].run(inst).max_wait == ref_fifo(inst)
        assert PRESET["maxmin"].run(inst).max_wait == ref_maxmin(inst)


def test_worked_example_from_progression_review():
    inst = Instance(10, 10, (5, 5), 2, [
        Trip((10, 3), (8, 6), 6), Trip((9, 0), (1, 10), 7),
        Trip((1, 1), (2, 9), 10), Trip((1, 8), (7, 6), 0),
    ])
    assert enumerate_optimal(inst).value == 16
    assert PRESET["fifo"].run(inst).max_wait == 16
    assert PRESET["maxmin"].run(inst).max_wait == 37


def test_zero_wait_matches_optimum():
    rng = random.Random(4)
    for _ in range(80):
        inst = random_instance(rng, rng.randint(1, 7), rng.randint(1, 3), horizon=rng.choice([20, 60, 150]))
        assert zero_wait_analysis(inst)["feasible_with_fleet"] == (enumerate_optimal(inst).value == 0)


@pytest.mark.parametrize("bad", [
    "__import__('os')", "wait.real", "'text'", "min", "(lambda: 1)()", "[wait]", "wait[0]",
    "unknown_var", "open('x')", "wait ** wait", "max(wait, key=1)",
])
def test_formula_rejects_unsafe_input(bad):
    with pytest.raises(FormulaError):
        compile_formula(bad, {"wait"})


def test_formula_tuple_and_functions():
    f = compile_formula("-wait, min(wait, 3), 2 if wait > 1 else 0", {"wait"})
    assert f({"wait": 5}) == (-5.0, 3.0, 2.0)
