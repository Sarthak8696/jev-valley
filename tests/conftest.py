"""Test setup: lets the benchmark and live code build the tests' stand-in brains by name.

The valley itself cannot run without a model, so `valley.bench` only knows Jev and `system-one@URL#MODEL`. The tests need
something deterministic that needs no key, so while a test runs `bench.make_brain` also builds the hand-written
stand-ins called "rules" and "random" (tests/offline.py), and treats them as offline brains that cost nothing.
"""

import pytest

from tests.offline import OFFLINE_NAMES, make_offline_brain


@pytest.fixture(autouse=True)
def stand_in_brains(monkeypatch):
    from valley import bench
    real_make, real_is_model = bench.make_brain, bench.is_model_brain

    def make(spec, seed=0, **options):
        return make_offline_brain(spec, seed) if spec in OFFLINE_NAMES else real_make(spec, seed, **options)

    monkeypatch.setattr(bench, "make_brain", make)
    monkeypatch.setattr(bench, "is_model_brain", lambda spec: spec not in OFFLINE_NAMES and real_is_model(spec))
