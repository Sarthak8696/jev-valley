"""Carries out each action. The model only chooses what to do; this module decides how.

Every function takes the simulation and one creature and changes the world and
the creature. They draw randomness only from `sim.event_rng`.
"""

import math

from valley.perception import nearest_carcass, visible_creatures
from valley.questions import NEUTRAL
from valley.species import ACTION_COST, PREY_SPECIES, WOLF
from valley.world import DIRECTIONS, FOREST, WATER, chebyshev

HIDING_CATCH_FACTOR = 0.5
FLEEING_CATCH_FACTOR = 0.7
# Wolves are not perfect hunters. Yellowstone wolves succeed in roughly 15-26% of hunts and prefer calves and
# weakened animals, so a hunting wolf can lose a prey that is still some way off, and a weak animal is easier to catch.
LOSE_TRAIL_DISTANCE = 2
LOSE_TRAIL_CHANCE = 0.4
WEAK_PREY_BIAS = 1.0  # catch chance changes by this much for every 100% of energy the prey is below half
WEAK_PREY_RANGE = (0.4, 1.6)
# How the world reacts to the answers of the rich mode (valley/questions.py). Each is the change per level of a 0 to 4
# score above or below the neutral 2, so a brain that answers 2 everywhere plays the choice-only game.
ALERT_INTAKE_PER_LEVEL = 0.08  # grazing yield falls this much per level of alertness
ALERT_CATCH_PER_LEVEL = 0.10  # a wolf's chance against that animal falls this much per level
EFFORT_CATCH_PER_LEVEL = 0.08  # a wolf's chance of a catch rises this much per level of chase effort
EFFORT_COST_PER_LEVEL = 0.15  # and a hunting hour costs this much more energy
EFFORT_TRAIL_PER_LEVEL = 0.08  # and it loses the trail this much less often
TARGET_DISTANCE_WEIGHT = 0.35  # a wolf trades one level of weakness for this many tiles of distance
EXPLORE_TURN_CHANCE = 0.25
SCAVENGE_STEPS = 2
SCAVENGE_BITE = 15


def execute(sim, creature) -> None:
    """Carry out the creature's executed action, then charge its upkeep for the hour."""
    HANDLERS[creature.executed](sim, creature)
    spec = creature.spec
    cost = ACTION_COST[creature.executed]
    if creature.executed == "hunt":
        cost *= 1 + EFFORT_COST_PER_LEVEL * (creature.effort - NEUTRAL)
    creature.energy -= spec.energy_loss * cost
    creature.hydration -= spec.hydration_loss


# -- movement ---------------------------------------------------------------

def _free_neighbours(sim, creature):
    for dx, dy in DIRECTIONS:
        nx, ny = creature.x + dx, creature.y + dy
        if sim.world.passable(nx, ny) and (nx, ny) not in sim.occupied:
            yield nx, ny


def _move(sim, creature, nx: int, ny: int) -> None:
    del sim.occupied[(creature.x, creature.y)]
    creature.x, creature.y = nx, ny
    sim.occupied[(nx, ny)] = creature
    creature.path.append((nx, ny))


def step_toward(sim, creature, tx: int, ty: int) -> bool:
    """Take one step to the free neighbour that most reduces Chebyshev distance to the target.

    Ties break by straight-line distance, then by `event_rng`. Stays put if no neighbour is closer.
    """
    current = chebyshev(creature.x, creature.y, tx, ty)
    options = [(chebyshev(nx, ny, tx, ty), (nx - tx) ** 2 + (ny - ty) ** 2, nx, ny)
               for nx, ny in _free_neighbours(sim, creature)]
    if not options:
        return False
    best = min((o[0], o[1]) for o in options)
    if best[0] >= current:
        return False
    ties = [o for o in options if (o[0], o[1]) == best]
    chosen = ties[0] if len(ties) == 1 else sim.event_rng.choice(ties)
    _move(sim, creature, chosen[2], chosen[3])
    return True


