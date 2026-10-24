# Jev Valley

A small simulated valley where every rabbit, deer and wolf decides its next action by asking a typed decision model a `Choice` question and a few `Score` and yes/no (`Noul`) questions, once per valley hour. Nothing in the valley is scripted: the model decides what each animal does, and ordinary code decides how it happens.

![Storm the wolf stalks Basil the rabbit at a pond: five seconds of a real run on Jev, recorded from the 3D viewer](docs/images/valley.gif)

*Five seconds of a real run (seed 7, decided by Jev). Storm the wolf is hunting; the red dashed line joins a wolf that chose to hunt to its target.*

Jump to: [Quick start](#quick-start) · [What you will see](#what-you-will-see) · [Commands](#commands) · [Troubleshooting](#troubleshooting) · [How it works](#how-it-works) · [Limitations](#limitations)

## Quick start

You need Python 3.11 or newer, an API key for Jev, and a current browser (Chrome, Edge, Firefox or Safari) with WebGL. The commands below are for macOS and Linux; Windows should work but has not been tried.

**1. Get the code and install it.**

```bash
git clone https://github.com/Sarthak8696/jev-valley.git
cd jev-valley
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev,charts]"
```

The valley itself uses only the Python standard library. The `dev` extra adds `pytest` for the tests, and `charts` adds `matplotlib`, which only the benchmark charts need. Check that it worked with `python -m valley --version`.

**2. Give it your Jev key.**

```bash
export TYPESAFE_API_KEY=your-key-here     # Windows PowerShell: $env:TYPESAFE_API_KEY = "your-key-here"
```

The key is read from the environment, in the same terminal you run the next command from. It is never written to a file or a log. Without it nothing runs: the valley has no offline mode, and stops at once with `error: TYPESAFE_API_KEY is not set`.

**3. Watch a two-day valley, live.**

```bash
python -m valley live --seed 7 --days 2 --open
```

The terminal prints `Jev Valley live at http://127.0.0.1:8765` and `Waiting for a viewer to connect before the valley starts.`, and your browser opens that page. (If it does not open, paste the address into a browser yourself.) The valley starts when the page is open and plays one valley hour per real second, so two days take about a minute and use roughly 2 million input tokens, about $0.10 at the documented price of $0.042 per million (an estimate: check your own usage). When the run ends, the timeline slider appears and the run is saved to `runs/live-jev-seed7/`. Leave `--days` out for a full month of 30 days, which takes 12 minutes or more.

**4. Watch it again later, with no key and no cost.**

```bash
python -m valley view runs/live-jev-seed7/replay.json -o valley.html
open valley.html                   # Linux: xdg-open valley.html    Windows: start valley.html
```

A finished replay has the timeline slider from the start, so you can scrub through it.

That is all there is to running it. `run`, `bench` and `tune` have no window of their own; [Commands](#commands) says which command to use for what.

## What you will see

![Storm the wolf has chosen to hunt. The Mind panel shows the probability Jev gave every action and its answers to the other questions.](docs/images/wolf-hunting.jpg)

*Day 2, 3 pm of the same run. Click any animal and the Mind panel shows what it needs, what it chose and why. Storm, a lazy 17-day-old wolf, chose Hunt (the model's own confidence was 89%; the bars are the probability of each action). Its other answers: Basil the rabbit looks 3.0 out of 4 on weakness, the chase deserves 1.9 out of 4 effort, and it is not a good time to have young. At 3 pm Storm caught Basil.*

![The same moment from Basil the rabbit's side: it chose to flee, scored itself 3.8 out of 4 alert, and said a wolf would try to catch it with 75% probability.](docs/images/rabbit-fleeing.jpg)

*The same hour, from the prey's side. Basil, hungry and thirsty, chose Flee, scored its alertness 3.8 out of 4, and put the chance that a wolf would go after it at 75%. It had escaped Storm three times already.*

- A 40 × 26 valley in 3D: a stream with fords, ponds, woods, meadows with wild flowers, and wooded hills around it. The sun, moon and stars follow the clock, and grass goes bare where animals have grazed. Rabbits, deer and wolves walk, trot, hop, graze, lie down, hide, hunt and drink, and keep moving smoothly across the turn of every hour.
- A **Mind** panel for the animal you click: its hunger and thirst, what it chose this hour and how sure the model was, the probability it gave to every action ("Why it chose this"), its answers to the extra questions, and its recent memories. The model's confidence is its own estimate, so it is not always the same number as the probability of the action it chose.
- A status line in live mode that shows the pace and the real usage so far, for example `Live: 1.0 hours per second · 214 model requests, 85,310 input tokens`. If the model is slow, the valley's clock slows down and the badge pulses while it waits. Decisions are never skipped or guessed.
- A red dashed line from a wolf that chose to hunt to its target. A legend in the corner of the view explains it, and clicking the legend hides the lines.
- A population chart and an event log. Playback is always one valley hour per second, with no fast-forward. The timeline slider appears once a live run has played to its end, so you cannot skip ahead of it; a finished replay has it from the start.

![The valley at midday, seen from above, with the population chart and event log](docs/images/valley-day.jpg)

![The same valley at night: the sun has set, and the red lines show wolves that are hunting in the dark](docs/images/valley-night.jpg)

| Control | What it does |
|---|---|
| Drag, or Q and E | Turn the view |
| Scroll, pinch, or + and − | Zoom |
| Right-drag, or two fingers | Slide the view |
| `0` or **Reset view** | See the whole valley again |
| Click an animal | Open its Mind panel; **Follow** keeps the camera on it; Esc clears the selection |
| Space | Play or pause. In live mode, pausing freezes the valley: no new decisions are asked while paused |
| ← and → | Step one hour back or forward, once the timeline is available |
| `F` or **Full screen** | Full screen; Esc leaves it |

**The valley does not run without a model.** `run` and `live` accept only Jev (or another server that speaks the same request format), and stop at once if the key is missing or a call fails. There is no offline mode and no hand-written stand-in inside the valley. Earlier versions had two comparison brains, `rules` and `random`; the last commit that has them is `4d545ed`.

**Pausing freezes the valley.** The page tells the server where its playhead is and whether it is paused. While it is paused, or more than three hours ahead of what is on screen, no new hour is started and nothing is asked of Jev; the hour already in flight finishes. Closing the page ends the run after a few seconds and saves what was decided. The valley does not start until a page is open, so no model calls are spent unseen.

The screenshots and the clip above come from one real month-long run on Jev (seed 7), played back in the viewer; there is no bundled demo, so every run you watch is one you make.

## Commands

| You want to | Command | Key needed | Opens a window | Writes to |
|---|---|---|---|---|
| Watch a valley as the model decides it | `python -m valley live --seed 7 --open` | yes | **yes**, in your browser | `runs/live-jev-seed7/` |
| Run a valley without watching it | `python -m valley run --seed 7 --days 2` | yes | **no** | `runs/run-jev-seed7/` |
| Watch a finished run | `python -m valley view runs/<run>/replay.json -o valley.html`, then open `valley.html` | no | **yes**, once you open the file | `valley.html` |
| Compare conditions over several seeds | `python -m valley bench survival` | yes | **no** | `results/survival/` |
| Set the hesitation thresholds | `python -m valley tune --thresholds RUN_DIR [RUN_DIR ...]` | no | no | `results/hesitation/thresholds.json` |
| Run the tests (they run offline, with stand-ins for the model) | `python -m pytest` | no | no | nothing |

`run` and `bench` open nothing: they print progress, write files and finish. To see a valley, use `live`, or use `view` on the `replay.json` that `run` wrote. When `run` finishes it prints the exact `view` command to paste. A run folder holds `replay.json` (the whole run, for the viewer), `metrics.json` (survival, blunders, calibration, judgement and cost) and, if you asked for it, `requests.jsonl` (every request and response). `live` keeps the request log by default, roughly 100 MB for a month: add `--no-log-requests` to skip it.

Options for `run` and `live`:

| Option | Meaning | Default |
|---|---|---|
| `--seed N` | Same seed, same map, same starting animals | 7 |
| `--days N` | Length of the run | 30 |
| `--size WxH` | Map size | 40x26 |
| `--max-creatures N` | Cap on the number of animals | 75 |
| `--questions rich\|basic` | `rich` also asks the score and yes/no questions and the world reacts; `basic` asks only which action to take | rich |
| `--hesitate-below C` | An animal freezes for the hour when the model's confidence is below `C` | off |
| `--batch N`, `--workers N` | Animals per request, and requests in parallel | 16, 4 |
| `--timeout S`, `--retries N` | Seconds per request, and retries after a rate limit, server error or timeout before the run stops | 30, 2 |
| `--log-requests` / `--no-log-requests` | Keep every request and response in `requests.jsonl` | off for `run`, on for `live` |
| `--out DIR`, `--run-id ID` | Where the run is saved, and its name | `runs/<run id>` |
| `--brain jev` | Which model (see below) | jev |
| `--port N`, `--pace S`, `--open`, `--no-wait` | `live` only: the port (8765), the least real seconds per valley hour (1.0), open the browser, start before a page has connected | |

Other servers that speak the same request format can be used with `--brain system-one@BASE_URL#MODEL` (an optional key goes in `SYSTEM_ONE_API_KEY`). For Jev the environment variables are `TYPESAFE_API_KEY`, and optionally `TYPESAFE_BASE_URL` and `TYPESAFE_MODEL`.

**What a run costs.** Every run prints how many requests and tokens it used, and the same numbers are in `metrics.json`. A rich-mode day is about 1 million input tokens. Three month-long runs on 2026-10-25 used 16 to 25 million input tokens each (1,600 to 2,400 requests, a median of about 0.4 s per request), which is under a dollar each at the documented price. The model's replies are free. `bench` prints how many decisions and requests it expects and asks before spending anything.

**Reproduce the benchmark.** `bench` skips runs that are already done and writes everything to `results/`:

```bash
python -m valley bench survival       # Jev on five seeds, 30 days each
python -m valley tune --thresholds runs/run-jev-seed7 -o results/hesitation/thresholds.json
python -m valley bench hesitation     # Jev with hesitation off, and at its own 10th and 25th percentile confidence
```

The default set is small on purpose (about 15 model runs, roughly $10 to $16 at the documented price, an estimate): the first five benchmark seeds. To use all ten, add `--seeds 3,7,11,19,23,42,57,64,88,101` to either command. `matplotlib` draws the charts. The `tune` step needs a smoke run, for example `python -m valley run --seed 7 --days 2 --log-requests`.

**The viewer** is one HTML file, `viewer/index.html`. It loads Three.js, and its sky add-on, from a CDN, so it needs a network connection; everything else in it, the land, water, plants and animals, is drawn in code and nothing is downloaded. It lowers its own resolution when a device cannot keep up. Add `?quality=low` to the page address for a lighter version, or `?resolution=full` to keep the full resolution whatever the speed. `?webgl=off` shows the flat map. You can also open `viewer/index.html` yourself and drop a `replay.json` on it.

## Troubleshooting

| What you see | What to do |
|---|---|
| `error: TYPESAFE_API_KEY is not set. Export it before using the jev brain.` | Export the key in the same terminal you run the command from (step 2 of the quick start). |
| "I ran `run` or `bench` and no window opened" | They are not meant to. Use `live --open`, or `view` on the `replay.json` that `run` wrote. |
| The terminal says `Waiting for a viewer to connect` and nothing happens | The valley starts only when a page is open. Open the address it printed, `http://127.0.0.1:8765` unless you changed `--port`. |
| The browser did not open | Paste the printed address into a browser yourself. `--open` is only a convenience. |
| `Address already in use` | Another program has port 8765. Use `--port 8766`. |
| The run stopped with `error: the run stopped.` followed by a step, an animal and an error | Any failed call stops the run on purpose: no animal is ever given a made-up decision. Check the key and your network, then run it again. Rate limits, server errors and timeouts are retried twice first (`--retries`). Add `--log-requests` to keep the request log for diagnosis. |
| `Nothing was saved.` after a failure | A run that stops on an error saves no replay. In live mode, closing the page or pressing Ctrl-C in the terminal does save what was decided so far. |
| "The 3D view needs WebGL, which is not available here. Showing a flat map instead." | Your browser has WebGL switched off. Turn on hardware acceleration, or use another browser. The flat map shows the same run. |
| The picture is blurry or the camera stutters | The viewer lowers its resolution when it cannot keep up, and never raises it again. Reload the page. Add `?resolution=full` to the address to keep full resolution, or `?quality=low` to draw a lighter scene. |
| The timeline slider is missing in live mode and a note says the timeline unlocks when the run has finished | That is on purpose: a live run cannot be skipped ahead of the model. The slider appears when the run ends. To scrub through a finished run, use `view` on its replay. |
| The page is blank when you are offline | The viewer loads Three.js from a CDN. Connect to a network and reload. |

## The question

Does a typed decision model make sensible decisions, and does it know when it is wrong? Every run uses the same maps, the same seeds and the same starting animals; only the brain changes (Jev, or another model behind `system-one@URL#MODEL`). Three things are measured: whether the valley survives the month; how often a choice is a clear blunder, and whether the model's confidence predicts it; and how well its answers to the extra questions match what really happens (see [More than a choice](#more-than-a-choice)). A second question: does knowing when you are unsure help you survive? With hesitation on, an animal freezes for the hour when the model's confidence is low, and survival is compared with hesitation off.

## Results

Results are produced by `python -m valley bench` and written to `results/<experiment>/` as `summary.md` and three charts. The full benchmark against Jev has not been run yet, so there are no benchmark results to report. To reproduce them, see [Commands](#commands).

### A first look: three month-long runs on Jev

Before the benchmark, three single month-long runs (seeds 7, 11 and 21, rich questions, on 2026-10-25) were done by hand, to see whether the valley holds together with Jev and whether the animals really try to survive. They are one-off runs, read from their replays and request logs with a throwaway script that is not in the repo, so treat them as an early look and not as a measurement. Final populations:

| Seed | Rabbits (24 at the start) | Deer (10) | Wolves (5) | All three alive at the end |
|---|---|---|---|---|
| 7 | 45 | 6 | 2 | yes |
| 11 | 19 | 1 | 0 (the last wolf died on day 27) | no |
| 21 | 25 | 0 (the last deer died on day 19) | 4 | no |

- **The valley is not balanced for Jev yet.** With the old stand-in brains all three species survived on 96 to 97% of unseen seeds; with Jev they survived in one run of three. Rabbits are the buffer (74 to 130 born per run). Deer had 29 births against 52 deaths over the three runs, and all 18 wolf deaths were starvation. The valley has not been retuned for Jev.
- **Wolves chase deer almost as often as they chase rabbits, and rarely catch them:** 40 catches in 426 chases of deer (9%), against 229 in 535 chases of rabbits (43%). A chase costs a wolf three times the energy of resting, and it keeps the deer running: deer spent 21% of their hours fleeing.
- **The animals do try to survive.** Hungry prey with no wolf in sight ate 92% of the time (rabbits) and 96% (deer), and thirsty ones drank 88% and 95%. With a wolf within two tiles, rabbits fled 92% of the time and deer 93%. Hungry wolves with a carcass in sight scavenged 97% of the time, hungry wolves with prey in view hunted 83% of the time and scavenged 14%, and a parched wolf drank every time (18 of 18). The animals that starved died trying: in their last day, wolves spent 88% of their hours hunting or scavenging, and prey spent 62 to 71% eating and 20 to 34% running away. They starved because there was no prey or no food near them.
- **Two weaknesses.** Prey flee from wolves that are still three or more tiles away 66 to 80% of the time, which costs energy. And personality changes effort a great deal: lazy animals rested 53% of the time (rabbits), 41% (deer) and 72% (wolves), restless ones never. Lazy and timid wolves hunted or scavenged in 78% and 74% of their hungry hours, against 84 to 95% for the other personalities, and lazy wolves starved least (0.9 deaths per 1000 wolf-hours against 2.2 to 2.9; only 24 wolves in all, so this is a hint).

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

The client expects each answer to hold `type` and the fields of that type (`choice`, `probabilities` and `confidence` for a choice), plus `usage.input_tokens` and `usage.output_tokens` for the cost figures. This is a real response, captured from a month-long run on 2026-10-25. It answers the rich-mode request for Juniper 6, a young rabbit with two hunting wolves in view, 3 and 5 tiles away, and plants right where it stands. The request carried a `choice` question and the `alert`, `breed` and `attack` questions; the score's `legend` is left out here to save space.

```json
{
  "model": "jev-1.14.0",
  "answers": {
    "action": {
      "type": "choice", "choice": "flee", "confidence": 0.47,
      "probabilities": {"eat": 0.08, "drink": 0.0, "flee": 0.54, "hide": 0.11,
                        "rest": 0.0, "seek_mate": 0.0, "follow_group": 0.27, "explore": 0.0}
    },
    "alert": {
      "type": "score", "score": 3.66, "confidence": 0.69,
      "probabilities": {"0": 0.01, "1": 0.01, "2": 0.03, "3": 0.24, "4": 0.71}
    },
    "breed":  {"type": "noul", "noul": 0.04},
    "attack": {"type": "noul", "noul": 0.78}
  },
  "usage": {"input_tokens": 920, "output_tokens": 126}
}
```

Every request and response of a run can be kept in `requests.jsonl` (`--log-requests`).

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

Things that did not help were tried and dropped: weaker wolves, stronger hiding, digestion time after a kill, and crowding between wolves. The valley was balanced with two hand-written stand-in brains, one that follows simple rules and one that picks at random, so that it could be checked without a model. With them, all three species survived on 96 to 97% of 100 unseen seeds, wolves were never the only species left, and the random brain collapsed every time. Those stand-ins were later removed because the valley does not run without a model, so how Jev does in this valley is what the benchmark is for. A first look with three month-long runs is under [Results](#a-first-look-three-month-long-runs-on-jev), and it is not encouraging for the deer and the wolves. The numbers, the experiments and the limits are in the [ecosystem redesign record](docs/build-spec.md#ecosystem-redesign-record).

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
- The balance of the valley was tuned with offline stand-ins that are no longer in the repo. With Jev, three month-long runs kept all three species alive in only one (see [Results](#results)): deer and wolves can die out, largely because wolves keep chasing deer they rarely catch. The valley has not been retuned for Jev. The game's numbers are scaled for play, not taken from field data, and the sources above are the only research behind them.
- Personality changes how hard an animal tries, so which personality an animal is dealt can change its odds. It was seen on 24 wolves only.
- The Jev client was first written against a fake server built from the documented request and response shape, and has since been checked against the live API: one-day runs and three month-long runs on 2026-10-25, with the model `jev-1.14.0`. A later model version may answer differently.

## How this was built

This project was built with AI assistance (Claude). The code, tests and viewer were written by the assistant from a written build specification, and every choice the specification left open is recorded in [docs/build-spec.md](docs/build-spec.md).

## License

MIT. See [LICENSE](LICENSE).
