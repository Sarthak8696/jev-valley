import json

import pytest

from tests.helpers import make_creature, open_rows, world_from_rows
from valley.perception import (
    build_request, direction, hunger_word, thirst_word, visible_creatures, where,
)

VIEW_FIELDS = ["id", "animal", "diet", "personality", "age", "hunger", "thirst", "standing_on",
               "can_have_young", "sees", "recent"]


def spec_example_scene():
    """The example from the spec, rebuilt on a hand-made map."""
    rows = open_rows(12, 10)
    rows[5] = rows[5][:3] + "~" + rows[5][4:7] + "T" + rows[5][8:]  # water at (3,5), forest at (7,5)
    world = world_from_rows(rows, plants={(5, 9): 1})
    clover = make_creature("rabbit", 5, 5, cid="r12", name="Clover", personality="timid",
                           energy=12, hydration=18, age=216)
    clover.memory = ["Day 9, 11 pm: escaped Ash the wolf"]
    ash = make_creature("wolf", 8, 2, cid="w1", name="Ash", last_action="hunt")
    kin = [make_creature("rabbit", x, y, cid=f"r{i}", name=f"K{i}")
           for i, (x, y) in enumerate([(5, 3), (6, 7), (4, 8), (7, 8)], start=1)]
    living = [clover, ash, *kin]
    return world, clover, living


def test_the_view_matches_the_spec_example():
    world, clover, living = spec_example_scene()
    view = build_request(world, clover, living).view
    assert list(view) == VIEW_FIELDS
    assert view["id"] == "r12"
    assert view["animal"] == "Clover the rabbit"
    assert view["diet"] == "eats plants"
    assert view["personality"] == "timid"
    assert view["age"] == "9 days (adult)"
    assert view["hunger"] == "hungry"
    assert view["thirst"] == "fine"
    assert view["standing_on"] == "open grass, grazed bare"
    assert view["can_have_young"] == "no, too hungry"
    assert view["sees"] == [
        "DANGER: wolf Ash, 3 tiles north-east, hunting",
        "4 other rabbits, nearest 2 tiles north",
        "water, 2 tiles west",
        "plants to eat, 4 tiles south",
        "forest cover, 2 tiles east",
    ]
    assert view["recent"] == ["Day 9, 11 pm: escaped Ash the wolf"]


def test_the_view_has_no_time_field():
    world, clover, living = spec_example_scene()
    assert "time" not in build_request(world, clover, living).view


def test_signals_are_separate_from_the_view():
    world, clover, living = spec_example_scene()
    request = build_request(world, clover, living)
    text = json.dumps(request.view)
    for key in ("threat_dist", "water_adjacent", "food_here", "can_mate", "group_dist", "energy"):
        assert key not in request.view
        assert f'"{key}"' not in text
    assert request.signals["threat_dist"] == 3
    assert request.signals["water_dist"] == 2
    assert request.signals["forest_dist"] == 2
    assert request.signals["group_dist"] == 2
    assert request.signals["can_mate"] is False
    assert request.signals["energy"] == pytest.approx(0.4)
    assert list(request.options) == ["eat", "drink", "flee", "hide", "rest", "seek_mate",
                                     "follow_group", "explore"]


@pytest.mark.parametrize("ratio, word", [(0.0, "starving"), (0.19, "starving"), (0.2, "hungry"),
                                         (0.44, "hungry"), (0.45, "fed"), (0.79, "fed"),
                                         (0.8, "full"), (1.0, "full")])
def test_hunger_words(ratio, word):
    assert hunger_word(ratio) == word


@pytest.mark.parametrize("ratio, word", [(0.0, "parched"), (0.19, "parched"), (0.2, "thirsty"),
                                         (0.44, "thirsty"), (0.45, "fine"), (0.79, "fine"),
                                         (0.8, "quenched"), (1.0, "quenched")])
def test_thirst_words(ratio, word):
    assert thirst_word(ratio) == word


