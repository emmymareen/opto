"""Eval harness: run tasks with original vs compressed context and compare.

ModelClient is an abstract seam — implement ``complete(messages) -> str`` for
whatever model you can reach (OpenAI/Anthropic API for testing, or a local
open-source model). The harness itself is model-agnostic and runs offline; only
the actual scoring requires a live model.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from opto.config import Config, get_config
from opto.pipeline import Pipeline
from opto.evals.tasks import Task


class ModelClient(ABC):
    """Implement this for the model you want to evaluate against."""

    @abstractmethod
    def complete(self, messages: list[dict]) -> str:  # pragma: no cover - user-supplied
        ...


@dataclass
class EvalResult:
    n: int = 0
    baseline_correct: int = 0
    opto_correct: int = 0
    original_tokens: int = 0
    compressed_tokens: int = 0
    per_task: list[dict] = field(default_factory=list)

    @property
    def baseline_accuracy(self) -> float:
        return self.baseline_correct / self.n if self.n else 0.0

    @property
    def opto_accuracy(self) -> float:
        return self.opto_correct / self.n if self.n else 0.0

    @property
    def accuracy_delta(self) -> float:
        return self.opto_accuracy - self.baseline_accuracy

    @property
    def saved_fraction(self) -> float:
        if not self.original_tokens:
            return 0.0
        return 1.0 - (self.compressed_tokens / self.original_tokens)


def _is_correct(answer: str, expected: str) -> bool:
    return expected.strip().lower() in (answer or "").strip().lower()


class EvalHarness:
    def __init__(self, config: Config | None = None):
        self.config = config or get_config()
        self.pipeline = Pipeline(config=self.config)

    def run(self, tasks: list[Task], model: ModelClient) -> EvalResult:
        res = EvalResult()
        for task in tasks:
            base_msgs = task.messages()
            out = self.pipeline.run([dict(m) for m in base_msgs])
            comp_msgs = out.messages

            base_ans = model.complete(base_msgs)
            comp_ans = model.complete(comp_msgs)

            base_ok = _is_correct(base_ans, task.answer)
            comp_ok = _is_correct(comp_ans, task.answer)

            res.n += 1
            res.baseline_correct += int(base_ok)
            res.opto_correct += int(comp_ok)
            res.original_tokens += out.report.original_tokens
            res.compressed_tokens += out.report.compressed_tokens
            res.per_task.append({
                "id": task.id,
                "category": task.category,
                "baseline_ok": base_ok,
                "opto_ok": comp_ok,
                "saved_fraction": round(out.report.saved_fraction, 4),
            })
        return res

    def dry_run(self, tasks: list[Task]) -> EvalResult:
        """Run compression only (no model) to report token savings — lets you
        validate the harness and see savings before wiring up a model."""
        res = EvalResult()
        for task in tasks:
            out = self.pipeline.run([dict(m) for m in task.messages()])
            res.n += 1
            res.original_tokens += out.report.original_tokens
            res.compressed_tokens += out.report.compressed_tokens
            res.per_task.append({
                "id": task.id,
                "category": task.category,
                "saved_fraction": round(out.report.saved_fraction, 4),
            })
        return res
