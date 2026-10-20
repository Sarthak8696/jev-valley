import pytest

from tests.helpers import FixedRng, make_creature, make_sim, open_rows, world_from_rows
from valley import actions
from valley.species import SPECIES
from valley.world import PLANT_MAX


def scene(creatures, rows=None, plants="none", roll=None):
    world = world_from_rows(rows or open_rows(), plants=plants)
    sim = make_sim(world, creatures)
    if roll is not None:
        sim.event_rng = FixedRng(roll)
    return sim


def act(sim, creature, action):
    creature.executed = action
    creature.path = []
    actions.execute(sim, creature)


def upkeep(creature, action):
    spec = creature.spec
    from valley.species import ACTION_COST
    return spec.energy_loss * ACTION_COST[action]


# -- eating, drinking, resting -------------------------------------------------

def test_eat_takes_a_plant_and_gains_energy():
    rabbit = make_creature("rabbit", 5, 5, energy=10)
    sim = scene([rabbit], plants={(5, 5): 2})
    act(sim, rabbit, "eat")
    assert sim.world.plants(5, 5) == 1
    assert rabbit.energy == pytest.approx(10 + rabbit.spec.plant_energy - upkeep(rabbit, "eat"))
    assert rabbit.path == []


def test_eat_energy_is_capped_at_the_maximum():
    rabbit = make_creature("rabbit", 5, 5, energy=29)
    sim = scene([rabbit], plants={(5, 5): 1})
    act(sim, rabbit, "eat")
    assert rabbit.energy == pytest.approx(30 - upkeep(rabbit, "eat"))


def test_eat_walks_toward_the_nearest_plants():
    rabbit = make_creature("rabbit", 5, 5, energy=10)
    sim = scene([rabbit], plants={(8, 5): 1})
    act(sim, rabbit, "eat")
    assert (rabbit.x, rabbit.y) == (6, 5)
    assert rabbit.path == [(6, 5)]
    assert sim.world.plants(8, 5) == 1


def test_eat_with_no_plants_in_sight_explores():
    rabbit = make_creature("rabbit", 5, 5, heading=(1, 0))
    sim = scene([rabbit], roll=0.5)
    act(sim, rabbit, "eat")
    assert (rabbit.x, rabbit.y) == (6, 5)


def water_rows():
    rows = open_rows()
    rows[5] = "...~........"
    return rows


def test_drink_next_to_water_fills_hydration():
    rabbit = make_creature("rabbit", 4, 5, hydration=5)
    sim = scene([rabbit], rows=water_rows())
    act(sim, rabbit, "drink")
    assert rabbit.hydration == pytest.approx(30 - rabbit.spec.hydration_loss)
    assert rabbit.path == []


def test_drink_walks_toward_water_and_drinks_on_arrival():
    rabbit = make_creature("rabbit", 6, 5, hydration=5)
    sim = scene([rabbit], rows=water_rows())
    act(sim, rabbit, "drink")
    assert (rabbit.x, rabbit.y) == (5, 5)
    assert rabbit.hydration == pytest.approx(5 - rabbit.spec.hydration_loss)  # not yet next to it
    act(sim, rabbit, "drink")
    assert (rabbit.x, rabbit.y) == (4, 5)
    assert rabbit.hydration == pytest.approx(30 - rabbit.spec.hydration_loss)


def test_drink_uses_known_water_when_none_is_in_sight():
    rows = open_rows(14, 10)
    rows[5] = "~" + rows[5][1:]
    rabbit = make_creature("rabbit", 10, 5, hydration=5, known_water=(0, 5))
    sim = scene([rabbit], rows=rows)
    act(sim, rabbit, "drink")
    assert (rabbit.x, rabbit.y) == (9, 5)


def test_drink_with_no_water_known_explores():
    rabbit = make_creature("rabbit", 5, 5, heading=(0, 1))
    sim = scene([rabbit], roll=0.5)
    act(sim, rabbit, "drink")
    assert (rabbit.x, rabbit.y) == (5, 6)


def test_rest_stays_and_costs_half():
    rabbit = make_creature("rabbit", 5, 5, energy=20)
    sim = scene([rabbit])
    act(sim, rabbit, "rest")
    assert (rabbit.x, rabbit.y) == (5, 5)
    assert rabbit.energy == pytest.approx(20 - upkeep(rabbit, "rest"))


# -- fleeing and hiding --------------------------------------------------------

