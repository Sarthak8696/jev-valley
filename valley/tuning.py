"""Checks the balance targets of spec 5.5 for the offline brains.

The targets keep the `rules` baseline good but not perfect, so a better brain has
room to do better and a worse one can visibly do worse. Target 1 was raised from
5 to 8 of 10 seeds, and target 5 added, when the ecosystem was redesigned: see the
Decisions log of docs/build-spec.md.
"""

import json
import math
import os
from multiprocessing import Pool

from valley.brains import make_brain
from valley.simulation import Simulation
from valley.species import SPECIES, SPECIES_ORDER, species_cap
from valley.world import DEFAULT_MAX_CREATURES

BENCH_SEEDS = (3, 7, 11, 19, 23, 42, 57, 64, 88, 101)

MIN_RULES_ALL_ALIVE = 8  # of 10 seeds
MIN_RULES_BOOM_BUST = 3
MIN_RANDOM_EXTINCTIONS = 7
BOOM_BUST_DROP = 0.30


def simulate_offline(brain_name: str, seed: int, days: int = 30,
                     max_creatures: int = DEFAULT_MAX_CREATURES, questions: str = "rich") -> dict:
    """Run one offline brain for every species and return the population series."""
    brain = make_brain(brain_name, seed)
    sim = Simulation(seed, {key: brain for key in SPECIES}, days=days, max_creatures=max_creatures,
                     questions=questions)
    sim.run()
    return {
        "brain": brain_name, "seed": seed, "days": days,
        "pops": [[f["pop"][key] for key in SPECIES_ORDER] for f in sim.frames],
    }


def species_caps(max_creatures: int) -> dict:
    return {key: species_cap(key, max_creatures) for key in SPECIES_ORDER}


def rabbit_boom_bust(rabbits: list[int], drop: float = BOOM_BUST_DROP) -> bool:
    """True if the rabbit population rises above its start, then falls by at least `drop` from its peak."""
    peak = max(range(len(rabbits)), key=lambda i: (rabbits[i], -i))
    return rabbits[peak] > rabbits[0] and min(rabbits[peak:]) <= (1 - drop) * rabbits[peak]


def analyse(run: dict, max_creatures: int = DEFAULT_MAX_CREATURES) -> dict:
    pops = run["pops"]
    steps = len(pops) - 1
    caps = species_caps(max_creatures)
    series = {key: [p[i] for p in pops] for i, key in enumerate(SPECIES_ORDER)}
    return {
        "seed": run["seed"],
        "steps": steps,
        "final": {key: series[key][-1] for key in SPECIES_ORDER},
        "all_alive": steps == run["days"] * 24 and all(series[key][-1] > 0 for key in SPECIES_ORDER),
        "boom_bust": rabbit_boom_bust(series["rabbit"]),
        "any_extinct": any(min(series[key]) == 0 for key in SPECIES_ORDER),
        "wolves_alone": series["wolf"][-1] > 0 and series["rabbit"][-1] + series["deer"][-1] == 0,
        "steps_at_cap": {key: sum(1 for n in series[key] if n >= caps[key]) for key in SPECIES_ORDER},
    }


def check_targets(rules: list[dict], random_runs: list[dict]) -> list[dict]:
    """Evaluate the five targets from analysed runs. Each result has `passed`, `count` and `text`."""
    n_rules, n_random = len(rules), len(random_runs)
    all_alive = sum(r["all_alive"] for r in rules)
    boom_bust = sum(r["boom_bust"] for r in rules)
    extinctions = sum(r["any_extinct"] for r in random_runs)
    over_cap = [r["seed"] for r in rules if any(n > r["steps"] / 2 for n in r["steps_at_cap"].values())]
    alone = [r["seed"] for r in rules if r.get("wolves_alone")]
    return [
        {"target": 1, "passed": all_alive >= MIN_RULES_ALL_ALIVE, "count": all_alive,
         "text": f"rules: all three species alive at the end on at least {MIN_RULES_ALL_ALIVE} of {n_rules} seeds"},
        {"target": 2, "passed": boom_bust >= MIN_RULES_BOOM_BUST, "count": boom_bust,
         "text": f"rules: rabbits rise then fall 30% or more from the peak on at least {MIN_RULES_BOOM_BUST} of {n_rules} seeds"},
        {"target": 3, "passed": extinctions >= MIN_RANDOM_EXTINCTIONS, "count": extinctions,
         "text": f"random: at least one species dies out on at least {MIN_RANDOM_EXTINCTIONS} of {n_random} seeds"},
        {"target": 4, "passed": not over_cap, "count": len(over_cap),
         "text": "rules: no species sits at its cap for more than half the month on any seed"
                 + (f" (over: seeds {', '.join(map(str, over_cap))})" if over_cap else "")},
        {"target": 5, "passed": not alone, "count": len(alone),
         "text": "rules: wolves are never the only species left at the end"
                 + (f" (alone: seeds {', '.join(map(str, alone))})" if alone else "")},
    ]


def _simulate_job(job):
    return simulate_offline(*job)