@pytest.mark.parametrize("dx, dy, expected", [
    (1, -5, "north"), (5, 1, "east"), (-5, 0, "west"), (0, 4, "south"),
    (3, -3, "north-east"), (-3, 3, "south-west"), (2, 2, "south-east"), (-4, -3, "north-west"),
    (2, -1, "north-east"),  # exactly half is not "less than half"
    (3, 1, "east"),
])
def test_direction_rule(dx, dy, expected):
    assert direction(dx, dy) == expected


def test_where_wording():
    assert where(4, 4, 4, 4) == "right here"
    assert where(4, 4, 5, 4) == "1 tile east"
    assert where(4, 4, 7, 1) == "3 tiles north-east"


def test_a_lone_creature_sees_nothing_nearby():
    world = world_from_rows(open_rows(), plants="none")
    rabbit = make_creature("rabbit", 5, 5)
    request = build_request(world, rabbit, [rabbit])
    assert request.view["sees"] == ["nothing nearby"]
    assert request.view["recent"] == ["nothing yet"]


def test_one_other_creature_is_singular():
    world = world_from_rows(open_rows(), plants="none")
    a, b = make_creature("rabbit", 5, 5, cid="r1"), make_creature("rabbit", 7, 5, cid="r2", name="Pip")
    assert build_request(world, a, [a, b]).view["sees"][0] == "1 other rabbit, nearest 2 tiles east"


def test_a_partner_is_listed_only_when_both_can_breed():
    world = world_from_rows(open_rows(), plants="none")
    a, b = make_creature("rabbit", 5, 5, cid="r1"), make_creature("rabbit", 7, 5, cid="r2", name="Pip")
    sees = build_request(world, a, [a, b]).view["sees"]
    assert "possible partner: Pip, 2 tiles east" in sees
    b.cooldown = 10
    assert not any("possible partner" in s for s in build_request(world, a, [a, b]).view["sees"])
    b.cooldown = 0
    a.energy = 5
    assert not any("possible partner" in s for s in build_request(world, a, [a, b]).view["sees"])


def test_can_have_young_reasons():
    world = world_from_rows(open_rows(), plants="none")
    young = make_creature("rabbit", 1, 1, age=5)
    assert build_request(world, young, [young]).view["can_have_young"] == "no, too young"
    recent = make_creature("rabbit", 1, 1, cooldown=3)
    assert build_request(world, recent, [recent]).view["can_have_young"] == "no, had young recently"
    ready = make_creature("rabbit", 1, 1)
    assert build_request(world, ready, [ready]).view["can_have_young"] == "yes"


def test_water_is_remembered_after_it_leaves_sight():
    rows = open_rows(14, 4)
    rows[1] = "~" + rows[1][1:]
    world = world_from_rows(rows, plants="none")
    rabbit = make_creature("rabbit", 3, 1)
    assert "water, 3 tiles west" in build_request(world, rabbit, [rabbit]).view["sees"]
    assert rabbit.known_water == (0, 1)
    rabbit.x = 10
    request = build_request(world, rabbit, [rabbit])
    assert request.view["sees"] == ["no water in sight; I remember water 10 tiles west"]
    assert request.signals["water_dist"] is None and request.signals["water_known"] is True


def test_water_next_to_me_and_adjacent_signal():
    rows = open_rows(6, 3)
    rows[1] = "~" + rows[1][1:]
    world = world_from_rows(rows, plants="none")
    rabbit = make_creature("rabbit", 1, 1)
    request = build_request(world, rabbit, [rabbit])
    assert request.view["sees"] == ["water, next to me"]
    assert request.signals["water_adjacent"] is True


def test_standing_on_and_forest_line():
    rows = open_rows(6, 3)
    rows[1] = ".T...."
    world = world_from_rows(rows, plants={(1, 1): 2, (3, 1): 0})
    on_forest = make_creature("rabbit", 1, 1)
    request = build_request(world, on_forest, [on_forest])
    assert request.view["standing_on"] == "forest cover, with berries"
    assert not any(s.startswith("forest cover") for s in request.view["sees"])
    assert request.signals["forest_dist"] == 0
    on_grass = make_creature("rabbit", 3, 1)
    request = build_request(world, on_grass, [on_grass])
    assert request.view["standing_on"] == "open grass, grazed bare"
    assert "forest cover, 2 tiles west" in request.view["sees"]


