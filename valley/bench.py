"""Runs simulations: one run for `run`, and whole experiments for `bench`.

`run_one` is the single place that turns a run description into a simulation,
runs it, and writes `replay.json`, `metrics.json` and, for model brains,
`requests.jsonl`. `bench` plans many runs, skips the ones that are already done,
and turns the results into `summary.json`, `summary.md` and charts. Benchmark
runs never use the response cache.
"""

import json
import os
import statistics
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from valley import charts
from valley.brains import MODEL_BRAINS, make_brain
from valley.metrics import BlunderTally, CALIBRATION_BINS, compute_metrics
from valley.replay import build_replay, write_replay
from valley.simulation import Simulation
from valley.species import SPECIES, SPECIES_ORDER
from valley.tuning import BENCH_SEEDS
from valley.world import DEFAULT_HEIGHT, DEFAULT_MAX_CREATURES, DEFAULT_WIDTH

PREY = ("rabbit", "deer")
EXPERIMENTS = ("survival", "hesitation", "rivals")
DEFAULT_BRAINS = {"survival": ("jev", "laya", "rules", "random"), "hesitation": ("jev",)}
# `bench` defaults to the first five benchmark seeds and to hesitation for Jev only, which keeps the set of
# model runs small (about 20). The full design is `--seeds` with all of BENCH_SEEDS and `--brains jev,laya`.
DEFAULT_SEEDS = BENCH_SEEDS[:5]
RIVALS = {"wolf-jev_prey-laya": {"wolf": "jev", "prey": "laya"},
          "wolf-laya_prey-jev": {"wolf": "laya", "prey": "jev"}}
HESITATION_LEVELS = ("off", "p10", "p25")
DECISIONS_PER_CREATURE_HOUR = 1.5  # the spec's estimate: starting creatures x steps x 1.5


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


def prepare_run(spec: RunSpec, out_dir: str | None):
    """Build the simulation and its brains, clearing any older request log. Returns (sim, instances)."""
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        log = os.path.join(out_dir, "requests.jsonl")
        if spec.log_requests and os.path.exists(log):
            os.remove(log)  # a rerun must not append to an older log
    brains, instances = build_brains(spec, out_dir)
    sim = Simulation(spec.seed, brains, days=spec.days, width=spec.width, height=spec.height,
                     max_creatures=spec.max_creatures, hesitate_below=spec.hesitate_below, tally=BlunderTally())
    return sim, instances


def finish_run(sim: Simulation, instances: list, spec: RunSpec, out_dir: str | None) -> dict:
    """Close the brains, then write `replay.json`, `metrics.json` and report where `requests.jsonl` is."""
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
        log = os.path.join(out_dir, "requests.jsonl")
        if spec.log_requests and os.path.exists(log):
            paths["requests"] = log
    return {"sim": sim, "replay": replay, "metrics": metrics, "paths": paths, "replay_bytes": replay_bytes}


def run_one(spec: RunSpec, out_dir: str | None, progress=None) -> dict:
    """Run one simulation and write `replay.json`, `metrics.json` and, if asked, `requests.jsonl`."""
    sim, instances = prepare_run(spec, out_dir)
    try:
        sim.run(on_frame=progress)
    finally:
        for brain in instances:
            brain.close()
    return finish_run(sim, instances, spec, out_dir)


def stderr_progress(spec: RunSpec):
    """A progress callback that prints one line per simulated day to stderr."""
    def show(frame):
        step = frame["step"]
        if step % 24 == 0:
            pop = frame["pop"]
            print(f"  {spec.id}: day {step // 24}/{spec.days}  rabbits {pop['rabbit']}  deer {pop['deer']}  "
                  f"wolves {pop['wolf']}", file=sys.stderr, flush=True)
    return show


# -- planning ------------------------------------------------------------------------------

def thresholds_path(base_dir: str) -> str:
    return os.path.join(base_dir, "hesitation", "thresholds.json")


