"""Accuracy evaluation harness.

The point of Opto is "fewer tokens, SAME answers." This harness proves the second
half: it runs each task through a model twice — once with the original context,
once with Opto-compressed context — and compares answers. The output is the
quality delta (did accuracy hold?) alongside the token savings.

Running it needs a live model (see ModelClient). Building/wiring it does not.
"""

from opto.evals.harness import EvalHarness, ModelClient, EvalResult
from opto.evals.tasks import load_sample_tasks, Task

__all__ = ["EvalHarness", "ModelClient", "EvalResult", "load_sample_tasks", "Task"]
