"""The hourly loop: perceive, decide, act, age, die, record.

Every living creature decides once per hour, all from the same snapshot of the
world. The loop waits for every decision before any action is carried out.
"""

import random
import re
import time
from concurrent.futures import ThreadPoolExecutor

from valley import actions
from valley.creatures import HESITATED, Creature
from valley.perception import build_request
from valley.species import ID_PREFIX, PERSONALITIES, SPECIES, SPECIES_ORDER, plural, species_cap
from valley.world import (
    DEFAULT_HEIGHT, DEFAULT_MAX_CREATURES, DEFAULT_WIDTH, DIRECTIONS, World, derive_seed,
)

HOURS_PER_DAY = 24
FOOD_SNAPSHOT_EVERY = 24

# Share of a creature's meat value left as a carcass, by cause of death (spec 5.2).
CARCASS_RATIO = {"eaten": 1.0, "starved": 0.4, "thirst": 0.6}


class Simulation:
    def __init__(self, seed: int, brains: dict, days: int = 30, width: int = DEFAULT_WIDTH,
                 height: int = DEFAULT_HEIGHT, max_creatures: int = DEFAULT_MAX_CREATURES,
                 hesitate_below: float | None = None, tally=None, world: World | None = None,
                 creatures: list[Creature] | None = None):
        self.seed = seed
        self.brains = brains  # species key -> Brain; species may share one instance
        self.steps = days * HOURS_PER_DAY
        self.max_creatures = max_creatures
        self.hesitate_below = hesitate_below
        self.tally = tally  # optional: records each decision for the blunder and calibration metrics
        self.world = world if world is not None else World.generate(seed, width, height)
        self.event_rng = random.Random(derive_seed(seed, "event"))
        self.step_no = 0
        self.events: list[str] = []
        self.creatures: dict[str, Creature] = {}  # every creature ever, in order of creation
        self.living: list[Creature] = []
        self.occupied: dict[tuple[int, int], Creature] = {}
        self.hour_seconds: list[float] = []
        self._id_counts = {key: 0 for key in SPECIES}
        self._name_counts: dict[str, int] = {}
        self._last_food: list[int] | None = None
        if creatures is None:
            self._spawn_starting_creatures()
        else:
            for creature in creatures:
                self.register(creature)
        self.frames = [self._frame()]

    # -- creatures --------------------------------------------------------

    def register(self, creature: Creature) -> None:
        creature.start_age = creature.age
        self.creatures[creature.id] = creature
        self.living.append(creature)
        self.occupied[(creature.x, creature.y)] = creature
        match = re.fullmatch(r"[a-z](\d+)", creature.id)
        if match:
            count = self._id_counts[creature.species]
            self._id_counts[creature.species] = max(count, int(match.group(1)))

    def _new_id(self, species: str) -> str:
        self._id_counts[species] += 1
        return f"{ID_PREFIX[species]}{self._id_counts[species]}"

    def _unique_name(self, base: str) -> str:
        count = self._name_counts.get(base, 0) + 1
        self._name_counts[base] = count
        return base if count == 1 else f"{base} {count}"

    def _spawn_starting_creatures(self) -> None:
        rng, world = self.event_rng, self.world
        free = [(x, y) for y in range(world.height) for x in range(world.width) if world.passable(x, y)]
        for key in SPECIES_ORDER:
            spec = SPECIES[key]
            for _ in range(spec.start_count):
                i = rng.randrange(len(free))
                x, y = free[i]
                free[i] = free[-1]
                free.pop()
                creature = Creature(
                    id=self._new_id(key), species=key,
                    name=self._unique_name(rng.choice(spec.names)),
                    personality=rng.choice(PERSONALITIES), x=x, y=y,
                    heading=rng.choice(DIRECTIONS),
                    age=rng.randint(spec.adult_age, 2 * spec.adult_age),
                    energy=spec.max_energy * rng.uniform(0.6, 0.9),
                    hydration=spec.max_hydration * 0.8,
                )
                self.register(creature)

    def counts(self) -> dict[str, int]:
        counts = {key: 0 for key in SPECIES_ORDER}
        for creature in self.living:
            if creature.alive:
                counts[creature.species] += 1
        return counts

    def cap_allows(self, species: str) -> bool:
        """A species cannot breed at or above its share of the cap, or when the total is at the cap."""
        counts = self.counts()
        return (counts[species] < species_cap(species, self.max_creatures)
                and sum(counts.values()) < self.max_creatures)

    def kill(self, creature: Creature, cause: str):
        """Mark a creature dead and leave a carcass on its tile. Returns the carcass."""
        creature.alive = False
        creature.died = self.step_no
        creature.cause = cause
        self.occupied.pop((creature.x, creature.y), None)
        meat = creature.spec.meat_value * CARCASS_RATIO[cause]
        return self.world.add_carcass(creature.x, creature.y, creature.species, meat)

    def breed(self, starter: Creature, partner: Creature) -> int:
        """Have young next to `starter`. Returns the litter size, 0 if there was no room."""
        spec = starter.spec
        tiles = [(starter.x + dx, starter.y + dy) for dx, dy in DIRECTIONS
                 if self.world.passable(starter.x + dx, starter.y + dy)
                 and (starter.x + dx, starter.y + dy) not in self.occupied]
        room = self.max_creatures - sum(self.counts().values())
        litter = min(self.event_rng.randint(*spec.litter), len(tiles), room)
        if litter <= 0:
            return 0
        for x, y in self.event_rng.sample(tiles, litter):
            self._spawn_newborn(starter, partner, x, y)
        for parent, other in ((starter, partner), (partner, starter)):
            parent.energy -= spec.breed_cost
            parent.cooldown = spec.breed_cooldown
            parent.remember(self.step_no, f"had {litter} young with {other.name}")
        self.events.append(f"{starter.name} and {partner.name} the {plural(starter.species)} had {litter} young")
        return litter

    def _spawn_newborn(self, starter: Creature, partner: Creature, x: int, y: int) -> Creature:
        spec, rng = starter.spec, self.event_rng
        newborn = Creature(
            id=self._new_id(starter.species), species=starter.species,
            name=self._unique_name(rng.choice(spec.names)),
            personality=rng.choice(PERSONALITIES), x=x, y=y, heading=rng.choice(DIRECTIONS),
            age=0, born=self.step_no, energy=spec.max_energy * 0.5, hydration=spec.max_hydration * 0.8,
            known_water=starter.known_water, parents=(starter.id, partner.id),
        )
        self.register(newborn)
        return newborn

    # -- one hour ---------------------------------------------------------

    def step(self) -> dict:
        """Run one hour and return its frame."""
        self.step_no += 1
        t = self.step_no
        self.events = []
        self.world.update()

        participants = [c for c in self.living if c.alive]
        for creature in participants:
            creature.path = []
            creature.hesitated = False
        self._decide(participants)

        order = list(participants)
        self.event_rng.shuffle(order)
        for creature in order:
            if creature.alive:
                actions.execute(self, creature)

        for creature in participants:
            if creature.alive:
                creature.age += 1
                creature.cooldown = max(0, creature.cooldown - 1)
                creature.last_action = creature.executed
        self._deaths()
        self.living = [c for c in self.living if c.alive]

        frame = self._frame()
        self.frames.append(frame)
        return frame

    def _decide(self, participants: list[Creature]) -> None:
        groups: dict[int, tuple] = {}
        for creature in participants:
            request = build_request(self.world, creature, self.living)
            brain = self.brains[creature.species]
            groups.setdefault(id(brain), (brain, []))[1].append((creature, request))

        started = time.perf_counter()
        batches = list(groups.values())
        if len(batches) > 1:
            with ThreadPoolExecutor(max_workers=len(batches)) as pool:
                results = list(pool.map(lambda b: b[0].decide([r for _, r in b[1]], step=self.step_no), batches))
        else:
            results = [batch[0].decide([r for _, r in batch[1]], step=self.step_no) for batch in batches]
        self.hour_seconds.append(time.perf_counter() - started)

        for (brain, items), decisions in zip(batches, results):
            for (creature, request), decision in zip(items, decisions):
                creature.decision = decision
                creature.action = decision.choice
                creature.executed = decision.choice
                if self.tally is not None:
                    self.tally.record(brain.name, creature.species, request.signals, decision)
                if (self.hesitate_below is not None and decision.source != "fallback"
                        and decision.confidence < self.hesitate_below):
                    creature.executed = "rest"
                    creature.hesitated = True
                    creature.remember(self.step_no, HESITATED)

    def _deaths(self) -> None:
        for creature in self.living:
            if not creature.alive:
                continue
            if creature.energy <= 0:
                self.kill(creature, "starved")
                self.events.append(f"{creature.name} the {creature.species} starved")
            elif creature.hydration <= 0:
                self.kill(creature, "thirst")
                self.events.append(f"{creature.name} the {creature.species} died of thirst")

    def run(self, on_frame=None) -> list[dict]:
        """Run until the month ends or nobody is left alive."""
        while self.step_no < self.steps and any(c.alive for c in self.living):
            frame = self.step()
            if on_frame is not None:
                on_frame(frame)
        return self.frames

    # -- recording --------------------------------------------------------

    def _agent_row(self, creature: Creature) -> list:
        spec = creature.spec
        decided = creature.action is not None and creature.born < self.step_no
        if decided:
            decision = creature.decision
            confidence = -1 if decision.source == "fallback" else round(decision.confidence * 100)
            probabilities = [round(100 * decision.probabilities.get(a, 0.0)) for a in spec.actions]
            action = creature.action
        else:
            action, confidence, probabilities = None, -1, []
        return [
            creature.id, creature.x, creature.y, action, confidence, int(creature.hesitated),
            max(0, round(100 * creature.energy / spec.max_energy)),
            max(0, round(100 * creature.hydration / spec.max_hydration)),
            probabilities, [list(tile) for tile in creature.path],
        ]

    def _frame(self) -> dict:
        t = self.step_no
        food = self.world.food
        frame = {"step": t}
        if t % FOOD_SNAPSHOT_EVERY == 0 or self._last_food is None:
            frame["food"] = "".join(str(v) for v in food)
        else:
            last = self._last_food
            frame["food_diff"] = [[i, v] for i, v in enumerate(food) if v != last[i]]
        self._last_food = list(food)
        frame["agents"] = [self._agent_row(c) for c in self.creatures.values()
                           if c.died is None or c.died == t]
        frame["carcasses"] = [[c.x, c.y, round(c.meat, 1), c.species] for c in self.world.carcasses]
        frame["events"] = list(self.events)
        frame["pop"] = self.counts()
        return frame

    def summary(self) -> dict:
        """Run totals that are not derivable from the frames."""
        seconds = sorted(self.hour_seconds)

        def pick(q):
            return seconds[min(len(seconds) - 1, int(q * len(seconds)))] if seconds else None

        brains = {}
        for brain in self.brains.values():
            brains[brain.name] = brain.summary()
        return {
            "steps_run": self.step_no,
            "hour_seconds": {"p50": pick(0.5), "p95": pick(0.95),
                             "mean": sum(seconds) / len(seconds) if seconds else None},
            "brain_totals": brains,
            "tallies": self.tally.to_dict() if self.tally is not None else {},
        }
