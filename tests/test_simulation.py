import json
import random

import pytest

from tests.helpers import FixedRng, ScriptedBrain, make_creature, make_sim, open_rows, world_from_rows
from valley.brains.random_brain import RandomBrain
from valley.simulation import Simulation
from valley.species import SPECIES, SPECIES_ORDER
from valley.world import DEFAULT_HEIGHT, DEFAULT_WIDTH, PASSABLE, derive_seed


def random_sim(seed=7, days=30, **kwargs):
    brain = RandomBrain(random.Random(derive_seed(seed, "brain")))
    return Simulation(seed, {s: brain for s in SPECIES}, days=days, **kwargs)


def start_signature(sim):
    return [(c.id, c.name, c.personality, c.x, c.y, c.age, round(c.energy, 9), c.hydration, c.heading)
            for c in sim.creatures.values()]


def test_starting_creatures_match_the_spec():
    sim = random_sim(7)
    by_species = {s: [c for c in sim.creatures.values() if c.species == s] for s in SPECIES}
    assert {s: len(v) for s, v in by_species.items()} == {"rabbit": 16, "deer": 7, "wolf": 3}
    assert [c.id for c in by_species["rabbit"]] == [f"r{i}" for i in range(1, 17)]
    tiles = [(c.x, c.y) for c in sim.creatures.values()]
    assert len(tiles) == len(set(tiles))
    for c in sim.creatures.values():
        spec = c.spec
        assert sim.world.terrain(c.x, c.y) in PASSABLE
        assert spec.adult_age <= c.age <= 2 * spec.adult_age
        assert 0.6 * spec.max_energy <= c.energy <= 0.9 * spec.max_energy
        assert c.hydration == pytest.approx(0.8 * spec.max_hydration)
        assert c.born == 0 and c.parents == () and c.alive


def test_names_are_numbered_when_repeated():
    sim = random_sim(7)
    names = [c.name for c in sim.creatures.values() if c.species == "rabbit"]
    assert len(names) == len(set(names))
    for name in names:
        base = name.rsplit(" ", 1)[0] if name.rsplit(" ", 1)[-1].isdigit() else name
        assert base in SPECIES["rabbit"].names


def test_the_same_seed_gives_the_same_start_for_every_brain():
    a = random_sim(7)
    brain = ScriptedBrain()
    b = Simulation(7, {s: brain for s in SPECIES})
    assert start_signature(a) == start_signature(b)
    assert a.world.cells == b.world.cells and a.world.food == b.world.food


def test_different_seeds_give_different_starts():
    assert start_signature(random_sim(7)) != start_signature(random_sim(8))


def test_a_100_hour_run_is_fully_repeatable():
    def run():
        sim = random_sim(7, days=5)
        sim.steps = 100
        sim.run()
        return json.dumps(sim.frames, sort_keys=True)
    assert run() == run()


def test_populations_never_go_negative_and_the_cap_holds():
    sim = random_sim(11, days=10)
    sim.run()
    for frame in sim.frames:
        assert all(n >= 0 for n in frame["pop"].values())
        assert sum(frame["pop"].values()) <= sim.max_creatures


def test_dead_creatures_never_act_or_appear_again():
    sim = random_sim(3, days=10)
    sim.run()
    dead = {c.id: c.died for c in sim.creatures.values() if c.died is not None}
    assert dead, "the random brain should lose some animals in 10 days"
    for frame in sim.frames:
        for row in frame["agents"]:
            died = dead.get(row[0])
            if died is not None:
                assert frame["step"] <= died
    for c in sim.creatures.values():
        if not c.alive:
            assert c.id not in sim.occupied.values()


def test_no_two_living_creatures_share_a_tile_in_any_frame():
    sim = random_sim(7, days=10)
    sim.run()
    died = {c.id: c.died for c in sim.creatures.values()}
    for frame in sim.frames:
        tiles = [(r[1], r[2]) for r in frame["agents"] if died[r[0]] is None or died[r[0]] > frame["step"]]
        assert len(tiles) == len(set(tiles))


