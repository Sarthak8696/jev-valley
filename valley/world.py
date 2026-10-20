"""The valley itself: terrain, plants and carcasses.

The world owns `world_rng`. Plant regrowth draws one number for every grass and
forest tile every hour, whatever the plants look like, so the regrowth dice are
the same for every brain that plays the same seed.
"""

import hashlib
import random
from dataclasses import dataclass
from functools import lru_cache

GRASS, FOREST, WATER, ROCK = ".", "T", "~", "^"

PLANT_MAX = {GRASS: 2, FOREST: 3, WATER: 0, ROCK: 0}
PASSABLE = (GRASS, FOREST)

# Compass order, clockwise from north. `x` grows east and `y` grows south.
DIRECTIONS = [(0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1)]

DEFAULT_WIDTH = 28
DEFAULT_HEIGHT = 18

# Tunable world values (spec 5.4). Changes are recorded in the Decisions log.
GRASS_REGROWTH = 0.015
FOREST_REGROWTH = 0.010
CARCASS_ROT = 0.3
CARCASS_LIFETIME = 72
DEFAULT_MAX_CREATURES = 50

MAX_MAP_ATTEMPTS = 500
MIN_WATER_AREAS = 2
MIN_PASSABLE_SHARE = 0.60


def derive_seed(seed: int, stream: str, attempt: int = 0) -> int:
    """A stable integer seed for a named random stream, independent of the Python version."""
    digest = hashlib.sha256(f"{seed}:{stream}:{attempt}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def chebyshev(ax: int, ay: int, bx: int, by: int) -> int:
    return max(abs(ax - bx), abs(ay - by))


@lru_cache(maxsize=None)
def offsets_by_distance(radius: int) -> tuple[tuple[int, int], ...]:
    """Every offset within `radius`, nearest first: Chebyshev distance, then straight-line distance,
    then row-major order. The first match in this order is the nearest tile, with a fixed tie-break."""
    points = [(dx, dy) for dy in range(-radius, radius + 1) for dx in range(-radius, radius + 1)]
    points.sort(key=lambda p: (max(abs(p[0]), abs(p[1])), p[0] * p[0] + p[1] * p[1], p[1], p[0]))
    return tuple(points)


@dataclass
class Carcass:
    id: int
    x: int
    y: int
    species: str
    meat: float
    age: int = 0


class World:
    def __init__(self, width: int, height: int, cells: str, food: list[int],
                 rng: random.Random, map_retries: int = 0):
        self.width = width
        self.height = height
        self.cells = cells  # row-major terrain characters
        self.food = food  # row-major plant units
        self.rng = rng  # world_rng
        self.map_retries = map_retries
        self.carcasses: list[Carcass] = []
        self._next_carcass_id = 1
        self.water_tiles = [(i % width, i // width) for i, c in enumerate(cells) if c == WATER]
        self._regrow_tiles = [i for i, c in enumerate(cells) if c in (GRASS, FOREST)]
        self._terrain_cache: dict[tuple, tuple[int, int] | None] = {}

    # -- generation -------------------------------------------------------

    @classmethod
    def generate(cls, seed: int, width: int = DEFAULT_WIDTH, height: int = DEFAULT_HEIGHT) -> "World":
        """Build the map for a seed, retrying with the next derived seed until it is playable."""
        for attempt in range(MAX_MAP_ATTEMPTS):
            rng = random.Random(derive_seed(seed, "world", attempt))
            cells = _generate_cells(rng, width, height)
            if not _playable(cells, width, height):
                continue
            food = [rng.randint(1, PLANT_MAX[c]) if PLANT_MAX[c] else 0 for c in cells]
            return cls(width, height, cells, food, rng, map_retries=attempt)
        raise RuntimeError(f"no playable {width}x{height} map found for seed {seed}")

    # -- tiles ------------------------------------------------------------

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def index(self, x: int, y: int) -> int:
        return y * self.width + x

    def terrain(self, x: int, y: int) -> str:
        return self.cells[y * self.width + x]

    def passable(self, x: int, y: int) -> bool:
        return self.in_bounds(x, y) and self.cells[y * self.width + x] in PASSABLE

    def plants(self, x: int, y: int) -> int:
        return self.food[y * self.width + x]

    def plant_max(self, x: int, y: int) -> int:
        return PLANT_MAX[self.cells[y * self.width + x]]

    def eat_plant(self, x: int, y: int) -> bool:
        """Remove one plant unit from a tile. Returns False if there was none."""
        i = y * self.width + x
        if self.food[i] <= 0:
            return False
        self.food[i] -= 1
        return True

    def next_to_water(self, x: int, y: int) -> bool:
        for dx, dy in DIRECTIONS:
            nx, ny = x + dx, y + dy
            if self.in_bounds(nx, ny) and self.cells[ny * self.width + nx] == WATER:
                return True
        return False

    def tiles_within(self, x: int, y: int, radius: int):
        """Every in-bounds tile within Chebyshev `radius` of (x, y), in row-major order."""
        for ty in range(max(0, y - radius), min(self.height, y + radius + 1)):
            for tx in range(max(0, x - radius), min(self.width, x + radius + 1)):
                yield tx, ty

    def rows(self) -> list[str]:
        return [self.cells[y * self.width:(y + 1) * self.width] for y in range(self.height)]

    # -- nearest-tile lookups ---------------------------------------------

    def nearest_terrain(self, terrain: str, x: int, y: int, radius: int) -> tuple[int, int] | None:
        """The nearest tile of a terrain within `radius`. Terrain never changes, so answers are cached."""
        key = (terrain, x, y, radius)
        if key in self._terrain_cache:
            return self._terrain_cache[key]
        found = None
        for dx, dy in offsets_by_distance(radius):
            tx, ty = x + dx, y + dy
            if 0 <= tx < self.width and 0 <= ty < self.height and self.cells[ty * self.width + tx] == terrain:
                found = (tx, ty)
                break
        self._terrain_cache[key] = found
        return found

    def nearest_plants(self, x: int, y: int, radius: int, include_here: bool = True,
                       occupied=None) -> tuple[int, int] | None:
        """The nearest tile within `radius` that has plants on it. If `occupied` is given, tiles in it are skipped."""
        width, height, food = self.width, self.height, self.food
        for dx, dy in offsets_by_distance(radius):
            if not include_here and dx == 0 and dy == 0:
                continue
            tx, ty = x + dx, y + dy
            if 0 <= tx < width and 0 <= ty < height and food[ty * width + tx] > 0:
                if occupied is None or (tx, ty) not in occupied:
                    return tx, ty
        return None

    def nearest_free_forest(self, x: int, y: int, radius: int, occupied) -> tuple[int, int] | None:
        """The nearest forest tile within `radius` that no creature is standing on."""
        width, height, cells = self.width, self.height, self.cells
        for dx, dy in offsets_by_distance(radius):
            tx, ty = x + dx, y + dy
            if 0 <= tx < width and 0 <= ty < height and cells[ty * width + tx] == FOREST:
                if (tx, ty) not in occupied:
                    return tx, ty
        return None

    # -- hourly update ----------------------------------------------------

    def regrow(self) -> None:
        """Each grass or forest tile below its maximum gains one plant unit with its regrowth chance."""
        rng_random = self.rng.random
        for i in self._regrow_tiles:
            roll = rng_random()  # drawn for every tile so the stream never depends on the plants
            cell = self.cells[i]
            if self.food[i] < PLANT_MAX[cell]:
                chance = GRASS_REGROWTH if cell == GRASS else FOREST_REGROWTH
                if roll < chance:
                    self.food[i] += 1

    def add_carcass(self, x: int, y: int, species: str, meat: float) -> Carcass:
        carcass = Carcass(self._next_carcass_id, x, y, species, meat)
        self._next_carcass_id += 1
        self.carcasses.append(carcass)
        return carcass

    def remove_carcass(self, carcass: Carcass) -> None:
        """Take a carcass away. The plants on its tile grow back to their maximum."""
        self.carcasses.remove(carcass)
        i = carcass.y * self.width + carcass.x
        self.food[i] = PLANT_MAX[self.cells[i]]

    def rot_carcasses(self) -> list[Carcass]:
        """Rot and age every carcass by one hour. Returns the carcasses that were removed."""
        removed = []
        for carcass in list(self.carcasses):
            carcass.meat -= CARCASS_ROT
            carcass.age += 1
            if carcass.meat <= 0 or carcass.age > CARCASS_LIFETIME:
                self.remove_carcass(carcass)
                removed.append(carcass)
        return removed

    def update(self) -> None:
        """World stage of an hour: plant regrowth, then carcass rot and removal."""
        self.regrow()
        self.rot_carcasses()


def _generate_cells(rng: random.Random, width: int, height: int) -> str:
    area = width * height
    grid = [[GRASS] * width for _ in range(height)]
    for _ in range(max(2, area // 180)):
        _paint_blob(grid, rng, FOREST, 2.0, 4.0)
    for _ in range(max(2, area // 240)):
        _paint_blob(grid, rng, WATER, 1.5, 3.0)
    grass = [(x, y) for y in range(height) for x in range(width) if grid[y][x] == GRASS]
    for x, y in rng.sample(grass, min(area // 70, len(grass))):
        grid[y][x] = ROCK
    return "".join("".join(row) for row in grid)


def _paint_blob(grid: list[list[str]], rng: random.Random, terrain: str,
                min_radius: float, max_radius: float) -> None:
    """A tile is covered when dx^2 + (1.25 dy)^2 <= (r + w)^2, with a fresh w in [-0.9, 0.9] per tile."""
    height, width = len(grid), len(grid[0])
    cx = rng.uniform(0, width - 1)
    cy = rng.uniform(0, height - 1)
    radius = rng.uniform(min_radius, max_radius)
    for y in range(height):
        for x in range(width):
            wobble = rng.uniform(-0.9, 0.9)
            dx, dy = x - cx, y - cy
            if dx * dx + (1.25 * dy) ** 2 <= (radius + wobble) ** 2:
                grid[y][x] = terrain


def _water_areas(cells: str, width: int, height: int) -> int:
    seen: set[int] = set()
    areas = 0
    for start, cell in enumerate(cells):
        if cell != WATER or start in seen:
            continue
        areas += 1
        stack = [start]
        seen.add(start)
        while stack:
            i = stack.pop()
            x, y = i % width, i // width
            for dx, dy in DIRECTIONS:
                nx, ny = x + dx, y + dy
                if 0 <= nx < width and 0 <= ny < height:
                    j = ny * width + nx
                    if cells[j] == WATER and j not in seen:
                        seen.add(j)
                        stack.append(j)
    return areas


def _playable(cells: str, width: int, height: int) -> bool:
    passable = sum(1 for c in cells if c in PASSABLE)
    return (passable / (width * height) >= MIN_PASSABLE_SHARE
            and _water_areas(cells, width, height) >= MIN_WATER_AREAS)
