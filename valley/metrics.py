"""Survival, blunders, calibration, and cost.

Blunder and calibration tallies are counted while the run happens, because the
blunder rules need signals that a replay does not store. `compute_metrics` turns
a finished replay (with those tallies in its summary) into `metrics.json`.
"""

from valley.clock import clock_text
from valley.perception import hunger_word, thirst_word
from valley.species import SPECIES_ORDER

CALIBRATION_BINS = ("0.0-0.2", "0.2-0.4", "0.4-0.6", "0.6-0.8", "0.8-1.0")

BLUNDER_RULES = (
    "ignored_thirst", "ignored_danger", "hunted_while_full", "ate_while_full", "ignored_hunger",
    "mated_while_starving",
)


def blunder_check(signals: dict, choice: str) -> list[tuple[str, bool]]:
    """Every blunder rule that applies to this situation, as (rule key, whether `choice` was a blunder).

    A rule applies when its opportunity is present: for example `ignored_thirst` applies when the
    creature is parched with water next to it. The choice is judged before any hesitation.
    """
    hunger = hunger_word(signals["energy"])
    thirst = thirst_word(signals["hydration"])
    prey = signals["species"] != "wolf"
    threat = signals["threat_dist"]
    results = []
    if thirst == "parched" and signals["water_adjacent"]:
        results.append(("ignored_thirst", choice != "drink"))
    if prey and threat is not None and threat <= 2:
        results.append(("ignored_danger", choice not in ("flee", "hide")))
    if not prey and hunger == "full":
        results.append(("hunted_while_full", choice == "hunt"))
    if prey and hunger == "full":
        results.append(("ate_while_full", choice == "eat"))
    if prey and hunger == "starving" and signals["food_here"] and (threat is None or threat > 2):
        results.append(("ignored_hunger", choice != "eat"))
    if hunger == "starving":
        results.append(("mated_while_starving", choice == "seek_mate"))
    return results


def confidence_bin(confidence: float) -> int:
    return min(len(CALIBRATION_BINS) - 1, max(0, int(confidence * len(CALIBRATION_BINS))))


class BlunderTally:
    """Counts decisions, blunder opportunities and blunders per brain while a run happens."""

    def __init__(self):
        self.brains: dict[str, dict] = {}

    def _stats(self, brain: str) -> dict:
        if brain not in self.brains:
            self.brains[brain] = {
                "decisions": 0,
                "rules": {rule: [0, 0] for rule in BLUNDER_RULES},  # rule -> [opportunities, blunders]
                "calibration": [[0, 0] for _ in CALIBRATION_BINS],  # bin -> [decisions with an opportunity, with a blunder]
            }
        return self.brains[brain]

    def record(self, brain: str, species: str, signals: dict, decision) -> None:
        stats = self._stats(brain)
        stats["decisions"] += 1
        checks = blunder_check(signals, decision.choice)
        for rule, blundered in checks:
            stats["rules"][rule][0] += 1
            stats["rules"][rule][1] += int(blundered)
        if checks and decision.source == "model":
            cell = stats["calibration"][confidence_bin(decision.confidence)]
            cell[0] += 1
            cell[1] += int(any(blundered for _, blundered in checks))

    def to_dict(self) -> dict:
        return {name: {**stats, "rules": {k: list(v) for k, v in stats["rules"].items()},
                       "calibration": [list(c) for c in stats["calibration"]]}
                for name, stats in self.brains.items()}


# -- from a replay -------------------------------------------------------------------------

def survival_metrics(replay: dict) -> dict:
    frames = replay["frames"]
    hours = frames[1:] or frames
    first_extinction = None
    for frame in frames[1:]:
        if any(frame["pop"][key] == 0 for key in SPECIES_ORDER):
            first_extinction = clock_text(frame["step"])
            break
    final = frames[-1]["pop"]
    creatures = replay["creatures"]
    births = {key: sum(1 for c in creatures.values() if c["species"] == key and c["born"] > 0)
              for key in SPECIES_ORDER}
    deaths = {key: {} for key in SPECIES_ORDER}
    for c in creatures.values():
        if c["cause"]:
            deaths[c["species"]][c["cause"]] = deaths[c["species"]].get(c["cause"], 0) + 1
    return {
        "hours_survived": frames[-1]["step"],
        "first_extinction": first_extinction,
        "all_species_alive": all(final[key] > 0 for key in SPECIES_ORDER),
        "final_population": dict(final),
        "mean_population": {key: sum(f["pop"][key] for f in hours) / len(hours) for key in SPECIES_ORDER},
        "births": births,
        "deaths_by_cause": deaths,
    }


