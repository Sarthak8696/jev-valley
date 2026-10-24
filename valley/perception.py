"""What a creature can see and feel, as plain language for a model and as raw signals for code.

`build_request` turns one creature's surroundings into a `DecisionRequest`. The
view is sent to the model. The signals are never sent: they are for the `rules`
brain and for the blunder metric.
"""

from valley.brains.base import DecisionRequest
from valley.questions import prey_questions, wolf_questions
from valley.species import PREY_SPECIES, WOLF, action_menu, plural
from valley.world import FOREST, WATER, chebyshev

HIDDEN_VISIBLE_DISTANCE = 2

_COMPASS = {
    (0, -1): "north", (1, -1): "north-east", (1, 0): "east", (1, 1): "south-east",
    (0, 1): "south", (-1, 1): "south-west", (-1, 0): "west", (-1, -1): "north-west",
}


def hunger_word(energy_ratio: float) -> str:
    if energy_ratio < 0.2:
        return "starving"
    if energy_ratio < 0.45:
        return "hungry"
    if energy_ratio < 0.8:
        return "fed"
    return "full"


def thirst_word(hydration_ratio: float) -> str:
    if hydration_ratio < 0.2:
        return "parched"
    if hydration_ratio < 0.45:
        return "thirsty"
    if hydration_ratio < 0.8:
        return "fine"
    return "quenched"


def direction(dx: int, dy: int) -> str:
    """One of the 8 compass words. The minor component is dropped when it is less than half the major one."""
    ax, ay = abs(dx), abs(dy)
    sx = (dx > 0) - (dx < 0)
    sy = (dy > 0) - (dy < 0)
    if ax < ay / 2:
        sx = 0
    elif ay < ax / 2:
        sy = 0
    return _COMPASS[(sx, sy)]


def where(ox: int, oy: int, tx: int, ty: int) -> str:
    distance = chebyshev(ox, oy, tx, ty)
    if distance == 0:
        return "right here"
    unit = "tile" if distance == 1 else "tiles"
    return f"{distance} {unit} {direction(tx - ox, ty - oy)}"


CONDITION_WORDS = ("looks well", "looks tired", "looks weak")


def condition(energy_ratio: float) -> int:
    """How worn an animal looks from outside: 0 well, 1 tired, 2 weak. Coarser than its real energy."""
    return 0 if energy_ratio >= 0.6 else 1 if energy_ratio >= 0.3 else 2


def prey_cues(prey: list, living) -> list[dict]:
    """What a wolf can see of each of up to three prey animals: how far, how worn, whether young, whether alone."""
    cues = []
    for animal in prey[:3]:
        company = any(o is not animal and o.alive and o.species == animal.species
                      and chebyshev(o.x, o.y, animal.x, animal.y) <= 3 for o in living)
        cues.append({"id": animal.id, "cond": condition(animal.energy_ratio), "young": not animal.is_adult,
                     "alone": not company})
    return cues


def is_hidden(world, creature) -> bool:
    """A creature on forest whose previous action was `hide` is only seen from close by."""
    return creature.last_action == "hide" and world.terrain(creature.x, creature.y) == FOREST


def nearest_first(observer, creatures) -> list:
    def key(c):
        dx, dy = c.x - observer.x, c.y - observer.y
        return max(abs(dx), abs(dy)), dx * dx + dy * dy, c.id
    return sorted(creatures, key=key)


def visible_creatures(world, observer, living) -> list:
    """Every other living creature the observer can see, nearest first."""
    vision = observer.spec.vision
    seen = []
    for other in living:
        if other is observer or not other.alive:
            continue
        distance = chebyshev(observer.x, observer.y, other.x, other.y)
        if distance <= vision and (distance <= HIDDEN_VISIBLE_DISTANCE or not is_hidden(world, other)):
            seen.append(other)
    return nearest_first(observer, seen)


def nearest_carcass(world, creature):
    """The nearest visible carcass. Wolves ignore wolf carcasses. Returns (carcass, distance) or None."""
    vision = creature.spec.vision
    predator = creature.spec.is_predator
    best, best_key = None, None
    for carcass in world.carcasses:
        if predator and carcass.species == WOLF:
            continue
        dx, dy = carcass.x - creature.x, carcass.y - creature.y
        distance = max(abs(dx), abs(dy))
        if distance > vision:
            continue
        key = (distance, dx * dx + dy * dy, carcass.id)
        if best_key is None or key < best_key:
            best, best_key = carcass, key
    return None if best is None else (best, best_key[0])


def _standing_on(world, creature) -> str:
    terrain = world.terrain(creature.x, creature.y)
    if creature.spec.is_predator:  # plants mean nothing to a meat eater
        return "forest cover" if terrain == FOREST else "open grass"
    has_plants = world.plants(creature.x, creature.y) > 0
    if terrain == FOREST:
        return "forest cover, with berries" if has_plants else "forest cover"
    return "open grass, with plants to eat" if has_plants else "open grass, grazed bare"


