import pytest

from valley.creatures import Creature
from valley.species import ACTION_COST, SPECIES, action_menu, plural

# Spec 5.3 (fixed) and 5.4 (tunable starting values), written out literally.
EXPECTED = {
    "rabbit": dict(diet="plants", vision=5, litter=(1, 3), flee_speed=2, hunt_speed=0,
                   cap_share=0.6, start_count=16, max_energy=30, max_hydration=30,
                   energy_loss=0.45, hydration_loss=0.6, adult_age=96, breed_min_energy=16,
                   breed_cost=7, breed_cooldown=72, plant_energy=5, meat_value=14),
    "deer": dict(diet="plants", vision=6, litter=(1, 2), flee_speed=2, hunt_speed=0,
                 cap_share=0.3, start_count=7, max_energy=50, max_hydration=45,
                 energy_loss=0.55, hydration_loss=0.7, adult_age=240, breed_min_energy=26,
                 breed_cost=12, breed_cooldown=168, plant_energy=6, meat_value=34),
    "wolf": dict(diet="meat", vision=6, litter=(1, 2), flee_speed=0, hunt_speed=2,
                 cap_share=0.14, start_count=3, max_energy=60, max_hydration=45,
                 energy_loss=0.5, hydration_loss=0.6, adult_age=360, breed_min_energy=44,
                 breed_cost=22, breed_cooldown=336, plant_energy=0, meat_value=20),
}


@pytest.mark.parametrize("key", EXPECTED)
def test_species_values_match_the_spec(key):
    species = SPECIES[key]
    for name, value in EXPECTED[key].items():
        assert getattr(species, name) == value, name


def test_wolf_catch_chances():
    assert SPECIES["wolf"].catch_chance == {"rabbit": 0.45, "deer": 0.22}


def test_name_lists():
    assert len(SPECIES["rabbit"].names) == 14
    assert len(SPECIES["deer"].names) == 10
    assert len(SPECIES["wolf"].names) == 10
    assert SPECIES["rabbit"].names[0] == "Clover"
    assert SPECIES["wolf"].names[-1] == "Smoke"


def test_action_menus_follow_the_species_action_order():
    assert list(action_menu("rabbit")) == ["eat", "drink", "flee", "hide", "rest", "seek_mate",
                                           "follow_group", "explore"]
    assert list(action_menu("deer")) == list(action_menu("rabbit"))
    assert list(action_menu("wolf")) == ["hunt", "scavenge", "drink", "hide", "rest", "seek_mate",
                                         "follow_group", "explore"]
    assert action_menu("wolf")["hide"] == "Wait in forest cover to ambush prey"
    assert action_menu("rabbit")["flee"].startswith("Run away")


def test_every_action_has_a_cost_multiplier():
    for species in SPECIES.values():
        for action in species.actions:
            assert action in ACTION_COST
    assert ACTION_COST["flee"] == 1.6 and ACTION_COST["hunt"] == 1.5 and ACTION_COST["rest"] == 0.5


def test_plurals():
    assert plural("rabbit") == "rabbits" and plural("deer") == "deer" and plural("wolf") == "wolves"


def make(species="rabbit", **kw):
    spec = SPECIES[species]
    base = dict(id="r1", species=species, name="Clover", personality="timid", x=1, y=1,
                energy=spec.max_energy, hydration=spec.max_hydration, age=spec.adult_age)
    base.update(kw)
    return Creature(**base)


def test_memory_keeps_the_last_three_and_formats_the_clock():
    c = make()
    for step, text in [(0, "a"), (1, "b"), (2, "c"), (3, "d")]:
        c.remember(step, text)
    assert c.memory == ["Day 1, 7 am: b", "Day 1, 8 am: c", "Day 1, 9 am: d"]


def test_hesitation_is_remembered_but_not_noted_for_the_replay():
    c = make()
    c.remember(4, "hesitated")
    c.remember(5, "escaped Ash the wolf")
    assert c.memory[0].endswith("hesitated")
    assert c.notes == [[5, "escaped Ash the wolf"]]


def test_can_breed_needs_adult_cooldown_and_energy():
    assert make().can_breed()
    assert not make(age=10).can_breed()
    assert not make(cooldown=5).can_breed()
    assert not make(energy=10).can_breed()


def test_display_name_and_ratios():
    c = make(energy=15, hydration=15)
    assert c.display_name == "Clover the rabbit"
    assert c.energy_ratio == 0.5 and c.hydration_ratio == 0.5
