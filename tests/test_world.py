import pytest

from valley.world import (
    CARCASS_LIFETIME, CARCASS_ROT, DEFAULT_HEIGHT, DEFAULT_WIDTH, FOREST, GRASS, PLANT_MAX,
    ROCK, WATER, World, _water_areas, derive_seed,
)

BENCH_SEEDS = [3, 7, 11, 19, 23, 42, 57, 64, 88, 101]


def make_world(seed=7):
    return World.generate(seed)


def test_same_seed_gives_the_same_map_and_plants():
    a, b = make_world(7), make_world(7)
    assert a.cells == b.cells
    assert a.food == b.food
    assert a.map_retries == b.map_retries


def test_different_seeds_give_different_maps():
    assert make_world(7).cells != make_world(8).cells


def test_derive_seed_is_stable_and_stream_specific():
    assert derive_seed(7, "world") == derive_seed(7, "world")
    assert derive_seed(7, "world") != derive_seed(7, "event")
    assert derive_seed(7, "world", 0) != derive_seed(7, "world", 1)


@pytest.mark.parametrize("seed", BENCH_SEEDS)
def test_generated_maps_meet_the_water_and_passable_rules(seed):
    world = make_world(seed)
    area = DEFAULT_WIDTH * DEFAULT_HEIGHT
    assert len(world.cells) == area
    passable = sum(1 for c in world.cells if c in (GRASS, FOREST))
    assert passable / area >= 0.60
    assert _water_areas(world.cells, world.width, world.height) >= 2
    for terrain in (GRASS, FOREST, WATER, ROCK):
        assert terrain in world.cells


def test_rock_count_matches_the_formula():
    world = make_world(7)
    assert world.cells.count(ROCK) == DEFAULT_WIDTH * DEFAULT_HEIGHT // 70


def test_starting_plants_are_between_one_and_the_tile_maximum():
    world = make_world(7)
    for i, cell in enumerate(world.cells):
        if PLANT_MAX[cell]:
            assert 1 <= world.food[i] <= PLANT_MAX[cell]
        else:
            assert world.food[i] == 0


def test_regrowth_never_exceeds_the_maximum_and_refills_empty_tiles():
    world = make_world(7)
    world.food = [0] * len(world.food)
    for _ in range(3000):
        world.regrow()
        for i, cell in enumerate(world.cells):
            assert world.food[i] <= PLANT_MAX[cell]
    refilled = sum(world.food)
    maximum = sum(PLANT_MAX[c] for c in world.cells)
    assert refilled > 0.8 * maximum


def test_regrowth_stream_does_not_depend_on_the_plants():
    full, empty = make_world(7), make_world(7)
    empty.food = [0] * len(empty.food)
    for _ in range(50):
        full.regrow()
        empty.regrow()
    assert full.rng.getstate() == empty.rng.getstate()


def test_carcass_rots_and_is_removed_when_meat_runs_out():
    world = make_world(7)
    x, y = next((i % world.width, i // world.width) for i, c in enumerate(world.cells) if c == GRASS)
    world.food[world.index(x, y)] = 0
    carcass = world.add_carcass(x, y, "rabbit", meat=1.0)
    for _ in range(3):
        assert world.rot_carcasses() == []
    assert carcass.meat == pytest.approx(1.0 - 3 * CARCASS_ROT)
    removed = world.rot_carcasses()
    assert removed == [carcass]
    assert world.carcasses == []
    assert world.plants(x, y) == PLANT_MAX[GRASS]


def test_carcass_is_removed_when_its_age_passes_the_lifetime():
    world = make_world(7)
    x, y = next((i % world.width, i // world.width) for i, c in enumerate(world.cells) if c == FOREST)
    world.food[world.index(x, y)] = 0
    carcass = world.add_carcass(x, y, "deer", meat=1000.0)
    for _ in range(CARCASS_LIFETIME):
        assert world.rot_carcasses() == []
    assert carcass.age == CARCASS_LIFETIME
    assert world.rot_carcasses() == [carcass]
    assert world.plants(x, y) == PLANT_MAX[FOREST]


def test_eat_plant_takes_one_unit_and_stops_at_zero():
    world = make_world(7)
    i = next(i for i, c in enumerate(world.cells) if c == FOREST)
    x, y = i % world.width, i // world.width
    world.food[i] = 2
    assert world.eat_plant(x, y) and world.eat_plant(x, y)
    assert not world.eat_plant(x, y)
    assert world.plants(x, y) == 0


def test_next_to_water_uses_eight_directions():
    world = make_world(7)
    wx, wy = world.water_tiles[0]
    assert not world.passable(wx, wy)
    near = [(wx + dx, wy + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)
            if (dx or dy) and world.in_bounds(wx + dx, wy + dy)]
    assert all(world.next_to_water(x, y) for x, y in near)
