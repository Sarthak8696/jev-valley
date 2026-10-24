# Running Jev Valley

How to run it, every option, what it costs and what to do when something goes wrong. The short version is the [quick start in the README](../README.md#quick-start).

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

## Options

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

## What a run costs

Every run prints how many requests and tokens it used, and the same numbers are in `metrics.json`. A rich-mode day is about 1 million input tokens. Three month-long runs on 2026-10-25 used 16 to 25 million input tokens each (1,600 to 2,400 requests, a median of about 0.4 s per request), which is under a dollar each at the documented price. The model's replies are free. `bench` prints how many decisions and requests it expects and asks before spending anything.

## Reproduce the benchmark

`bench` skips runs that are already done and writes everything to `results/`:

```bash
python -m valley bench survival       # Jev on five seeds, 30 days each
python -m valley tune --thresholds runs/run-jev-seed7 -o results/hesitation/thresholds.json
python -m valley bench hesitation     # Jev with hesitation off, and at its own 10th and 25th percentile confidence
```

The default set is small on purpose (about 15 model runs, roughly $10 to $16 at the documented price, an estimate): the first five benchmark seeds. To use all ten, add `--seeds 3,7,11,19,23,42,57,64,88,101` to either command. `matplotlib` draws the charts. The `tune` step needs a smoke run, for example `python -m valley run --seed 7 --days 2 --log-requests`.

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

The viewer's own options (`?quality=low`, `?resolution=full`, `?webgl=off`) are described in the [viewer guide](viewer.md#page-options).
