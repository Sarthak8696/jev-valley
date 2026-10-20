import json

import pytest

from valley.bench import RunSpec, run_one
from valley.brains.base import Decision
from valley.metrics import (
    BLUNDER_RULES, CALIBRATION_BINS, BlunderTally, blunder_check, blunder_metrics, calibration_metrics,
    compute_metrics, confidence_bin, cost_metrics, percentile, survival_metrics,
)


def signals(**overrides):
    base = dict(species="rabbit", energy=0.6, hydration=0.6, personality="bold", threat_dist=None,
                prey_dist=None, mate_dist=None, water_dist=None, water_known=False, forest_dist=None,
                carcass_dist=None, group_dist=None, water_adjacent=False, food_here=False, can_mate=False)
    base.update(overrides)
    return base


def verdicts(sig, choice):
    return dict(blunder_check(sig, choice))


# -- each rule triggers on a hand-built case and stays silent on its opposite ----------------

def test_ignored_thirst():
    sig = signals(hydration=0.1, water_adjacent=True)
    assert verdicts(sig, "eat")["ignored_thirst"] is True
    assert verdicts(sig, "drink")["ignored_thirst"] is False
    assert "ignored_thirst" not in verdicts(signals(hydration=0.1, water_adjacent=False), "eat")
    assert "ignored_thirst" not in verdicts(signals(hydration=0.3, water_adjacent=True), "eat")


def test_ignored_danger():
    sig = signals(threat_dist=2)
    assert verdicts(sig, "eat")["ignored_danger"] is True
    assert verdicts(sig, "rest")["ignored_danger"] is True
    assert verdicts(sig, "flee")["ignored_danger"] is False
    assert verdicts(sig, "hide")["ignored_danger"] is False
    assert "ignored_danger" not in verdicts(signals(threat_dist=3), "eat")
    assert "ignored_danger" not in verdicts(signals(), "eat")
    assert "ignored_danger" not in verdicts(signals(species="wolf", threat_dist=1), "hunt")


def test_hunted_while_full():
    sig = signals(species="wolf", energy=0.9)
    assert verdicts(sig, "hunt")["hunted_while_full"] is True
    assert verdicts(sig, "rest")["hunted_while_full"] is False
    assert "hunted_while_full" not in verdicts(signals(species="wolf", energy=0.7), "hunt")
    assert "hunted_while_full" not in verdicts(signals(species="rabbit", energy=0.9), "hunt")


def test_ate_while_full():
    sig = signals(energy=0.9)
    assert verdicts(sig, "eat")["ate_while_full"] is True
    assert verdicts(sig, "rest")["ate_while_full"] is False
    assert "ate_while_full" not in verdicts(signals(energy=0.7), "eat")
    assert "ate_while_full" not in verdicts(signals(species="wolf", energy=0.9), "eat")


def test_ignored_hunger():
    sig = signals(energy=0.1, food_here=True)
    assert verdicts(sig, "explore")["ignored_hunger"] is True
    assert verdicts(sig, "eat")["ignored_hunger"] is False
    assert "ignored_hunger" not in verdicts(signals(energy=0.1, food_here=False), "explore")
    assert "ignored_hunger" not in verdicts(signals(energy=0.1, food_here=True, threat_dist=2), "explore")
    assert "ignored_hunger" in verdicts(signals(energy=0.1, food_here=True, threat_dist=3), "explore")
    assert "ignored_hunger" not in verdicts(signals(energy=0.3, food_here=True), "explore")
    assert "ignored_hunger" not in verdicts(signals(species="wolf", energy=0.1, food_here=False), "rest")


def test_mated_while_starving():
    sig = signals(energy=0.1)
    assert verdicts(sig, "seek_mate")["mated_while_starving"] is True
    assert verdicts(sig, "eat")["mated_while_starving"] is False
    assert "mated_while_starving" not in verdicts(signals(energy=0.5), "seek_mate")
    assert verdicts(signals(species="wolf", energy=0.1), "seek_mate")["mated_while_starving"] is True


def test_an_ordinary_moment_has_no_opportunities():
    assert blunder_check(signals(), "explore") == []


def test_every_rule_can_trigger():
    seen = set()
    cases = [signals(hydration=0.1, water_adjacent=True), signals(threat_dist=1), signals(energy=0.95),
             signals(species="wolf", energy=0.95), signals(energy=0.05, food_here=True)]
    for sig in cases:
        seen.update(rule for rule, _ in blunder_check(sig, "rest"))
    seen.update(rule for rule, _ in blunder_check(signals(energy=0.05), "seek_mate"))
    assert seen == set(BLUNDER_RULES)


def test_a_choice_is_judged_before_hesitation():
    """The tally sees the chosen action, so a creature that would freeze is still scored on what it chose."""
    tally = BlunderTally()
    tally.record("jev", "rabbit", signals(threat_dist=1), Decision("eat", {"eat": 1.0}, 0.9, "model"))
    assert tally.brains["jev"]["rules"]["ignored_danger"] == [1, 1]


