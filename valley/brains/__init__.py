"""Decision makers and the factory that builds them from a short name.

The valley runs only on a model: Jev, or any server that speaks the same request format. The hand-written `rules` and
`random` baselines that earlier versions had were removed (see the Decisions log of docs/build-spec.md).
"""

from valley.brains.base import Brain

MODEL_BRAINS = ("jev",)


def make_brain(spec: str, seed: int = 0, **options) -> Brain:
    """Build a brain from `jev` or `system-one@{base_url}#{model}`. Model brains read their configuration from the
    environment; `options` are the settings of 7.3. `seed` is not used: a model has no random stream of ours."""
    if spec in MODEL_BRAINS or spec.startswith("system-one@"):
        from valley.brains.system_one import make_system_one_brain
        return make_system_one_brain(spec, **options)
    raise ValueError(f"unknown brain {spec!r}; the valley runs only on a model: use jev or system-one@URL#MODEL")
