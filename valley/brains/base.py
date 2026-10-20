"""The brain interface: what a brain is asked and what it answers."""

from dataclasses import dataclass


@dataclass
class DecisionRequest:
    creature_id: str
    view: dict  # sent to the model
    options: dict  # action key -> description, in the species' action order
    signals: dict  # never sent to a model


class DecisionError(RuntimeError):
    """A model could not give a valid decision. The run stops: nothing stands in for the model's answer."""


@dataclass
class Decision:
    choice: str
    probabilities: dict  # action key -> probability
    confidence: float
    source: str  # "model" or "baseline"
    latency_ms: float | None = None


class Brain:
    name: str = "brain"

    def decide(self, requests: list[DecisionRequest], step: int = 0) -> list[Decision]:
        """Return one decision per request, in the same order. `step` is only used for logging."""
        raise NotImplementedError

    def summary(self) -> dict:
        """Totals for the cost and speed metrics."""
        return {}

    def close(self) -> None:
        """Release resources such as open log files."""
