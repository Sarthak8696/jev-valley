"""The creature record and its short memory."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from valley.clock import clock_text
from valley.species import SPECIES, Species

if TYPE_CHECKING:
    from valley.brains.base import Decision

MEMORY_SIZE = 3
HESITATED = "hesitated"


@dataclass
class Creature:
    id: str
    species: str
    name: str
    personality: str
    x: int
    y: int
    energy: float
    hydration: float
    age: int = 0  # hours
    born: int = 0  # step
    cooldown: int = 0  # hours until it can breed again
    heading: tuple[int, int] = (0, 1)
    known_water: tuple[int, int] | None = None
    memory: list[str] = field(default_factory=list)  # last 3 notable events
    action: str | None = None  # this hour's choice, before hesitation
    executed: str | None = None  # the action actually carried out this hour
    last_action: str | None = None  # the executed action of the previous hour
    decision: "Decision | None" = None
    hesitated: bool = False
    path: list[tuple[int, int]] = field(default_factory=list)  # tiles entered this hour
    parents: tuple[str, ...] = ()
    alive: bool = True
    died: int | None = None
    cause: str | None = None
    notes: list[list] = field(default_factory=list)  # [[step, text], ...] for the replay
    start_age: int = 0  # age in hours when it entered the valley, so a replay can show its age at any step

    @property
    def spec(self) -> Species:
        return SPECIES[self.species]

    @property
    def display_name(self) -> str:
        return f"{self.name} the {self.species}"

    @property
    def energy_ratio(self) -> float:
        return self.energy / self.spec.max_energy

    @property
    def hydration_ratio(self) -> float:
        return self.hydration / self.spec.max_hydration

    @property
    def is_adult(self) -> bool:
        return self.age >= self.spec.adult_age

    def can_breed(self) -> bool:
        spec = self.spec
        return self.is_adult and self.cooldown <= 0 and self.energy >= spec.breed_min_energy

    def remember(self, step: int, text: str) -> None:
        """Add a notable event. Only the last three are kept; the replay keeps every one except hesitation."""
        self.memory.append(f"{clock_text(step)}: {text}")
        del self.memory[:-MEMORY_SIZE]
        if text != HESITATED:
            self.notes.append([step, text])
