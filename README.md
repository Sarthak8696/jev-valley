# Jev Valley

A small simulated valley where every rabbit, deer and wolf decides its next action by asking a typed decision model one `Choice` question, once per valley hour.

<!-- Add here: a GIF of the 3D viewer and a link to the hosted viewer. The author records the GIF and hosts the page. -->

## See it running

The quickest way to see Jev Valley work is **live mode**. It starts a local page (on 127.0.0.1 only), waits for you to open it, and then plays the valley at one valley hour per real second while the model decides what every animal does next:

```bash
export TYPESAFE_API_KEY=...        # your Jev key; it is read from the environment and never logged
python -m valley live --seed 7 --open
```

What you will see in the page:

- The valley in 3D, with rabbits, deer and wolves moving, hunting, hiding and drinking, in day and night light. Rotate with Q and E, zoom with + and -, and switch to a flat map.
- Click any animal to see its hunger and thirst, what it chose this hour, the probability the model gave to every action ("Why it chose this"), and its recent memories.
- A pace badge. If the model is slow, the valley's clock slows down and the badge pulses while it waits. Decisions are never skipped or guessed.
- A population chart, an event log, and a timeline you can scrub back along.

A month is 720 valley hours, so a full run takes 12 minutes or more, and longer if the model is slow. Add `--days 2` for a short one. Closing the page stops the run and saves what was decided to `runs/live-jev-seed7/`. The valley does not start until a page is open, so no model calls are spent unseen.

To try the viewer without a key, run live mode with the offline baseline. This is the hand-written `rules` brain, not a model, so it shows nothing about Jev:

```bash
python -m valley live --brain rules --seed 57 --open
```

