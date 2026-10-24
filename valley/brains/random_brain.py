"""The floor: picks uniformly at random."""

import random

from valley.brains.base import Brain, Decision, DecisionRequest


class RandomBrain(Brain):
    name = "random"

    def __init__(self, rng: random.Random):
        self.rng = rng  # brain_rng
        self.decisions = 0

    def decide(self, requests: list[DecisionRequest], step: int = 0) -> list[Decision]:
        out = []
        for request in requests:
            keys = list(request.options)
            chance = 1.0 / len(keys)
            choice = self.rng.choice(keys)
            extras = {q.key: round(self.rng.uniform(0.0, q.top), 3) for q in request.questions}  # a yes/no is a number from 0 to 1 too
            out.append(Decision(choice, {key: chance for key in keys}, chance, "baseline", extras=extras))
        self.decisions += len(out)
        return out

    def summary(self) -> dict:
        return {"decisions": self.decisions, "requests": 0, "retries": 0,
                "input_tokens": 0, "output_tokens": 0, "latencies_ms": []}
