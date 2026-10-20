"""The three species, their action menus and the personalities.

Section 5.3 of the spec lists the fixed values. Section 5.4 lists the tunable
values, which phase 5 tuned until the balance targets of 5.5 passed. The starting
value of every tunable that changed, and the reason, is in the Decisions log of
docs/build-spec.md. Changing any value means re-running every experiment.
"""

from dataclasses import dataclass, field

RABBIT, DEER, WOLF = "rabbit", "deer", "wolf"
PREY_SPECIES = (RABBIT, DEER)

PERSONALITIES = ("bold", "timid", "curious", "lazy", "greedy", "loyal", "restless", "cautious")

PREY_ACTIONS = ("eat", "drink", "flee", "hide", "rest", "seek_mate", "follow_group", "explore")
WOLF_ACTIONS = ("hunt", "scavenge", "drink", "hide", "rest", "seek_mate", "follow_group", "explore")

# Energy cost multiplier of each action (spec 5.11).
ACTION_COST = {
    "eat": 1.0, "drink": 1.0, "flee": 1.6, "hide": 0.8, "rest": 0.5,
    "seek_mate": 1.0, "follow_group": 1.0, "explore": 1.0, "hunt": 1.5, "scavenge": 1.0,
}

# What the model reads for each action, in the first person (spec 7.2).
PREY_DESCRIPTIONS = {
    "eat": "Eat the plants where I stand, or walk toward the nearest plants I can see",
    "drink": "Walk to the nearest water and drink",
    "flee": "Run away from the nearest predator as fast as I can",
    "hide": "Move into forest cover, or stay hidden there",
    "rest": "Stay still to save energy",
    "seek_mate": "Walk toward a partner of my kind and have young",
    "follow_group": "Move closer to others of my kind for safety",
    "explore": "Wander somewhere new to find food, water or partners",
}
WOLF_DESCRIPTIONS = {
    "hunt": "Chase the nearest prey animal and try to catch it",
    "scavenge": "Walk to the nearest carcass and eat from it",
    "drink": "Walk to the nearest water and drink",
    "hide": "Wait in forest cover to ambush prey",
    "rest": "Stay still to save energy",
    "seek_mate": "Walk toward a partner of my kind and have young",
    "follow_group": "Move closer to my pack",
    "explore": "Roam somewhere new to find prey, water or partners",
}

PLURALS = {RABBIT: "rabbits", DEER: "deer", WOLF: "wolves"}
ID_PREFIX = {RABBIT: "r", DEER: "d", WOLF: "w"}


@dataclass(frozen=True)
class Species:
    key: str
    diet: str  # "plants" or "meat"
    vision: int
    litter: tuple[int, int]
    flee_speed: int
    hunt_speed: int
    cap_share: float
    start_count: int
    names: tuple[str, ...]
    actions: tuple[str, ...]
    # Tunable values (spec 5.4)
    max_energy: float
    max_hydration: float
    energy_loss: float  # per hour, before the action cost multiplier
    hydration_loss: float  # per hour
    adult_age: int  # hours
    breed_min_energy: float
    breed_cost: float  # energy, paid by each parent
    breed_cooldown: int  # hours
    plant_energy: float  # energy per plant unit eaten, 0 for meat eaters
    meat_value: float
    catch_chance: dict = field(default_factory=dict)  # prey species -> chance, wolves only

    @property
    def is_predator(self) -> bool:
        return self.diet == "meat"

    @property
    def descriptions(self) -> dict:
        return WOLF_DESCRIPTIONS if self.is_predator else PREY_DESCRIPTIONS


SPECIES = {
    RABBIT: Species(
        key=RABBIT, diet="plants", vision=5, litter=(1, 3), flee_speed=2, hunt_speed=0,
        cap_share=0.6, start_count=24,
        names=("Clover", "Thistle", "Pip", "Bramble", "Hazel", "Juniper", "Moss", "Sorrel",
               "Fern", "Basil", "Nettle", "Poppy", "Tansy", "Yarrow"),
        actions=PREY_ACTIONS,
        max_energy=30, max_hydration=30, energy_loss=0.46, hydration_loss=0.47,
        adult_age=96, breed_min_energy=16, breed_cost=7.9, breed_cooldown=94,
        plant_energy=4.3, meat_value=22.7,
    ),
    DEER: Species(
        key=DEER, diet="plants", vision=6, litter=(1, 2), flee_speed=2, hunt_speed=0,
        cap_share=0.3, start_count=10,
        names=("Birch", "Aspen", "Rowan", "Willow", "Alder", "Larch", "Cedar", "Linden",
               "Holly", "Elm"),
        actions=PREY_ACTIONS,
        max_energy=50, max_hydration=45, energy_loss=0.6, hydration_loss=0.41,
        adult_age=240, breed_min_energy=26, breed_cost=14.0, breed_cooldown=212,
        plant_energy=6.9, meat_value=39.4,
    ),
    WOLF: Species(
        key=WOLF, diet="meat", vision=6, litter=(1, 2), flee_speed=0, hunt_speed=2,
        cap_share=0.14, start_count=5,
        names=("Ash", "Ember", "Flint", "Slate", "Cinder", "Storm", "Shade", "Grit", "Frost",
               "Smoke"),
        actions=WOLF_ACTIONS,
        max_energy=60, max_hydration=45, energy_loss=0.51, hydration_loss=0.48,
        adult_age=360, breed_min_energy=41, breed_cost=23.1, breed_cooldown=380,
        plant_energy=0, meat_value=18.0,
        catch_chance={RABBIT: 0.6, DEER: 0.13},
    ),
}

SPECIES_ORDER = (RABBIT, DEER, WOLF)


def action_menu(species_key: str) -> dict:
    """The action key -> first-person description menu, in the species' action order."""
    species = SPECIES[species_key]
    return {action: species.descriptions[action] for action in species.actions}


def plural(species_key: str) -> str:
    return PLURALS[species_key]


def species_cap(species_key: str, max_creatures: int) -> float:
    """A species' share of the creature cap. Rounded so that 50 * 0.14 is exactly 7, not 7.000000000000001."""
    return round(max_creatures * SPECIES[species_key].cap_share, 6)
