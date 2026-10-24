# Jev Valley

A small simulated valley where every rabbit, deer and wolf decides its next action by asking a typed decision model a `Choice` question and a few `Score` and yes/no (`Noul`) questions, once per valley hour.

<!-- Add here: a GIF of the 3D viewer and a link to the hosted viewer. The author records the GIF and hosts the page. -->

## See it running

The quickest way to see Jev Valley work is **live mode**. It starts a local page (on 127.0.0.1 only), waits for you to open it, and then plays the valley at one valley hour per real second while the model decides what every animal does next:

```bash
export TYPESAFE_API_KEY=...        # your Jev key; it is read from the environment and never logged
python -m valley live --seed 7 --open
```

What you will see in the page:

- A 40 × 26 valley in 3D: a stream with fords, ponds, woods, meadows with wild flowers, and wooded hills around it. The sun, moon and stars follow the clock, and grass goes bare where animals have grazed. Rabbits, deer and wolves walk, trot, hop, graze, lie down, hide, hunt and drink, and keep moving smoothly across the turn of every hour. Drag to look around, scroll or pinch to zoom, right-drag or two fingers to slide, Q and E to turn, 0 to see the whole valley again, F for full screen.
- Click any animal to see its hunger and thirst, what it chose this hour, the probability the model gave to every action ("Why it chose this"), and its recent memories.
- A status line that shows the pace and the real usage so far, for example `Live: 1.0 hours per second · 214 model requests, 85,310 input tokens`. If the model is slow, the valley's clock slows down and the badge pulses while it waits. Decisions are never skipped or guessed.
- A red dashed line from a wolf that chose to hunt to its nearest target. A legend in the corner of the view explains it, and clicking the legend hides the lines.
- A population chart and an event log. Playback is always one valley hour per second, with no fast-forward. The timeline slider appears once a live run has played to its end, so you cannot skip ahead of it; a finished replay has it from the start.

A month is 720 valley hours, so a full run takes 12 minutes or more, and longer if the model is slow. Add `--days 2` for a short one. Closing the page stops the run and saves what was decided to `runs/live-jev-seed7/`. The valley does not start until a page is open, so no model calls are spent unseen.

**The valley does not run without a model.** `run` and `live` accept only Jev (or another server that speaks the same request format), and stop at once if the key is missing or a call fails. There is no offline mode and no hand-written stand-in inside the valley. Earlier versions had two comparison brains, `rules` and `random`; the last commit that has them is `4d545ed`.

**Pausing freezes the valley.** The page tells the server where its playhead is and whether it is paused. While it is paused, or more than three hours ahead of what is on screen, no new hour is started and nothing is asked of Jev; the hour already in flight finishes. Closing the page ends the run after a few seconds and saves what was decided.