def load_thresholds(path: str) -> dict:
    """The fixed hesitation thresholds, per brain, written by `python -m valley tune --thresholds`."""
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"{path} not found. Fix the hesitation thresholds from the smoke runs first: "
            f"python -m valley tune --thresholds <smoke run folders> -o {path}")
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)["brains"]


def plan_runs(experiment: str, seeds, days: int = 30, brains=None, thresholds: dict | None = None,
              **common) -> list[RunSpec]:
    """Every run of an experiment, in a fixed order."""
    specs: list[RunSpec] = []
    if experiment == "survival":
        for brain in brains or DEFAULT_BRAINS["survival"]:
            for seed in seeds:
                specs.append(RunSpec(seed, {k: brain for k in SPECIES_ORDER}, "survival", days, **common))
    elif experiment == "hesitation":
        for brain in brains or DEFAULT_BRAINS["hesitation"]:
            for level in HESITATION_LEVELS:
                value = None
                if level != "off":
                    if not thresholds or brain not in thresholds:
                        raise KeyError(f"no hesitation thresholds for the {brain} brain")
                    value = thresholds[brain][level]
                for seed in seeds:
                    specs.append(RunSpec(seed, {k: brain for k in SPECIES_ORDER}, "hesitation", days,
                                         hesitate_below=value, hesitation_label=f"h-{level}", **common))
    elif experiment == "rivals":
        for roles in RIVALS.values():
            for seed in seeds:
                mapping = {"rabbit": roles["prey"], "deer": roles["prey"], "wolf": roles["wolf"]}
                specs.append(RunSpec(seed, mapping, "rivals", days, **common))
    else:
        raise ValueError(f"unknown experiment {experiment!r}; use one of {', '.join(EXPERIMENTS)}")
    return specs


def run_dir(base_dir: str, spec: RunSpec) -> str:
    return os.path.join(base_dir, spec.experiment, spec.id)


def survival_twin(spec: RunSpec) -> RunSpec:
    """The survival run with the same brain and seed, which is the same configuration as hesitation `off`."""
    return RunSpec(spec.seed, dict(spec.brains), "survival", spec.days, batch=spec.batch, workers=spec.workers,
                   timeout=spec.timeout, max_creatures=spec.max_creatures)


def resolve_dir(base_dir: str, spec: RunSpec, reuse_survival: bool = True) -> tuple[str, str | None]:
    """Where a run's files live. Hesitation `off` runs reuse the matching survival run when it exists."""
    if reuse_survival and spec.experiment == "hesitation" and spec.hesitation_label == "h-off":
        twin = survival_twin(spec)
        if run_complete(run_dir(base_dir, twin), twin):
            return run_dir(base_dir, twin), twin.id
    return run_dir(base_dir, spec), None


def run_complete(directory: str, spec: RunSpec) -> bool:
    """True if the folder holds a finished run of exactly this seed and hesitation setting."""
    metrics_file = os.path.join(directory, "metrics.json")
    replay_file = os.path.join(directory, "replay.json")
    if not (os.path.exists(metrics_file) and os.path.exists(replay_file)):
        return False
    try:
        with open(metrics_file, encoding="utf-8") as handle:
            metrics = json.load(handle)
        return metrics.get("seed") == spec.seed and metrics.get("hesitate_below") == spec.hesitate_below
    except (OSError, ValueError):
        return False


