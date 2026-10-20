"""Runs simulations. `run_one` is the single place that turns a run description into a
simulation, runs it, and writes `replay.json`, `metrics.json` and, for model brains,
`requests.jsonl`.
"""

import json
import os
import sys
from dataclasses import dataclass, field

from valley.brains import MODEL_BRAINS, make_brain
from valley.metrics import BlunderTally, compute_metrics
from valley.replay import build_replay, write_replay
from valley.simulation import Simulation
from valley.species import SPECIES_ORDER
from valley.world import DEFAULT_HEIGHT, DEFAULT_MAX_CREATURES, DEFAULT_WIDTH

PREY = ("rabbit", "deer")


@dataclass
class RunSpec:
    seed: int
    brains: dict  # species key -> brain spec such as "jev" or "rules"
    experiment: str = "run"
    days: int = 30
    width: int = DEFAULT_WIDTH
    height: int = DEFAULT_HEIGHT
    max_creatures: int = DEFAULT_MAX_CREATURES
    hesitate_below: float | None = None
    hesitation_label: str | None = None  # e.g. "h-p10"; defaults to "h{value}" when a threshold is set
    batch: int = 16
    workers: int = 4
    timeout: float = 30
    log_requests: bool = False
    cache_dir: str | None = None
    price_per_mtok: float | None = None  # price per million input tokens; money is only reported when given
    run_id: str | None = None
    options: dict = field(default_factory=dict)

    @property
    def brain_label(self) -> str:
        return brain_label(self.brains)

    @property
    def label(self) -> str:
        label = self.brain_label
        suffix = self.hesitation_label or (f"h{self.hesitate_below:g}" if self.hesitate_below is not None else None)
        return f"{label}-{suffix}" if suffix else label

    @property
    def id(self) -> str:
        return self.run_id or f"{self.experiment}-{self.label}-seed{self.seed}"

    @property
    def uses_model(self) -> bool:
        return any(is_model_brain(b) for b in self.brains.values())


def is_model_brain(spec: str) -> bool:
    return spec in MODEL_BRAINS or spec.startswith("system-one@")


def brain_label(brains: dict) -> str:
    """The brain name, or `wolf-{brain}_prey-{brain}` when wolves and prey differ."""
    specs = {brains[key] for key in SPECIES_ORDER}
    if len(specs) == 1:
        return _short(specs.pop())
    prey = {brains[key] for key in PREY}
    if len(prey) == 1:
        return f"wolf-{_short(brains['wolf'])}_prey-{_short(prey.pop())}"
    return "-".join(f"{key}-{_short(brains[key])}" for key in SPECIES_ORDER)


def _short(spec: str) -> str:
    return "system-one" if spec.startswith("system-one@") else spec


def build_brains(spec: RunSpec, out_dir: str | None) -> tuple[dict, list]:
    """One brain instance per distinct spec, shared by every species that uses it."""
    instances: dict[str, object] = {}
    log_path = os.path.join(out_dir, "requests.jsonl") if (out_dir and spec.log_requests) else None
    for brain_spec in spec.brains.values():
        if brain_spec not in instances:
            cache_path = None
            if spec.cache_dir:
                cache_path = os.path.join(spec.cache_dir, f"{_short(brain_spec)}.jsonl")
            instances[brain_spec] = make_brain(
                brain_spec, spec.seed, batch=spec.batch, workers=spec.workers, timeout=spec.timeout,
                log_path=log_path, cache_path=cache_path, **spec.options)
    return {key: instances[spec.brains[key]] for key in SPECIES_ORDER}, list(instances.values())


def run_one(spec: RunSpec, out_dir: str | None, progress=None) -> dict:
    """Run one simulation and write `replay.json`, `metrics.json` and, if asked, `requests.jsonl`."""
    log = None
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        log = os.path.join(out_dir, "requests.jsonl")
        if spec.log_requests and os.path.exists(log):
            os.remove(log)  # a rerun must not append to an older log
    brains, instances = build_brains(spec, out_dir)
    tally = BlunderTally()
    try:
        sim = Simulation(spec.seed, brains, days=spec.days, width=spec.width, height=spec.height,
                         max_creatures=spec.max_creatures, hesitate_below=spec.hesitate_below, tally=tally)
        sim.run(on_frame=progress)
    finally:
        for brain in instances:
            brain.close()
    replay = build_replay(sim, spec.id)
    metrics = compute_metrics(replay, spec.price_per_mtok)
    replay["summary"]["valid"] = metrics["valid"]
    paths, replay_bytes = {}, None
    if out_dir:
        paths["replay"] = os.path.join(out_dir, "replay.json")
        replay_bytes = write_replay(paths["replay"], replay)
        paths["metrics"] = os.path.join(out_dir, "metrics.json")
        with open(paths["metrics"], "w", encoding="utf-8") as handle:
            json.dump(metrics, handle, indent=2)
        if spec.log_requests and os.path.exists(log):
            paths["requests"] = log
    return {"sim": sim, "replay": replay, "metrics": metrics, "paths": paths, "replay_bytes": replay_bytes}


def stderr_progress(spec: RunSpec):
    """A progress callback that prints one line per simulated day to stderr."""
    def show(frame):
        step = frame["step"]
        if step % 24 == 0:
            pop = frame["pop"]
            print(f"  {spec.id}: day {step // 24}/{spec.days}  rabbits {pop['rabbit']}  deer {pop['deer']}  "
                  f"wolves {pop['wolf']}", file=sys.stderr, flush=True)
    return show