def _can_have_young(creature) -> str:
    if not creature.is_adult:
        return "no, too young"
    if creature.cooldown > 0:
        return "no, had young recently"
    if creature.energy < creature.spec.breed_min_energy:
        return "no, too hungry"
    return "yes"


def build_request(world, creature, living, rich: bool = False) -> DecisionRequest:
    """Build the view and signals for one creature from the world as it is now.

    With `rich`, the request also carries the extra score and noul questions (valley/questions.py), and a wolf's
    view says how each prey animal looks, so that it has something to judge.

    Side effect: if the creature can see water, it remembers the nearest water tile.
    """
    spec = creature.spec
    predator = spec.is_predator
    vision = spec.vision
    x, y = creature.x, creature.y

    visible = visible_creatures(world, creature, living)
    wolves = [] if predator else [c for c in visible if c.species == WOLF]
    prey = [c for c in visible if c.species in PREY_SPECIES] if predator else []
    kin = [c for c in visible if c.species == creature.species]
    can_mate = creature.can_breed()
    partners = [c for c in kin if c.can_breed()]

    water = world.nearest_terrain(WATER, x, y, vision)
    if water is not None:
        creature.known_water = water
    on_forest = world.terrain(x, y) == FOREST
    forest = None if on_forest else world.nearest_terrain(FOREST, x, y, vision)
    plants = None if predator else world.nearest_plants(x, y, vision)
    carcass = nearest_carcass(world, creature)

    cues = prey_cues(prey, living) if predator else []
    sees = []
    if not predator:
        for wolf in wolves[:2]:
            text = f"DANGER: wolf {wolf.name}, {where(x, y, wolf.x, wolf.y)}"
            if wolf.last_action == "hunt":
                text += ", hunting"
            sees.append(text)
    else:
        for animal, cue in zip(prey[:3], cues):
            text = f"prey: {animal.species} {animal.name}, {where(x, y, animal.x, animal.y)}"
            if rich:
                text += (", young" if cue["young"] else "") + (", alone" if cue["alone"] else "") + ", " + CONDITION_WORDS[cue["cond"]]
            if is_hidden(world, animal):
                text += " (hiding in forest)"
            sees.append(text)
    if kin:
        noun = creature.species if len(kin) == 1 else plural(creature.species)
        sees.append(f"{len(kin)} other {noun}, nearest {where(x, y, kin[0].x, kin[0].y)}")
    if can_mate and partners:
        sees.append(f"possible partner: {partners[0].name}, {where(x, y, partners[0].x, partners[0].y)}")
    if water is not None:
        sees.append("water, next to me" if chebyshev(x, y, *water) <= 1 else f"water, {where(x, y, *water)}")
    elif creature.known_water is not None:
        sees.append(f"no water in sight; I remember water {where(x, y, *creature.known_water)}")
    if plants is not None:
        sees.append(f"plants to eat, {where(x, y, *plants)}")
    if carcass is not None:
        found = carcass[0]
        sees.append(f"carcass of a {found.species}, {where(x, y, found.x, found.y)}")
    if forest is not None:
        sees.append(f"forest cover, {where(x, y, *forest)}")
    if not sees:
        sees.append("nothing nearby")

    stage = "adult" if creature.is_adult else "young"
    view = {
        "id": creature.id,
        "animal": creature.display_name,
        "diet": "eats meat" if predator else "eats plants",
        "personality": creature.personality,
        "age": f"{creature.age // 24} days ({stage})",
        "hunger": hunger_word(creature.energy_ratio),
        "thirst": thirst_word(creature.hydration_ratio),
        "standing_on": _standing_on(world, creature),
        "can_have_young": _can_have_young(creature),
        "sees": sees,
        "recent": list(creature.memory[-3:]) or ["nothing yet"],
    }

    signals = {
        "species": creature.species,
        "energy": creature.energy_ratio,
        "hydration": creature.hydration_ratio,
        "personality": creature.personality,
        "threat_dist": chebyshev(x, y, wolves[0].x, wolves[0].y) if wolves else None,
        "prey_dist": chebyshev(x, y, prey[0].x, prey[0].y) if prey else None,
        "mate_dist": chebyshev(x, y, partners[0].x, partners[0].y) if partners else None,
        "water_dist": chebyshev(x, y, *water) if water is not None else None,
        "water_known": water is not None or creature.known_water is not None,
        "forest_dist": 0 if on_forest else (chebyshev(x, y, *forest) if forest is not None else None),
        "carcass_dist": carcass[1] if carcass is not None else None,
        "group_dist": chebyshev(x, y, kin[0].x, kin[0].y) if kin else None,
        "water_adjacent": world.next_to_water(x, y),
        "food_here": (not predator) and world.plants(x, y) > 0,
        "can_mate": can_mate,
        "prey_cues": cues,
    }
    questions, truth = [], {}
    if rich:
        questions = wolf_questions(prey) if predator else prey_questions()
        if predator:
            truth["weak"] = {p.id: p.energy_ratio for p in prey[:3]}
    return DecisionRequest(creature.id, view, action_menu(creature.species), signals, questions, truth)