To watch a finished run afterwards, see [Run it](#run-it). There is no bundled demo: every run you watch is one you make.

## The question

Which brain keeps the valley alive for a month? Every run uses the same maps, the same seeds and the same starting animals, and only the brain changes: Jev, a hand-written `rules` baseline, or `random`. A second question: does knowing when you are unsure help you survive? With hesitation on, an animal freezes for the hour when the model's confidence is low, and survival is compared with hesitation off.

## Results

Results are produced by `python -m valley bench` and written to `results/<experiment>/` as `summary.md` and three charts. The full runs against Jev have not been done yet, so there is nothing to report here. Nothing in this README is typed by hand from a result.

To reproduce them, see [Run it](#run-it).

## How it works

**The model decides what. The code decides how.** The model only ever returns one action key: `eat`, `drink`, `flee`, `hide`, `rest`, `seek_mate`, `follow_group` or `explore` for rabbits and deer, and `hunt`, `scavenge`, `drink`, `hide`, `rest`, `seek_mate`, `follow_group` or `explore` for wolves. Paths, catches, births and deaths are ordinary deterministic code, so a run is fair and repeatable.

Each hour, every animal gets a plain-language view of what it can see and feel, and one `Choice` question. This is a real request, written by the client from a real view of a simulated valley:

```json
{
  "model": "jev-latest",
  "state": {
    "id": "r4",
    "animal": "Basil the rabbit",
    "diet": "eats plants",
    "personality": "loyal",
    "age": "7 days (adult)",
    "hunger": "fed",
    "thirst": "thirsty",
    "standing_on": "open grass, with plants to eat",
    "can_have_young": "no, had young recently",
    "sees": [
      "DANGER: wolf Frost, 5 tiles north, hunting",
      "3 other rabbits, nearest 2 tiles south-east",
      "water, 5 tiles north",
      "plants to eat, right here"
    ],
    "recent": ["Day 1, 8 am: had 1 young with Fern 4"]
  },
  "questions": {
    "action": {
      "type": "choice",
      "instructions": "You are deciding the next action of one wild animal in a valley for the coming hour. Weigh its hunger, thirst, nearby dangers, chances to breed and its personality, then pick the single action it takes now.",
      "criteria": {
        "eat": "Eat the plants where I stand, or walk toward the nearest plants I can see",
        "drink": "Walk to the nearest water and drink",
        "flee": "Run away from the nearest predator as fast as I can",
        "hide": "Move into forest cover, or stay hidden there",
        "rest": "Stay still to save energy",
        "seek_mate": "Walk toward a partner of my kind and have young",
        "follow_group": "Move closer to others of my kind for safety",
        "explore": "Wander somewhere new to find food, water or partners"
      }
    }
  }
}
```

The client expects each answer to hold `type`, `choice`, `probabilities` (one per option) and `confidence`, plus `usage.input_tokens` and `usage.output_tokens` for the cost figures. A captured response from a real run will be added here once there is one; every request and response of a run is logged to `requests.jsonl`.

Several animals go into one request (16 by default, `--batch` to change it), each with its own question id, and requests run in parallel. The hour waits for every decision. If a call fails, times out or returns an invalid answer, that animal rests, the decision is marked as a fallback and counted, and a run with more than 2% fallbacks is marked invalid.

## Run it

Python 3.11 or newer. The simulation, client and viewer need nothing else. `matplotlib` is optional and only draws the charts.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,charts]"
python -m pytest                      # every test runs offline, with no API key
python -m valley tune --check         # offline: checks the balance of the baseline brains
```

Runs use a model, so they need a key. Keys are read only from the environment and never written to a log:

```bash
export TYPESAFE_API_KEY=...           # required for jev; also TYPESAFE_BASE_URL, TYPESAFE_MODEL
python -m valley run --seed 7 --days 2 --log-requests    # a small first run with Jev, the default brain
```

Watch a finished run in the viewer (to watch one as it is decided, see [See it running](#see-it-running)):

```bash
python -m valley view runs/run-jev-seed7/replay.json -o valley.html   # then open valley.html in a browser
```

The viewer loads Three.js from a CDN, so it needs a network connection. The offline `rules` and `random` brains are the baselines the models are compared against. They are not run by default; name one with `--brain rules` if you want to see it.

Reproduce the results. `bench` prints how many decisions and requests it expects and asks before spending any, skips runs that are already done, and writes everything to `results/`:

```bash
python -m valley bench survival       # jev, rules and random on five seeds, 30 days each
python -m valley tune --thresholds runs/run-jev-seed7 -o results/hesitation/thresholds.json
python -m valley bench hesitation     # Jev with hesitation off, and at its own 10th and 25th percentile confidence
```

The default set is small on purpose (about 15 model runs): the first five benchmark seeds. To use all ten, add `--seeds 3,7,11,19,23,42,57,64,88,101` to either command.

Other servers that speak the same request format can be used with `--brain system-one@BASE_URL#MODEL` (an optional key goes in `SYSTEM_ONE_API_KEY`).

The full specification and the log of every decision made while building it are in [docs/build-spec.md](docs/build-spec.md).

## Design decisions

- **Separate random streams.** The map and plant regrowth, the events (catches, litters, names, action order) and the `rules` and `random` brains each have their own stream, all derived from the seed. A brain never touches the world's or the events' stream, and plant regrowth draws the same dice whatever the plants look like, so every brain faces the same valley.
- **Hourly steps, with waiting.** Every animal decides once per hour, from one snapshot of the world, and the loop waits for all decisions before anything moves. Slow decisions make a run take longer; they never change what happens.
- **Batching and fallbacks.** Many creatures share a request to keep the cost down. A failed or invalid answer becomes a counted fallback instead of a hidden failure, and 429s, 5xx errors and timeouts are retried twice before that.
- **Blunder rules.** Six simple rules mark a choice as clearly bad given what the animal could see, for example ignoring a wolf two tiles away. They are counted while the run happens, because they need information a replay does not store, and confidence is binned to show whether the model is surer when it is right.
- **A fair baseline.** The `rules` brain scores each action from the same signals and samples through a softmax. It was tuned only through the world's numbers, never weakened, so a model has to beat something reasonable. `random` is the floor.
- **Everything is traceable.** Each benchmark number comes from `python -m valley bench` and a file under `results/`, and the raw requests and responses are kept.

## Limitations

- Model answers vary between runs, so one run is not a measurement. The benchmark reports its seeds together (five by default, ten with `--seeds`), and five seeds give noisier medians than ten.
- The blunder rules are a simple, hand-written measure, and the `rules` brain was written with similar ideas, so it has a natural advantage on this metric.
- Results apply to this valley and these prompts, not to the models in general.
- The balance of the valley was tuned for the offline brains on the ten benchmark seeds. The `rules` brain keeps all three species alive on about half of them, which is intended: a better brain has room to do better and a worse one can visibly do worse.
- The live API has not been called while building this. The client was tested against a fake server written from the documented request and response shape.

## How this was built

This project was built with AI assistance (Claude). The code, tests and viewer were written by the assistant from a written build specification, and every choice the specification left open is recorded in [docs/build-spec.md](docs/build-spec.md).

<!-- Add here, before publishing: what you designed, decided and verified yourself. The assistant cannot state that for you. -->

## License

MIT. See [LICENSE](LICENSE).