def test_the_run_ends_early_when_nobody_is_left():
    rabbit = make_creature("rabbit", 1, 1, energy=0.1)
    sim = make_sim(world_from_rows(open_rows(), plants="none"), [rabbit], days=30)
    sim.run()
    assert sim.step_no == 1
    assert not rabbit.alive


def test_starvation_leaves_a_smaller_carcass_and_an_event():
    rabbit = make_creature("rabbit", 1, 1, name="Pip", energy=0.1)
    sim = make_sim(world_from_rows(open_rows(), plants="none"), [rabbit])
    frame = sim.step()
    assert rabbit.cause == "starved" and rabbit.died == 1
    assert frame["events"] == ["Pip the rabbit starved"]
    assert sim.world.carcasses[0].meat == pytest.approx(14 * 0.4)  # made after the hour's rot, so it is still whole
    assert frame["pop"]["rabbit"] == 0
    assert [r[0] for r in frame["agents"]] == ["r1"]  # shown on the hour it died


def test_thirst_is_checked_after_starvation_and_leaves_more_meat():
    rabbit = make_creature("rabbit", 1, 1, name="Pip", hydration=0.1)
    sim = make_sim(world_from_rows(open_rows(), plants="none"), [rabbit])
    frame = sim.step()
    assert rabbit.cause == "thirst"
    assert frame["events"] == ["Pip the rabbit died of thirst"]
    assert sim.world.carcasses[0].meat == pytest.approx(14 * 0.6)


def test_a_creature_both_starving_and_parched_is_recorded_as_starved():
    rabbit = make_creature("rabbit", 1, 1, energy=0.1, hydration=0.1)
    sim = make_sim(world_from_rows(open_rows(), plants="none"), [rabbit])
    sim.step()
    assert rabbit.cause == "starved"


def test_a_hunt_in_the_loop_kills_the_prey_and_updates_the_frame():
    wolf = make_creature("wolf", 5, 5, cid="w1", name="Ash")
    rabbit = make_creature("rabbit", 6, 5, cid="r1", name="Pip")
    sim = make_sim(world_from_rows(open_rows(), plants="none"), [wolf, rabbit],
                   choices={"w1": "hunt", "r1": "rest"})
    sim.event_rng = FixedRng(0.0)
    frame = sim.step()
    assert "Ash the wolf caught Pip the rabbit" in frame["events"]
    assert frame["pop"] == {"rabbit": 0, "deer": 0, "wolf": 1}
    assert [r[0] for r in frame["agents"]] == ["w1", "r1"]
    sim.step()
    assert sim.frames[-1]["agents"][0][0] == "w1" and len(sim.frames[-1]["agents"]) == 1


def test_newborns_skip_the_hour_they_are_born():
    a = make_creature("rabbit", 5, 5, cid="r1", name="Clover")
    b = make_creature("rabbit", 6, 5, cid="r2", name="Pip")
    sim = make_sim(world_from_rows(open_rows(), plants="none"), [a, b],
                   choices={"r1": "seek_mate", "r2": "rest"})
    sim.event_rng = FixedRng(0.5)
    frame = sim.step()
    baby = next(c for c in sim.creatures.values() if c.parents)
    assert baby.age == 0 and baby.born == 1
    assert baby.energy == pytest.approx(15)  # no upkeep in its birth hour
    row = next(r for r in frame["agents"] if r[0] == baby.id)
    assert row[3] is None and row[4] == -1 and row[8] == []
    assert frame["pop"]["rabbit"] == 3
    assert a.age == 97 and baby.id not in [c.id for c in sim.living if c.born == 0]
    sim.step()
    assert baby.age == 1


def test_cooldown_counts_down_each_hour():
    rabbit = make_creature("rabbit", 1, 1, cooldown=3)
    sim = make_sim(world_from_rows(open_rows(), plants="none"), [rabbit])
    sim.step()
    sim.step()
    assert rabbit.cooldown == 1
    sim.step()
    sim.step()
    assert rabbit.cooldown == 0


