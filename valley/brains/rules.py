"""A hand-written baseline that never calls a model.

It scores each action from the signals, turns the scores into probabilities with
a softmax, and samples a choice with `brain_rng`. It is a fair reference, not a
strawman: do not weaken it to make a model look better.
"""

import math
import random

from valley.brains.base import Brain, Decision, DecisionRequest

TEMPERATURE = 0.35

# Scores for actions that make no sense in the current situation. Section 7.4 gives these for
# `hunt`, `scavenge` and `seek_mate`; the value for `flee` with no wolf in sight is the builder's choice.
FLEE_WITHOUT_THREAT = -1.0


def score_actions(signals: dict, actions) -> dict:
    """The raw score of each available action, from the signals alone."""
    hunger = 1.0 - signals["energy"]
    thirst = 1.0 - signals["hydration"]
    personality = signals["personality"]
    threat = signals["threat_dist"]
    forest = signals["forest_dist"]
    scores = {}
    for action in actions:
        if action == "flee":
            if threat is None:
                score = FLEE_WITHOUT_THREAT
            else:
                score = 1.6 if threat <= 2 else 0.9 if threat <= 4 else 0.3
                if personality == "bold":
                    score *= 0.6
                elif personality == "timid":
                    score *= 1.3
        elif action == "hide":
            if threat is not None:
                score = 0.8 if forest is not None and forest <= 2 else 0.1
            else:
                score = 0.05
            if personality == "cautious":
                score += 0.3
        elif action == "drink":
            score = thirst * (1.6 if signals["water_known"] else 0.6)
        elif action == "eat":
            score = (hunger - 0.15) * 1.8 + (0.3 if signals["food_here"] else 0.0)
        elif action == "hunt":
            score = (hunger - 0.3) * 2.5 + (0.4 if signals["prey_dist"] is not None else -0.6)
        elif action == "scavenge":
            score = hunger * 1.2 + (0.9 if signals["carcass_dist"] is not None else -1.0)
        elif action == "seek_mate":
            score = 0.9 if signals["can_mate"] and signals["mate_dist"] is not None else -0.8
        elif action == "rest":
            score = 0.15 + (0.5 if personality == "lazy" else 0.0)
        elif action == "explore":
            score = 0.25 + (0.4 if personality in ("curious", "restless") else 0.0)
        elif action == "follow_group":
            group = signals["group_dist"]
            score = 0.4 if group is not None and group > 2 else 0.0
            if personality == "loyal" and group is not None:
                score += 0.3
        else:
            raise ValueError(f"no score defined for action {action!r}")
        scores[action] = score
    return scores


def softmax(scores: dict, temperature: float = TEMPERATURE) -> dict:
    top = max(scores.values())
    weights = {a: math.exp((s - top) / temperature) for a, s in scores.items()}
    total = sum(weights.values())
    return {a: w / total for a, w in weights.items()}


class RulesBrain(Brain):
    name = "rules"

    def __init__(self, rng: random.Random):
        self.rng = rng  # brain_rng
        self.decisions = 0

    def decide(self, requests: list[DecisionRequest], step: int = 0) -> list[Decision]:
        out = []
        for request in requests:
            probabilities = softmax(score_actions(request.signals, request.options))
            roll = self.rng.random()
            cumulative, choice = 0.0, None
            for action, probability in probabilities.items():
                cumulative += probability
                choice = action
                if roll < cumulative:
                    break
            out.append(Decision(choice, probabilities, probabilities[choice], "baseline"))
        self.decisions += len(out)
        return out

    def summary(self) -> dict:
        return {"decisions": self.decisions, "requests": 0, "fallbacks": 0, "retries": 0,
                "input_tokens": 0, "output_tokens": 0, "latencies_ms": []}
