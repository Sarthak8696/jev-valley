"""The extra score and noul questions of the rich mode, and how the world reacts to their answers."""

import random

import pytest

from tests.helpers import FixedRng, make_creature, make_sim, open_rows, world_from_rows
from valley import actions
from tests.offline import RulesBrain, answer_question, make_offline_brain as make_brain
from valley.brains.base import Decision, Question
from valley.perception import build_request, condition, prey_cues
from valley.questions import ALERT_LEVELS, NEUTRAL, prey_questions, wolf_questions
from valley.simulation import Simulation
from valley.species import SPECIES


def scene(creatures, rows=None, plants="none", roll=None):
    sim = make_sim(world_from_rows(rows or open_rows(), plants=plants), creatures)
    if roll is not None:
        sim.event_rng = FixedRng(roll)
    return sim


def act(sim, creature, action):
    creature.executed = action
    creature.path = []
    actions.execute(sim, creature)


# -- the questions ------------------------------------------------------------------

def test_a_prey_animal_is_asked_for_alertness_breeding_and_attack():
    questions = prey_questions()
    assert [(q.key, q.type) for q in questions] == [("alert", "score"), ("breed", "noul"), ("attack", "noul")]
    assert questions[0].criteria == ALERT_LEVELS and questions[0].top == 4.0
    assert set(questions[1].criteria) == {"true", "false"} and questions[1].top == 1.0


def test_a_wolf_is_asked_about_each_of_up_to_three_prey_then_effort_and_breeding():
    prey = [make_creature("rabbit", i, 0, cid=f"r{i}", name=f"Pip{i}") for i in range(5)]
    keys = [q.key for q in wolf_questions(prey)]
    assert keys == ["weak:r0", "weak:r1", "weak:r2", "effort", "breed"]
    assert [q.key for q in wolf_questions([])] == ["effort", "breed"]
    assert "Pip1 the rabbit" in wolf_questions(prey)[1].instructions


def test_the_request_carries_the_questions_only_in_rich_mode():
    wolf = make_creature("wolf", 5, 5, cid="w1")
    rabbit = make_creature("rabbit", 7, 5, cid="r1", name="Pip")
    world = world_from_rows(open_rows(), plants="none")
    basic = build_request(world, wolf, [wolf, rabbit])
    rich = build_request(world, wolf, [wolf, rabbit], rich=True)
    assert basic.questions == [] and basic.truth == {}
    assert [q.key for q in rich.questions] == ["weak:r1", "effort", "breed"]
    assert rich.truth["weak"] == {"r1": 1.0}
    prey_request = build_request(world, rabbit, [wolf, rabbit], rich=True)
    assert [q.key for q in prey_request.questions] == ["alert", "breed", "attack"]


def test_a_wolf_sees_how_each_prey_looks_only_in_rich_mode():
    wolf = make_creature("wolf", 5, 5, cid="w1")
    rabbit = make_creature("rabbit", 7, 5, cid="r1", name="Pip", age=10, energy=8)  # young and worn
    world = world_from_rows(open_rows(), plants="none")
    basic = build_request(world, wolf, [wolf, rabbit]).view["sees"][0]
    rich = build_request(world, wolf, [wolf, rabbit], rich=True).view["sees"][0]
    assert basic == "prey: rabbit Pip, 2 tiles east"
    assert rich == "prey: rabbit Pip, 2 tiles east, young, alone, looks weak"


def test_how_a_prey_animal_looks_is_coarser_than_its_energy():
    assert [condition(r) for r in (1.0, 0.6, 0.59, 0.3, 0.29, 0.0)] == [0, 0, 1, 1, 2, 2]
    wolf = make_creature("wolf", 5, 5)
    pair = [make_creature("rabbit", 7, 5, cid="r1"), make_creature("rabbit", 8, 5, cid="r2", energy=1)]
    cues = prey_cues(pair, [wolf] + pair)
    assert cues[0] == {"id": "r1", "cond": 0, "young": False, "alone": False}
    assert cues[1]["cond"] == 2 and cues[1]["alone"] is False  # the other rabbit is one tile away