# -- the tally and calibration -------------------------------------------------------------------

def test_confidence_bins():
    assert [confidence_bin(c) for c in (0.0, 0.19, 0.2, 0.39, 0.4, 0.6, 0.8, 0.999, 1.0)] == [0, 0, 1, 1, 2, 3, 4, 4, 4]
    assert len(CALIBRATION_BINS) == 5


def model(choice, confidence):
    return Decision(choice, {choice: confidence}, confidence, "model")


def test_calibration_counts_decisions_with_an_opportunity_by_confidence():
    tally = BlunderTally()
    danger = signals(threat_dist=1)
    tally.record("jev", "rabbit", danger, model("eat", 0.3))     # blunder, bin 1
    tally.record("jev", "rabbit", danger, model("flee", 0.3))    # fine, bin 1
    tally.record("jev", "rabbit", danger, model("flee", 0.95))   # fine, bin 4
    tally.record("jev", "rabbit", signals(), model("eat", 0.95))  # no opportunity, not counted
    cal = tally.brains["jev"]["calibration"]
    assert cal[1] == [2, 1] and cal[4] == [1, 0]
    assert sum(cell[0] for cell in cal) == 3


def test_calibration_bins_sum_to_the_total_of_model_decisions_with_an_opportunity():
    tally = BlunderTally()
    import random
    rng = random.Random(1)
    with_opportunity = 0
    for _ in range(500):
        sig = signals(threat_dist=rng.choice([None, 1, 2, 5]), energy=rng.random(), hydration=rng.random(),
                      water_adjacent=rng.random() < 0.5, food_here=rng.random() < 0.5)
        choice = rng.choice(["eat", "drink", "flee", "hide", "rest", "seek_mate"])
        if blunder_check(sig, choice):
            with_opportunity += 1
        tally.record("jev", "rabbit", sig, model(choice, rng.random()))
    report = calibration_metrics(tally.to_dict())["jev"]
    assert sum(row["decisions_with_opportunity"] for row in report) == with_opportunity
    assert [row["bin"] for row in report] == list(CALIBRATION_BINS)


def test_every_decision_is_counted_and_there_is_no_fallback_bucket():
    tally = BlunderTally()
    tally.record("jev", "rabbit", signals(threat_dist=1), model("eat", 0.5))
    tally.record("jev", "rabbit", signals(), model("rest", 0.7))
    stats = tally.brains["jev"]
    assert stats["decisions"] == 2 and "fallbacks" not in stats and "scored" not in stats
    assert stats["rules"]["ignored_danger"] == [1, 1]
    assert sum(cell[0] for cell in stats["calibration"]) == 1
    report = blunder_metrics(tally.to_dict())["jev"]
    assert report["decisions"] == 2 and "fallbacks" not in report


def test_baseline_brains_get_blunder_counts_but_no_calibration():
    tally = BlunderTally()
    tally.record("rules", "rabbit", signals(threat_dist=1), Decision("eat", {"eat": 1.0}, 0.9, "baseline"))
    assert tally.brains["rules"]["rules"]["ignored_danger"] == [1, 1]
    assert calibration_metrics(tally.to_dict()) == {}


def test_blunder_metrics_rates():
    tally = BlunderTally()
    for choice in ("eat", "flee", "flee", "rest"):
        tally.record("jev", "rabbit", signals(threat_dist=1), model(choice, 0.8))
    for _ in range(6):
        tally.record("jev", "rabbit", signals(), model("rest", 0.8))
    report = blunder_metrics(tally.to_dict())["jev"]
    assert report["opportunities"]["ignored_danger"] == 4 and report["blunders"]["ignored_danger"] == 2
    assert report["overall_blunder_rate"] == pytest.approx(0.5)
    assert report["blunders_per_1000_decisions"] == pytest.approx(1000 * 2 / 10)
    empty = blunder_metrics(BlunderTally().to_dict())
    assert empty == {}


def test_a_brain_with_no_opportunities_has_no_rate():
    tally = BlunderTally()
    tally.record("rules", "rabbit", signals(), Decision("rest", {"rest": 1.0}, 0.5, "baseline"))
    assert blunder_metrics(tally.to_dict())["rules"]["overall_blunder_rate"] is None


# -- survival ----------------------------------------------------------------------------------------

def fake_replay(pops, creatures=None, summary=None):
    frames = [{"step": i, "pop": {"rabbit": r, "deer": d, "wolf": w}} for i, (r, d, w) in enumerate(pops)]
    return {"frames": frames, "creatures": creatures or {},
            "summary": summary or {}, "meta": {"run_id": "x", "seed": 1, "brains": {}, "hesitate_below": None}}


