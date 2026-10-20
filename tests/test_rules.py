import json
import random

import pytest

from tests.helpers import make_creature
from valley.brains.base import DecisionRequest
from valley.brains.rules import RulesBrain, TEMPERATURE, score_actions, softmax
from valley.perception import build_request
from valley.simulation import Simulation
from valley.species import PREY_ACTIONS, SPECIES, WOLF_ACTIONS
from valley.world import derive_seed
from tests.helpers import open_rows, world_from_rows


def signals(**overrides):
    base = dict(species="rabbit", energy=1.0, hydration=1.0, personality="curious", threat_dist=None,
                prey_dist=None, mate_dist=None, water_dist=None, water_known=False, forest_dist=None,
                carcass_dist=None, group_dist=None, water_adjacent=False, food_here=False,
                can_mate=False)
    base.update(overrides)
    return base


def test_flee_scales_with_threat_distance_and_personality():
    near = score_actions(signals(threat_dist=2, personality="curious"), ["flee"])["flee"]
    mid = score_actions(signals(threat_dist=4, personality="curious"), ["flee"])["flee"]
    far = score_actions(signals(threat_dist=5, personality="curious"), ["flee"])["flee"]
    assert (near, mid, far) == (1.6, 0.9, 0.3)
    assert score_actions(signals(threat_dist=2, personality="bold"), ["flee"])["flee"] == pytest.approx(1.6 * 0.6)
    assert score_actions(signals(threat_dist=2, personality="timid"), ["flee"])["flee"] == pytest.approx(1.6 * 1.3)
    assert score_actions(signals(), ["flee"])["flee"] < 0


def test_hide_depends_on_threat_and_nearby_forest():
    assert score_actions(signals(threat_dist=3, forest_dist=2), ["hide"])["hide"] == 0.8
    assert score_actions(signals(threat_dist=3, forest_dist=4), ["hide"])["hide"] == 0.1
    assert score_actions(signals(threat_dist=3), ["hide"])["hide"] == 0.1
    assert score_actions(signals(), ["hide"])["hide"] == 0.05
    assert score_actions(signals(personality="cautious"), ["hide"])["hide"] == pytest.approx(0.35)


def test_drink_is_stronger_when_water_is_known():
    thirsty = dict(hydration=0.4)
    assert score_actions(signals(**thirsty, water_known=True), ["drink"])["drink"] == pytest.approx(0.6 * 1.6)
    assert score_actions(signals(**thirsty), ["drink"])["drink"] == pytest.approx(0.6 * 0.6)


def test_eat_and_hunt_and_scavenge_follow_hunger():
    hungry = dict(energy=0.4)
    assert score_actions(signals(**hungry), ["eat"])["eat"] == pytest.approx((0.6 - 0.15) * 1.8)
    assert score_actions(signals(**hungry, food_here=True), ["eat"])["eat"] == pytest.approx((0.6 - 0.15) * 1.8 + 0.3)
    assert score_actions(signals(**hungry, prey_dist=3), ["hunt"])["hunt"] == pytest.approx((0.6 - 0.3) * 2.5 + 0.4)
    assert score_actions(signals(**hungry), ["hunt"])["hunt"] == pytest.approx((0.6 - 0.3) * 2.5 - 0.6)
    assert score_actions(signals(**hungry, carcass_dist=2), ["scavenge"])["scavenge"] == pytest.approx(0.6 * 1.2 + 0.9)
    assert score_actions(signals(**hungry), ["scavenge"])["scavenge"] == pytest.approx(0.6 * 1.2 - 1.0)


def test_mating_rest_explore_and_follow_scores():
    assert score_actions(signals(can_mate=True, mate_dist=3), ["seek_mate"])["seek_mate"] == 0.9
    assert score_actions(signals(can_mate=True), ["seek_mate"])["seek_mate"] == -0.8
    assert score_actions(signals(mate_dist=3), ["seek_mate"])["seek_mate"] == -0.8
    assert score_actions(signals(personality="lazy"), ["rest"])["rest"] == pytest.approx(0.65)
    assert score_actions(signals(personality="bold"), ["rest"])["rest"] == 0.15
    assert score_actions(signals(personality="restless"), ["explore"])["explore"] == pytest.approx(0.65)
    assert score_actions(signals(personality="bold"), ["explore"])["explore"] == 0.25
    assert score_actions(signals(group_dist=3, personality="bold"), ["follow_group"])["follow_group"] == 0.4
    assert score_actions(signals(group_dist=2, personality="bold"), ["follow_group"])["follow_group"] == 0.0
    assert score_actions(signals(group_dist=3, personality="loyal"), ["follow_group"])["follow_group"] == pytest.approx(0.7)
    assert score_actions(signals(personality="bold"), ["follow_group"])["follow_group"] == 0.0


def test_every_action_in_both_menus_can_be_scored():
    for actions in (PREY_ACTIONS, WOLF_ACTIONS):
        scores = score_actions(signals(), actions)
        assert set(scores) == set(actions)


def test_softmax_sums_to_one_and_prefers_higher_scores():
    probs = softmax({"a": 1.0, "b": 0.0, "c": -1.0})
    assert sum(probs.values()) == pytest.approx(1.0)
    assert probs["a"] > probs["b"] > probs["c"]
    assert probs["a"] / probs["b"] == pytest.approx(2.718281828 ** (1.0 / TEMPERATURE), rel=1e-6)


def make_request(**sig):
    options = {a: "" for a in PREY_ACTIONS}
    return DecisionRequest("r1", {}, options, signals(**sig))


def test_confidence_is_the_probability_of_the_choice_and_source_is_baseline():
    brain = RulesBrain(random.Random(1))
    decisions = brain.decide([make_request(threat_dist=1, energy=0.9, hydration=0.9)] * 20)
    for decision in decisions:
        assert decision.source == "baseline"
        assert decision.confidence == pytest.approx(decision.probabilities[decision.choice])
        assert sum(decision.probabilities.values()) == pytest.approx(1.0)
        assert set(decision.probabilities) == set(PREY_ACTIONS)
    assert sum(d.choice == "flee" for d in decisions) >= 10  # a wolf next door makes fleeing likely


def test_a_starving_rabbit_standing_on_plants_mostly_eats():
    brain = RulesBrain(random.Random(2))
    decisions = brain.decide([make_request(energy=0.1, food_here=True, hydration=0.9)] * 200)
    assert sum(d.choice == "eat" for d in decisions) > 120


def test_the_brain_uses_only_its_own_random_stream():
    world = world_from_rows(open_rows())
    rabbit = make_creature("rabbit", 5, 5)
    request = build_request(world, rabbit, [rabbit])
    seed = 5
    a = RulesBrain(random.Random(derive_seed(seed, "brain")))
    b = RulesBrain(random.Random(derive_seed(seed, "brain")))
    assert [d.choice for d in a.decide([request] * 30)] == [d.choice for d in b.decide([request] * 30)]


def rules_sim(seed, days=5):
    brain = RulesBrain(random.Random(derive_seed(seed, "brain")))
    sim = Simulation(seed, {s: brain for s in SPECIES}, days=days)
    sim.steps = 100
    return sim


def test_a_100_hour_rules_run_is_fully_repeatable():
    def run():
        sim = rules_sim(7)
        sim.run()
        return json.dumps(sim.frames, sort_keys=True)
    assert run() == run()


def test_a_rules_run_and_a_random_run_start_from_the_same_valley():
    from tests.test_simulation import random_sim, start_signature
    assert start_signature(rules_sim(7)) == start_signature(random_sim(7))