def test_hidden_creatures_are_only_seen_from_two_tiles():
    rows = open_rows(12, 3)
    rows[1] = "...T........"
    world = world_from_rows(rows, plants="none")
    wolf = make_creature("wolf", 3, 1, cid="w1")
    rabbit = make_creature("rabbit", 3, 1, last_action="hide")
    rabbit.x, rabbit.y = 3, 1
    wolf.x, wolf.y = 6, 1  # distance 3
    assert visible_creatures(world, wolf, [wolf, rabbit]) == []
    wolf.x = 5  # distance 2
    assert visible_creatures(world, wolf, [wolf, rabbit]) == [rabbit]
    rabbit.last_action = "rest"
    wolf.x = 6
    assert visible_creatures(world, wolf, [wolf, rabbit]) == [rabbit]


def test_hiding_prey_is_flagged_for_wolves():
    rows = open_rows(12, 3)
    rows[1] = "...T........"
    world = world_from_rows(rows, plants="none")
    wolf = make_creature("wolf", 5, 1, cid="w1")
    rabbit = make_creature("rabbit", 3, 1, last_action="hide", name="Pip")
    sees = build_request(world, wolf, [wolf, rabbit]).view["sees"]
    assert sees[0] == "prey: rabbit Pip, 2 tiles west (hiding in forest)"


def test_wolves_see_prey_not_danger_and_ignore_wolf_carcasses():
    world = world_from_rows(open_rows(), plants="none")
    wolf = make_creature("wolf", 5, 5, cid="w1")
    deer = make_creature("deer", 7, 5, cid="d1", name="Birch")
    world.add_carcass(4, 5, "wolf", 5)
    world.add_carcass(5, 7, "rabbit", 5)
    request = build_request(world, wolf, [wolf, deer])
    assert request.view["diet"] == "eats meat"
    assert request.view["standing_on"] == "open grass"
    assert request.view["sees"] == ["prey: deer Birch, 2 tiles east", "carcass of a rabbit, 2 tiles south"]
    assert request.signals["prey_dist"] == 2 and request.signals["carcass_dist"] == 2
    assert request.signals["threat_dist"] is None
    assert list(request.options)[:2] == ["hunt", "scavenge"]


def test_wolf_standing_on_grass_with_plants_is_not_told_about_them():
    world = world_from_rows(open_rows())  # plants everywhere
    wolf = make_creature("wolf", 5, 5, cid="w1")
    assert build_request(world, wolf, [wolf]).view["standing_on"] == "open grass"
    assert build_request(world, wolf, [wolf]).signals["food_here"] is False


def test_prey_see_only_the_two_nearest_wolves():
    world = world_from_rows(open_rows(), plants="none")
    rabbit = make_creature("rabbit", 5, 5)
    wolves = [make_creature("wolf", 5 + d, 5, cid=f"w{d}", name=f"W{d}") for d in (1, 2, 3)]
    sees = build_request(world, rabbit, [rabbit, *wolves]).view["sees"]
    assert sees[:2] == ["DANGER: wolf W1, 1 tile east", "DANGER: wolf W2, 2 tiles east"]
    assert not any("W3" in s for s in sees)


def test_objects_beyond_vision_are_not_seen():
    world = world_from_rows(open_rows(20, 3), plants="none")
    rabbit = make_creature("rabbit", 1, 1)
    far = make_creature("wolf", 7, 1, cid="w1")  # distance 6, rabbit vision is 5
    assert build_request(world, rabbit, [rabbit, far]).view["sees"] == ["nothing nearby"]
    deer = make_creature("deer", 1, 1, cid="d1")
    assert build_request(world, deer, [deer, far]).view["sees"][0].startswith("DANGER")