def step_away(sim, creature, tx: int, ty: int) -> bool:
    """The reverse of `step_toward`: the free neighbour that most increases distance from the target."""
    current = chebyshev(creature.x, creature.y, tx, ty)
    options = [(chebyshev(nx, ny, tx, ty), (nx - tx) ** 2 + (ny - ty) ** 2, nx, ny)
               for nx, ny in _free_neighbours(sim, creature)]
    if not options:
        return False
    best = max((o[0], o[1]) for o in options)
    if best[0] <= current:
        return False
    ties = [o for o in options if (o[0], o[1]) == best]
    chosen = ties[0] if len(ties) == 1 else sim.event_rng.choice(ties)
    _move(sim, creature, chosen[2], chosen[3])
    return True


def _visible(sim, creature):
    return visible_creatures(sim.world, creature, sim.living)


# -- actions ----------------------------------------------------------------

def explore(sim, creature) -> None:
    rng = sim.event_rng
    if rng.random() < EXPLORE_TURN_CHANCE:
        creature.heading = rng.choice(DIRECTIONS)
    nx, ny = creature.x + creature.heading[0], creature.y + creature.heading[1]
    if sim.world.passable(nx, ny) and (nx, ny) not in sim.occupied:
        _move(sim, creature, nx, ny)
    else:
        creature.heading = rng.choice(DIRECTIONS)


def eat(sim, creature) -> None:
    world, spec = sim.world, creature.spec
    if world.plants(creature.x, creature.y) > 0:
        world.eat_plant(creature.x, creature.y)
        gain = spec.plant_energy * max(0.3, 1 - ALERT_INTAKE_PER_LEVEL * (creature.alertness - NEUTRAL))
        creature.energy = min(spec.max_energy, creature.energy + gain)
        return
    target = world.nearest_plants(creature.x, creature.y, spec.vision, include_here=False,
                                  occupied=sim.occupied)
    if target is None:
        explore(sim, creature)
    else:
        step_toward(sim, creature, *target)


def drink(sim, creature) -> None:
    world, spec = sim.world, creature.spec
    if not world.next_to_water(creature.x, creature.y):
        target = world.nearest_terrain(WATER, creature.x, creature.y, spec.vision) or creature.known_water
        if target is None:
            explore(sim, creature)
            return
        step_toward(sim, creature, *target)
    if world.next_to_water(creature.x, creature.y):
        creature.hydration = spec.max_hydration


def flee(sim, creature) -> None:
    wolves = [c for c in _visible(sim, creature) if c.species == WOLF]
    if not wolves:
        explore(sim, creature)
        return
    threat = wolves[0]
    for _ in range(creature.spec.flee_speed):
        if not step_away(sim, creature, threat.x, threat.y):
            break


def hide(sim, creature) -> None:
    if sim.world.terrain(creature.x, creature.y) == FOREST:
        return
    target = sim.world.nearest_free_forest(creature.x, creature.y, creature.spec.vision, sim.occupied)
    if target is not None:
        step_toward(sim, creature, *target)


def rest(sim, creature) -> None:
    return None


def seek_mate(sim, creature) -> None:
    if not creature.can_breed():
        explore(sim, creature)
        return
    partners = [c for c in _visible(sim, creature) if c.species == creature.species and c.can_breed() and c.breed_ok]
    if not partners:
        explore(sim, creature)
        return
    partner = partners[0]
    step_toward(sim, creature, partner.x, partner.y)
    if chebyshev(creature.x, creature.y, partner.x, partner.y) <= 1 and creature.breed_ok and sim.cap_allows(creature.species):
        sim.breed(creature, partner)


def follow_group(sim, creature) -> None:
    kin = [c for c in _visible(sim, creature) if c.species == creature.species]
    if not kin:
        return
    cx = math.floor(sum(c.x for c in kin) / len(kin) + 0.5)
    cy = math.floor(sum(c.y for c in kin) / len(kin) + 0.5)
    step_toward(sim, creature, cx, cy)