To watch a finished run afterwards, see [Run it](#run-it). There is no bundled demo: every run you watch is one you make.

## The question

Does a typed decision model make sensible decisions, and does it know when it is wrong? Every run uses the same maps, the same seeds and the same starting animals; only the brain changes (Jev, or another model behind `system-one@URL#MODEL`). Three things are measured: whether the valley survives the month; how often a choice is a clear blunder, and whether the model's confidence predicts it; and how well its answers to the extra questions match what really happens (see [More than a choice](#more-than-a-choice)). A second question: does knowing when you are unsure help you survive? With hesitation on, an animal freezes for the hour when the model's confidence is low, and survival is compared with hesitation off.

## Results

Results are produced by `python -m valley bench` and written to `results/<experiment>/` as `summary.md` and three charts. The full runs against Jev have not been done yet, so there is nothing to report here. Nothing in this README is typed by hand from a result.

To reproduce them, see [Run it](#run-it).

## How it works

**The model decides what. The code decides how.** The model only ever returns one action key: `eat`, `drink`, `flee`, `hide`, `rest`, `seek_mate`, `follow_group` or `explore` for rabbits and deer, and `hunt`, `scavenge`, `drink`, `hide`, `rest`, `seek_mate`, `follow_group` or `explore` for wolves. Paths, catches, births and deaths are ordinary deterministic code, so a run is fair and repeatable.

Each hour, every animal gets a plain-language view of what it can see and feel, and one `Choice` question, plus the extra questions described above. This is a real request, written by the client from a real view of a simulated valley:

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

Several animals go into one request (16 by default, `--batch` to change it), each with its own question id, and requests run in parallel. The hour waits for every decision.

**Nothing stands in for the model.** If the key is missing, or a call fails, or any answer is missing or invalid, the run stops at once with a message that names the step, the animal and the error. No animal is made to "rest" or guess. A rate limit (429), a server error (5xx) or a timeout is retried twice first, and the retries are counted in the metrics; `--retries 0` stops on the first error instead. A stopped run saves no replay or metrics, only the request log if it was on, and `bench` keeps the runs that had already finished so you can rerun the same command.

The code overrides a model's choice in two places only. If the chosen action cannot be done at that moment (flee with no wolf in sight, for example), the animal explores instead. And with hesitation on, which is off unless you ask for it, an animal freezes when the model's confidence is below the threshold.

## More than a choice

Jev answers three kinds of question: `choice` (pick one of several), `score` (a place on an ordered scale, which can fall between levels) and `noul` (the probability of yes). Each hour an animal gets its `Choice` question and, in the default `rich` mode, a few of the others in the same request:

| Animal | Question | Type | What the valley does with the answer |
|---|---|---|---|
| prey | How alert should I be? (0 to 4) | score | The more alert, the less it gets from grazing and the harder a wolf finds it to catch. |
| everyone | Is now a good time to have young? | yes/no | Two animals breed only if both say yes. |
| prey | Will a wolf try to catch me this hour? | yes/no | Nothing: it is only scored. |
| wolves | How weak does each of up to three prey look? (0 to 4) | score | The wolf chases the best mix of weak-looking and near. |
| wolves | How hard should I chase? (0 to 4) | score | More effort catches more and loses the trail less, and tires the wolf more. |

A score of 2 changes nothing, so a brain that answers 2 everywhere plays the choice-only game. `--questions basic` asks only which action to take.

The answers are also checked against what the simulation knows, and the benchmark summary has a **Judgement** section: how close the attack answer was to what happened (a Brier score, and the answer next to the outcome with and without a wolf near), whether alertness rises as the wolf gets closer, how well the weakness score matches the prey's real energy, and how the breeding answer differs between an animal that could breed and one that could not. These measure whether the model understands the scene, which survival alone cannot.

Checked against the live API on 2026-10-25 with one-day runs: every request returned valid answers, the median request took about 0.4 s, and a rich-mode day used about 1.0 million input tokens, a little under twice the choice-only day.

## Why the valley is balanced this way

The first version of the valley ended with wolves alone on some runs, and with nobody left on others. A hand-written stand-in for a model kept all three species alive to the end of the month on only 29 of 60 seeds. The cause was water: 31% of rabbit deaths were thirst, and the median rabbit died five tiles from the nearest drink, so the rabbits went first and the wolves, which can go about 105 hours without food, outlived them. Wolves were never the problem.

The valley was changed in the ways real predator and prey systems suggest, and each change was tested alone before it was kept:

- **Water within reach.** No tile is more than five tiles, the rabbit's vision, from water. On the old map this alone took that stand-in from 48% to 97% of seeds with all three species alive.
- **Wolves are not perfect hunters.** Yellowstone wolves succeed in about 15 to 26% of hunts ([USGS](https://digitalcommons.unl.edu/usgsnpwrc/337)) and take calves out of proportion to their numbers ([Smith and others](https://digitalcommons.mtu.edu/michigantech-p/13805)). A hunting wolf can lose a prey that is still some way off, and weak animals are easier to catch than strong ones.
- **Food limits the prey.** Plants regrow slower, so the prey settle below their caps instead of piling up against them. NetLogo's wolf and sheep model needs the same thing to be stable ([NetLogo](https://ccl.northwestern.edu/netlogo/models/WolfSheepPredation)).
- **More room.** A bigger valley at a lower density gives prey places to be, which is the idea behind [Huffaker's mite experiment](https://en.wikipedia.org/wiki/Huffaker%27s_mite_experiment).

Things that did not help were tried and dropped: weaker wolves, stronger hiding, digestion time after a kill, and crowding between wolves. The valley was balanced with two hand-written stand-in brains, one that follows simple rules and one that picks at random, so that it could be checked without a model. With them, all three species survived on 96 to 97% of 100 unseen seeds, wolves were never the only species left, and the random brain collapsed every time. Those stand-ins were later removed because the valley does not run without a model, so how Jev does in this valley is what the benchmark is for. The numbers, the experiments and the limits are in the [ecosystem redesign record](docs/build-spec.md#ecosystem-redesign-record).

## Run it

Python 3.11 or newer. The simulation, client and viewer need nothing else. `matplotlib` is optional and only draws the charts.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,charts]"
python -m pytest                      # every test runs offline, with no API key, using stand-ins for the model
```

Runs use a model, so they need a key. Every run ends by printing how many requests and tokens it used, and the same numbers are in the run's `metrics.json`. Keys are read only from the environment and never written to a log:

```bash
export TYPESAFE_API_KEY=...           # required for jev; also TYPESAFE_BASE_URL, TYPESAFE_MODEL
python -m valley run --seed 7 --days 2 --log-requests    # a small first run with Jev, the default brain
```

Watch a finished run in the viewer (to watch one as it is decided, see [See it running](#see-it-running)):

```bash
python -m valley view runs/run-jev-seed7/replay.json -o valley.html   # then open valley.html in a browser
```

The viewer loads Three.js, and its sky add-on, from a CDN, so it needs a network connection. Everything else in it, the land, water, plants and animals, is drawn in code, and nothing is downloaded. It lowers its own resolution when a device cannot keep up; add `?quality=low` to the page address to force the lighter version. The offline `rules` and `random` brains are the baselines the models are compared against. They are not run by default; name one with `--brain rules` if you want to see it.

Reproduce the results. `bench` prints how many decisions and requests it expects and asks before spending any, skips runs that are already done, and writes everything to `results/`:

```bash
python -m valley bench survival       # jev on five seeds, 30 days each
python -m valley tune --thresholds runs/run-jev-seed7 -o results/hesitation/thresholds.json
python -m valley bench hesitation     # Jev with hesitation off, and at its own 10th and 25th percentile confidence
```

The default set is small on purpose (about 15 model runs): the first five benchmark seeds. To use all ten, add `--seeds 3,7,11,19,23,42,57,64,88,101` to either command.

Other servers that speak the same request format can be used with `--brain system-one@BASE_URL#MODEL` (an optional key goes in `SYSTEM_ONE_API_KEY`).

The full specification and the log of every decision made while building it are in [docs/build-spec.md](docs/build-spec.md).

## Design decisions

- **Separate random streams.** The map and plant regrowth, the events (catches, litters, names, action order) each have their own stream, all derived from the seed. A brain never touches the world's or the events' stream, and plant regrowth draws the same dice whatever the plants look like, so every brain faces the same valley.
- **Hourly steps, with waiting.** Every animal decides once per hour, from one snapshot of the world, and the loop waits for all decisions before anything moves. Slow decisions make a run take longer; they never change what happens.
- **Batching, and stopping on errors.** Many creatures share a request to keep the cost down. Any error that survives the retries stops the run, because a made-up decision would not be the model's.
- **Blunder rules.** Six simple rules mark a choice as clearly bad given what the animal could see, for example ignoring a wolf two tiles away. They are counted while the run happens, because they need information a replay does not store, and confidence is binned to show whether the model is surer when it is right.
- **No offline stand-in.** The valley cannot run without a model: there is no hand-written brain in it, so nothing can be mistaken for Jev. The tests use stand-ins, and they live only under `tests/`.
- **Everything is traceable.** Each benchmark number comes from `python -m valley bench` and a file under `results/`, and the raw requests and responses are kept.

## Limitations

- Model answers vary between runs, so one run is not a measurement. The benchmark reports its seeds together (five by default, ten with `--seeds`), and five seeds give noisier medians than ten.
- The blunder rules are a simple, hand-written measure of what is clearly a bad choice, so they are a rough guide, not a verdict.
- Results apply to this valley and these prompts, not to the models in general.
- The balance of the valley was tuned with offline stand-ins that are no longer in the repo, and has not been checked with Jev. In the rich mode a species sat at its population cap for over half the month on 11% of unseen seeds, against 2% in the choice-only mode. The game's numbers are scaled for play, not taken from field data, and the sources above are the only research behind them.
- The live API has not been called while building this. The client was tested against a fake server written from the documented request and response shape.

## How this was built

This project was built with AI assistance (Claude). The code, tests and viewer were written by the assistant from a written build specification, and every choice the specification left open is recorded in [docs/build-spec.md](docs/build-spec.md).

<!-- Add here, before publishing: what you designed, decided and verified yourself. The assistant cannot state that for you. -->

## License

MIT. See [LICENSE](LICENSE).
