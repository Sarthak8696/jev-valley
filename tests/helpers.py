"""Small builders for hand-made worlds and creatures."""

import random

from valley.creatures import Creature
from valley.species import SPECIES
from valley.world import PLANT_MAX, World


def world_from_rows(rows, plants=None, seed=0):
    """A world from text rows (`.` grass, `T` forest, `~` water, `^` rock).

    Plants start at each tile's maximum unless `plants` maps (x, y) -> amount for every tile,
    or is the string "none" for a bare world.
    """
    width, height = len(rows[0]), len(rows)
    cells = "".join(rows)
    if plants == "none":
        food = [0] * len(cells)
    elif plants is None:
        food = [PLANT_MAX[c] for c in cells]
    else:
        food = [plants.get((i % width, i // width), 0) for i in range(len(cells))]
    return World(width, height, cells, food, random.Random(seed))


def open_rows(width=12, height=10):
    return ["." * width for _ in range(height)]


def make_creature(species, x, y, cid=None, name=None, **overrides):
    """A fully fed, hydrated adult unless overridden."""
    spec = SPECIES[species]
    cid = cid or f"{species[0]}1"
    fields = dict(
        id=cid, species=species, name=name or cid, personality="bold", x=x, y=y,
        energy=spec.max_energy, hydration=spec.max_hydration, age=spec.adult_age,
    )
    fields.update(overrides)
    return Creature(**fields)
