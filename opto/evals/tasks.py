"""Evaluation tasks.

A Task is a question plus the context needed to answer it and the expected answer.
A small bundled sample set ships with Opto so the harness runs end-to-end offline
(structurally); for real numbers, load standard datasets (GSM8K, SQuAD v2,
TruthfulQA, BFCL) via the ``datasets`` library and map them into Task objects.
"""

from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass
class Task:
    id: str
    category: str
    question: str
    context: str  # the bulky context Opto will compress
    answer: str  # expected answer (substring match by default)

    def messages(self) -> list[dict]:
        return [
            {"role": "system", "content": "Answer using only the provided context. Be concise."},
            {"role": "user", "content": f"{self.context}\n\nQuestion: {self.question}"},
        ]


def _sample_json_context(n: int = 200) -> str:
    rows = [{"id": i, "user": f"user{i}", "plan": "free" if i % 3 else "pro"} for i in range(n)]
    rows[57]["plan"] = "enterprise"
    return "Tool output:\n" + json.dumps(rows)


def load_sample_tasks() -> list[Task]:
    """A tiny, self-contained sample set for smoke-testing the harness offline."""
    return [
        Task(
            id="json-lookup-1",
            category="tool-output",
            question="Which user has the enterprise plan? Give the user id.",
            context=_sample_json_context(),
            answer="57",
        ),
        Task(
            id="qa-1",
            category="factual",
            question="What port does the service listen on?",
            context=(
                "The deployment guide covers many topics. " * 20
                + "Importantly, the service listens on port 8799 by default. "
                + "Other sections discuss logging and metrics at length. " * 20
            ),
            answer="8799",
        ),
        Task(
            id="log-1",
            category="logs",
            question="What error occurred?",
            context="\n".join(
                (f"2025-06-27 10:00:{i%60:02d} INFO heartbeat {i}" if i != 142 else
                 "2025-06-27 10:02:22 ERROR database connection refused")
                for i in range(300)
            ),
            answer="connection refused",
        ),
    ]