def estimate(specs: list[RunSpec]) -> dict:
    """Decisions and requests for the runs that use a model: starting creatures x steps x 1.5."""
    starting = sum(s.start_count for s in SPECIES.values())
    decisions = sum(int(starting * spec.days * 24 * DECISIONS_PER_CREATURE_HOUR) for spec in specs)
    batch = specs[0].batch if specs else 16
    return {"runs": len(specs), "decisions": decisions, "requests": -(-decisions // batch), "batch": batch}


def confirm(question: str) -> bool:
    if not sys.stdin.isatty():
        return False
    return input(f"{question} [y/N] ").strip().lower() in ("y", "yes")


def run_experiment(experiment: str, base_dir: str = "results", seeds=DEFAULT_SEEDS, days: int = 30, brains=None,
                   jobs: int = 1, yes: bool = False, force: bool = False, summary_only: bool = False,
                   reuse_survival: bool = True, thresholds_file: str | None = None, out=print, **common) -> dict:
    """Plan an experiment, run what is missing, and write the summary. Returns what happened."""
    thresholds = None
    if experiment == "hesitation":
        thresholds = load_thresholds(thresholds_file or thresholds_path(base_dir))
    specs = plan_runs(experiment, seeds, days, brains, thresholds, log_requests=True, **common)
    todo = []
    for spec in specs:
        directory, reused = resolve_dir(base_dir, spec, reuse_survival)
        if reused is None and (force or not run_complete(directory, spec)):
            todo.append(spec)
    out(f"{experiment}: {len(specs)} runs planned, {len(specs) - len(todo)} already done, {len(todo)} to run")

    ran = []
    if todo and not summary_only:
        model_specs = [s for s in todo if s.uses_model]
        if model_specs:
            settings = {k: v for k, v in common.items() if k in ("batch", "workers", "timeout")}
            for brain in sorted({b for s in model_specs for b in s.brains.values() if is_model_brain(b)}):
                make_brain(brain, 0, **settings).close()  # fails early with a clear message if a key is missing
            est = estimate(model_specs)
            out(f"{est['runs']} runs call a model: about {est['decisions']:,} decisions and "
                f"{est['requests']:,} requests at batch {est['batch']}")
            if not yes and not confirm("Run them?"):
                out("not confirmed; nothing was run. Pass --yes to skip this question.")
                return {"specs": specs, "ran": [], "aborted": True}

        def work(item):
            index, spec = item
            result = run_one(spec, run_dir(base_dir, spec), progress=None)
            metrics = result["metrics"]
            out(f"[{index}/{len(todo)}] {spec.id}: {result['sim'].step_no} hours, "
                f"{'valid' if metrics['valid'] else 'INVALID'}")
            return spec.id

        items = list(enumerate(todo, start=1))
        if jobs > 1:
            with ThreadPoolExecutor(max_workers=jobs) as pool:
                ran = list(pool.map(work, items))
        else:
            ran = [work(item) for item in items]

    summary = summarise(base_dir, experiment, specs, reuse_survival, days)
    out(f"wrote {os.path.join(base_dir, experiment, 'summary.md')}")
    return {"specs": specs, "ran": ran, "summary": summary, "aborted": False}


# -- summarising ---------------------------------------------------------------------------

def _load_runs(base_dir: str, specs: list[RunSpec], reuse_survival: bool) -> tuple[list[dict], list[str]]:
    runs, missing = [], []
    for spec in specs:
        directory, reused = resolve_dir(base_dir, spec, reuse_survival)
        metrics_file = os.path.join(directory, "metrics.json")
        if not os.path.exists(metrics_file):
            missing.append(spec.id)
            continue
        with open(metrics_file, encoding="utf-8") as handle:
            metrics = json.load(handle)
        runs.append({"group": spec.label, "spec_id": spec.id, "dir": directory, "reused_from": reused,
                     "hesitation_label": spec.hesitation_label, "metrics": metrics})
    return runs, missing


def _median(values):
    values = [v for v in values if v is not None]
    return statistics.median(values) if values else None


def _mean(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def _population_series(runs: list[dict], steps: int) -> dict:
    """Median population per species at every step across the given runs; runs that ended early count as 0."""
    per_species = {key: [] for key in SPECIES_ORDER}
    for run in runs:
        with open(os.path.join(run["dir"], "replay.json"), encoding="utf-8") as handle:
            frames = json.load(handle)["frames"]
        for key in SPECIES_ORDER:
            counts = [f["pop"][key] for f in frames] + [0] * (steps + 1 - len(frames))
            per_species[key].append(counts[:steps + 1])
    return {key: [statistics.median(column) for column in zip(*series)] if series else []
            for key, series in per_species.items()}


def aggregate_group(runs: list[dict]) -> dict:
    """Totals and medians for one group of runs. Medians use only valid runs."""
    valid = [r for r in runs if r["metrics"]["valid"]]
    metrics = [r["metrics"] for r in valid]
    blunder_rates = [b["overall_blunder_rate"] for m in metrics for b in m["blunders"].values()
                     if b["overall_blunder_rate"] is not None]
    rules: dict[str, list] = {}
    for m in metrics:
        for b in m["blunders"].values():
            for rule, n in b["opportunities"].items():
                rules.setdefault(rule, [0, 0])[0] += n
            for rule, n in b["blunders"].items():
                rules.setdefault(rule, [0, 0])[1] += n
    calibration: dict[str, list] = {}
    for m in metrics:
        for brain, rows in m["calibration"].items():
            cells = calibration.setdefault(brain, [[0, 0.0] for _ in CALIBRATION_BINS])
            for cell, row in zip(cells, rows):
                cell[0] += row["decisions_with_opportunity"]
                if row["blunder_rate"] is not None:
                    cell[1] += row["blunder_rate"] * row["decisions_with_opportunity"]
    cost: dict[str, dict] = {}
    for m in metrics:
        for brain, c in m["cost"].items():
            entry = cost.setdefault(brain, {"decisions": 0, "requests": 0, "fallbacks": 0, "retries": 0,
                                            "input_tokens": 0, "output_tokens": 0, "p50": [], "p95": [],
                                            "hour_p50": [], "hour_p95": [], "input_cost": []})
            for key in ("decisions", "requests", "fallbacks", "retries", "input_tokens", "output_tokens"):
                entry[key] += c[key]
            entry["p50"].append(c["latency_ms_p50"])
            entry["p95"].append(c["latency_ms_p95"])
            entry["hour_p50"].append(c["seconds_per_valley_hour_p50"])
            entry["hour_p95"].append(c["seconds_per_valley_hour_p95"])
            if "input_cost" in c:
                entry["input_cost"].append(c["input_cost"])
    cost_out = {}
    for brain, e in cost.items():
        n = e["decisions"]
        cost_out[brain] = {
            "decisions": n, "requests": e["requests"], "fallbacks": e["fallbacks"], "retries": e["retries"],
            "fallback_rate": e["fallbacks"] / n if n else 0.0,
            "input_tokens_per_1000_decisions": 1000 * e["input_tokens"] / n if n else None,
            "output_tokens_per_1000_decisions": 1000 * e["output_tokens"] / n if n else None,
            "latency_ms_p50": _median(e["p50"]), "latency_ms_p95": _median(e["p95"]),
            "seconds_per_valley_hour_p50": _median(e["hour_p50"]),
            "seconds_per_valley_hour_p95": _median(e["hour_p95"]),
            "input_cost_total": sum(e["input_cost"]) if e["input_cost"] else None,
        }
    thresholds = {m["hesitate_below"] for m in metrics if m["hesitate_below"] is not None}
    return {
        "runs": len(runs),
        "valid_runs": len(valid),
        "median_hours_survived": _median(m["survival"]["hours_survived"] for m in metrics),
        "runs_all_species_alive": sum(m["survival"]["all_species_alive"] for m in metrics),
        "mean_population": {key: _mean(m["survival"]["mean_population"][key] for m in metrics)
                            for key in SPECIES_ORDER},
        "mean_blunder_rate": _mean(blunder_rates),
        "blunder_rates": blunder_rates,
        "rules": {rule: {"opportunities": v[0], "blunders": v[1]} for rule, v in rules.items()},
        "calibration": {brain: [{"bin": label, "decisions_with_opportunity": cell[0],
                                 "blunder_rate": cell[1] / cell[0] if cell[0] else None}
                                for label, cell in zip(CALIBRATION_BINS, cells)]
                        for brain, cells in calibration.items()},
        "hesitation_threshold": next(iter(thresholds)) if len(thresholds) == 1 else None,
        "hesitation_rate": _mean(m["hesitation"]["rate"] for m in metrics if m["hesitate_below"] is not None),
        "cost": cost_out,
    }


def summarise(base_dir: str, experiment: str, specs: list[RunSpec], reuse_survival: bool = True,
              days: int = 30) -> dict:
    """Write `summary.json`, `summary.md` and the charts for whatever runs exist."""
    runs, missing = _load_runs(base_dir, specs, reuse_survival)
    groups: dict[str, list[dict]] = {}
    for run in runs:
        groups.setdefault(run["group"], []).append(run)
    steps = days * 24
    aggregates = {group: aggregate_group(items) for group, items in groups.items()}
    summary = {
        "experiment": experiment,
        "seeds": sorted({s.seed for s in specs}),
        "days": days,
        "groups": aggregates,
        "runs": [{"run_id": r["spec_id"], "group": r["group"], "reused_from": r["reused_from"],
                  "metrics": r["metrics"]} for r in runs],
        "missing": missing,
    }
    out_dir = os.path.join(base_dir, experiment)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "summary.json"), "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)
    with open(os.path.join(out_dir, "summary.md"), "w", encoding="utf-8") as handle:
        handle.write(render_markdown(summary))
    if charts.available():
        _draw_charts(out_dir, groups, aggregates, steps)
    else:
        print("matplotlib is not installed, so the charts were skipped (pip install matplotlib)", file=sys.stderr)
    return summary


def _draw_charts(out_dir: str, groups: dict, aggregates: dict, steps: int) -> None:
    chart_dir = os.path.join(out_dir, "charts")
    os.makedirs(chart_dir, exist_ok=True)
    plotted = {g: [r for r in items if r["metrics"]["valid"]] for g, items in groups.items()}
    plotted = {g: items for g, items in plotted.items() if items}
    series = {g: _population_series(items, steps) for g, items in plotted.items()}
    charts.population_chart(os.path.join(chart_dir, "population.svg"), series,
                            {g: len(items) for g, items in plotted.items()})
    charts.blunders_chart(os.path.join(chart_dir, "blunders.svg"),
                          {g: aggregates[g]["blunder_rates"] for g in plotted})
    model_calibration = {}
    for group in plotted:
        for rows in aggregates[group]["calibration"].values():
            model_calibration[group] = rows
    charts.calibration_chart(os.path.join(chart_dir, "calibration.svg"), model_calibration)


# -- markdown ------------------------------------------------------------------------------

def _pct(value, digits=1):
    return "-" if value is None else f"{100 * value:.{digits}f}%"


def _num(value, digits=1):
    return "-" if value is None else f"{value:,.{digits}f}"


def _table(headers: list[str], rows: list[list]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    lines += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join(lines)


def render_markdown(summary: dict) -> str:
    groups = summary["groups"]
    seeds = ", ".join(str(s) for s in summary["seeds"])
    parts = [f"# {summary['experiment'].capitalize()} results", "",
             f"Seeds: {seeds}. Length: {summary['days']} days ({summary['days'] * 24} valley hours). "
             "Medians and charts use valid runs only (at most 2% fallbacks); every run is listed under *All runs*.", ""]
    if not groups:
        return "\n".join(parts + ["No runs have finished yet.", ""])

    hesitating = any(a["hesitation_threshold"] is not None for a in groups.values())
    headers = ["Brain", "Valid runs", "Median hours survived", "All species alive at the end",
               "Mean rabbits", "Mean deer", "Mean wolves"]
    if hesitating:
        headers += ["Hesitation threshold", "Share of decisions frozen"]
    rows = []
    for name, a in groups.items():
        row = [name, f"{a['valid_runs']}/{a['runs']}", _num(a["median_hours_survived"], 0),
               f"{a['runs_all_species_alive']}/{a['valid_runs']}",
               _num(a["mean_population"]["rabbit"]), _num(a["mean_population"]["deer"]),
               _num(a["mean_population"]["wolf"])]
        if hesitating:
            row += ["-" if a["hesitation_threshold"] is None else f"{a['hesitation_threshold']:.3f}",
                    _pct(a["hesitation_rate"])]
        rows.append(row)
    parts += ["## Survival", "", _table(headers, rows), ""]

    rows = [[name, _pct(a["mean_blunder_rate"]),
             "; ".join(f"{r.replace('_', ' ')} {v['blunders']}/{v['opportunities']}" for r, v in a["rules"].items()
                       if v["opportunities"])]
            for name, a in groups.items()]
    parts += ["## Blunders", "",
              "A blunder is a choice that is clearly bad given what the animal could see. "
              "The rate is blunders divided by opportunities; the last column gives blunders/opportunities per rule.", "",
              _table(["Brain", "Mean blunder rate", "By rule"], rows), ""]

    calibrated = {name: a for name, a in groups.items() if a["calibration"]}
    if calibrated:
        parts += ["## Calibration", "",
                  "Among model decisions with a blunder opportunity, the blunder rate by stated confidence. "
                  "A well-calibrated brain shows fewer blunders at higher confidence.", ""]
        headers = ["Confidence"] + [f"{n} ({m})" for n in calibrated for m in ("decisions", "blunder rate")]
        rows = []
        for i, label in enumerate(CALIBRATION_BINS):
            row = [label]
            for a in calibrated.values():
                cell = next(iter(a["calibration"].values()))[i]
                row += [f"{cell['decisions_with_opportunity']:,}", _pct(cell["blunder_rate"])]
            rows.append(row)
        parts += [_table(headers, rows), ""]

    cost_rows = []
    for name, a in groups.items():
        for brain, c in a["cost"].items():
            if not c["requests"] and not c["decisions"]:
                continue
            cost_rows.append([
                name, brain, f"{c['decisions']:,}", f"{c['requests']:,}", _pct(c["fallback_rate"], 2), f"{c['retries']:,}",
                _num(c["input_tokens_per_1000_decisions"], 0), _num(c["output_tokens_per_1000_decisions"], 0),
                f"{_num(c['latency_ms_p50'], 0)} / {_num(c['latency_ms_p95'], 0)}",
                f"{_num(c['seconds_per_valley_hour_p50'], 2)} / {_num(c['seconds_per_valley_hour_p95'], 2)}",
                "-" if c["input_cost_total"] is None else f"{c['input_cost_total']:.2f}",
            ])
    parts += ["## Cost and speed", "",
              "Totals over valid runs. Latency is per request, and the valley-hour pace is the wait for all of "
              "an hour's decisions. Baseline brains make no requests. The last column is input-token cost and "
              "appears only when a price was given.", "",
              _table(["Group", "Brain", "Decisions", "Requests", "Fallback rate", "Retries",
                      "Input tokens per 1,000", "Output tokens per 1,000", "Latency p50 / p95 (ms)",
                      "Seconds per hour p50 / p95", "Input cost"], cost_rows), ""]

    rows = []
    for run in summary["runs"]:
        m = run["metrics"]
        pop = m["survival"]["final_population"]
        rows.append([run["run_id"] + (f" (from {run['reused_from']})" if run["reused_from"] else ""),
                     "yes" if m["valid"] else "**no**", m["survival"]["hours_survived"],
                     f"{pop['rabbit']} / {pop['deer']} / {pop['wolf']}",
                     "yes" if m["survival"]["all_species_alive"] else "no", _pct(m["fallbacks"]["rate"], 2)])
    parts += ["## All runs", "",
              _table(["Run", "Valid", "Hours", "Final rabbits / deer / wolves", "All species alive", "Fallback rate"],
                     rows), ""]
    if summary["missing"]:
        parts += [f"Not yet run: {', '.join(summary['missing'])}", ""]
    return "\n".join(parts)
