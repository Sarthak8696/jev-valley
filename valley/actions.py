"""Carries out each action. The model only chooses what to do; this module decides how.

Every function takes the simulation and one creature and changes the world and
the creature. They draw randomness only from `sim.event_rng`.
"""

import math

from valley.perception import nearest_carcass, visible_creatures
from valley.species import ACTION_COST, PREY_SPECIES, WOLF
from valley.world import DIRECTIONS, FOREST, WATER, chebyshev

HIDING_CATCH_FACTOR = 0.5
FLEEING_CATCH_FACTOR = 0.7
EXPLORE_TURN_CHANCE = 0.25
SCAVENGE_STEPS = 2
SCAVENGE_BITE = 15


def execute(sim, creature) -> None:
    """Carry out the creature's executed action, then charge its upkeep for the hour."""
    HANDLERS[creature.executed](sim, creature)
    spec = creature.spec
    creature.energy -= spec.energy_loss * ACTION_COST[creature.executed]
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
        creature.energy = min(spec.max_energy, creature.energy + spec.plant_energy)
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
    partners = [c for c in _visible(sim, creature) if c.species == creature.species and c.can_breed()]
    if not partners:
        explore(sim, creature)
        return
    partner = partners[0]
    step_toward(sim, creature, partner.x, partner.y)
    if chebyshev(creature.x, creature.y, partner.x, partner.y) <= 1 and sim.cap_allows(creature.species):
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
    target = prey[0]
    for _ in range(creature.spec.hunt_speed):
        if chebyshev(creature.x, creature.y, target.x, target.y) <= 1:
            break
        if not step_toward(sim, creature, target.x, target.y):
            break
    if chebyshev(creature.x, creature.y, target.x, target.y) <= 1:
        _try_catch(sim, creature, target)


def _try_catch(sim, wolf, prey) -> None:
    chance = wolf.spec.catch_chance[prey.species]
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
