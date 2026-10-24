"""HTTP API and static file server."""

from __future__ import annotations

import random
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .exact import ENUMERATION_LIMIT, HAVE_ORTOOLS
from .experiments import JobManager, compare, find_counterexample, run_batch, run_sweep
from .expr import FUNCTIONS, FormulaError
from .heuristics import CAR_VARIABLES, PRESETS, TRIP_VARIABLES, Heuristic
from .model import Instance, random_instance

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
MAX_TRIPS = 300
app = FastAPI(title="Robotaxi dispatch lab")
jobs = JobManager()


class HeuristicIn(BaseModel):
    id: str = ""
    name: str = "Heuristic"
    car_formula: str
    trip_formula: str


class ExactIn(BaseModel):
    enabled: bool = True
    time_limit: float = Field(20, ge=0.5, le=600)
    workers: int = Field(4, ge=1, le=32)


class RandomIn(BaseModel):
    n: int = Field(10, ge=1, le=MAX_TRIPS)
    cars: int = Field(2, ge=1, le=50)
    width: int = Field(10, ge=2, le=40)
    horizon: int = Field(40, ge=0, le=5000)
    seed: Optional[int] = None
    min_ride: int = Field(1, ge=0, le=40)


class CompareIn(BaseModel):
    instance: dict
    heuristics: List[HeuristicIn]
    exact: ExactIn = ExactIn()


class BatchConfig(BaseModel):
    n: int = Field(8, ge=1, le=MAX_TRIPS)
    cars: int = Field(2, ge=1, le=50)
    width: int = Field(10, ge=2, le=40)
    horizon: int = Field(40, ge=0, le=5000)
    instances: int = Field(50, ge=1, le=2000)
    seed: int = 3821
    reference: str = Field("optimal", pattern="^(optimal|best_heuristic)$")


class BatchIn(BaseModel):
    config: BatchConfig
    heuristics: List[HeuristicIn]
    exact: ExactIn = ExactIn(time_limit=10)


class SweepConfig(BatchConfig):
    variable: str = Field("n", pattern="^(n|cars|horizon|width)$")
    values: List[int] = Field(default_factory=lambda: [4, 6, 8, 10, 12])
    instances: int = Field(10, ge=1, le=500)


class SweepIn(BaseModel):
    config: SweepConfig
    heuristics: List[HeuristicIn]
    exact: ExactIn = ExactIn(time_limit=10)


class CounterConfig(BaseModel):
    n: int = Field(5, ge=2, le=7)
    cars: int = Field(2, ge=1, le=6)
    width: int = Field(10, ge=2, le=40)
    horizon: int = Field(20, ge=0, le=500)
    iterations: int = Field(800, ge=10, le=20000)
    seed: int = 1
    objective: str = Field("ratio", pattern="^(ratio|gap)$")


class CounterIn(BaseModel):
    config: CounterConfig
    target: HeuristicIn
    opponent: Optional[HeuristicIn] = None


def _heuristics(items: List[HeuristicIn]) -> List[Heuristic]:
    if not items:
        raise HTTPException(400, "Add at least one heuristic.")
    out = []
    for h in items:
        try:
            out.append(Heuristic.from_dict(h.model_dump()))
        except FormulaError as exc:
            raise HTTPException(400, f"{h.name}: {exc}")
    return out


def _instance(d: dict) -> Instance:
    try:
        inst = Instance.from_dict(d)
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(400, f"Invalid instance: {exc}")
    if inst.n > MAX_TRIPS:
        raise HTTPException(400, f"Instances are limited to {MAX_TRIPS} trips.")
    return inst


@app.exception_handler(FormulaError)
async def formula_error(_, exc: FormulaError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.get("/api/meta")
def meta():
    return {
        "presets": PRESETS,
        "car_variables": CAR_VARIABLES,
        "trip_variables": TRIP_VARIABLES,
        "functions": sorted(FUNCTIONS),
        "have_ortools": HAVE_ORTOOLS,
        "enumeration_limit": ENUMERATION_LIMIT,
        "max_trips": MAX_TRIPS,
    }


@app.post("/api/heuristics/validate")
def validate(h: HeuristicIn):
    try:
        Heuristic.from_dict(h.model_dump())
    except FormulaError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True}


@app.post("/api/instance/random")
def make_random(body: RandomIn):
    seed = body.seed if body.seed is not None else random.randrange(1, 10**6)
    inst = random_instance(random.Random(seed), body.n, body.cars, width=body.width, horizon=body.horizon,
                           min_ride=body.min_ride, seed=seed)
    return inst.to_dict()


@app.post("/api/compare")
def compare_endpoint(body: CompareIn):
    inst = _instance(body.instance)
    hs = _heuristics(body.heuristics)
    try:
        return compare(inst, hs, body.exact.model_dump())
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/jobs/batch")
def start_batch(body: BatchIn):
    hs = _heuristics(body.heuristics)
    cfg, exact = body.config.model_dump(), body.exact.model_dump()
    return {"job": jobs.start("batch", lambda progress, stop: run_batch(cfg, hs, exact, progress))}


@app.post("/api/jobs/sweep")
def start_sweep(body: SweepIn):
    hs = _heuristics(body.heuristics)
    if not body.config.values or len(body.config.values) > 25:
        raise HTTPException(400, "Give between 1 and 25 values to sweep over.")
    cfg, exact = body.config.model_dump(), body.exact.model_dump()
    return {"job": jobs.start("sweep", lambda progress, stop: run_sweep(cfg, hs, exact, progress))}


@app.post("/api/jobs/counterexample")
def start_counter(body: CounterIn):
    target = _heuristics([body.target])[0]
    opponent = _heuristics([body.opponent])[0] if body.opponent else None
    cfg = body.config.model_dump()
    return {"job": jobs.start("counterexample",
                              lambda progress, stop: find_counterexample(cfg, target, opponent, progress, stop))}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "No such job.")
    return job


@app.post("/api/jobs/{job_id}/cancel")
def job_cancel(job_id: str):
    if not jobs.cancel(job_id):
        raise HTTPException(404, "No such job.")
    return {"ok": True}


@app.get("/")
def index():
    return FileResponse(FRONTEND / "index.html")


app.mount("/", StaticFiles(directory=FRONTEND), name="static")
