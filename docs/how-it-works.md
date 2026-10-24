# How it works

This page shows a real request and response, the extra questions the rich mode asks, and the design decisions behind the valley. For how to run it, see the [README](../README.md#quick-start) and [running.md](running.md).

## The model decides what, the code decides how

**The model decides what. The code decides how.** The model only ever returns one action key: `eat`, `drink`, `flee`, `hide`, `rest`, `seek_mate`, `follow_group` or `explore` for rabbits and deer, and `hunt`, `scavenge`, `drink`, `hide`, `rest`, `seek_mate`, `follow_group` or `explore` for wolves. Paths, catches, births and deaths are ordinary deterministic code, so a run is fair and repeatable.

Each hour, every animal gets a plain-language view of what it can see and feel, and one `Choice` question, plus, in the rich mode, the extra questions described [below](#more-than-a-choice). This is a real request, written by the client from a real view of a simulated valley:

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

## Design decisions

- **Separate random streams.** The map and plant regrowth, the events (catches, litters, names, action order) each have their own stream, all derived from the seed. A brain never touches the world's or the events' stream, and plant regrowth draws the same dice whatever the plants look like, so every brain faces the same valley.
- **Hourly steps, with waiting.** Every animal decides once per hour, from one snapshot of the world, and the loop waits for all decisions before anything moves. Slow decisions make a run take longer; they never change what happens.
- **Batching, and stopping on errors.** Many creatures share a request to keep the cost down. Any error that survives the retries stops the run, because a made-up decision would not be the model's.
- **Blunder rules.** Six simple rules mark a choice as clearly bad given what the animal could see, for example ignoring a wolf two tiles away. They are counted while the run happens, because they need information a replay does not store, and confidence is binned to show whether the model is surer when it is right.
- **No offline stand-in.** The valley cannot run without a model: there is no hand-written brain in it, so nothing can be mistaken for Jev. The tests use stand-ins, and they live only under `tests/`.
- **Everything is traceable.** Each benchmark number comes from `python -m valley bench` and a file under `results/`, and the raw requests and responses are kept.
