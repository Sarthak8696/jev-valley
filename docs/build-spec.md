# Jev Valley: Build Specification

This document is the single source of truth for building Jev Valley. Follow it in order. Where this document gives a name, value or rule, use it exactly. If something is not covered here, choose the simplest option and record the choice in the "Decisions log" at the end of this file.

---

## 1. What we are building

Jev Valley is a small valley that lives for one month. Rabbits, deer and wolves each have a name, a personality, hunger, thirst and a short memory. Every valley hour, every animal decides what to do next by asking a typed decision model a `Choice` question and, in the default rich mode, a few `Score` and `Noul` questions in the same request. Ordinary, deterministic code then carries the action out. The valley is shown in a 3D "god's view" where one valley hour plays out in one real second.

The project is an experiment that looks like a living world.

| | Question | How it is answered |
|---|---|---|
| Headline | Which brain keeps the valley alive for a month? | Same valleys, same seeds, same starting animals; only the brain changes. |
| Twist | Does knowing when you are unsure help you survive? | With hesitation on, an animal freezes when the model's confidence is low. Compare survival with hesitation off and on. |
| Supporting | What does a living month cost, and how fast is it? | Tokens, requests, latency and fallbacks per brain. |

### 1.1 What we are showcasing

1. A 3D viewer where the valley plays back at one hour per second, and clicking any animal shows the probability the model gave to each action.
2. A live mode, run locally, where the valley is decided by the model as you watch.
3. A short screen recording (20–30 seconds) of the viewer.
4. A README with three charts and one table, produced by the benchmark command from real runs.
5. Raw request and response logs that prove the model was really called.

### 1.2 Out of scope

Do not build any of these:

- Large language models in the decision loop, or anywhere in the simulation.
- Event-driven decisions, triggers, reaction times or virtual clocks. Every animal decides once per hour.
- Deadline-based experiments where late decisions change the outcome.
- Death by old age, seasons, weather, new species, terrain changes, learning or training.
- A game mode where a person controls an animal.
- Any server other than the local live mode in section 11.

---

## 2. Ground rules

1. **The model decides what, the code decides how.** The model only ever returns one action key. Paths, catches, births and deaths are computed by code.
2. **One decision per animal per hour.** The simulation is a loop of hourly steps. No animal acts on an old decision.
3. **Same seed, same start.** For a given seed, the map, the plants and the starting animals are identical whichever brain is used.
4. **Separate random streams.** Use three independent `random.Random` instances derived from the seed: `world_rng` (map and plant regrowth), `event_rng` (catches, litters, names, personalities, movement tie-breaks, action order), and `brain_rng` (only for the `rules` and `random` brains). A brain never consumes `world_rng` or `event_rng`.
5. **Waiting, never guessing.** If decisions for an hour are slow, the simulation waits for them. In benchmark runs this only makes the run take longer. In live mode the valley's clock slows down and the viewer shows the real pace.
6. **No hidden failures.** If a model call fails or passes the hard timeout, the affected animals rest that hour, the decisions are marked as fallbacks, and they are counted. A run with more than 2% fallbacks is marked `"valid": false`.
7. **Numbers only from real runs.** No result, chart or figure in the README is typed by hand. Every number is produced by `python -m valley bench` and traceable to a file in `results/`.
8. **Never log secrets.** API keys come from environment variables and never appear in logs, replays, errors, tests or commits.
9. **Standard library first.** The simulation, client, CLI and live server use only the Python standard library. `pytest` is a development dependency. `matplotlib` is an optional dependency for charts. The viewer loads exactly one external script: a pinned version of Three.js.
10. **Code comments describe the code.** Comments and docstrings explain what the code does and why. They do not mention people, lists, submissions or marketing.
11. **Commit in stages.** Build the repository through the phases in section 14, with one or more commits per phase. Never commit the whole project at once.
12. **Disclose AI assistance.** The README has a short "How this was built" section stating that AI assistance was used and which parts the author designed and verified.

---

## 3. Naming conventions

### 3.1 Project, package and files

| Thing | Name |
|---|---|
| Project and repository | `jev-valley` |
| Display name | Jev Valley |
| Python package | `valley` |
| Command | `python -m valley <subcommand>` |
| Subcommands | `run`, `bench`, `tune`, `view`, `live` |
| Minimum Python | 3.11 |
| Python files | `snake_case.py` |
| Classes | `PascalCase` |
| Functions, variables, JSON keys | `snake_case` |
| Constants | `UPPER_SNAKE_CASE` |
| CLI flags | `--kebab-case` |
| Environment variables | `UPPER_SNAKE_CASE` |

### 3.2 Repository layout

```
jev-valley/
├── README.md
├── LICENSE                      MIT
├── pyproject.toml
├── valley/
│   ├── __init__.py              version string only
│   ├── __main__.py              calls cli.main()
│   ├── cli.py                   argument parsing and subcommands
│   ├── clock.py                 hour, day and time-of-day helpers
│   ├── world.py                 World: terrain, plants, carcasses
│   ├── species.py               Species, SPECIES, action menus, personalities
│   ├── creatures.py             Creature dataclass and memory
│   ├── perception.py            builds a creature's view and signals
│   ├── actions.py               carries out each action
│   ├── simulation.py            Simulation: the hourly loop
│   ├── replay.py                writes and reads replay files
│   ├── metrics.py               survival, blunders, calibration, cost
│   ├── tuning.py                checks the balance targets in 4.5
│   ├── bench.py                 runs experiments across seeds and brains
│   ├── charts.py                draws charts (optional matplotlib)
│   ├── live.py                  local live server for the viewer
│   └── brains/
│       ├── __init__.py          make_brain()
│       ├── base.py              Brain, DecisionRequest, Decision
│       ├── system_one.py        SystemOneBrain (Jev and Laya)
│       └── (rules.py and random_brain.py were removed: see the Decisions log)
├── viewer/
│   └── index.html               the 3D viewer, one file
├── tests/
│   ├── test_clock.py
│   ├── test_world.py
│   ├── test_actions.py
│   ├── test_perception.py
│   ├── test_simulation.py
│   ├── test_system_one.py
│   ├── test_metrics.py
│   ├── test_replay.py
│   └── test_live.py
├── examples/
│   └── sample-replay.json       a rules-brain month, for the viewer
└── results/                     generated by bench; committed for final runs only
```

### 3.3 Classes

`World`, `Species`, `Creature`, `Simulation`, `DecisionRequest`, `Decision`, `Brain`, `SystemOneBrain`, `RulesBrain`, `RandomBrain`, `LiveServer`.

### 3.4 Keys and identifiers

| Thing | Values |
|---|---|
| Species keys | `rabbit`, `deer`, `wolf` (lowercase, singular) |
| Prey actions | `eat`, `drink`, `flee`, `hide`, `rest`, `seek_mate`, `follow_group`, `explore` |
| Wolf actions | `hunt`, `scavenge`, `drink`, `hide`, `rest`, `seek_mate`, `follow_group`, `explore` |
| Brain names | `jev`, `laya`, `rules`, `random` |
| Personalities | `bold`, `timid`, `curious`, `lazy`, `greedy`, `loyal`, `restless`, `cautious` |
| Causes of death | `eaten`, `starved`, `thirst` |
| Decision sources | `model`, `fallback`, `baseline` |
| Times of day | `night`, `dawn`, `day`, `dusk` |
| Terrain characters | `.` grass, `T` forest, `~` water, `^` rock |
| Creature ids | species initial plus a counter: `r1`, `d1`, `w1`. Never reused within a run. |
| Creature names | from the species name list; if a name is already used in the run, append a number: `Clover 2` |
| Display name | `{name} the {species}`, for example `Clover the rabbit` |
| Clock text | `Day {d}, {h} {am/pm}`, for example `Day 12, 6 pm`; midnight is `12 am`, noon is `12 pm` |
| Run id | `{experiment}-{brain_label}-seed{seed}`, for example `survival-jev-seed7` |
| Brain label | the brain name, or for mixed runs `wolf-{brain}_prey-{brain}`, for example `wolf-jev_prey-laya` |

### 3.5 Question naming in model requests

- A request for one creature uses the question id `action`.
- A batched request uses each creature's id (`r12`, `w3`) as its question id.

### 3.6 Commit messages

Use Conventional Commits: `feat(world): ...`, `feat(brains): ...`, `test(actions): ...`, `fix(perception): ...`, `docs(readme): ...`, `chore: ...`, and `bench: ...` for committed results.

---

## 4. Time

### 4.1 The clock

- One step is one valley hour. A run lasts 30 days: 720 steps (`--days 30`).
- Step 0 is `Day 1, 6 am`. Step `n` is `n` hours later.
- Times of day, by hour of the clock:

| Hours | Time of day |
|---|---|
| 5 am – 6:59 am | `dawn` |
| 7 am – 5:59 pm | `day` |
| 6 pm – 7:59 pm | `dusk` |
| 8 pm – 4:59 am | `night` |

- Time of day affects only two things: the lighting in the viewer and the `time` field in each animal's view. It changes no rules.
- `valley/clock.py` provides `day_of(step)`, `hour_of(step)`, `time_of_day(step)` and `clock_text(step)`. All other code uses these helpers.

### 4.2 Playback speed

- The viewer plays one valley hour per real second at normal speed.
- A full month plays in 12 minutes at 1×. There is no fast-forward: the speed buttons and the live catch-up were removed at the author's request (see the Decisions log). The scrubber still jumps to any hour.

---

## 5. The environment

### 5.1 The map

- Default size: 40 wide × 26 high (`--size 40x26`). It was 28 × 18 until the ecosystem redesign (see the Decisions log). `x` grows east, `y` grows south. `(0, 0)` is the north-west corner.
- Movement and distance use 8 directions. Distance is Chebyshev distance: `max(|dx|, |dy|)`.
- Generation, in this order, using `world_rng`:
  1. Fill with grass.
  2. Forest blobs: `max(2, area // 150)` blobs, radius 2.0–4.0.
  3. Water blobs: `max(2, area // 240)` blobs, radius 1.5–3.0.
  4. On maps at least 32 wide and 20 high, a stream that wanders from one side to the other, one tile wide (sometimes two), with 3 fords of two tiles where animals can cross.
  5. Ponds: while any tile is more than 5 tiles (Chebyshev) from water, paint a small pond on the tile farthest from water. No animal is ever more than its vision range from a drink.
  6. Rocks: `area // 70` single grass tiles turned to rock.
  7. Plants: every grass or forest tile starts with a random amount from 1 to its maximum.
- A blob covers tile `(x, y)` when `dx² + (1.25·dy)² ≤ (r + w)²`, where `w` is a fresh random value in `[-0.9, 0.9]` per tile.
- The generator retries with the next derived seed until the map has at least two separate water areas and at least 60% of tiles passable. Record the number of retries in the replay's `meta`.