def run_check(seeds=BENCH_SEEDS, days: int = 30, max_creatures: int = DEFAULT_MAX_CREATURES,
              jobs: int = 1, questions: str = "rich") -> dict:
    """Run `rules` and `random` on every seed and check the targets, in the given question mode."""
    tasks = [(name, seed, days, max_creatures, questions) for name in ("rules", "random") for seed in seeds]
    if jobs > 1:
        with Pool(jobs) as pool:
            runs = pool.map(_simulate_job, tasks)
    else:
        runs = [_simulate_job(t) for t in tasks]
    analysed = {name: [analyse(r, max_creatures) for r in runs if r["brain"] == name]
                for name in ("rules", "random")}
    targets = check_targets(analysed["rules"], analysed["random"])
    return {"runs": analysed, "targets": targets, "passed": all(t["passed"] for t in targets)}


def format_report(result: dict) -> str:
    lines = []
    for name in ("rules", "random"):
        lines.append(f"{name} brain")
        lines.append("  seed  hours  final (rabbit/deer/wolf)  all alive  rabbit boom-bust  steps at cap (r/d/w)")
        for r in result["runs"][name]:
            final = "/".join(str(r["final"][k]) for k in SPECIES_ORDER)
            cap = "/".join(str(r["steps_at_cap"][k]) for k in SPECIES_ORDER)
            lines.append(f"  {r['seed']:>4}  {r['steps']:>5}  {final:<24}  {'yes' if r['all_alive'] else 'no':<9}  "
                         f"{'yes' if r['boom_bust'] else 'no':<16}  {cap}")
        lines.append("")
    lines.append("balance targets")
    for t in result["targets"]:
        lines.append(f"  [{'pass' if t['passed'] else 'FAIL'}] {t['target']}. {t['text']} (got {t['count']})")
    lines.append("")
    lines.append("all targets pass" if result["passed"] else "some targets fail")
    return "\n".join(lines)


# -- hesitation thresholds ------------------------------------------------------------------

THRESHOLD_PERCENTILES = (10, 25)


def percentile_nearest_rank(values: list[float], percent: float) -> float:
    """The nearest-rank percentile: the smallest value with at least `percent` of the values at or below it."""
    if not values:
        raise ValueError("no values")
    ordered = sorted(values)
    return ordered[max(0, math.ceil(percent / 100 * len(ordered)) - 1)]


def _confidences_from_requests(path: str) -> dict[str, list[float]]:
    """Exact confidences from a requests.jsonl log, for answers that were accepted as valid choices."""
    found: dict[str, list[float]] = {}
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            entry = json.loads(line)
            answers = (entry.get("response") or {}).get("answers") if isinstance(entry.get("response"), dict) else None
            if not isinstance(answers, dict):
                continue
            for answer in answers.values():
                if (isinstance(answer, dict) and answer.get("type") == "choice"
                        and isinstance(answer.get("confidence"), (int, float))
                        and not isinstance(answer.get("confidence"), bool)):
                    found.setdefault(entry["brain"], []).append(min(1.0, max(0.0, float(answer["confidence"]))))
    return found


def _confidences_from_replay(path: str) -> dict[str, list[float]]:
    """Confidences (whole percents) from a replay, for runs that have no request log."""
    with open(path, encoding="utf-8") as handle:
        replay = json.load(handle)
    brains = replay["meta"]["brains"]
    species = {cid: c["species"] for cid, c in replay["creatures"].items()}
    found: dict[str, list[float]] = {}
    for frame in replay["frames"]:
        for row in frame.get("agents", []):
            if row[3] is not None and row[4] >= 0:
                found.setdefault(brains[species[row[0]]], []).append(row[4] / 100)
    return found


def collect_confidences(run_dirs: list[str]) -> dict[str, list[float]]:
    """Every brain's own confidence values across the given run folders."""
    pooled: dict[str, list[float]] = {}
    for directory in run_dirs:
        requests = os.path.join(directory, "requests.jsonl")
        replay = os.path.join(directory, "replay.json")
        if os.path.exists(requests):
            found = _confidences_from_requests(requests)
        elif os.path.exists(replay):
            found = _confidences_from_replay(replay)
        else:
            raise FileNotFoundError(f"{directory} has neither requests.jsonl nor replay.json")
        for brain, values in found.items():
            pooled.setdefault(brain, []).extend(values)
    return pooled


def thresholds_from_runs(run_dirs: list[str], percentiles=THRESHOLD_PERCENTILES) -> dict:
    """Hesitation thresholds: each brain's 10th and 25th percentile of its own confidence in the given runs."""
    pooled = collect_confidences(run_dirs)
    brains = {}
    for brain, values in sorted(pooled.items()):
        brains[brain] = {f"p{p}": percentile_nearest_rank(values, p) for p in percentiles}
        brains[brain]["decisions"] = len(values)
    return {"percentiles": list(percentiles), "source_runs": [os.path.basename(d.rstrip("/")) for d in run_dirs],
            "brains": brains}


def write_thresholds(path: str, thresholds: dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(thresholds, handle, indent=2)