def test_flee_runs_two_steps_away_from_the_wolf():
    rabbit = make_creature("rabbit", 5, 5)
    wolf = make_creature("wolf", 4, 5, cid="w1")
    sim = scene([rabbit, wolf])
    act(sim, rabbit, "flee")
    assert len(rabbit.path) == 2
    from valley.world import chebyshev
    assert chebyshev(rabbit.x, rabbit.y, 4, 5) == 3
    assert rabbit.energy == pytest.approx(30 - upkeep(rabbit, "flee"))


def test_flee_with_no_wolf_visible_explores():
    rabbit = make_creature("rabbit", 5, 5, heading=(1, 0))
    sim = scene([rabbit], roll=0.5)
    act(sim, rabbit, "flee")
    assert rabbit.path == [(6, 5)]


def test_flee_stops_when_cornered():
    rows = open_rows(6, 3)
    rabbit = make_creature("rabbit", 5, 1)
    wolf = make_creature("wolf", 4, 1, cid="w1")
    sim = scene([rabbit, wolf], rows=rows)
    act(sim, rabbit, "flee")
    assert rabbit.path == []


def forest_rows():
    rows = open_rows()
    rows[5] = ".......T...."
    return rows


def test_hide_moves_toward_forest_and_stays_once_there():
    rabbit = make_creature("rabbit", 5, 5)
    sim = scene([rabbit], rows=forest_rows())
    act(sim, rabbit, "hide")
    assert (rabbit.x, rabbit.y) == (6, 5)
    act(sim, rabbit, "hide")
    assert (rabbit.x, rabbit.y) == (7, 5)
    act(sim, rabbit, "hide")
    assert (rabbit.x, rabbit.y) == (7, 5) and rabbit.path == []
    assert rabbit.energy == pytest.approx(30 - 3 * upkeep(rabbit, "hide"))


def test_hide_skips_forest_that_is_occupied():
    rabbit = make_creature("rabbit", 5, 5)
    squatter = make_creature("rabbit", 7, 5, cid="r2")
    sim = scene([rabbit, squatter], rows=forest_rows())
    act(sim, rabbit, "hide")
    assert (rabbit.x, rabbit.y) == (5, 5)


# -- mating --------------------------------------------------------------------

def test_seek_mate_has_young_next_to_the_seeker():
    a = make_creature("rabbit", 5, 5, cid="r1", name="Clover")
    b = make_creature("rabbit", 6, 5, cid="r2", name="Pip")
    sim = scene([a, b], roll=0.5)
    act(sim, a, "seek_mate")
    newborns = [c for c in sim.creatures.values() if c.born == sim.step_no and c.parents]
    assert len(newborns) == 1
    baby = newborns[0]
    assert baby.parents == ("r1", "r2") and baby.age == 0
    assert baby.energy == pytest.approx(15) and baby.hydration == pytest.approx(24)
    assert abs(baby.x - 5) <= 1 and abs(baby.y - 5) <= 1 and (baby.x, baby.y) != (5, 5)
    for parent in (a, b):
        assert parent.cooldown == a.spec.breed_cooldown
    assert a.energy == pytest.approx(30 - a.spec.breed_cost - upkeep(a, "seek_mate"))
    assert b.energy == pytest.approx(30 - a.spec.breed_cost)
    assert a.memory == ["Day 1, 6 am: had 1 young with Pip"]
    assert b.memory == ["Day 1, 6 am: had 1 young with Clover"]
    assert sim.events == ["Clover and Pip the rabbits had 1 young"]


def test_the_newborn_inherits_known_water():
    a = make_creature("rabbit", 5, 5, cid="r1", known_water=(1, 1))
    b = make_creature("rabbit", 6, 5, cid="r2")
    sim = scene([a, b], roll=0.5)
    act(sim, a, "seek_mate")
    baby = [c for c in sim.creatures.values() if c.parents][0]
    assert baby.known_water == (1, 1)


@pytest.mark.parametrize("change", [
    dict(cooldown=5),
    dict(energy=10),
    dict(age=10),
])
def test_breeding_respects_the_partners_cooldown_energy_and_age(change):
    a = make_creature("rabbit", 5, 5, cid="r1")
    b = make_creature("rabbit", 6, 5, cid="r2", **change)
    sim = scene([a, b], roll=0.5)
    act(sim, a, "seek_mate")
    assert len(sim.creatures) == 2