| Terrain | Passable | Plant maximum | Notes |
|---|---|---|---|
| Grass `.` | yes | 2 | open ground |
| Forest `T` | yes | 3 | gives cover |
| Water `~` | no | 0 | drink when on an adjacent tile |
| Rock `^` | no | 0 | blocks movement |

Each hour, each grass or forest tile below its maximum gains 1 plant unit with the regrowth chance in 5.4.

### 5.2 Carcasses

- An animal that dies leaves a carcass on its tile with `meat = meat_value × ratio`.

| Cause | Ratio |
|---|---|
| eaten | 1.0 (the hunter eats from it immediately) |
| starved | 0.4 |
| thirst | 0.6 |

- Each hour a carcass loses its rot amount (5.4) and ages by 1 hour.
- A carcass is removed when its meat reaches 0 or its age passes the carcass lifetime (5.4). When it is removed, the plants on its tile (if grass or forest) are set to the tile's maximum.

### 5.3 Species

Fixed values:

| Stat | rabbit | deer | wolf |
|---|---|---|---|
| Diet | plants | plants | meat |
| Vision (tiles) | 5 | 6 | 6 |
| Litter size | 1–3 | 1–2 | 1–2 |
| Flee speed (tiles per hour) | 2 | 2 | – |
| Hunt speed (tiles per hour) | – | – | 2 |
| Population share of the cap | 0.6 | 0.3 | 0.14 |
| Starting count | 24 | 10 | 5 |

Name lists:

- rabbit: Clover, Thistle, Pip, Bramble, Hazel, Juniper, Moss, Sorrel, Fern, Basil, Nettle, Poppy, Tansy, Yarrow
- deer: Birch, Aspen, Rowan, Willow, Alder, Larch, Cedar, Linden, Holly, Elm
- wolf: Ash, Ember, Flint, Slate, Cinder, Storm, Shade, Grit, Frost, Smoke

### 5.4 Tunable values

These are the starting values. They are tuned in phase 5 until the targets in 5.5 are met. The final values live in `valley/species.py` and `valley/world.py`, and every change is recorded in the Decisions log.

| Value | rabbit | deer | wolf |
|---|---|---|---|
| Max energy | 30 | 50 | 60 |
| Max hydration | 30 | 45 | 45 |
| Energy lost per hour | 0.45 | 0.55 | 0.5 |
| Hydration lost per hour | 0.6 | 0.7 | 0.6 |
| Adult age (hours) | 96 | 240 | 360 |
| Minimum energy to breed | 16 | 26 | 44 |
| Energy cost of breeding (each parent) | 7 | 12 | 22 |
| Breeding cooldown (hours) | 72 | 168 | 336 |
| Energy per plant unit eaten | 5 | 6 | – |
| Meat value | 14 | 34 | 20 |
| Catch chance | – | – | rabbit 0.45, deer 0.22 |

| World value | Starting value |
|---|---|
| Grass regrowth chance per hour | 0.015 |
| Forest regrowth chance per hour | 0.010 |
| Carcass rot per hour | 0.3 |
| Carcass lifetime (hours) | 72 |
| Creature cap | 50 |

### 5.5 Balance targets

**Removed on 2026-10-25.** The offline brains these targets were checked with no longer exist, and the valley cannot run without a model, so the targets cannot be checked. They stay here as the record of how the valley was balanced. The check, and the brains, are in the history at commit `4d545ed`.

`python -m valley tune --check` runs the `rules` and `random` brains on the ten benchmark seeds (8.1) and reports each target as pass or fail. Tuning is finished when all pass.

1. With `rules`, all three species are alive at the end of the month on at least 8 of 10 seeds. (5 of 10 until the ecosystem redesign.)
2. With `rules`, at least 3 of 10 seeds show a rabbit population that rises and then falls by at least 30% from its peak.
3. With `random`, at least one species dies out on at least 7 of 10 seeds.
4. With `rules`, no species sits at its cap for more than half of the month on any seed.
5. With `rules`, wolves are never the only species left at the end of the month on any seed.

These targets keep the baseline good but not perfect, so a better brain has room to do better and a worse one can visibly do worse.

### 5.6 Population cap

- A species cannot breed when its own count is at or above `cap × share`, or when the total is at the cap. The default cap is 75 (it was 50 until the ecosystem redesign).

### 5.7 Starting creatures

- Placed with `event_rng` on random free passable tiles.
- Age: random between adult age and 2 × adult age.
- Energy: random between 60% and 90% of max. Hydration: 80% of max.
- Personality and heading: random.

### 5.8 Creature state

| Field | Meaning |
|---|---|
| `id`, `species`, `name`, `personality` | identity |
| `x`, `y` | position; at most one creature per tile |
| `energy`, `hydration` | dies at 0 |
| `age`, `born` | in hours |
| `cooldown` | hours until it can breed again |
| `heading` | direction used by `explore` |
| `known_water` | the last water tile it saw, or none |
| `memory` | the last 3 notable events, as `"{clock text}: {text}"` |
| `action`, `decision`, `hesitated` | this hour's choice, the full decision, and whether it froze |
| `parents` | ids of its parents, empty for starting creatures |
| `alive`, `died`, `cause` | end of life |

Memory texts:

- `escaped {hunter name} the wolf`
- `{prey name} the {species} got away`
- `caught {prey name} the {species}`
- `ate from a {species} carcass`
- `had {n} young with {partner name}`
- `hesitated`

### 5.9 One hour

Each step runs these stages in order:

1. Increase the step counter by 1. Clear the hour's events.
2. World update: plant regrowth, carcass rot and removal.
3. Perception: build a `DecisionRequest` for every living creature, from the world as it is now.
4. Decisions: group requests by brain and send them. Wait until every decision is back, failed or timed out.
5. Hesitation: if a threshold is set and a decision's confidence is below it, the executed action becomes `rest`, `hesitated` is true, and the creature remembers `hesitated`. The chosen action is kept in the record.
6. Actions: shuffle the living creatures with `event_rng` and carry out each executed action, skipping any creature that died earlier this hour.
7. Upkeep for every survivor: energy drops by `energy lost per hour × action cost` and hydration by `hydration lost per hour` (both inside the action step); age goes up by 1; cooldown goes down by 1.
8. Deaths, checked in this order: energy ≤ 0 → `starved`; hydration ≤ 0 → `thirst`.
9. Record the frame.

The run ends after 720 steps or when no creature is alive.

### 5.10 Visibility

- A creature sees every tile and creature within its vision distance.
- Exception: a creature on forest whose previous action was `hide` is only seen from 2 tiles away.

### 5.11 Actions

Movement is one tile per step in 8 directions, onto a free passable tile. "Step toward" means: among free neighbouring tiles, take the one that most reduces Chebyshev distance to the target, breaking ties by straight-line distance and then by `event_rng`. If no neighbour is better than staying, stay. "Step away" is the reverse.

| Action | Species | What the code does | Energy cost multiplier |
|---|---|---|---|
| `eat` | prey | If plants are on its tile, eat 1 unit and gain energy (capped at max). Otherwise step toward the nearest visible tile with plants; if none, explore. | 1.0 |
| `drink` | all | If next to water, set hydration to max. Otherwise step toward the nearest visible water, or toward `known_water` if none is visible, and drink if now next to water. If neither is known, explore. | 1.0 |
| `flee` | prey | Step away from the nearest visible wolf, flee-speed steps. If no wolf is visible, explore. | 1.6 |
| `hide` | all | If not on forest, step toward the nearest visible free forest tile. If on forest, stay. | 0.8 |
| `rest` | all | Stay. | 0.5 |
| `seek_mate` | all | If it cannot breed, explore. Otherwise step toward the nearest visible creature of its species that can also breed. If they are then adjacent and the cap allows, have young (5.12). | 1.0 |
| `follow_group` | all | Step toward the rounded centre of the visible creatures of its species. If none are visible, stay. | 1.0 |
| `explore` | all | With chance 0.25 pick a new random heading. Step in the heading direction if that tile is free; otherwise pick a new random heading and stay. | 1.0 |
| `hunt` | wolf | Step toward the nearest visible prey, up to hunt-speed steps. If then adjacent, try a catch (5.13). If no prey is visible, explore. | 1.5 |
| `scavenge` | wolf | Step toward the nearest visible carcass, up to 2 steps. If within 1 tile of a carcass, eat up to 15 meat (capped by the energy it can still take). If none is visible, explore. | 1.0 |

Every action records the path it took this hour (a list of tiles, 0 to 2 steps) so the viewer can animate it exactly.

### 5.12 Births

- Both parents are adults, past cooldown, and at or above the minimum breeding energy.
- Litter size is drawn with `event_rng` from the species' range, limited by free tiles next to the parent that started it.
- Newborns: age 0, energy 50% of max, hydration 80% of max, random personality, and they inherit `known_water` from the parent that started it.
- Each parent loses the breeding cost, gets its cooldown set, and remembers the birth.

### 5.13 Catches

- Base chance: the wolf's catch chance for that prey species.
- × 0.5 if the prey is on forest and its action this hour is `hide`.
- × 0.7 if the prey's action this hour is `flee`.
- On success: the prey dies (`eaten`), leaves a carcass with ratio 1.0, and the wolf immediately eats as much as it can.
- On failure: both the wolf and the prey remember the escape.

---

## 6. Perception: what the model sees

Every creature's view is a JSON object with exactly these fields, in this order:

```json
{
  "id": "r12",
  "animal": "Clover the rabbit",
  "diet": "eats plants",
  "personality": "timid",
  "time": "night, 2 am",
  "age": "9 days (adult)",
  "hunger": "hungry",
  "thirst": "fine",
  "standing_on": "open grass, grazed bare",
  "can_have_young": "no, too hungry",
  "sees": [
    "DANGER: wolf Ash, 3 tiles north-east, hunting",
    "4 other rabbits, nearest 2 tiles west",
    "water, 2 tiles west",
    "plants to eat, 4 tiles south",
    "forest cover, 2 tiles east"
  ],
  "recent": ["Day 9, 11 pm: escaped Ash the wolf"]
}
```

### 6.1 Field rules

- `time`: `"{time of day}, {h} {am/pm}"`.
- `age`: `"{days} days ({stage})"` where days is age ÷ 24 rounded down, and stage is `young` below adult age, otherwise `adult`.
- `hunger`, from energy ÷ max: below 0.2 `starving`, below 0.45 `hungry`, below 0.8 `fed`, otherwise `full`.
- `thirst`, from hydration ÷ max: below 0.2 `parched`, below 0.45 `thirsty`, below 0.8 `fine`, otherwise `quenched`.
- `standing_on`: `open grass, with plants to eat` / `open grass, grazed bare` / `forest cover, with berries` / `forest cover`.
- `can_have_young`: `yes` / `no, too young` / `no, had young recently` / `no, too hungry`.
- `recent`: the last 3 memory entries, or `["nothing yet"]`.