def hesitation_metrics(replay: dict) -> dict:
    """How often creatures froze because the model's confidence was below the threshold."""
    decided = hesitated = 0
    for frame in replay["frames"]:
        for row in frame.get("agents", []):
            if row[3] is not None:  # a real decision, not a newborn's empty row
                decided += 1
                hesitated += row[5]
    return {"threshold": replay["meta"]["hesitate_below"], "decisions": decided, "hesitated": hesitated,
            "rate": hesitated / decided if decided else None}


def blunder_metrics(tallies: dict) -> dict:
    out = {}
    for brain, stats in tallies.items():
        opportunities = {rule: cell[0] for rule, cell in stats["rules"].items()}
        blunders = {rule: cell[1] for rule, cell in stats["rules"].items()}
        total_opportunities, total_blunders = sum(opportunities.values()), sum(blunders.values())
        out[brain] = {
            "opportunities": opportunities,
            "blunders": blunders,
            "overall_blunder_rate": total_blunders / total_opportunities if total_opportunities else None,
            "blunders_per_1000_decisions": 1000 * total_blunders / stats["decisions"] if stats["decisions"] else None,
            "decisions": stats["decisions"],
        }
    return out


def calibration_metrics(tallies: dict) -> dict:
    """Blunder rate per confidence bin, for brains that produced model decisions."""
    out = {}
    for brain, stats in tallies.items():
        cells = stats["calibration"]
        if not any(cell[0] for cell in cells):
            continue
        out[brain] = [
            {"bin": label, "decisions_with_opportunity": cell[0],
             "blunder_rate": cell[1] / cell[0] if cell[0] else None}
            for label, cell in zip(CALIBRATION_BINS, cells)
        ]
    return out


def percentile(values: list[float], q: float):
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * len(ordered)))]


def cost_metrics(summary: dict, price_per_mtok: float | None = None) -> dict:
    out = {}
    hour = summary.get("hour_seconds", {})
    for brain, totals in summary.get("brain_totals", {}).items():
        decisions = totals.get("decisions", 0)
        latencies = totals.get("latencies_ms", [])
        entry = {
            "decisions": decisions,
            "requests": totals.get("requests", 0),
            "retries": totals.get("retries", 0),
            "input_tokens": totals.get("input_tokens", 0),
            "output_tokens": totals.get("output_tokens", 0),
            "input_tokens_per_1000_decisions": 1000 * totals.get("input_tokens", 0) / decisions if decisions else None,
            "output_tokens_per_1000_decisions": 1000 * totals.get("output_tokens", 0) / decisions if decisions else None,
            "latency_ms_p50": percentile(latencies, 0.5),
            "latency_ms_p95": percentile(latencies, 0.95),
            "seconds_per_valley_hour_p50": hour.get("p50"),
            "seconds_per_valley_hour_p95": hour.get("p95"),
        }
        if price_per_mtok is not None:
            entry["input_cost"] = totals.get("input_tokens", 0) / 1_000_000 * price_per_mtok
        out[brain] = entry
    return out


def compute_metrics(replay: dict, price_per_mtok: float | None = None) -> dict:
    summary = replay["summary"]
    tallies = summary.get("tallies", {})
    cost = cost_metrics(summary, price_per_mtok)
    meta = replay["meta"]
    return {
        "run_id": meta["run_id"],
        "seed": meta["seed"],
        "brains": meta["brains"],
        "hesitate_below": meta["hesitate_below"],
        "questions": meta.get("questions", "basic"),
        "survival": survival_metrics(replay),
        "hesitation": hesitation_metrics(replay),
        "blunders": blunder_metrics(tallies),
        "calibration": calibration_metrics(tallies),
        "cost": cost,
    }
