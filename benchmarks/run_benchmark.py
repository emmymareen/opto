"""Token-savings benchmark — produces the 'proof' numbers for Opto.

Runs the pipeline over synthetic-but-realistic Copilot-style workloads and prints
a before/after table. Run: ``python benchmarks/run_benchmark.py``.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from opto.config import Config
from opto.pipeline import Pipeline


def _cfg(tmp: Path) -> Config:
    cfg = Config(
        cache_dir=tmp / "cache",
        audit_log_path=tmp / "audit.jsonl",
        telemetry_db=tmp / "tel.sqlite",
        min_tokens_to_compress=50,
    )
    cfg.ensure_dirs()
    return cfg


def workloads() -> dict[str, list[dict]]:
    code_file = (
        "import os\n\n# helper module\n\n"
        + "\n\n".join(
            f"def func_{i}(a, b):\n    # does step {i}\n    result = a + b  \n    return result\n"
            for i in range(40)
        )
    )
    big_json = json.dumps(
        [{"id": i, "name": f"item-{i}", "meta": {"x": i, "y": "v" * 12}} for i in range(400)]
    )
    logs = "\n".join(
        (f"2025-06-27 10:00:{i%60:02d} INFO routine heartbeat {i}" if i % 9 else
         f"2025-06-27 10:00:{i%60:02d} ERROR connection reset {i}")
        for i in range(300)
    )
    return {
        "Code search (open files)": [
            {"role": "system", "content": "You are a coding assistant."},
            {"role": "user", "content": "Where is the bug?\n\n" + code_file},
        ],
        "Tool output (JSON)": [
            {"role": "user", "content": "Summarize results:\n" + big_json},
        ],
        "Log debugging": [
            {"role": "user", "content": "What failed?\n" + logs},
        ],
    }


def main() -> None:
    rows = []
    with tempfile.TemporaryDirectory() as td:
        pipe = Pipeline(config=_cfg(Path(td)))
        for name, messages in workloads().items():
            out = pipe.run([dict(m) for m in messages])
            r = out.report
            rows.append((name, r.original_tokens, r.compressed_tokens, r.saved_fraction))

    w = max(len(n) for n, *_ in rows)
    print(f"\n{'Workload'.ljust(w)} | {'Before':>8} | {'After':>8} | {'Saved':>6}")
    print("-" * (w + 30))
    for name, before, after, frac in rows:
        print(f"{name.ljust(w)} | {before:>8,} | {after:>8,} | {frac*100:>5.0f}%")
    print()


if __name__ == "__main__":
    main()