### 6.2 The `sees` list, in this order

1. Up to 2 nearest wolves (prey only): `DANGER: wolf {name}, {where}`, plus `, hunting` if that wolf's previous action was `hunt`.
2. Up to 3 nearest prey (wolves only): `prey: {species} {name}, {where}`, plus ` (hiding in forest)` if it is hiding.
3. Kin: `{n} other {species}s, nearest {where}` (singular when n is 1).
4. A possible partner, if one is visible and can breed: `possible partner: {name}, {where}`.
5. Water: `water, next to me` or `water, {where}`. If none is visible but `known_water` is set: `no water in sight; I remember water {where}`.
6. Plants (prey only): `plants to eat, {where}`.
7. The nearest carcass: `carcass of a {species}, {where}`.
8. Forest, only when not standing on forest: `forest cover, {where}`.
9. If the list would be empty: `nothing nearby`.

`{where}` is `right here` at distance 0, otherwise `{d} tiles {direction}`. Direction is one of the 8 compass words. Drop the minor component when one axis is less than half the other: `dx = 1, dy = -5` is `north`.

### 6.3 Signals

Perception also produces a `signals` dictionary of raw numbers. Signals are never sent to a model. They are used by the `rules` brain and by the blunder metric.

| Signal | Meaning |
|---|---|
| `energy`, `hydration` | ratios from 0 to 1 |
| `personality` | as above |
| `threat_dist`, `prey_dist`, `mate_dist`, `water_dist`, `forest_dist`, `carcass_dist`, `group_dist` | distance to the nearest of each, or `None` |
| `water_adjacent` | true if next to water |
| `food_here` | true if a plant-eater stands on plants |
| `can_mate` | true if it can breed |

---

## 7. Brains

### 7.1 Interface

```python
@dataclass
class DecisionRequest:
    creature_id: str
    view: dict           # sent to the model
    options: dict        # action key -> description, in the species' action order
    signals: dict        # never sent to the model

@dataclass
class Decision:
    choice: str
    probabilities: dict  # action key -> probability
    confidence: float
    source: str          # "model" | "fallback" | "baseline"
    latency_ms: float | None

class Brain:
    name: str
    def decide(self, requests: list[DecisionRequest]) -> list[Decision]: ...
    def summary(self) -> dict: ...
```

`decide` returns one decision per request, in the same order.

### 7.2 The question

Every creature gets one `Choice` question. In the rich mode (the default, `--questions rich`) the same request also carries `score` and `noul` questions, described in `valley/questions.py` and in the Decisions log; `--questions basic` asks only the choice.

- `type`: `"choice"`
- `instructions`: exactly the constant below, plus, in batched requests, the sentence `Decide only for the creature with id '{id}', using creatures['{id}'].`
- `criteria`: the species' action menu, key to description.

```
You are deciding the next action of one wild animal in a valley for the coming hour. Weigh its hunger, thirst, nearby dangers, the time of day, chances to breed and its personality, then pick the single action it takes now.
```

Action descriptions, in the first person:

| Action | Prey description | Wolf description |
|---|---|---|
| `eat` | Eat the plants where I stand, or walk toward the nearest plants I can see | – |
| `hunt` | – | Chase the nearest prey animal and try to catch it |
| `scavenge` | – | Walk to the nearest carcass and eat from it |
| `drink` | Walk to the nearest water and drink | Walk to the nearest water and drink |
| `flee` | Run away from the nearest predator as fast as I can | – |
| `hide` | Move into forest cover, or stay hidden there | Wait in forest cover to ambush prey |
| `rest` | Stay still to save energy | Stay still to save energy |
| `seek_mate` | Walk toward a partner of my kind and have young | Walk toward a partner of my kind and have young |
| `follow_group` | Move closer to others of my kind for safety | Move closer to my pack |
| `explore` | Wander somewhere new to find food, water or partners | Roam somewhere new to find prey, water or partners |

### 7.3 `SystemOneBrain` (used for `jev` and `laya`)

Wire format of the System One API:

- `POST {base_url}/v1/systemone`
- Headers: `Content-Type: application/json`, and `Authorization: Bearer {key}` when a key is set. Check the header against the provider's current documentation before the first real run.
- Body for one creature:

```json
{
  "model": "jev-latest",
  "state": { "...the view...": "" },
  "questions": {
    "action": { "type": "choice", "instructions": "...", "criteria": { "eat": "...", "drink": "..." } }
  }
}
```

- Body for a batch: `"state": {"creatures": {"r12": {...}, "r13": {...}}}`, with one question per creature id.
- Response: read `answers[question_id]`. Accept it only if `type` is `"choice"` and `choice` is one of the options. Take `probabilities` and `confidence` from the answer. Read `usage.input_tokens` and `usage.output_tokens` if present.
- If the call fails, passes the hard timeout, or an answer is missing or invalid, return a fallback for that creature: choice `rest`, probabilities `{"rest": 1.0}`, confidence 0, source `fallback`.

Settings:

| Flag | Default | Meaning |
|---|---|---|
| `--batch` | 16 | creatures per request; lower it if the provider caps questions per request |
| `--workers` | 4 | parallel requests per brain |
| `--timeout` | 30 | hard timeout in seconds per request |
| `--log-requests` | on for `bench` and `live`, off for `run` | write every request and response to `requests.jsonl` |

Configuration from the environment:

| Brain | Variables | Defaults |
|---|---|---|
| `jev` | `TYPESAFE_API_KEY` (required), `TYPESAFE_BASE_URL`, `TYPESAFE_MODEL` | `https://api.typesafe.ai`, `jev-latest` |
| `laya` | `LAYA_BASE_URL`, `LAYA_MODEL`, `LAYA_API_KEY` (optional) | `http://localhost:8000`, `laya-auto` |

Confirm the Laya server's port and model name from its own documentation and set them through the environment if they differ.

Each line of `requests.jsonl`:

```json
{"brain": "jev", "step": 12, "latency_ms": 241.7, "request_id": "...", "request": {...}, "response": {...}, "error": null}
```

`request_id` comes from the `x-typesafe-request-id` response header when present, otherwise `null`.

### 7.4 `RulesBrain`

**Removed on 2026-10-25.** The valley runs only on a model. The description below is the record of what the brain did; the code is at commit `4d545ed`. The tests keep a copy under `tests/offline.py` as a stand-in for a model, because they must run offline.

A hand-written baseline that never calls a model. It scores each action from the signals, turns the scores into probabilities with a softmax at temperature 0.35, and samples a choice with `brain_rng`. Confidence is the probability of the chosen action. Source is `baseline`.

Scores, where `hunger = 1 − energy` and `thirst = 1 − hydration`:

| Action | Score |
|---|---|
| `flee` | with a wolf visible: 1.6 if within 2, 0.9 within 4, otherwise 0.3; × 0.6 if bold, × 1.3 if timid |
| `hide` | with a wolf visible: 0.8 if forest is within 2, else 0.1; with none: 0.05, + 0.3 if cautious |
| `drink` | thirst × 1.6 if water is visible or remembered, else thirst × 0.6 |
| `eat` | (hunger − 0.15) × 1.8, + 0.3 if food is here |
| `hunt` | (hunger − 0.3) × 2.5, + 0.4 if prey is visible, otherwise − 0.6 |
| `scavenge` | hunger × 1.2, + 0.9 if a carcass is visible, otherwise − 1.0 |
| `seek_mate` | 0.9 if it can breed and a partner is visible, otherwise − 0.8 |
| `rest` | 0.15, + 0.5 if lazy |
| `explore` | 0.25, + 0.4 if curious or restless |
| `follow_group` | 0.4 if the group is more than 2 tiles away, + 0.3 if loyal |

The rules brain is a fair reference, not a strawman. Do not weaken it to make a model look better.

### 7.5 `RandomBrain`

**Removed on 2026-10-25**, with `RulesBrain` (see 7.4).

Picks uniformly at random with `brain_rng`. Probabilities are uniform. Source is `baseline`.

### 7.6 `make_brain(spec)`

Since 2026-10-25 it knows only `jev` and `system-one@URL#MODEL`; any other name raises an error that says the valley runs only on a model.

Accepts `jev`, `laya`, `rules`, `random`, or `system-one@{base_url}#{model}` for any other server using the same API. Species that use the same spec share one brain instance, so their totals are combined and their requests can share batches.

---

## 8. Measurement

### 8.1 Experiments

`python -m valley bench <experiment>` runs an experiment and writes everything to `results/<experiment>/`.

| Experiment | What changes | Brains |
|---|---|---|
| `survival` | the brain, used by all three species | `jev`, `laya`, `rules`, `random` |
| `hesitation` | the threshold: off, 0.3, 0.5 | `jev` and `laya`, each used by all species |
| `rivals` (optional, for the video) | wolves on one brain, prey on the other | `wolf-jev_prey-laya`, `wolf-laya_prey-jev` |

The headline result comes from `survival`. `rivals` is not used for conclusions, because mixing brains makes it unclear which brain caused an outcome.

Defaults:

| Setting | Value |
|---|---|
| Seeds | `3, 7, 11, 19, 23, 42, 57, 64, 88, 101` |
| Length | 30 days |
| `--seeds`, `--days`, `--brains` | override the defaults |

Before any run that uses `jev` or `laya`, `bench` prints an estimate of decisions and requests and waits for confirmation, unless `--yes` is given. Estimate decisions as starting creatures × 720 × 1.5.

Start small: one seed for 2 days per brain, then 3 seeds for the full month, then all seeds if the budget allows. The README states exactly which seeds and lengths were used.

### 8.2 Survival

| Metric | Definition |
|---|---|
| `hours_survived` | steps until the run ended |
| `first_extinction` | clock text of the first hour any species reached 0, or `null` |
| `all_species_alive` | true if all three species are alive at the end |
| `mean_population` | per species, mean count over all hours |
| `births`, `deaths_by_cause` | per species |

### 8.3 Blunders

A blunder is a choice that is clearly bad given what the creature could see. Each rule has an opportunity (the situation) and a bad choice. Rules are checked against the chosen action, before hesitation.

| Rule key | Opportunity | Blunder if the choice is |
|---|---|---|
| `ignored_thirst` | thirst is `parched` and water is adjacent | anything other than `drink` |
| `ignored_danger` | prey, with a wolf within 2 tiles | anything other than `flee` or `hide` |
| `hunted_while_full` | wolf, hunger is `full` | `hunt` |
| `ate_while_full` | prey, hunger is `full` | `eat` |
| `ignored_hunger` | prey, `starving`, plants here, no wolf within 2 | anything other than `eat` |
| `mated_while_starving` | hunger is `starving` | `seek_mate` |