# -- how the world reacts -------------------------------------------------------------

@pytest.mark.parametrize("alertness, factor", [(0.0, 1.12), (2.0, 1.0), (4.0, 0.88)])
def test_a_watchful_animal_gets_less_from_grazing(alertness, factor):
    rabbit = make_creature("rabbit", 5, 5, energy=10, alertness=alertness)
    sim = scene([rabbit], plants={(5, 5): 2})
    act(sim, rabbit, "eat")
    upkeep = rabbit.spec.energy_loss * 1.0
    assert rabbit.energy == pytest.approx(10 + rabbit.spec.plant_energy * factor - upkeep)


def catch_happens(roll, prey_alertness=NEUTRAL, effort=NEUTRAL):
    wolf = make_creature("wolf", 0, 1, cid="w1", effort=effort)
    rabbit = make_creature("rabbit", 1, 1, cid="r1", energy=15, alertness=prey_alertness)  # half energy
    rabbit.executed = "rest"
    sim = scene([wolf, rabbit], rows=open_rows(11, 3), roll=roll)
    act(sim, wolf, "hunt")
    return not rabbit.alive, rabbit.attacked


@pytest.mark.parametrize("alertness, effort, factor", [
    (2.0, 2.0, 1.0), (4.0, 2.0, 0.9), (0.0, 2.0, 1.1), (2.0, 4.0, 1.16), (2.0, 0.0, 0.84), (4.0, 4.0, 0.9 * 1.16),
])
def test_alertness_and_chase_effort_change_the_chance_of_a_catch(alertness, effort, factor):
    chance = SPECIES["wolf"].catch_chance["rabbit"] * factor
    assert catch_happens(chance - 0.001, alertness, effort)[0] is True
    assert catch_happens(chance + 0.001, alertness, effort)[0] is False


def test_a_catch_attempt_marks_the_prey_as_attacked_whether_or_not_it_succeeds():
    assert catch_happens(0.0) == (True, True)
    assert catch_happens(0.99) == (False, True)


def test_a_hard_chase_costs_more_energy_and_a_lazy_one_less():
    costs = {}
    for effort in (0.0, 2.0, 4.0):
        wolf = make_creature("wolf", 0, 1, cid="w1", energy=30, effort=effort)
        sim = scene([wolf], rows=open_rows(11, 3))
        act(sim, wolf, "hunt")
        costs[effort] = 30 - wolf.energy
    assert costs[0.0] < costs[2.0] < costs[4.0]
    assert costs[4.0] == pytest.approx(costs[2.0] * 1.3) and costs[0.0] == pytest.approx(costs[2.0] * 0.7)


@pytest.mark.parametrize("effort, loses", [(0.0, True), (2.0, True), (4.0, False)])
def test_chase_effort_changes_how_often_a_far_target_is_lost(effort, loses):
    wolf = make_creature("wolf", 2, 5, cid="w1", effort=effort, heading=(1, 0))
    rabbit = make_creature("rabbit", 8, 5, cid="r1")
    sim = scene([wolf, rabbit], roll=0.3)  # the chance of losing the trail is 0.56, 0.40 and 0.24
    act(sim, wolf, "hunt")
    assert (len(wolf.memory) == 1) is loses


