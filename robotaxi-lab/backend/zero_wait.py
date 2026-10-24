"""Zero-wait schedules via bipartite matching (minimum path cover).

With zero waiting, trip i is picked up exactly at t_i, so a car can serve j right
after i only if t_i + d(s_i, w_i) + d(w_i, s_j) <= t_j, and a car can start with j
only if d(o, s_j) <= t_j. These "can follow" edges form a DAG, every car's day is a
path, and covering all trips with k cars is a matching problem (Dantzig &
Fulkerson, 1954; Vazifeh et al., 2018): each trip needs exactly one predecessor,
either another trip or one of the k car starts.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from .model import Instance, dist


def _edges(inst: Instance):
    trips = inst.trips
    n = inst.n
    order = sorted(range(n), key=lambda i: (trips[i].t, i))
    rank = {i: r for r, i in enumerate(order)}
    preds: List[List[int]] = [[] for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i != j and rank[i] < rank[j]:
                if trips[i].t + trips[i].ride + dist(trips[i].w, trips[j].s) <= trips[j].t:
                    preds[j].append(i)
    startable = [dist(inst.depot, trips[j].s) <= trips[j].t for j in range(n)]
    return preds, startable


def _cover_possible(n, preds, startable, k) -> bool:
    """Can every trip get a distinct predecessor (a trip, or one of k car starts)?"""
    # left nodes: trips 0..n-1 and starts n..n+k-1; right nodes: trips
    match_right: Dict[int, int] = {}

    def candidates(j):
        yield from preds[j]
        if startable[j]:
            yield from range(n, n + k)

    match_left: Dict[int, int] = {}

    def augment(j, seen):
        for left in candidates(j):
            if left in seen:
                continue
            seen.add(left)
            if left not in match_left or augment(match_left[left], seen):
                match_left[left] = j
                match_right[j] = left
                return True
        return False

    for j in range(n):
        if not augment(j, set()):
            return False
    return True


def zero_wait_analysis(inst: Instance) -> dict:
    n = inst.n
    if n == 0:
        return {"feasible_with_fleet": True, "min_fleet": 0}
    preds, startable = _edges(inst)
    if not _cover_possible(n, preds, startable, n):
        return {"feasible_with_fleet": False, "min_fleet": None}
    lo, hi = 1, n
    while lo < hi:
        mid = (lo + hi) // 2
        if _cover_possible(n, preds, startable, mid):
            hi = mid
        else:
            lo = mid + 1
    return {"feasible_with_fleet": lo <= inst.cars, "min_fleet": lo}