Report per brain: opportunities and blunders per rule, the overall blunder rate (all blunders ÷ all opportunities), and blunders per 1,000 decisions. Fallback decisions are excluded and counted separately.

### 8.4 Calibration

For model decisions only: group decisions into five confidence bins (0–0.2, 0.2–0.4, 0.4–0.6, 0.6–0.8, 0.8–1.0). For each bin, report the number of decisions that had at least one blunder opportunity and the blunder rate among them.

### 8.5 Cost and speed

Per brain: decisions, requests, fallbacks, fallback rate, input and output tokens, tokens per 1,000 decisions, latency p50 and p95 per request, and seconds per valley hour (p50 and p95). A money figure appears only when `--price-per-mtok` (price per million input tokens) is given. Never estimate prices in code.

### 8.6 Results layout

```
results/<experiment>/
├── <run_id>/
│   ├── replay.json
│   ├── metrics.json
│   └── requests.jsonl           model brains only
├── summary.json                 all runs, all metrics
├── summary.md                   tables for the README
└── charts/
    ├── population.svg           median population per species over the month, one line per brain
    ├── blunders.svg             blunder rate per brain
    └── calibration.svg          blunder rate per confidence bin, per model brain
```

---

## 9. Replay format

A replay is one JSON file, under 3 MB for a 30-day run.

```json
{
  "format": "jev-valley/replay@2",
  "meta": {
    "run_id": "survival-jev-seed7",
    "seed": 7,
    "map_retries": 0,
    "steps": 720,
    "start_hour": 6,
    "width": 28,
    "height": 18,
    "tiles": ["....TT~~..", "..."],
    "brains": {"rabbit": "jev", "deer": "jev", "wolf": "jev"},
    "hesitate_below": null,
    "actions": {"rabbit": ["eat", "drink", "..."], "wolf": ["hunt", "..."]},
    "version": "0.1.0"
  },
  "creatures": {
    "r12": {"name": "Clover", "species": "rabbit", "personality": "timid",
            "born": 31, "died": 188, "cause": "eaten", "parents": ["r3", "r7"]}
  },
  "frames": [
    {
      "step": 0,
      "food": "2120112...",
      "agents": [["r12", 4, 9, "flee", 81, 0, 45, 70, [5, 2, 81, 9, 1, 0, 1, 1], [[5, 9], [6, 10]]]],
      "carcasses": [[10, 3, 12.4, "deer"]],
      "events": ["Ash the wolf caught Pip the rabbit"],
      "pop": {"rabbit": 16, "deer": 7, "wolf": 3}
    }
  ],
  "summary": {}
}
```

Rules:

- `food` is the full plant grid (one digit per tile, row by row) on step 0 and every 24th step. Other steps use `"food_diff": [[tile_index, value], ...]` with only the changed tiles.
- Each agent row is `[id, x, y, chosen_action, confidence_pct, hesitated, energy_pct, hydration_pct, probabilities_pct, path]`.
  - `x`, `y` are the position at the end of the hour.
  - `hesitated` is 0 or 1.
  - `probabilities_pct` is a list of whole-number percentages in the species' action order.
  - `path` is the list of tiles stepped through this hour, empty if it did not move.
  - A fallback decision has `confidence_pct` of −1.
- Events are plain sentences, newest last:
  - `{hunter} the wolf caught {prey} the {species}`
  - `{hunter} the wolf missed {prey} the {species}`
  - `{a} and {b} the {species}s had {n} young`
  - `{name} the {species} starved`
  - `{name} the {species} died of thirst`

---

## 10. The 3D viewer

`viewer/index.html` is one file: HTML, CSS and plain JavaScript, with no build step and no framework. It loads Three.js as an ES module from one pinned URL through an import map:

```html
<script type="importmap">
{ "imports": { "three": "https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js", "three/addons/": "https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/" } }
</script>
```

The only add-on it uses is `three/addons/objects/Sky.js`, from the same pinned package. It makes no other network requests, except to the local live server in live mode. Every model, texture and shape is drawn in code; nothing is downloaded. (The viewer was redesigned after the first build: sections 10.2 to 10.4 below describe the current one.)

### 10.1 Loading

1. If the page contains `<script id="replay-data" type="application/json">` with content, play it.
2. If the page was opened by the live server, connect to its stream (section 11).
3. Otherwise show an empty state that asks the person to drop a replay file onto the page or choose one, with a button to load `examples/sample-replay.json` when hosted next to it.

`python -m valley view <replay.json> -o valley.html` writes a copy of the viewer with the replay embedded.

If WebGL is unavailable, show a plain message that says the 3D view needs WebGL and offer the flat map (10.3).

### 10.2 The valley view