def test_a_wolf_chases_the_weakest_looking_prey_it_has_scored_and_otherwise_the_nearest():
    wolf = make_creature("wolf", 5, 5, cid="w1")
    near = make_creature("rabbit", 6, 5, cid="r1")
    mid = make_creature("rabbit", 7, 5, cid="r2")
    far = make_creature("deer", 9, 5, cid="d1")
    prey = [near, mid, far]
    assert actions.pick_target(wolf, prey) is near  # no scores: the nearest
    wolf.weak_scores = {"r1": 1.0, "r2": 3.5, "d1": 4.0}
    assert actions.pick_target(wolf, prey) is mid  # weak and near beats the weakest, far away
    wolf.weak_scores = {"r1": 2.0, "r2": 2.0, "d1": 2.0}
    assert actions.pick_target(wolf, prey) is near  # a tie goes to the nearest
    wolf.weak_scores = {"d1": 2.0, "r1": 0.0}
    assert actions.pick_target(wolf, prey) is mid  # r2 was never scored, so it counts as neutral: 2.0 - 0.7 is best
    wolf.weak_scores = {"r1": 0.0, "r2": 0.0}
    assert actions.pick_target(wolf, prey) is far  # unscored d1 is neutral: 2.0 - 1.4 beats the two it found strong


def test_breeding_needs_both_partners_to_say_yes():
    def attempt(first_ok, second_ok):
        a = make_creature("rabbit", 5, 5, cid="r1", breed_ok=first_ok)
        b = make_creature("rabbit", 6, 5, cid="r2", breed_ok=second_ok)
        sim = scene([a, b], roll=0.5)
        act(sim, a, "seek_mate")
        return len(sim.creatures) == 2 and a.cooldown == 0 and not any("young" in e for e in sim.events)

    assert attempt(True, True) is False  # they had young
    assert attempt(True, False) is True
    assert attempt(False, True) is True


def test_answers_are_read_into_the_creature_and_missing_ones_mean_neutral():
    rabbit = make_creature("rabbit", 1, 1)
    rabbit.take_answers({"alert": 3.2, "breed": 0.4})
    assert (rabbit.alertness, rabbit.effort, rabbit.breed_ok) == (3.2, NEUTRAL, False)
    wolf = make_creature("wolf", 1, 1)
    wolf.take_answers({"weak:r4": 3.0, "effort": 1.0, "breed": 0.5})
    assert wolf.weak_scores == {"r4": 3.0} and wolf.effort == 1.0 and wolf.breed_ok is True
    wolf.take_answers({})
    assert (wolf.weak_scores, wolf.effort, wolf.alertness, wolf.breed_ok) == ({}, NEUTRAL, NEUTRAL, True)


# -- the baselines' answers -----------------------------------------------------------

def signals(**overrides):
    base = dict(species="rabbit", energy=0.8, hydration=0.8, personality="curious", threat_dist=None, prey_dist=None,
                prey_cues=[])
    base.update(overrides)
    return base


ALERT = Question("alert", "score", "", ALERT_LEVELS)
BREED = Question("breed", "noul", "", {"true": "", "false": ""})
ATTACK = Question("attack", "noul", "", {"true": "", "false": ""})
EFFORT = Question("effort", "score", "", ["a", "b", "c", "d", "e"])


def test_the_rules_brain_is_more_alert_the_closer_the_wolf():
    levels = [answer_question(signals(threat_dist=d), ALERT) for d in (None, 6, 4, 2)]
    assert levels == [1.0, 2.0, 3.0, 4.0]
    assert answer_question(signals(personality="timid"), ALERT) == 1.5
    assert answer_question(signals(personality="bold", threat_dist=2), ALERT) == 3.5
    assert answer_question(signals(threat_dist=2, personality="cautious"), ALERT) == 4.0  # capped at the top
    assert answer_question(signals(energy=0.2), ALERT) == 0.5


def test_the_rules_brain_breeds_only_when_fed_watered_and_safe():
    assert answer_question(signals(), BREED) == 0.9
    assert answer_question(signals(energy=0.4), BREED) == 0.15
    assert answer_question(signals(hydration=0.3), BREED) == 0.15
    assert answer_question(signals(threat_dist=3), BREED) == 0.15
    assert answer_question(signals(threat_dist=6), BREED) == 0.9


def test_the_rules_brain_expects_an_attack_when_a_wolf_is_close():
    assert [answer_question(signals(threat_dist=d), ATTACK) for d in (None, 6, 4, 2)] == [0.03, 0.15, 0.35, 0.7]