@pytest.mark.parametrize("change", [dict(cooldown=5), dict(energy=10), dict(age=10)])
def test_breeding_respects_the_seekers_own_state(change):
    a = make_creature("rabbit", 5, 5, cid="r1", **change)
    b = make_creature("rabbit", 6, 5, cid="r2")
    sim = scene([a, b], roll=0.5)
    act(sim, a, "seek_mate")
    assert len(sim.creatures) == 2


def test_breeding_respects_the_total_cap():
    a = make_creature("rabbit", 5, 5, cid="r1")
    b = make_creature("rabbit", 6, 5, cid="r2")
    sim = scene([a, b], roll=0.5)
    sim.max_creatures = 2
    act(sim, a, "seek_mate")
    assert len(sim.creatures) == 2 and a.cooldown == 0


def test_breeding_respects_the_species_share_of_the_cap():
    a = make_creature("wolf", 5, 5, cid="w1")
    b = make_creature("wolf", 6, 5, cid="w2")
    sim = scene([a, b], roll=0.5)
    sim.max_creatures = 10  # wolves may hold 1.4 of 10
    act(sim, a, "seek_mate")
    assert len(sim.creatures) == 2


def test_no_free_tile_means_no_birth_and_no_cost():
    rows = ["^^^^^", "^...^", "^^^^^"]
    a = make_creature("rabbit", 1, 1, cid="r1")
    b = make_creature("rabbit", 2, 1, cid="r2")
    sim = scene([a, b], rows=rows)
    act(sim, a, "seek_mate")
    assert len(sim.creatures) == 2 and a.cooldown == 0


def test_seek_mate_walks_toward_a_partner_in_sight():
    a = make_creature("rabbit", 3, 5, cid="r1")
    b = make_creature("rabbit", 7, 5, cid="r2")
    sim = scene([a, b], roll=0.5)
    act(sim, a, "seek_mate")
    assert (a.x, a.y) == (4, 5) and len(sim.creatures) == 2


def test_newborns_are_never_placed_on_occupied_tiles():
    a = make_creature("rabbit", 5, 5, cid="r1")
    b = make_creature("rabbit", 6, 5, cid="r2")
    sim = scene([a, b], roll=0.5)
    act(sim, a, "seek_mate")
    tiles = [(c.x, c.y) for c in sim.living]
    assert len(tiles) == len(set(tiles))


# -- following and exploring ----------------------------------------------------

def test_follow_group_steps_toward_the_centre_of_visible_kin():
    me = make_creature("rabbit", 2, 5, cid="r1")
    others = [make_creature("rabbit", 6, 4, cid="r2"), make_creature("rabbit", 6, 6, cid="r3")]
    sim = scene([me, *others])
    act(sim, me, "follow_group")
    assert (me.x, me.y) == (3, 5)


def test_follow_group_with_nobody_in_sight_stays():
    me = make_creature("rabbit", 2, 5, cid="r1")
    sim = scene([me])
    act(sim, me, "follow_group")
    assert me.path == []


def test_explore_follows_its_heading_and_picks_a_new_one_when_blocked():
    rows = open_rows(6, 3)
    rows[1] = ".^...."
    rabbit = make_creature("rabbit", 0, 1, heading=(1, 0))
    sim = scene([rabbit], rows=rows, roll=0.5)
    act(sim, rabbit, "explore")
    assert (rabbit.x, rabbit.y) == (0, 1)
    assert rabbit.heading == (0, -1)  # FixedRng picks the first compass direction


# -- hunting and scavenging -----------------------------------------------------

def test_hunt_catches_prey_within_one_tile_after_moving():
    wolf = make_creature("wolf", 5, 5, cid="w1", name="Ash", energy=20)
    rabbit = make_creature("rabbit", 7, 5, cid="r1", name="Pip", energy=15)  # half energy: neither weak nor strong
    sim = scene([wolf, rabbit], roll=0.3)
    sim.world.food[sim.world.index(7, 5)] = 0
    act(sim, wolf, "hunt")
    assert (wolf.x, wolf.y) == (6, 5)
    assert not rabbit.alive and rabbit.cause == "eaten"
    assert sim.events == ["Ash the wolf caught Pip the rabbit"]
    assert wolf.energy == pytest.approx(20 + SPECIES["rabbit"].meat_value - upkeep(wolf, "hunt"))
    assert wolf.memory == ["Day 1, 6 am: caught Pip the rabbit"]
    assert sim.world.carcasses == []  # eaten down to nothing
    assert sim.world.plants(7, 5) == PLANT_MAX["."]  # and the plants grew back
    assert (7, 5) not in sim.occupied


