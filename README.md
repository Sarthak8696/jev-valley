# Jev Valley

A small simulated valley where every rabbit, deer and wolf decides its next action by asking a typed decision model one `Choice` question, once per valley hour.

<!-- Add here: a GIF of the 3D viewer and a link to the hosted viewer. The author records the GIF and hosts the page. -->

Play the sample month with nothing installed but Python. It is a recording of the offline `rules` brain, so it needs no API key and the probabilities it shows are the rules brain's, not a model's. The viewer loads Three.js from a CDN, so it needs a network connection:

```bash
python -m valley view examples/sample-replay.json -o valley.html   # then open valley.html in a browser
```

## The question

Which brain keeps the valley alive for a month? Every run uses the same maps, the same seeds and the same starting animals, and only the brain changes: Jev, Laya, a hand-written `rules` baseline, or `random`. A second question: does knowing when you are unsure help you survive? With hesitation on, an animal freezes for the hour when the model's confidence is low, and survival is compared with hesitation off.

## Results

Results are produced by `python -m valley bench` and written to `results/<experiment>/` as `summary.md` and three charts. The full runs against Jev and Laya have not been done yet, so there is nothing to report here. Nothing in this README is typed by hand from a result.

To reproduce them, see [Run it](#run-it).

## How it works

**The model decides what. The code decides how.** The model only ever returns one action key: `eat`, `drink`, `flee`, `hide`, `rest`, `seek_mate`, `follow_group` or `explore` for rabbits and deer, and `hunt`, `scavenge`, `drink`, `hide`, `rest`, `seek_mate`, `follow_group` or `explore` for wolves. Paths, catches, births and deaths are ordinary deterministic code, so a run is fair and repeatable.

Each hour, every animal gets a plain-language view of what it can see and feel, and one `Choice` question. This is a real request, written by the client from a real view in the sample world:

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
python -m valley tune --check         # the balance targets for the offline brains
python -m valley run --seed 57        # a month with the rules brain, written to runs/
python -m valley view runs/run-rules-seed57/replay.json -o valley.html
```

Point it at Jev or Laya through environment variables. Keys are read only from the environment and never written to a log:

```bash
export TYPESAFE_API_KEY=...           # required for jev; also TYPESAFE_BASE_URL, TYPESAFE_MODEL
export LAYA_BASE_URL=http://localhost:8000   # check Laya's own docs for its port and model name
export LAYA_MODEL=laya-auto                  # optional: LAYA_API_KEY
python -m valley run --brain jev --days 2 --log-requests   # a small first run
```

Watch a valley being decided, as it happens (binds to 127.0.0.1 only):

```bash
python -m valley live --brain jev --seed 57 --open
```

Reproduce the results. `bench` prints how many decisions and requests it expects and asks before spending any, skips runs that are already done, and writes everything to `results/`:

```bash
python -m valley bench survival       # jev, laya, rules and random on five seeds, 30 days each
python -m valley tune --thresholds runs/run-jev-seed7 -o results/hesitation/thresholds.json
python -m valley bench hesitation     # Jev with hesitation off, and at its own 10th and 25th percentile confidence
```

The default set is small on purpose (about 20 model runs): the first five benchmark seeds, and hesitation for Jev only. The full design is one flag away: add `--seeds 3,7,11,19,23,42,57,64,88,101` to either command, and `--brains jev,laya` to `bench hesitation` (with a Laya smoke run in `tune --thresholds`).

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
