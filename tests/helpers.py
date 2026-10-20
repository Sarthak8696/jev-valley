"""Small builders for hand-made worlds and creatures."""

import random

from valley.brains.base import Brain, Decision
from valley.creatures import Creature
from valley.simulation import Simulation
from valley.species import SPECIES
from valley.world import PLANT_MAX, World


class FixedRng:
    """A stand-in for `event_rng` whose every answer is predictable."""

    def __init__(self, roll=0.5):
        self.roll = roll

    def random(self):
        return self.roll

    def choice(self, seq):
        return seq[0]

    def randint(self, a, b):
        return a

    def randrange(self, n):
        return 0

    def uniform(self, a, b):
        return a

    def sample(self, population, k):
        return list(population)[:k]

    def shuffle(self, seq):
        return None


class ScriptedBrain(Brain):
    """Chooses the action named for each creature id (or `default`), with a fixed confidence."""
    name = "scripted"

    def __init__(self, choices=None, default="rest", confidence=1.0, source="baseline"):
        self.choices = choices or {}
        self.default = default
        self.confidence = confidence
        self.source = source

    def decide(self, requests, step=0):
        out = []
        for request in requests:
            choice = self.choices.get(request.creature_id, self.default)
            if callable(choice):
                choice = choice(request, step)
            out.append(Decision(choice, {choice: 1.0}, self.confidence, self.source))
        return out


def make_sim(world, creatures, choices=None, default="rest", confidence=1.0, **kwargs):
    brain = ScriptedBrain(choices, default, confidence)
    brains = {species: brain for species in SPECIES}
    return Simulation(seed=1, brains=brains, world=world, creatures=creatures, **kwargs)


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
