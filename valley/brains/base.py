"""The brain interface: what a brain is asked and what it answers."""

from dataclasses import dataclass, field


@dataclass
class Question:
    """An extra question asked in the same request as the action. Its answer is a number, not an action."""
    key: str  # "alert", "breed", "attack", "effort" or "weak:<creature id>"
    type: str  # "score" or "noul"
    instructions: str
    criteria: object  # a score: the ordered level descriptions. A noul: {"true": ..., "false": ...}

    @property
    def top(self) -> float:
        """The highest value a score can take."""
        return float(len(self.criteria) - 1) if self.type == "score" else 1.0


@dataclass
class DecisionRequest:
    creature_id: str
    view: dict  # sent to the model
    options: dict  # action key -> description, in the species' action order
    signals: dict  # never sent to a model
    questions: list = field(default_factory=list)  # extra Questions, empty in the choice-only mode
    truth: dict = field(default_factory=dict)  # what is really the case, for scoring the answers; never sent


class DecisionError(RuntimeError):
    """A model could not give a valid decision. The run stops: nothing stands in for the model's answer."""


@dataclass
class Decision:
    choice: str
    probabilities: dict  # action key -> probability
    confidence: float
    source: str  # "model" or "baseline"
    latency_ms: float | None = None
    extras: dict = field(default_factory=dict)  # question key -> a score (0 to its top) or a noul (probability of yes)


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