def test_survival_metrics():
    pops = [(16, 7, 3), (16, 7, 3), (14, 7, 3), (10, 6, 0), (8, 6, 0)]
    creatures = {
        "r1": {"species": "rabbit", "born": 0, "died": 3, "cause": "eaten"},
        "r17": {"species": "rabbit", "born": 2, "died": None, "cause": None},
        "w1": {"species": "wolf", "born": 0, "died": 3, "cause": "starved"},
        "w2": {"species": "wolf", "born": 0, "died": 3, "cause": "thirst"},
    }
    m = survival_metrics(fake_replay(pops, creatures))
    assert m["hours_survived"] == 4
    assert m["first_extinction"] == "Day 1, 9 am"  # step 3 is 6 am + 3 hours
    assert m["all_species_alive"] is False
    assert m["final_population"] == {"rabbit": 8, "deer": 6, "wolf": 0}
    assert m["mean_population"]["rabbit"] == pytest.approx((16 + 14 + 10 + 8) / 4)
    assert m["births"] == {"rabbit": 1, "deer": 0, "wolf": 0}
    assert m["deaths_by_cause"]["rabbit"] == {"eaten": 1}
    assert m["deaths_by_cause"]["wolf"] == {"starved": 1, "thirst": 1}


def test_a_run_where_everyone_survives_has_no_extinction():
    m = survival_metrics(fake_replay([(16, 7, 3)] * 5))
    assert m["first_extinction"] is None and m["all_species_alive"] is True


# -- cost -------------------------------------------------------------------------------

def test_percentile():
    assert percentile([], 0.5) is None
    assert percentile([5.0], 0.95) == 5.0
    assert percentile(list(range(1, 101)), 0.5) == 51
    assert percentile(list(range(1, 101)), 0.95) == 96


def test_cost_metrics_per_brain():
    summary = {"hour_seconds": {"p50": 0.8, "p95": 1.4},
               "brain_totals": {"jev": {"decisions": 2000, "requests": 130, "retries": 3,
                                        "input_tokens": 400_000, "output_tokens": 20_000,
                                        "latencies_ms": [200.0] * 100 + [900.0] * 30}}}
    cost = cost_metrics(summary)["jev"]
    assert "fallback_rate" not in cost and cost["retries"] == 3
    assert cost["input_tokens_per_1000_decisions"] == pytest.approx(200_000)
    assert cost["output_tokens_per_1000_decisions"] == pytest.approx(10_000)
    assert cost["latency_ms_p50"] == 200.0 and cost["latency_ms_p95"] == 900.0
    assert cost["seconds_per_valley_hour_p50"] == 0.8 and cost["seconds_per_valley_hour_p95"] == 1.4
    assert "input_cost" not in cost
    priced = cost_metrics(summary, price_per_mtok=2.0)["jev"]
    assert priced["input_cost"] == pytest.approx(0.8)


def test_compute_metrics_has_every_section():
    m = compute_metrics(fake_replay([(16, 7, 3)] * 3))
    assert set(m) == {"run_id", "seed", "brains", "hesitate_below", "survival", "hesitation", "blunders",
                      "calibration", "cost"}


def test_run_one_writes_metrics_for_a_rules_run(tmp_path):
    spec = RunSpec(seed=7, brains={"rabbit": "rules", "deer": "rules", "wolf": "rules"}, days=5)
    result = run_one(spec, str(tmp_path / "out"))
    metrics = json.loads(open(result["paths"]["metrics"]).read())
    assert metrics["run_id"] == "run-rules-seed7" and "valid" not in metrics and "fallbacks" not in metrics
    rules = metrics["blunders"]["rules"]
    assert rules["decisions"] > 0
    assert set(rules["opportunities"]) == set(BLUNDER_RULES)
    assert metrics["calibration"] == {}  # no model decisions
    assert metrics["cost"]["rules"]["decisions"] == rules["decisions"]
    assert "valid" not in result["replay"]["summary"]
    assert "rules" in result["replay"]["summary"]["tallies"]


def test_hesitation_metrics_count_real_decisions_that_froze():
    frames = [
        {"step": 1, "pop": {}, "agents": [["r1", 1, 1, "eat", 80, 0, 50, 50, [], []],
                                          ["r2", 2, 2, "eat", 30, 1, 50, 50, [], []],
                                          ["r4", 4, 4, None, -1, 0, 50, 50, [], []]]},       # a newborn
        {"step": 2, "pop": {}, "agents": [["r1", 1, 1, "drink", 20, 1, 50, 50, [], []]]},
    ]
    replay = {"frames": frames, "meta": {"hesitate_below": 0.5}}
    from valley.metrics import hesitation_metrics
    assert hesitation_metrics(replay) == {"threshold": 0.5, "decisions": 3, "hesitated": 2, "rate": 2 / 3}
    assert hesitation_metrics({"frames": [], "meta": {"hesitate_below": None}})["rate"] is None
