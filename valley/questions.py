"""The extra questions of the rich mode: what a brain is asked besides the action, and how the world reacts.

In the choice-only mode a brain answers one `choice` question per animal per hour. In the rich mode the same
request also carries `score` and `noul` questions about the same animal:

- `alert` (score, prey): how watchful to be. A watchful animal feeds less and is harder to catch.
- `breed` (noul, everyone): is now a good time to have young. Both partners must say yes.
- `attack` (noul, prey): will a wolf try to catch me this hour. Only scored, it changes nothing.
- `weak:<id>` (score, wolves): how weak a visible prey animal looks. The wolf goes for the weakest, nearest one.
- `effort` (score, wolves): how hard to chase. More effort catches more and tires the wolf more.

A score of NEUTRAL changes nothing, so a brain that always answers 2 plays the choice-only game. The sizes of the
reactions are in valley/actions.py.
"""

from valley.brains.base import Question

NEUTRAL = 2.0  # the middle of a five-level score
MODES = ("basic", "rich")

ALERT_LEVELS = [
    "Head down, grazing without a care",
    "Relaxed, glancing up now and then",
    "Watchful, ears up",
    "Alert, ready to run",
    "On guard, about to bolt",
]
WEAK_LEVELS = [
    "Looks strong and healthy",
    "A little tired",
    "Visibly worn",
    "Weak",
    "Barely standing",
]
EFFORT_LEVELS = [
    "Barely trying, a lazy trot",
    "A steady pace",
    "A real chase",
    "A hard run",
    "An all-out sprint",
]

ALERT_TEXT = ("How alert should this animal be for the coming hour? A more alert animal spots danger sooner and is "
              "harder to catch, but it feeds less.")
BREED_TEXT = ("Is now a good time for this animal to have young? Having young costs a lot of energy, so it is wise "
              "only when the animal is well fed and safe.")
ATTACK_TEXT = "Will a wolf try to catch this animal during the coming hour?"
EFFORT_TEXT = ("How hard should this wolf chase its prey in the coming hour? A harder chase is more likely to catch "
               "prey, but it tires the wolf more.")
WEAK_TEXT = ("How weak does {name} the {species} look to this wolf? Judge from what a wolf can see: its age, "
             "whether it is alone, how worn it looks, and what it is doing.")

BREED_CRITERIA = {"true": "Yes, it is safe and well fed enough to have young",
                  "false": "No, it is hungry, thirsty or in danger"}
ATTACK_CRITERIA = {"true": "Yes, a wolf is likely to go after this animal", "false": "No, it is unlikely to be attacked"}


def prey_questions() -> list[Question]:
    return [
        Question("alert", "score", ALERT_TEXT, list(ALERT_LEVELS)),
        Question("breed", "noul", BREED_TEXT, dict(BREED_CRITERIA)),
        Question("attack", "noul", ATTACK_TEXT, dict(ATTACK_CRITERIA)),
    ]


def wolf_questions(prey: list) -> list[Question]:
    """One weakness score for each of up to three visible prey animals, then the chase effort and breeding."""
    questions = [Question(f"weak:{p.id}", "score", WEAK_TEXT.format(name=p.name, species=p.species), list(WEAK_LEVELS))
                 for p in prey[:3]]
    questions.append(Question("effort", "score", EFFORT_TEXT, list(EFFORT_LEVELS)))
    questions.append(Question("breed", "noul", BREED_TEXT, dict(BREED_CRITERIA)))
    return questions