def test_hunt_leaves_a_carcass_when_the_wolf_is_nearly_full():
    wolf = make_creature("wolf", 5, 5, cid="w1", energy=55)
    deer = make_creature("deer", 6, 5, cid="d1")
    sim = scene([wolf, deer], roll=0.0)
    act(sim, wolf, "hunt")
    assert not deer.alive
    assert len(sim.world.carcasses) == 1
    assert sim.world.carcasses[0].meat == pytest.approx(SPECIES["deer"].meat_value - 5)
    assert wolf.energy == pytest.approx(60 - upkeep(wolf, "hunt"))


def test_a_missed_catch_is_remembered_by_both():
    wolf = make_creature("wolf", 5, 5, cid="w1", name="Ash")
    rabbit = make_creature("rabbit", 6, 5, cid="r1", name="Pip")
    sim = scene([wolf, rabbit], roll=0.9)
    act(sim, wolf, "hunt")
    assert rabbit.alive
    assert sim.events == ["Ash the wolf missed Pip the rabbit"]
    assert wolf.memory == ["Day 1, 6 am: Pip the rabbit got away"]
    assert rabbit.memory == ["Day 1, 6 am: escaped Ash the wolf"]


def test_no_catch_is_tried_when_the_wolf_ends_more_than_one_tile_away():
    wolf = make_creature("wolf", 2, 5, cid="w1")
    rabbit = make_creature("rabbit", 8, 5, cid="r1")
    sim = scene([wolf, rabbit], roll=0.5)  # 0.5 is above the chance of losing the trail
    act(sim, wolf, "hunt")
    assert (wolf.x, wolf.y) == (4, 5)
    assert rabbit.alive and sim.events == []


def test_hunt_with_no_prey_in_sight_explores():
    wolf = make_creature("wolf", 5, 5, cid="w1", heading=(1, 0))
    sim = scene([wolf], roll=0.5)
    act(sim, wolf, "hunt")
    assert wolf.path == [(6, 5)]


@pytest.mark.parametrize("species, prey_action, terrain_row, factor", [
    ("deer", "rest", None, 1.0),
    ("deer", "hide", ".T.........", 0.5),   # hiding in forest halves the chance
    ("deer", "hide", None, 1.0),            # hiding on open ground does not help
    ("deer", "flee", None, 0.7),            # fleeing cuts it to 70%
    ("rabbit", "rest", None, 1.0),
    ("rabbit", "flee", None, 0.7),
    ("rabbit", "hide", ".T.........", 0.5),
])
def test_catch_chances_are_adjusted_for_hiding_and_fleeing(species, prey_action, terrain_row, factor):
    chance = SPECIES["wolf"].catch_chance[species] * factor

    def attempt(roll):
        rows = open_rows(11, 3)
        if terrain_row:
            rows[1] = terrain_row
        wolf = make_creature("wolf", 0, 1, cid="w1")
        prey = make_creature(species, 1, 1, cid="p1", energy=SPECIES[species].max_energy / 2)  # half energy: factor 1
        prey.executed = prey_action
        sim = scene([wolf, prey], rows=rows, roll=roll)
        act(sim, wolf, "hunt")
        return not prey.alive

    assert attempt(chance - 0.001) is True
    assert attempt(chance + 0.001) is False


def test_a_hunting_wolf_can_lose_a_prey_that_is_still_far_off():
    wolf = make_creature("wolf", 2, 5, cid="w1", heading=(1, 0))
    rabbit = make_creature("rabbit", 8, 5, cid="r1")
    sim = scene([wolf, rabbit], roll=0.1)  # below the 40% chance of losing the trail
    act(sim, wolf, "hunt")
    assert wolf.x == 2 and len(wolf.path) == 1  # it wandered one step instead of closing in on the rabbit
    assert wolf.memory == ["Day 1, 6 am: lost the trail of " + rabbit.name + " the rabbit"]


def test_a_wolf_close_behind_its_prey_never_loses_the_trail():
    wolf = make_creature("wolf", 5, 5, cid="w1")
    rabbit = make_creature("rabbit", 7, 5, cid="r1", energy=15)
    sim = scene([wolf, rabbit], roll=0.0)  # the lowest roll there is
    act(sim, wolf, "hunt")
    assert (wolf.x, wolf.y) == (6, 5) and not rabbit.alive


