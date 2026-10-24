"""The ten benchmark seeds, and the hesitation thresholds that are fixed from a brain's own smoke runs.

An offline balance check used to live here, run on the hand-written `rules` and `random` baselines. Those were removed:
the valley runs only on a model, so there is no offline way to play it. The check, and the numbers it gave, are in the
history at commit 4d545ed and in the "Ecosystem redesign record" of docs/build-spec.md.
"""

import json
import math
import os

BENCH_SEEDS = (3, 7, 11, 19, 23, 42, 57, 64, 88, 101)


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
