"""Writes and reads replay files (spec section 9).

A replay holds the map, every creature's position and action each hour, the
probabilities behind each decision, events and population counts. The plant grid
is stored in full every 24th step and as a list of changes in between.
"""

import json

from valley import __version__
from valley.clock import START_HOUR
from valley.species import SPECIES, SPECIES_ORDER

FORMAT = "jev-valley/replay@2"
MAX_REPLAY_BYTES = 3 * 1024 * 1024


def replay_meta(sim, run_id: str) -> dict:
    """The `meta` block of a replay. Live mode sends it first, before any hour has been decided."""
    return {
        "run_id": run_id,
        "seed": sim.seed,
        "map_retries": sim.world.map_retries,
        "steps": sim.steps,
        "start_hour": START_HOUR,
        "width": sim.world.width,
        "height": sim.world.height,
        "tiles": sim.world.rows(),
        "brains": {key: sim.brains[key].name for key in SPECIES_ORDER},
        "hesitate_below": sim.hesitate_below,
        "actions": {key: list(SPECIES[key].actions) for key in SPECIES_ORDER},
        "max_creatures": sim.max_creatures,
        "questions": "rich" if sim.rich else "basic",
        "version": __version__,
    }


def creature_record(creature) -> dict:
    """One creature's entry in the replay's `creatures` map."""
    return {
        "name": creature.name, "species": creature.species, "personality": creature.personality,
        "born": creature.born, "died": creature.died, "cause": creature.cause, "parents": list(creature.parents),
        "notes": creature.notes, "age0": creature.start_age,
    }


def build_replay(sim, run_id: str, summary_extra: dict | None = None) -> dict:
    """Assemble the replay document from a finished (or stopped) simulation."""
    summary = sim.summary()
    summary.update(summary_extra or {})
    return {
        "format": FORMAT,
        "meta": replay_meta(sim, run_id),
        "creatures": {c.id: creature_record(c) for c in sim.creatures.values()},
        "frames": sim.frames,
        "summary": summary,
    }


def dumps(replay: dict) -> str:
    return json.dumps(replay, separators=(",", ":"), ensure_ascii=False)


def write_replay(path: str, replay: dict) -> int:
    """Write a replay as compact JSON. Returns the file size in bytes."""
    text = dumps(replay)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return len(text.encode("utf-8"))


def read_replay(path: str) -> dict:
    with open(path, encoding="utf-8") as handle:
        replay = json.load(handle)
    check_format(replay)
    return replay


def check_format(replay: dict) -> None:
    if not isinstance(replay, dict) or replay.get("format") != FORMAT:
        found = replay.get("format") if isinstance(replay, dict) else type(replay).__name__
        raise ValueError(f"not a {FORMAT} replay (found {found!r})")


def food_grids(replay: dict):
    """Yield the full plant grid, as a list of ints, for every frame."""
    grid = None
    for frame in replay["frames"]:
        if "food" in frame:
            grid = [int(ch) for ch in frame["food"]]
        elif grid is None:
            raise ValueError("the first frame has no full plant grid")
        else:
            grid = list(grid)
            for index, value in frame["food_diff"]:
                grid[index] = value
        yield grid


def embed_in_viewer(viewer_html: str, replay: dict) -> str:
    """Put the replay into the viewer's `replay-data` script tag so the page needs no other file."""
    marker = '<script id="replay-data" type="application/json"></script>'
    if marker not in viewer_html:
        raise ValueError("the viewer has no empty replay-data script tag to fill")
    payload = dumps(replay).replace("<", "\\u003c")  # keeps `</script>` and `<!--` out of the page
    return viewer_html.replace(marker, f'<script id="replay-data" type="application/json">{payload}</script>', 1)