def hunt(sim, creature) -> None:
    prey = [c for c in _visible(sim, creature) if c.species in PREY_SPECIES]
    if not prey:
        explore(sim, creature)
        return
    target = pick_target(creature, prey)
    trail_chance = min(0.9, max(0.05, LOSE_TRAIL_CHANCE - EFFORT_TRAIL_PER_LEVEL * (creature.effort - NEUTRAL)))
    if (chebyshev(creature.x, creature.y, target.x, target.y) > LOSE_TRAIL_DISTANCE
            and sim.event_rng.random() < trail_chance):
        creature.remember(sim.step_no, f"lost the trail of {target.name} the {target.species}")
        explore(sim, creature)
        return
    for _ in range(creature.spec.hunt_speed):
        if chebyshev(creature.x, creature.y, target.x, target.y) <= 1:
            break
        if not step_toward(sim, creature, target.x, target.y):
            break
    if chebyshev(creature.x, creature.y, target.x, target.y) <= 1:
        _try_catch(sim, creature, target)


def pick_target(wolf, prey: list):
    """The prey animal to chase. `prey` is nearest first. Without any weakness scores that is the nearest.

    With them, among the first three the wolf takes the best trade of weakness against distance, the nearest on a tie.
    An animal the wolf has not judged (it came into view after the question was asked) counts as neutral.
    """
    if not wolf.weak_scores:
        return prey[0]
    scored = [(wolf.weak_scores.get(p.id, NEUTRAL) - TARGET_DISTANCE_WEIGHT * chebyshev(wolf.x, wolf.y, p.x, p.y), -i, p)
              for i, p in enumerate(prey[:3])]
    return max(scored, key=lambda item: item[:2])[2]


def _try_catch(sim, wolf, prey) -> None:
    prey.attacked = True
    chance = wolf.spec.catch_chance[prey.species]
    low, high = WEAK_PREY_RANGE
    chance *= max(low, min(high, 1.0 + WEAK_PREY_BIAS * (0.5 - prey.energy_ratio)))
    chance *= max(0.2, 1 + ALERT_CATCH_PER_LEVEL * (NEUTRAL - prey.alertness))
    chance *= max(0.2, 1 + EFFORT_CATCH_PER_LEVEL * (wolf.effort - NEUTRAL))
    chance = min(0.95, chance)
    if sim.world.terrain(prey.x, prey.y) == FOREST and prey.executed == "hide":
        chance *= HIDING_CATCH_FACTOR
    if prey.executed == "flee":
        chance *= FLEEING_CATCH_FACTOR
    if sim.event_rng.random() < chance:
        carcass = sim.kill(prey, "eaten")
        sim.events.append(f"{wolf.name} the wolf caught {prey.name} the {prey.species}")
        wolf.remember(sim.step_no, f"caught {prey.name} the {prey.species}")
        _eat_from(sim, wolf, carcass, carcass.meat)
    else:
        sim.events.append(f"{wolf.name} the wolf missed {prey.name} the {prey.species}")
        wolf.remember(sim.step_no, f"{prey.name} the {prey.species} got away")
        prey.remember(sim.step_no, f"escaped {wolf.name} the wolf")


def _eat_from(sim, wolf, carcass, limit: float) -> float:
    """Eat up to `limit` meat, no more than the carcass holds or the wolf has room for. 1 meat is 1 energy."""
    room = wolf.spec.max_energy - wolf.energy
    amount = max(0.0, min(limit, carcass.meat, room))
    wolf.energy += amount
    carcass.meat -= amount
    if carcass.meat <= 1e-9:
        sim.world.remove_carcass(carcass)
    return amount


def scavenge(sim, creature) -> None:
    found = nearest_carcass(sim.world, creature)
    if found is None:
        explore(sim, creature)
        return
    carcass = found[0]
    for _ in range(SCAVENGE_STEPS):
        if chebyshev(creature.x, creature.y, carcass.x, carcass.y) <= 1:
            break
        if not step_toward(sim, creature, carcass.x, carcass.y):
            break
    if chebyshev(creature.x, creature.y, carcass.x, carcass.y) <= 1:
        species = carcass.species
        if _eat_from(sim, creature, carcass, SCAVENGE_BITE) > 0:
            creature.remember(sim.step_no, f"ate from a {species} carcass")


HANDLERS = {
    "eat": eat, "drink": drink, "flee": flee, "hide": hide, "rest": rest,
    "seek_mate": seek_mate, "follow_group": follow_group, "explore": explore,
    "hunt": hunt, "scavenge": scavenge,
}