def test_the_rules_brain_chases_hard_when_starving_and_when_prey_is_close():
    assert answer_question(signals(species="wolf", energy=0.2), EFFORT) == 3.0
    assert answer_question(signals(species="wolf", prey_dist=2), EFFORT) == 2.5
    assert answer_question(signals(species="wolf", prey_dist=5), EFFORT) == 1.5


def test_the_rules_brain_judges_weakness_from_what_a_wolf_can_see():
    weak = Question("weak:r1", "score", "", ["a", "b", "c", "d", "e"])
    cue = {"id": "r1", "cond": 2, "young": True, "alone": True}
    assert answer_question(signals(prey_cues=[cue]), weak) == pytest.approx(4.0)  # 3.5 + 0.5 + 0.4, capped
    well = dict(cue, cond=0, young=False, alone=False)
    assert answer_question(signals(prey_cues=[well]), weak) == pytest.approx(0.8)
    assert answer_question(signals(prey_cues=[]), weak) == 2.0  # a prey it was not shown


def test_both_baselines_answer_every_question_within_range():
    wolf = make_creature("wolf", 5, 5, cid="w1")
    rabbits = [make_creature("rabbit", 6 + i, 5, cid=f"r{i + 1}") for i in range(2)]
    world = world_from_rows(open_rows(), plants="none")
    for name, creature in (("rules", wolf), ("rules", rabbits[0]), ("random", wolf), ("random", rabbits[0])):
        request = build_request(world, creature, [wolf] + rabbits, rich=True)
        decision = make_brain(name, 3).decide([request])[0]
        assert set(decision.extras) == {q.key for q in request.questions}
        for question in request.questions:
            assert 0.0 <= decision.extras[question.key] <= question.top


def test_the_baselines_give_no_extras_in_the_choice_only_mode():
    rabbit = make_creature("rabbit", 5, 5, cid="r1")
    request = build_request(world_from_rows(open_rows(), plants="none"), rabbit, [rabbit])
    assert make_brain("rules", 1).decide([request])[0].extras == {}
    assert make_brain("random", 1).decide([request])[0].extras == {}


# -- the whole simulation --------------------------------------------------------------

def test_an_unknown_questions_mode_is_refused():
    with pytest.raises(ValueError, match="questions must be one of"):
        Simulation(1, {}, questions="everything")


class NeutralRules(RulesBrain):
    """Chooses like the rules brain but answers every extra question with the value that changes nothing."""

    def decide(self, requests, step=0):
        out = []
        for request, decision in zip(requests, super().decide(requests, step)):
            neutral = {q.key: (NEUTRAL if q.type == "score" else 1.0 if q.key == "breed" else 0.5) for q in request.questions}
            out.append(Decision(decision.choice, decision.probabilities, decision.confidence, decision.source, extras=neutral))
        return out


def run(questions, brain_class, days=6):
    brain = brain_class(random.Random(5))
    sim = Simulation(57, {s: brain for s in SPECIES}, days=days, questions=questions)
    sim.run()
    return sim


def test_answering_neutrally_plays_exactly_the_choice_only_game():
    basic = run("basic", RulesBrain)
    rich = run("rich", NeutralRules)
    assert [f["pop"] for f in basic.frames] == [f["pop"] for f in rich.frames]
    assert [f["events"] for f in basic.frames] == [f["events"] for f in rich.frames]
    assert [[row[:4] for row in f["agents"]] for f in basic.frames] == [[row[:4] for row in f["agents"]] for f in rich.frames]


def test_real_answers_change_the_game_and_the_run_stays_repeatable():
    basic = run("basic", RulesBrain)
    first, second = run("rich", RulesBrain), run("rich", RulesBrain)
    assert [f["pop"] for f in first.frames] == [f["pop"] for f in second.frames]
    assert [f["pop"] for f in first.frames] != [f["pop"] for f in basic.frames]
    assert any(c.alertness != NEUTRAL for c in first.living)
