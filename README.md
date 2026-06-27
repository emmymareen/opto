# Opto

**Local, reversible context-compression proxy for GitHub Copilot.**
Fewer tokens, the same answers — with a quality guarantee.

Opto sits between your editor and GitHub Copilot. Developers keep working
normally in VS Code Copilot Chat or the Copilot CLI; in the background Opto
compresses the context of every request (open files, selections, tool output,
history) before it reaches the model, then streams the answer straight back.

```
 VS Code / Copilot CLI  ──►  Opto (localhost)  ──►  GitHub Copilot
        prompts · files · tool output        compressed prompt
```

## Why Opto

- **Quality guarantee** — a content-aware gate estimates fidelity risk per request
  and *backs off* (sends the request uncompressed) when compression looks risky,
  so you never get degraded answers. An optional holdout leaves a fraction of
  traffic uncompressed to *measure* real savings, not just estimate them.
- **Smarter relevance** — chunks are scored against the current turn; low-value
  context is dropped before compression instead of squeezing everything blindly.
- **Transparency** — a local dashboard shows tokens saved, what was trimmed, and
  every gate decision. Nothing is hidden.
- **Reversible** — originals are cached locally and retrievable on demand (CCR).
- **Local & enterprise-ready** — runs entirely on your machine; content-redacted
  audit log by default; fully environment-configurable.

## Measured savings

From `benchmarks/run_benchmark.py` on representative Copilot workloads:

| Workload                  | Before | After | Saved |
|---------------------------|-------:|------:|------:|
| Code search (open files)  |    802 |   580 |  28%  |
| Tool output (JSON)        |  7,322 |    71 |  99%  |
| Log debugging             |  3,500 |   409 |  88%  |

## Install

```bash
pip install -e ".[dev]"     # from a checkout
```

Requires Python 3.10+.

## Use

```bash
opto proxy                  # start the compression proxy (default :8799)
opto wrap copilot           # print how to route Copilot through Opto
opto dashboard              # transparency dashboard (default :8800)
opto stats                  # cumulative savings in the terminal
```

Point Copilot at Opto:

```bash
export OPENAI_BASE_URL=http://127.0.0.1:8799
# Copilot CLI: just run it as usual.
# VS Code: set the Copilot endpoint/proxy override to the same URL.
```

Use it as a library too:

```python
from opto import compress

out = compress(messages)          # messages = [{"role": ..., "content": ...}]
print(out.report.saved_fraction)  # e.g. 0.62
```

## How it works

Each request flows through a pipeline:

1. **Segment** every message into typed spans (code / diff / JSON / log / prose),
   so embedded code or JSON inside a prose message is compressed too.
2. **Score relevance** of each span against the latest user turn; drop the
   low-value ones (kept reversibly).
3. **Compress** each span with a specialised compressor — JSON crusher,
   AST-ish code trimmer, log deduper/severity filter, prose cleaner.
4. **Quality gate** estimates content-aware fidelity risk; if it's too high, the
   request is sent through uncompressed.
5. **Forward & stream** to the upstream provider; the developer sees no change.
6. **Telemetry** records before/after tokens and decisions for the dashboard.

## Configuration

All settings are environment variables prefixed `OPTO_` (or a `.env` file). Key ones:

| Variable | Default | Meaning |
|----------|---------|---------|
| `OPTO_PORT` | `8799` | Proxy port |
| `OPTO_UPSTREAM_BASE_URL` | `https://api.githubcopilot.com` | Where Opto forwards |
| `OPTO_TARGET_RATIO` | `0.45` | Keep ~this fraction of tokens |
| `OPTO_QUALITY_RISK_THRESHOLD` | `0.7` | Back off above this risk |
| `OPTO_HOLDOUT_FRACTION` | `0.0` | Uncompressed control group |
| `OPTO_REDACT_CONTENT_IN_LOGS` | `true` | Never log raw prompt content |

## Develop

```bash
pip install -e ".[dev]"
pytest -q
python benchmarks/run_benchmark.py
```

## License

Apache-2.0.
