"""Decision makers and the factory that builds them from a short name."""

import random

from valley.brains.base import Brain
from valley.world import derive_seed

BASELINE_BRAINS = ("rules", "random")
MODEL_BRAINS = ("jev", "laya")
BRAIN_NAMES = MODEL_BRAINS + BASELINE_BRAINS


def make_brain(spec: str, seed: int = 0, **options) -> Brain:
    """Build a brain from `jev`, `laya`, `rules`, `random`, or `system-one@{base_url}#{model}`.

    `seed` only matters for `rules` and `random`, which draw from their own `brain_rng`.
    Model brains read their configuration from the environment; `options` are the settings of 7.3.
    """
    if spec in BASELINE_BRAINS:
        rng = random.Random(derive_seed(seed, "brain", 0))
        if spec == "rules":
            from valley.brains.rules import RulesBrain
            return RulesBrain(rng)
        from valley.brains.random_brain import RandomBrain
        return RandomBrain(rng)
    if spec in MODEL_BRAINS or spec.startswith("system-one@"):
        from valley.brains.system_one import make_system_one_brain
        return make_system_one_brain(spec, **options)
    raise ValueError(f"unknown brain {spec!r}; use one of {', '.join(BRAIN_NAMES)} or system-one@URL#MODEL")