def test_hesitation_freezes_a_low_confidence_creature_and_keeps_the_choice():
    rabbit = make_creature("rabbit", 5, 5, cid="r1", heading=(1, 0))
    sim = make_sim(world_from_rows(open_rows(), plants="none"), [rabbit], default="explore",
                   confidence=0.3, hesitate_below=0.5)
    sim.event_rng = FixedRng(0.5)
    frame = sim.step()
    assert rabbit.action == "explore" and rabbit.executed == "rest" and rabbit.hesitated
    assert (rabbit.x, rabbit.y) == (5, 5)
    row = frame["agents"][0]
    assert row[3] == "explore" and row[5] == 1 and row[4] == 30
    assert rabbit.memory[-1].endswith("hesitated")
    assert rabbit.notes == []  # hesitation is not kept as a replay note
    assert rabbit.energy == pytest.approx(30 - 0.5 * 0.45)


def test_a_confident_creature_does_not_hesitate():
    rabbit = make_creature("rabbit", 5, 5, cid="r1", heading=(1, 0))
    sim = make_sim(world_from_rows(open_rows(), plants="none"), [rabbit], default="explore",
                   confidence=0.6, hesitate_below=0.5)
    sim.event_rng = FixedRng(0.5)
    sim.step()
    assert not rabbit.hesitated and (rabbit.x, rabbit.y) == (6, 5)


def test_fallback_decisions_are_not_treated_as_hesitation():
    rabbit = make_creature("rabbit", 5, 5, cid="r1")
    world = world_from_rows(open_rows(), plants="none")
    brain = ScriptedBrain(default="rest", confidence=0.0, source="fallback")
    sim = Simulation(1, {s: brain for s in SPECIES}, world=world, creatures=[rabbit], hesitate_below=0.5)
    frame = sim.step()
    assert not rabbit.hesitated and frame["agents"][0][4] == -1 and frame["agents"][0][5] == 0


def test_food_snapshots_and_diffs():
    sim = random_sim(7, days=3)
    sim.run()
    assert len(sim.frames[0]["food"]) == DEFAULT_WIDTH * DEFAULT_HEIGHT
    assert "food" in sim.frames[24] and "food_diff" not in sim.frames[24]
    assert "food_diff" in sim.frames[1] and "food" not in sim.frames[1]
    assert "food" in sim.frames[48]


def test_agent_rows_have_the_documented_shape():
    sim = random_sim(7, days=2)
    sim.run()
    row = sim.frames[5]["agents"][0]
    cid, x, y, action, conf, hesitated, energy, hydration, probs, path = row
    assert action in SPECIES[sim.creatures[cid].species].actions
    assert len(probs) == 8 and conf == 12  # uniform over 8 actions
    assert 0 <= energy <= 100 and 0 <= hydration <= 100 and hesitated == 0
    assert all(len(tile) == 2 for tile in path)


def test_mixed_brains_get_their_own_species_requests():
    seen = {}

    class Recorder(ScriptedBrain):
        def __init__(self, label):
            super().__init__()
            self.name = label

        def decide(self, requests, step=0):
            seen.setdefault(self.name, set()).update(r.creature_id[0] for r in requests)
            return super().decide(requests, step)

    prey, wolf = Recorder("prey"), Recorder("wolf")
    sim = Simulation(7, {"rabbit": prey, "deer": prey, "wolf": wolf}, days=1)
    sim.step()
    assert seen == {"prey": {"r", "d"}, "wolf": {"w"}}


def test_summary_reports_timing_and_brain_totals():
    sim = random_sim(7, days=1)
    sim.run()
    summary = sim.summary()
    assert summary["steps_run"] == 24
    assert summary["hour_seconds"]["p50"] is not None
    assert summary["brain_totals"]["random"]["decisions"] > 0