@pytest.mark.parametrize("energy_share, factor", [(0.0, 1.5), (0.5, 1.0), (1.0, 0.5)])
def test_weak_prey_is_easier_to_catch_and_strong_prey_harder(energy_share, factor):
    chance = SPECIES["wolf"].catch_chance["rabbit"] * factor

    def attempt(roll):
        wolf = make_creature("wolf", 0, 1, cid="w1")
        rabbit = make_creature("rabbit", 1, 1, cid="r1", energy=SPECIES["rabbit"].max_energy * energy_share)
        rabbit.executed = "rest"
        sim = scene([wolf, rabbit], rows=open_rows(11, 3), roll=roll)
        act(sim, wolf, "hunt")
        return not rabbit.alive

    assert attempt(chance - 0.001) is True
    assert attempt(chance + 0.001) is False


def test_scavenge_walks_up_and_eats_the_carcass():
    wolf = make_creature("wolf", 5, 5, cid="w1", energy=10)
    sim = scene([wolf])
    carcass = sim.world.add_carcass(7, 5, "rabbit", 14.0)
    sim.world.food[sim.world.index(7, 5)] = 0
    act(sim, wolf, "scavenge")
    assert (wolf.x, wolf.y) == (6, 5)
    assert wolf.energy == pytest.approx(10 + 14 - upkeep(wolf, "scavenge"))
    assert sim.world.carcasses == []
    assert sim.world.plants(7, 5) == PLANT_MAX["."]
    assert wolf.memory == ["Day 1, 6 am: ate from a rabbit carcass"]
    assert carcass not in sim.world.carcasses


def test_scavenge_takes_at_most_fifteen_and_only_what_fits():
    wolf = make_creature("wolf", 5, 5, cid="w1", energy=20)
    sim = scene([wolf])
    carcass = sim.world.add_carcass(5, 6, "deer", 34.0)
    act(sim, wolf, "scavenge")
    assert carcass.meat == pytest.approx(19)
    full = make_creature("wolf", 1, 1, cid="w2", energy=55)
    sim2 = scene([full])
    c2 = sim2.world.add_carcass(1, 2, "deer", 34.0)
    act(sim2, full, "scavenge")
    assert c2.meat == pytest.approx(29)


def test_scavenge_ignores_wolf_carcasses_and_explores():
    wolf = make_creature("wolf", 5, 5, cid="w1", heading=(1, 0))
    sim = scene([wolf], roll=0.5)
    sim.world.add_carcass(5, 6, "wolf", 12.0)
    act(sim, wolf, "scavenge")
    assert wolf.path == [(6, 5)]
    assert sim.world.carcasses[0].meat == 12.0


# -- movement rules -------------------------------------------------------------

def test_step_toward_stays_put_when_every_closer_tile_is_blocked():
    rows = open_rows(12, 10)
    for y in (4, 5, 6):
        rows[y] = rows[y][:6] + "^" + rows[y][7:]
    rabbit = make_creature("rabbit", 5, 5)
    sim = scene([rabbit], rows=rows)
    assert actions.step_toward(sim, rabbit, 8, 5) is False
    assert (rabbit.x, rabbit.y) == (5, 5)


def test_step_toward_goes_around_a_single_rock_diagonally():
    rows = open_rows(12, 10)
    rows[5] = rows[5][:6] + "^" + rows[5][7:]
    rabbit = make_creature("rabbit", 5, 5)
    sim = scene([rabbit], rows=rows)
    assert actions.step_toward(sim, rabbit, 8, 5) is True
    assert (rabbit.x, rabbit.y) in {(6, 4), (6, 6)}


def test_recorded_paths_match_the_moves_made():
    rabbit = make_creature("rabbit", 5, 5)
    wolf = make_creature("wolf", 4, 5, cid="w1")
    sim = scene([rabbit, wolf])
    start = (rabbit.x, rabbit.y)
    act(sim, rabbit, "flee")
    previous = start
    from valley.world import chebyshev
    for tile in rabbit.path:
        assert chebyshev(*previous, *tile) == 1
        assert sim.world.passable(*tile)
        previous = tile
    assert previous == (rabbit.x, rabbit.y)
    assert sim.occupied[(rabbit.x, rabbit.y)] is rabbit
    assert start not in sim.occupied


def test_species_table_has_a_hunt_speed_for_wolves_only():
    assert SPECIES["wolf"].hunt_speed == 2 and SPECIES["rabbit"].hunt_speed == 0