- **Camera.** A perspective camera that orbits the point it looks at, eased so it never snaps. Drag (one finger) to turn and tilt, drag with the right button or two fingers to slide, scroll or pinch to zoom, `Q` and `E` turn it by 45°, `0` or "Reset view" shows the whole valley again. "Follow" keeps the selected animal in the centre. It never goes below the ground.
- **Land.** One smooth mesh whose height comes from the tile map and gradient noise: shallow basins where there is water, bumps where there is rock, and wooded hills around the valley that only exist for the view. Water, rock and woods taper off beyond the edge of the map instead of being stretched outward, and a belt of trees on the hills hides the edge. Ground colour comes from biome (meadow patches, forest floor, sandy shore, river bed, rock, high bare slopes) and is tinted live by how much food is left on each tile.
- **Water.** One sheet at sea level that only shows where the land dips below it, coloured and made see-through by depth, with moving ripples and reflections of the sky.
- **Plants.** Instanced pine, oak and birch trees that sway, bushes, boulders, wild flowers in drifts, reeds and lily pads, and grass blades whose height follows the food on the tile, so grazed ground goes bare.
- **Sky.** The three.js `Sky` follows the clock: sun, warm light at dawn and dusk, a moon, stars and fireflies at night, fog that changes colour, and the sky itself lights the scene and is reflected in the water.
- **Animals.** One skinned mesh each, built from smooth parts on a small skeleton: deer (some stags with antlers), wolves and rabbits with individual coats and sizes, young animals smaller than adults.
- **Carcasses.** A small dark mound with bones that shrinks as meat runs out.
- **Selection.** Clicking an animal (raycast) draws a ring under it, shows its name above it, and opens the mind panel. In full screen, where the panels are off screen, a small card shows its name, what it chose and how sure it was.
- **Full screen.** A button, or `F`, makes the view and the timeline fill the screen (the browser's own full screen where it exists, otherwise the same layout covering the page, as on an iPhone).
- **Readability helpers.** A hunting wolf has a dashed line to its target. A hiding animal crouches with its ears back. A hesitating animal shows a small pause marker above it.
- **Quality.** `?quality=low` or `?quality=high` forces a setting; by default phones and small machines get fewer plants, smaller shadows and a lower resolution. The resolution also drops by itself, in steps of 0.25 down to 0.85, when the median frame time over a window is well above the display's own frame time for two windows in a row; it never rises again, and `?resolution=full` turns the stepping down off.

### 10.3 Flat map

Removed from the 3D view at the author's request. Only the no-WebGL fallback draws a flat map.

### 10.4 Motion

The simulation is hourly, but nothing on screen moves hour by hour.

- Each animal has a track: one keyframe per tile it entered, spread across the hour it entered them in. A cubic curve joins the keyframes, and an animal's speed at a keyframe comes from its neighbours, so one that keeps moving never slows at a tile or at the turn of an hour, one that stops eases to a halt, and one that sets off waits a short random time of its own first. Position and speed come from the same curve.
- An animal faces the way it goes. While standing it looks at what it is busy with (water, prey) and drifts about inside its tile.
- Legs follow the ground actually covered, so feet do not slide at any playback speed. Deer and wolves walk, trot and gallop; rabbits hop.
- Action poses: `eat` grazes with the head down, `drink` leans to the water, `rest` lies down with legs folded, `hide` crouches with ears back, `hunt` stalks low, `flee` runs with ears back (a deer raises its white tail), and idle animals breathe, look around and flick their ears.
- While a run is still being decided the view stays one hour behind the newest hour, because the curve needs the next hour to be known.
- Births: newborns grow in. Deaths: the animal falls over and becomes a carcass.

### 10.5 Panels

HTML panels around the 3D view. On phones in portrait, they stack under it.

- **Header:** which brain controls each species, the seed, hesitation on or off, and in live mode the real pace (`1.0 hours per second`).
- **Timeline:** play and pause, a scrubber across the month, and the clock text. Playback is always one valley hour per second (in live mode, the pace the run arrives at). A finished replay has its scrubber at once. In live mode there is no scrubber, and no stepping with the arrow keys, until the run has played to its end; a note says so.
- **Mind panel** for the selected animal: display name, personality, age, hunger and thirst bars, what it chose, its confidence, a bar for every action's probability (the chosen action highlighted), whether it hesitated, its recent memories, and its fate if it died. Title the probability section "Why it chose this".
- **Population chart:** one line per species across the month, with a marker at the current hour.
- **Events:** the latest events, newest first.

### 10.6 Design rules

- Light and dark mode through CSS variables and `prefers-color-scheme`. The 3D scene keeps its own lighting in both.
- Keyboard: space plays and pauses, left and right arrows step one hour, `Q` and `E` turn the camera, `0` resets it, `F` toggles full screen, Esc leaves it, Tab reaches every control, and focus is visible.
- `prefers-reduced-motion`: start paused, rotate instantly, and turn off hops and idle breathing.
- Aims for a steady 60 frames per second on a mid-range phone with 75 animals; the resolution lowers itself if it cannot.
- Plain, specific labels in sentence case, named the way a viewer would name them.

---

## 11. Live mode

`python -m valley live` runs the simulation and shows it in the viewer as it is decided.

```
python -m valley live --brain jev --seed 7 --port 8765
```

- It serves the viewer at `http://localhost:8765/` and streams each finished hour at `/stream` as Server-Sent Events, using only the standard library.
- Each event is one frame in the replay format of section 9, plus `"pace": {"seconds_this_hour": 0.31, "hours_per_second": 1.0}`.
- The loop: ask the brain for every animal's decision, carry out the hour, send the frame, then wait until at least one real second has passed since the previous frame was sent. If decisions take longer than a second, the next frame is sent as soon as it is ready, and the valley's clock slows down. It never skips or guesses decisions.
- The viewer animates each frame over the time until the next one arrives, so slow hours look slower, not jerky.
- While waiting for decisions, animals keep their idle animations and a small "thinking" indicator shows in the header.
- When the month ends or the page is closed, the run is saved as a normal replay with its `requests.jsonl`.
- Live mode binds to `127.0.0.1` only.
- Live runs are for showing the valley. Benchmark results come only from `bench`.

---

## 12. Tests

Use `pytest`. Every test runs offline, in under 10 seconds in total, with no API key.

| File | Must check |
|---|---|
| `test_clock.py` | step 0 is `Day 1, 6 am`; step 18 is `Day 2, 12 am`; times of day match the table in 4.1 |
| `test_world.py` | the same seed gives the same map; generated maps meet the water and passable rules; regrowth never exceeds the maximum; carcasses rot and are removed on time |
| `test_actions.py` | each action moves or changes state as specified on a small hand-built map; `drink` uses `known_water`; catches only happen within 1 tile; breeding respects cooldown, energy and caps; no two creatures share a tile; recorded paths match the moves made |
| `test_perception.py` | the view has exactly the specified fields in order; hunger, thirst and time words match their tables; directions follow 6.2; signals never appear in the view |
| `test_simulation.py` | the same seed gives the same starting creatures for every brain; a 100-hour `rules` run is fully repeatable; populations never go negative; dead creatures never act |
| `test_system_one.py` | using a fake transport (no network): single and batched request bodies match 7.3 exactly; valid answers are parsed; missing, invalid, slow or failed answers become fallbacks; the API key never appears in the request log |
| `test_metrics.py` | each blunder rule triggers on a hand-built case and stays silent on its opposite; calibration bins sum to the total; fallbacks are excluded |
| `test_replay.py` | a replay round-trips through write and read; a 30-day `rules` replay is under 3 MB; `food_diff` rebuilds the full grid correctly |
| `test_live.py` | with the `rules` brain, the live server streams valid frames in order and saves a replay that matches them |

---

## 13. README outline

Keep the README shorter than the code. Use these sections, in this order:

1. **Jev Valley:** one sentence, then a GIF of the 3D viewer and a link to the hosted viewer.
2. **The question:** which brain keeps the valley alive for a month, and the hesitation twist, in three sentences.
3. **Results:** the three charts and one table from `results/survival/summary.md` and `results/hesitation/summary.md`, with the seeds and lengths used.
4. **How it works:** the "model decides what, code decides how" rule, one real example request and response, batching, waiting and fallbacks.
5. **Run it:** install, a rules-brain run, how to point it at Jev or Laya, live mode, and how to reproduce the results.
6. **Design decisions:** five or six short points: separate random streams, hourly steps with waiting, batching, fallbacks, the blunder rules, why the rules baseline is fair.
7. **Limitations:** model answers vary between runs; the blunder rules are a simple, hand-written measure; results apply to this valley, not to the models in general.
8. **How this was built:** a short statement that AI assistance was used, and what the author designed, decided and verified.
9. **License:** MIT.

---

## 14. Build plan

Build in this order. Each phase ends with its tests passing and at least one commit.

| Phase | Build | Done when | Commit message |
|---|---|---|---|
| 0 | Skeleton, `pyproject.toml`, MIT licence, empty package, `pytest` running | `pytest` runs with zero tests | `chore: project skeleton` |
| 1 | `clock.py`, `world.py` | `test_clock.py` and `test_world.py` pass | `feat(world): clock, terrain, plants and carcasses` |
| 2 | `species.py`, `creatures.py` | values match 5.3 and 5.4 | `feat(species): species, creatures and action menus` |
| 3 | `perception.py` | `test_perception.py` passes | `feat(perception): creature views and signals` |
| 4 | `actions.py`, `simulation.py`, `brains/random_brain.py` | `test_actions.py` and `test_simulation.py` pass | `feat(simulation): hourly loop and actions` |
| 5 | `brains/rules.py`, `tuning.py`, `tune` command | `python -m valley tune --check` passes every target in 5.5 | `feat(brains): rules baseline and balance tuning` |
| 6 | `brains/system_one.py` | `test_system_one.py` passes | `feat(brains): System One client for Jev and Laya` |
| 7 | `replay.py`, `cli.py` with `run` and `view` | `test_replay.py` passes; `python -m valley run` writes a 30-day replay | `feat(cli): run and view commands` |
| 8 | `metrics.py` | `test_metrics.py` passes | `feat(metrics): survival, blunders, calibration and cost` |
| 9 | `bench.py`, `charts.py`, `bench` command | a `survival` bench with `rules` and `random` produces the full results layout | `feat(bench): experiments and charts` |
| 10 | `viewer/index.html`, `examples/sample-replay.json` | the sample month plays in a browser with every feature in section 10 | `feat(viewer): 3D god's view` |
| 11 | Smoke runs: Laya, then Jev, 1 seed × 2 days | under 2% fallbacks, a `requests.jsonl` for each, and measured seconds per valley hour | `bench: smoke runs for laya and jev` |
| 12 | Full `survival`, then `hesitation`, then optional `rivals` | `summary.md` and charts generated | `bench: survival and hesitation results` |
| 13 | `live.py`, `live` command | `test_live.py` passes; a Jev live run plays in the viewer | `feat(live): live mode` |
| 14 | README (section 13), hosted viewer, screen recording | every number in the README comes from `results/` | `docs(readme): results and how to run` |

If phase 11 shows the API differs from 7.3, fix the client, add a test for the real shape, and record the change in the Decisions log. If phase 11 shows that Jev cannot decide a valley hour within one second, lower `--batch` or raise `--workers` and record the measured pace; do not change the simulation.

---

## 15. Definition of done

- [ ] Every test in section 12 passes offline.
- [x] ~~`python -m valley tune --check` passes.~~ Removed 2026-10-25 with the offline brains (see the Decisions log).
- [ ] A real Jev run and a real Laya run exist, each with a `requests.jsonl`.
- [ ] `survival` and `hesitation` results are generated and committed.
- [ ] The 3D viewer is hosted and plays a real Jev month.
- [ ] Live mode runs locally with Jev.
- [ ] Every number in the README traces to a file in `results/`.
- [ ] No API key appears anywhere in the repository or its history.
- [ ] The commit history shows the phases in section 14.
- [ ] The README includes the "How this was built" section.

---

## Decisions log

Record every choice not covered above, and every change to a value in this document, with the date and the reason.

| Date | Decision | Reason |
|---|---|---|
| 2026-10-20 | Repository lives in `~/Documents/projects/jev-valley` on branch `main`, with a repo-level git identity set to the author's personal identity. | Personal project; the global git identity is a work identity and must not be used. |
| 2026-10-20 | This spec is copied to `docs/build-spec.md` so the Decisions log is versioned with the code. This file is not in the 3.2 layout. | The log has to live somewhere traceable. It can be removed before publishing. |
| 2026-10-20 | Time of day is removed from the model's view and from the instruction. Day and night are visual only. This changes 4.1 (the `time` field), the 6 example, 6.1 (the `time` rule), the 7.2 instruction and the 12 perception test. The instruction constant is now: `You are deciding the next action of one wild animal in a valley for the coming hour. Weigh its hunger, thirst, nearby dangers, chances to breed and its personality, then pick the single action it takes now.` | Time of day changes no rules, so telling the model to weigh it would bias the headline result against models for a reason unrelated to survival. |
| 2026-10-20 | Tuning in phase 5 changes only the 5.4 values. If the 5.5 targets do not pass, stop and ask the author. | Keeps the 5.3 fixed values and the "rules baseline is fair" claim intact. |
| 2026-10-20 | The replay gets sparse per-creature `notes`: `[[step, text], ...]` for every memory event except `hesitated`. The viewer rebuilds `hesitated` memories from the per-hour hesitation flags. | The mind panel needs recent memories, and the 9 format had no way to carry them. |
| 2026-10-20 | Blunder and calibration tallies are computed during the run and stored in the replay's `summary`. `metrics.py` reads those tallies. | The blunder rules need signals that the replay does not store. |
| 2026-10-20 | Model calls retry up to 2 times with backoff on HTTP 429, HTTP 5xx and timeouts only. Retries are counted in the metrics. Any other failure, or a failure after the retries, becomes a fallback. An off-by-default `--cache` flag exists for `run` and `live`; `bench` never uses it. | A transient burst should not push a run past the 2% fallback limit. A cache must never touch benchmark results. |
| 2026-10-20 | Hesitation thresholds are the 10th and 25th percentile of each brain's own confidence in its smoke runs, fixed before the full runs and logged here. Hesitation run ids use `h-p10` and `h-p25` (and `h-off` for no hesitation). | The fixed 0.3 and 0.5 might never trigger for a confident model. |
| 2026-10-20 | `--batch` stays configurable (default 16). The smoke run must confirm the provider's questions-per-request limit; some gateways cap it at 10. | The limit is not known in advance. |
| 2026-10-20 | If a Laya month takes more than an hour in the smoke measurement, Laya runs on 3 seeds only and the author is told. Jev cost is not the limit; time is. | Author's instruction. |
| 2026-10-20 | Runs marked `"valid": false` are excluded from chart medians but still listed in the results table. | Author's instruction. |
| 2026-10-20 | Nothing is pushed or hosted without the author's explicit go-ahead. The author tests the viewer on a phone and records the GIF. Real API calls (phases 11 and 12) run only with the author's go-ahead, and the author exports the keys. | Author's instruction. |
| 2026-10-20 | Meat converts to energy 1 to 1. Wolves ignore wolf carcasses. Newborns do not act, age or pay upkeep in the hour they are born. Option order is fixed in every request. Batches may mix species (per 7.6). Frame 0 is the initial state, so a month has 721 frames. matplotlib is installed in a project venv. CLI flag names the spec does not give are chosen by the builder. | Defaults the author approved. |
| 2026-10-20 | The "How this was built" README section is drafted by the assistant. The author edits it so it states only what they designed and verified. | Section 13 requires it to be accurate. |
| 2026-10-20 | Plant regrowth draws one random number for every grass and forest tile every hour, whether or not the tile is below its maximum. | Keeps `world_rng` aligned across brains, so every brain faces the same regrowth dice for a seed. |
| 2026-10-20 | Random streams are seeded with `derive_seed(seed, stream, attempt)`, a SHA-256 of `seed:stream:attempt`. Separate water areas are counted with 8-direction connectivity. | Stable across Python versions; matches how animals move. |
| 2026-10-20 | `tests/test_species.py` is added to the 12 test list. | Phase 2's "values match 5.3 and 5.4" needs a test. |
| 2026-10-20 | Species names are pluralised as `rabbits`, `deer`, `wolves`, and a distance of 1 reads `1 tile`. This applies to the view text and to the births event. | The spec templates (`{species}s`, `tiles`) read as errors for deer, wolves and single tiles. |
| 2026-10-20 | A wolf's `standing_on` is `open grass` or `forest cover`, never mentioning plants. | Plants are irrelevant to a meat eater and could mislead a model. |
| 2026-10-20 | The `possible partner` line appears only when the creature itself can breed as well as the partner. Wolves do not see wolf carcasses. A creature's `known_water` updates during perception. | Keeps the view consistent with what `seek_mate` and `scavenge` will actually do. |
| 2026-10-20 | Signals gain `species` and `water_known` (water visible or remembered). The `rules` brain and the blunder rules need them. | 6.3 lists no way to read the species or remembered water. |
| 2026-10-20 | "Previous action" (hiding visibility, `hunting` text) means the previous executed action, so a creature that froze did not hunt or hide. `Brain.decide` takes an optional `step` for logging, and `Decision.latency_ms` defaults to `None`. | A frozen animal did not do what it chose. `requests.jsonl` needs the step. |
| 2026-10-20 | Nearest-thing ties break by Chebyshev distance, then straight-line distance, then row-major tile order or creature id, without using any random stream. | Keeps views and lookups deterministic and independent of `event_rng`. |
| 2026-10-20 | Upkeep is charged after a creature's action finishes, so an animal that eats still pays that hour's metabolism. A creature eaten earlier in the hour pays nothing. | 5.9 puts upkeep inside the action step without saying whether before or after. |
| 2026-10-20 | Hesitation, the catch modifiers and the `hunting` and `hide` visibility all use the executed action, so a frozen animal counts as having rested. | A frozen animal did not do what it chose. |
| 2026-10-20 | `hide` with no visible forest stays put. `seek_mate` with no visible partner explores. `eat` and `hide` look for the nearest tile that no other creature is standing on. | The spec is silent. Stepping toward an occupied tile can never succeed. |
| 2026-10-20 | A litter is also limited by the room left under the total cap. The species share is checked only before breeding, so a species can overshoot its share by up to a litter minus one. | The spec checks the share only as a precondition. |
| 2026-10-20 | A carcass eaten down to nothing is removed at once and the plants on its tile grow back to their maximum, like a rotted one. | 5.2 says a carcass is removed when its meat reaches 0. |
| 2026-10-20 | A species' cap is `cap x share` rounded to 6 decimals, because `50 x 0.14` is `7.000000000000001` in floating point and seven wolves would not have counted as at the cap. | A bug caught by a test. |
| 2026-10-20 | A creature that died during an hour still has a row in that hour's frame. Newborns and animals that made no decision have a `null` action, confidence -1 and no probabilities. | The viewer needs the death hour to animate it, and a newborn has no decision yet. |
| 2026-10-20 | When species use different brains, the brains decide in parallel threads, and the hour waits for all of them. | Keeps a mixed run as fast as its slowest brain. |
| 2026-10-20 | The rules brain scores `flee` as -1.0 when no wolf is visible. The `cautious` bonus on `hide` applies with or without a wolf in sight. `follow_group` scores 0 with no group visible, and the `loyal` bonus applies only when a group is visible. `drink` treats remembered water like visible water. | 7.4 leaves these unspecified or ambiguous. |
| 2026-10-20 | Balance target definitions: all species alive means the run lasted the full month with every species above 0. A rabbit boom and bust means the rabbit count rose above its start and later fell to 70% or less of its peak (a crash to nothing counts). A species sits at its cap when its count is at or above `cap x share`. A species dies out when its count reaches 0 at any hour. | 5.5 states the targets but not these measurements. |
| 2026-10-20 | Phase 5 values were chosen by random search over the 5.4 values only. About 800 configurations were scored on the four targets using the ten benchmark seeds. The earliest searches also let the creature cap vary, but the values chosen come from a search that held the cap at 50, so the viewer's 50-animal target still applies. Configurations that passed were rechecked on 20 held-out seeds, and the final, rounded values on 40 (seeds 200 to 239). See the tuning record below. | 5.5 asks for tuning until the targets pass, and the author asked that only 5.4 be touched. The held-out check guards against fitting the ten seeds. |
| 2026-10-20 | Target 1 passes at its minimum: all three species are alive at the end on exactly 5 of 10 seeds. On the 40 held-out seeds the figure is 16 of 40. | Reported so the margin is not overstated. |
| 2026-10-20 | `tests/test_rules.py` and `tests/test_tuning.py` are added. `tune --thresholds RUN_DIR...` is added to fix the hesitation thresholds from smoke runs. | Not in the 12 test list; the author's threshold rule needs a command. |
| 2026-10-20 | The tests that name tuned values read them from the species table or pin them in `tests/test_species.py`. | A tuning change should change one place. |
| 2026-10-20 | An answer is accepted only if its `type` is `choice`, its `choice` is an option, its `probabilities` are a non-empty map of options to non-negative numbers, and its `confidence` is a number. Confidence outside 0 to 1 is clamped. | 7.3 says to take probabilities and confidence from the answer but not what a valid one looks like. |
| 2026-10-20 | The hard timeout is the socket timeout of each attempt, not a deadline across a slow response. A retry waits 0.5 s, then 1 s, or the server's `Retry-After` up to 10 s. Request latency in the metrics is that of the final attempt. | The standard library gives socket timeouts. |
| 2026-10-20 | Each `requests.jsonl` line also has `attempts`. Responses that are not JSON are logged as text, cut to 2,000 characters. | Retries are counted in the metrics, so the log should show them. |
| 2026-10-20 | `--cache` stores responses by SHA-256 of the request body in `.valley-cache/<brain>.jsonl`. It exists only for `run` and `live`. | The author approved an off-by-default cache that bench never uses. |
| 2026-10-20 | Servers given as `system-one@URL#MODEL` read an optional key from `SYSTEM_ONE_API_KEY`. The Jev key is never sent to them. | 7.3 names no variable for them, and a key must not go to an unrelated server. |
| 2026-10-20 | Every string written to a log or error has the API key replaced by `[redacted]`. | Ground rule 8, enforced even if a server echoes the key. |
| 2026-10-20 | Replay `meta` gains `max_creatures`. Each creature record gains `notes` and `age0` (its age in hours when it entered the valley). The summary holds the run totals, the tallies and `valid`. | The mind panel needs memories and ages, which the 9 format could not carry. |
| 2026-10-20 | Manual `run` ids with hesitation on use `h{value}`, for example `run-rules-h0.4-seed7`. `run` writes to `runs/<run id>` and logs requests only with `--log-requests`. | Run ids need a place for the threshold, and the 6.3 table makes logging off by default for `run`. |
| 2026-10-20 | `view` writes the replay into the page with every `<` escaped as `\u003c`. | Keeps `</script>` and `<!--` inside a replay from breaking the page. |
| 2026-10-20 | `python -m valley` exits with the handler's status code. | `tune --check` and `bench` need a non-zero exit on failure. |
| 2026-10-20 | Calibration counts only decisions whose source is `model`. Baseline brains get blunder counts but no calibration. Blunders per 1,000 decisions divide by decisions that were not fallbacks. | 8.4 says calibration is for model decisions, and 8.3 excludes fallbacks. |
| 2026-10-20 | `first_extinction` is the clock text of the first hour any species reached 0. `mean_population` averages over hours 1 to N. A run is valid when fallbacks are at most 2% of all decisions across its brains. | 8.2 and ground rule 6, made precise. |
| 2026-10-20 | Metrics gain a `hesitation` section: the threshold, the real decisions, how many froze, and the share. | The hesitation experiment needs to say how often animals froze. |
| 2026-10-20 | `bench` asks for confirmation before any run that uses a model, using the spec's estimate of starting creatures x steps x 1.5. It stops early with a clear message if a key is missing. Finished runs are skipped on a rerun unless `--force`, and `--jobs` runs several in parallel. | Runs take hours, so they must be resumable. |
| 2026-10-20 | Hesitation `off` reuses the survival run with the same brain and seed, because the configuration is identical, unless `--no-reuse-survival` is given. The results table says which survival run it came from. | Saves 20 model runs. The author listed this as a default. |
| 2026-10-20 | Hesitation thresholds are read from `results/hesitation/thresholds.json`, written by `tune --thresholds`. `bench hesitation` refuses to run without it. | The author fixed the thresholds from the smoke runs. |
| 2026-10-20 | The charts are SVG cards on the light chart surface, in both color schemes. Each brain keeps its color in every chart: Jev blue, Laya orange, rules aqua, random gray. Each also has its own marker shape, and every chart has a legend and a table in `summary.md`. Mixed-brain and hesitation groups reuse the brain color with a different line style or extra palette slots. | Aqua and magenta fall below 3:1 contrast on the light surface in the palette validator, so identity cannot rely on color alone. |
| 2026-10-20 | The population chart shows the median over valid runs, counting a run that ended early as 0. Charts are skipped with a message if matplotlib is not installed. | matplotlib is optional. |
| 2026-10-20 | `tests/test_bench.py` and `tests/test_charts.py` are added. | Phase 9's done condition needs tests. |
| 2026-10-20 | The viewer imports Three.js 0.160.0 from jsdelivr through an import map. With no WebGL it shows a notice and a 2D flat map. `?webgl=off` forces that fallback for testing. | 10.1 asks for a message and a flat map. |
| 2026-10-20 | The camera fits the whole valley using the projected size of the map at the current angle, rotates in 90 degree steps over 400 ms, and zooms in to about 8 tiles across. Dragging pans only when zoomed in. One-finger swipes scroll the page while the whole valley is in view. | 10.2, plus phone scrolling. |
| 2026-10-20 | A hunting wolf's dashed line points at the nearest prey within 6 tiles in the displayed frame. The replay does not record the actual target. | An approximation of the wolf's target. |
| 2026-10-20 | The mind panel rebuilds a creature's recent memories from its notes plus its hesitation flags, shows its age from `age0`, and the population chart has a table view. | The replay format keeps memories as sparse notes. |
| 2026-10-20 | Measured in a desktop browser with 45 animals in view: 120 frames per second (the display's limit), 102 draw calls, about 10,000 triangles. The 60 fps target on a mid-range phone has not been tested by the builder. | The author tests on their phone. |
| 2026-10-20 | `examples/sample-replay.json` is a rules-brain month on seed 57 (about 2 MB), chosen because all three species are alive at the end. | A lively month for the viewer's sample button. |
| 2026-10-20 | Live stream: a `meta` event first (format, meta, every creature record, frame 0), then one `frame` event per hour, then `end`. Each frame is a replay frame plus `pace`, `new_creatures`, `notes` and `fates`, so the viewer can name newborns and show memories before the run is saved. A viewer that joins late receives the earlier hours first. | 11 says each event is a replay frame plus `pace`; the extras are what the viewer needs. |
| 2026-10-20 | The valley waits for the first viewer before starting (`--no-wait` skips this). When every viewer has left for 5 seconds the run stops and is saved with what was decided. | Avoids spending API calls nobody watches. |
| 2026-10-20 | `pace.hours_per_second` is 1 divided by the larger of the pace setting and that hour's compute time. `--pace` (default 1.0) is the least real time per valley hour. | Matches the example in 11. |
| 2026-10-20 | The viewer animates each live hour over a smoothed estimate of the time between frames, speeds up when it falls behind, and shows a pulsing indicator while it waits for the next hour. | 11 asks that slow hours look slower, not jerky. |
| 2026-10-20 | `run_one` is split into `prepare_run` and `finish_run`, used by both `run` and `live`. | Live mode shares setup and saving with every other run. |
| 2026-10-20 | `bench` defaults to the first five benchmark seeds (3, 7, 11, 19, 23) and runs hesitation for Jev only, which is about 20 model runs instead of 60. The full design is still one flag away: `--seeds` with all ten and `--brains jev,laya`. `tune --check` keeps using all ten seeds. | The author found the full set too many runs and left the choice to the builder. Five seeds give noisier medians, so results must name the seeds used. |
| 2026-10-20 | The bundled sample month (`examples/sample-replay.json`), the viewer's sample button and loader, and the README's sample instructions are removed. `run` and `live` now default to `--brain jev`, so they need a key unless a brain is named. The offline `rules` and `random` brains stay: they are the baselines in `bench`, they back `tune --check`, and the tests need them. Phase 10's check that the viewer plays a month was done with replays made by the offline brain. | The author wants every run that is shown to come from a real model with a key. This overrides the earlier row about the sample replay and the `examples/` folder in the 3.2 layout and the 10.1 sample button. |
| 2026-10-20 | Laya is removed for now. This drops the `laya` brain and its `LAYA_*` variables, the `rivals` experiment (it needs two model brains), Laya's survival and hesitation runs, and the rule about running Laya on 3 seeds if a month takes over an hour. `bench survival` now defaults to jev, rules and random, and the default set is about 15 model runs. Laya's orange is left unassigned in the charts. Everything the spec says about Laya is not built, and earlier rows that mention Laya are superseded. The generic `system-one@URL#MODEL` brain stays, so a local server that speaks the same format can be added back without new code. | The author asked for Laya to be removed completely, for now. |
| 2026-10-20 | Fallbacks are removed. If a model call fails (after the 2 retries on 429, 5xx and timeouts), or any answer is missing or invalid, the client raises a `DecisionError` and the run stops. No animal is made to rest in the model's place. This replaces ground rule 6 and the fallback rules in 7.3, the 2% invalid-run rule, and the earlier rows about fallbacks, `valid`, and excluding invalid runs from medians. A stopped run writes no replay or metrics, and keeps `requests.jsonl` if it was on. In live mode the viewer is told why and nothing is saved. `bench` stops all runs at the first error, including parallel ones at their next hour, and keeps runs that had finished. | The author wants every decision to depend on Jev: if the key is missing or Jev returns any error, the run must simply stop. |
| 2026-10-20 | The `valid` flag, the `fallbacks` metrics, the fallback-rate columns and the 'valid runs' wording are removed from metrics, the summaries and the charts. A run that finishes is complete by definition. | With no fallbacks, there are no invalid runs. |
| 2026-10-20 | `--retries N` (default 2) sets how many times a rate limit, server error or timeout is retried before the run stops. `--retries 0` stops on the very first error. | Retrying the same request is not a made-up decision, but the author's rule is strict, so the strict setting is one flag. |
| 2026-10-20 | Viewer motion: an animal's move starts after a delay of up to 15% of the hour and takes 65% of it (45% for flee and hunt, which cover more tiles). At playback speeds above 1x animals glide across 95% of the hour, because an hour is then only a few frames. The easing function is clamped to the start and end of the move. | A bug where the easing returned values outside 0 to 1 made animals jump up to 4 tiles in one frame, then snap back to their start tile each hour. The simulation data was never wrong. A test now runs the viewer's own motion code under Node against a real replay and fails on any jump of half a tile in one frame. |
| 2026-10-20 | Live frames also carry `calls`: running totals of requests, decisions, tokens and retries across the brains. The viewer shows them in its status line, shows an 'Offline baseline: no model is deciding' chip when the brain is rules or random, and `run` prints the same totals at the end. | The author could not tell whether Jev was being called. Usage and the kind of brain should be visible without opening a console. |
| 2026-10-20 | A legend and a toggle for the red dashed lines from hunting wolves are added to the viewer. | The author did not know what the red lines were. |
| 2026-10-20 | `LiveServer.close()` is safe to call on a server that was never started. | A test found that it waited forever. |
| 2026-10-20 | Ecosystem redesign. The author found that every run ended with wolves left, and asked for a proper look at real ecosystems and rules designed from it. This overrides the 2026-10-20 decision that tuning changes only 5.4, because the problem was in the map and the rules, not the numbers. Everything below is recorded in the "Ecosystem redesign record" at the end of this file. | Author's request. A 60-seed diagnosis with the `rules` brain on the old valley found all three species alive on 29 of 60 seeds, nobody alive on 13, and wolves alone on 6. |
| 2026-10-20 | The cause was water, not predation: 31% of rabbit deaths were thirst and the median rabbit died 5 tiles from water. The map generator now keeps every tile within 5 tiles of water (the rabbit's vision), by painting a pond on the tile farthest from water until none is farther. Maps at least 32 × 20 also get a wandering stream with 3 fords. | With only this change, the old 28 × 18 map went from 48% to 97% of seeds with all three species alive, and rabbit thirst deaths from 31% to 1%. |
| 2026-10-20 | The default map is 40 × 26 with a creature cap of 75 and starting counts of 24 rabbits, 10 deer and 5 wolves (1.5 times the old counts, rounded). This changes 5.1, 5.3 and 5.6. Forest blobs are `area // 150` (was `// 180`). | The author asked for a bigger, more varied ground. A larger valley at a lower animal density also stabilises predator and prey, as in Huffaker's mite experiments. It costs more model tokens per run: the `rules` brain averaged 53 animals alive per hour on the new valley against 42 on the old one, about 1.3 times the tokens. |
| 2026-10-20 | Wolves are no longer perfect hunters. A hunting wolf whose target is more than 2 tiles away loses the trail with a 40% chance each hour and wanders instead, and the chance to catch prey is scaled by the prey's energy: `clamp(1 + (0.5 - energy share), 0.4, 1.6)`, so a starving animal is caught 1.5 times as often and a full one half as often. | Yellowstone wolves succeed in about 15 to 26% of hunts and take calves out of proportion to their numbers. Each change alone moved the all-alive rate from 48% to 60% and 58%. |
| 2026-10-20 | Tried and rejected, because none moved the all-alive rate beyond noise (60 seeds, plus or minus 6 points): wolf catch chance times 0.7 (47%), a refuge where hiding prey is seen only from 1 tile and caught 25% as often (48%), 12 or 24 hours of digestion after a kill (52%, 38%), a herd effect on catch chance (57%), and wolves crowding each other (52%). | Recorded so they are not tried again. |
| 2026-10-20 | The 5.4 values were re-tuned for the new valley by random search (120 configurations, 16 seeds, then the top 8 on 60 held-out seeds, then a small grid around the winner). Plant regrowth is now 0.0048 (grass) and 0.00419 (forest), roughly 40% of before, so food limits the prey; wolf catch chance on rabbits is 0.6 and on deer 0.13; wolves lose 0.51 energy an hour, need 41 energy to breed and wait 380 hours; rabbits lose 0.46 an hour and wait 94 hours; deer wait 212 hours. Minimum energy to breed for wolves moved from 44 to 41, which 5.4 had listed as fixed. | Without a lower regrowth the prey sat at their caps and wolves did not regulate them, the same food limit that NetLogo's Wolf Sheep Predation model needs to be stable. |
| 2026-10-20 | Balance target 1 is raised from 5 to 8 of 10 seeds, and a fifth target is added: wolves are never the only species left at the end. Targets 2 to 4 are unchanged. | The old bar let a baseline fail on half the seeds, which the author correctly called unfair. `random` still collapses, so the benchmark still separates a good brain from a bad one. |
| 2026-10-20 | Wolves that lose a trail remember it ("lost the trail of ..."), so the model sees it in `recent`. The model is not told about the rule itself. | A failed hunt is something the animal would know. |
| 2026-10-20 | The viewer is rewritten. There is no flat-map option (a flat map is drawn only when WebGL is missing). Motion is a continuous curve through each animal's tiles instead of a move per hour. The camera is a perspective orbit instead of 90 degree steps. Terrain, water, sky, plants and animals are drawn in code, with the `Sky` add-on from the same pinned three.js package, and nothing is downloaded. This changes 10.2 to 10.4 and 10.6, and the import map in 10. | The author asked for natural movement without an hourly tick, no flat map, a more realistic game-like look and a bigger, more varied ground. No assets were downloaded because downloads need the author's explicit permission. |
| 2026-10-20 | While a live run is still coming in, the viewer stays one hour behind the newest hour and shows the last hour only after the run has ended. | The motion curve needs the next hour to be known, or the last stretch would change shape when the next hour arrives. |
| 2026-10-20 | The ground masks for water, rock and woods fade to nothing within 6 tiles beyond the map, the water sheet reaches 9 tiles past it, and the hills around the valley carry a belt of trees that thins out with distance. | The author's screenshot showed the edge of the valley as long dark channels and blue slabs with square ends: the masks were being clamped at the map edge and stretched outward, and the water sheet was cut off at 3 tiles. |
| 2026-10-21 | The playback speed buttons (1×, 4×, 16×) are removed, and so is the live viewer's automatic speed-up when it falls behind. Playback is one valley hour per second, or in live mode the pace the run arrives at. This changes 4.2, 10.5 and the 2026-10-20 live-motion row. | The author asked for the fast-forward option to be removed completely. |
| 2026-10-21 | The viewer gains a full-screen button (also `F`; `Esc` leaves). It fullscreens the view and the timeline, using the browser's full screen where it exists and a page-covering layout otherwise (an iPhone). A small card with the selected animal's name, choice and confidence shows in full screen, because the side panels are not on screen. | The author asked for a full-screen option. |
| 2026-10-21 | In live mode the timeline slider is hidden, and the arrow keys do not step hours, until the run has played to its end. A finished replay has the slider from the start. A run that stopped on a model error also unlocks it once its last hour has played. | The author asked that the slider be a playback option only after the whole playthrough has completed. |
| 2026-10-25 | **The offline brains are removed completely.** `rules` and `random` are deleted from `valley/`, together with the balance check (`tune --check`, the 5.5 targets, `simulate_offline`) and the offline chip in the viewer. `run`, `live` and `bench` accept only `jev` or `system-one@URL#MODEL`; any other name is an error. `bench survival` now defaults to Jev alone, so it compares Jev with other models only when given `--brains jev,system-one@URL#MODEL`. The last commit that has the code is `4d545ed`. The tests keep hand-written stand-ins for a model in `tests/offline.py`, wired in by `tests/conftest.py`, because the tests must run offline and repeatably; nothing in `valley/` can use them. | The author's instruction, twice: first that the valley must not run without Jev, then "completely remove the offline run". This settles the question left open on 2026-10-20 about keeping the baselines. It costs the benchmark its hand-written comparison and the project its offline balance check, so the valley's balance is now checked only by running Jev. |
| 2026-10-25 | The rich question mode is added and is the default (`--questions rich|basic`). Each animal also answers `score` and `noul` questions in the same request, and the world reacts: prey `alert` (0 to 4; each level costs 6% of grazing yield and makes a wolf 5% less likely to catch it), everyone `breed` (both partners must say yes), prey `attack` (only scored), wolves `weak:<id>` for up to three visible prey (the wolf takes the best of weakness minus 0.35 per tile) and `effort` (each level adds 8% to the catch chance, costs 15% more energy and loses the trail 8 points less often). A score of 2 changes nothing, and a test checks that neutral answers play exactly the choice-only game. The answers are scored against what the simulation knows (Brier score and calibration by wolf distance for `attack`, alertness by threat, weakness against real energy, breeding by whether the animal could) and shown in the benchmark's Judgement section. The replay format is `@3`, with the answers as an optional eleventh item of an agent row; `@2` files still load. | The author asked for the other two Jev question types, with a world that reacts. A wolf's view says how each prey looks (age, alone, looks well, tired or weak) only in this mode, so that the weakness question has something to judge. |
| 2026-10-25 | The alertness effects were set to 6% of grazing and 5% of the catch chance per level. With the `rules` and `random` brains answering (then still present): all five balance targets passed on the ten benchmark seeds; on 100 unseen seeds all three species were alive on 96%, wolves were never alone, a rabbit boom and bust happened on 90%, and a species sat at its cap for over half the month on 11% (2% in the choice-only mode). | The larger first sizes (8% and 10%) let prey sit at their caps more often. The 11% shows the rich mode is a little less balanced than the choice-only one; it was not re-tuned further because the brains it was measured with were then removed. |
| 2026-10-25 | The live valley never runs ahead of the viewer: the page POSTs its playhead and paused state to `/control`, and the server starts no new hour while paused or when more than 3 hours ahead of the playhead (the hour in flight finishes). A viewer that never reports is not held back. A termination signal stops a live run like Ctrl-C and saves it, and the stream keepalive is 2 seconds so a viewer closed during a pause is noticed. | The author: when the simulation is stopped, everything should freeze at once because no decisions are happening. Checked against the real API: 74 requests stayed 74 for 10 seconds while paused. |
| 2026-10-25 | Checked against the live Jev API (jev-latest is jev-1.14.0): one-day valley runs of 95 and 94 requests had no errors and no retries, with a median of 360 and 421 ms. `choice`, `score` and `noul` answers have the shapes in the docs; a captured response is a test fixture. | First contact with the real API; the author supplied the key. The key is never written to a file. |

## Phase 5 tuning record

The `rules` baseline was tuned by changing only the 5.4 values. `python -m valley tune --check` passes all four targets with these values: all species alive at the end on 5 of 10 seeds, a rabbit boom and bust on 10 of 10, `random` losing a species on 10 of 10, and no species at its cap for more than half the month on any seed. On 40 held-out seeds (200 to 239) the same values gave all species alive on 16, a rabbit boom and bust on 38 and a species at its cap for over half the month on 2.

| Value | Species | Starting | Final |
|---|---|---|---|
| Energy lost per hour | rabbit | 0.45 | 0.43 |
| Energy lost per hour | deer | 0.55 | 0.6 |
| Energy lost per hour | wolf | 0.5 | 0.57 |
| Hydration lost per hour | rabbit | 0.6 | 0.47 |
| Hydration lost per hour | deer | 0.7 | 0.41 |
| Hydration lost per hour | wolf | 0.6 | 0.48 |
| Energy cost of breeding | rabbit | 7 | 7.9 |
| Energy cost of breeding | deer | 12 | 14.0 |
| Energy cost of breeding | wolf | 22 | 23.1 |
| Breeding cooldown (hours) | rabbit | 72 | 84 |
| Breeding cooldown (hours) | deer | 168 | 168 |
| Breeding cooldown (hours) | wolf | 336 | 412 |
| Energy per plant unit eaten | rabbit | 5 | 4.3 |
| Energy per plant unit eaten | deer | 6 | 6.9 |
| Meat value | rabbit | 14 | 22.7 |
| Meat value | deer | 34 | 39.4 |
| Meat value | wolf | 20 | 18.0 |
| Catch chance on rabbits | wolf | 0.45 | 0.46 |
| Catch chance on deer | wolf | 0.22 | 0.16 |
| Grass regrowth chance per hour | world | 0.015 | 0.0125 |
| Forest regrowth chance per hour | world | 0.010 | 0.0109 |
| Carcass rot per hour | world | 0.3 | 0.29 |
| Carcass lifetime (hours) | world | 72 | 48 |

Unchanged: max energy, max hydration, adult age, minimum energy to breed, and the creature cap of 50.

## Ecosystem redesign record

Everything here was measured with the offline `rules` and `random` brains. No model was called. "All alive" means all three species are alive at the end of the 30 days. The 60-seed experiments carry about plus or minus 6 points of noise, so only differences of 12 points or more mean anything.

### The problem, measured on the old valley (28 × 18, cap 50, 60 seeds)

| Measure | Result |
|---|---|
| All three species alive at the end | 29 of 60 |
| Only wolves alive at the end | 6 of 60 |
| Nobody alive at the end | 13 of 60 |
| Wolves alive at the end | 45 of 60 |
| How long wolves outlast the prey when the prey all die first | median 99 hours, at most 115 (a full wolf starves in about 105) |
| How rabbits died | 59% eaten, 31% thirst, 10% starved |
| How deer died | 73% eaten, 20% thirst, 6% starved |
| Rabbits that died of thirst, distance to the nearest water | median 5 tiles; 477 of 770 within 6 tiles; 398 of 770 had `drink` as their last action |

Wolves are the last ones standing for a simple reason: a wolf has a long starvation buffer, so when the prey go it is the last to die. The prey went because they died of thirst, on a map with about two ponds.

### What each change did on its own (old valley, `rules`, 60 seeds, all alive)

| Change | All alive |
|---|---|
| Nothing (baseline) | 48% |
| Twice as many ponds | 73% |
| Three times as many ponds | 78% |
| Every tile within 5 tiles of water | 97% |
| Every tile within 6 tiles / within 4 tiles | 93% / 85% |
| Wolves lose a far target 40% of hours | 60% |
| Weak prey easier to catch | 58% |
| Herd effect on catch chance | 57% |
| 12 / 24 hours of digestion after a kill | 52% / 38% |
| Wolves crowding each other | 52% |
| Wolf catch chance times 0.7 | 47% |
| Hiding prey seen only from 1 tile and caught 25% as often | 48% |
| Bigger map, same animals (40 × 26 / 56 × 36) | 85% / 77% (at 56 × 36 wolves starve in 20% of runs) |

The `random` brain keeps all three alive on 0 to 7% of seeds in every variant above, so the benchmark still separates brains.

### After the water fix: prey at their caps

With the new valley and the old 5.4 values, rabbits or deer sat at their caps for over half the month on 95 to 100% of seeds and wolves did not regulate them. Plant regrowth was cut to about 40% of its old value so that food limits the prey, as the grass does in NetLogo's Wolf Sheep Predation model, and the other 5.4 values were searched again.

| Value | Species | Before | After |
|---|---|---|---|
| Grass regrowth chance per hour | world | 0.0125 | 0.0048 |
| Forest regrowth chance per hour | world | 0.0109 | 0.00419 |
| Catch chance on rabbits | wolf | 0.46 | 0.6 |
| Catch chance on deer | wolf | 0.16 | 0.13 |
| Energy lost per hour | wolf | 0.57 | 0.51 |
| Minimum energy to breed | wolf | 44 | 41 |
| Breeding cooldown (hours) | wolf | 412 | 380 |
| Energy lost per hour | rabbit | 0.43 | 0.46 |
| Breeding cooldown (hours) | rabbit | 84 | 94 |
| Breeding cooldown (hours) | deer | 168 | 212 |
| Starting count | rabbit / deer / wolf | 16 / 7 / 3 | 24 / 10 / 5 |
| Creature cap | all | 50 | 75 |
| Map size | world | 28 × 18 | 40 × 26 |

Method: 120 random configurations scored on 16 seeds; the best 8 re-scored on 60 seeds that were not used in the search (500 to 559); then a small grid around the winner, which fixed the one benchmark seed (101) where rabbits sat at their cap.

### Result on the final values

| Check | Result |
|---|---|
| `tune --check`, ten benchmark seeds | all five targets pass: all alive on 10 of 10, rabbit boom and bust on 10 of 10, `random` loses a species on 10 of 10, no species at its cap for over half the month on 0, wolves alone on 0 |
| `rules`, 100 fresh seeds (1000 to 1099) | all alive on 97%, wolves alone on 0%, nobody left on 0%, a species at its cap for over half the month on 2%, rabbit boom and bust on 96%, 53 animals alive on average |
| `random`, the same seeds | all alive on 0%; wolves extinct on 100%, rabbits extinct on 75% |

### Where the rules come from

- Wolves are not perfect hunters. Yellowstone wolves succeed in about 26% of hunts in a severe winter and 15% in a mild one (USGS, https://digitalcommons.unl.edu/usgsnpwrc/337), and make about 1.9 kills per wolf per month (Smith and others, https://digitalcommons.mtu.edu/michigantech-p/13805).
- Wolves take the young and the weak: calves were 43% of elk kills in 1995 to 2000, and selection varied with the condition of the herd (same source). Predators kill most deer fawns in their first summer, while adult deer are rarely killed by predators (Pennsylvania Game Commission, https://www.pa.gov/agencies/pgc/wildlife/discover-pa-wildlife/white-tailed-deer/predation-and-deer-population).
- Refuges, spatial patchiness, and density-dependent predator mortality are named as stabilisers, and rich food and perfect predators as destabilisers, at https://en.wikipedia.org/wiki/Paradox_of_enrichment. Huffaker's mite experiment found predators overexploited their prey in a simple setting and coexisted when the habitat was patchy and prey could disperse (https://en.wikipedia.org/wiki/Huffaker%27s_mite_experiment).
- NetLogo's Wolf Sheep Predation is unstable with only sheep and wolves and generally stable once sheep must eat regrowing grass (https://ccl.northwestern.edu/netlogo/models/WolfSheepPredation).

### Limits of this record

- The numbers are game-scaled, not field data. No source was found for wolf food per day, fasting time or wolf to prey ratios, so none was used. A fact sheet that gives one wolf per 50 to 200 deer is an educational figure, not a study, and was not used either.
- The theory pages are encyclopedia articles, not the original papers.
- The valley was tuned for the offline brains. Jev may do better or worse than `rules`; that is what the benchmark is for.
