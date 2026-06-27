<div align="center">

# Opto

**Local, reversible context-compression proxy for GitHub Copilot, Claude Code, and Codex.**

Fewer tokens. The same answers. With a quality guarantee.

</div>

---

Opto sits between your editor and the model. Developers keep working normally in
the Copilot CLI, Claude Code, or Codex; in the background Opto compresses the
context of every request — open files, selections, tool output, history — before
it reaches the model, then streams the answer straight back. You send a fraction
of the tokens and get the same results, with a safety gate that refuses to
compress when it would hurt answer quality.

```
 Editor / CLI  ──►  Opto (localhost, no API key)  ──►  GitHub Copilot / Anthropic
   prompts · files · tool output       compressed prompt        valid licensed request
```

## Contents

- [Why Opto](#why-opto)
- [How it works](#how-it-works)
- [Install](#install)
- [Quick start](#quick-start)
- [Enterprise Copilot — no API key needed](#enterprise-copilot--no-api-key-needed)
- [Integrating each tool](#integrating-each-tool)
- [The transparency dashboard](#the-transparency-dashboard)
- [Configuration](#configuration)
- [Use as a library](#use-as-a-library)
- [Measured savings](#measured-savings)
- [Development](#development)
- [FAQ](#faq)
- [License](#license)

## Why Opto

- **Quality guarantee.** A content-aware gate estimates fidelity risk for every
  request and *backs off* — sending the request uncompressed — when compression
  looks risky. You never silently get a worse answer. An optional holdout leaves
  a slice of traffic uncompressed so savings can be *measured*, not just claimed.
- **Smarter relevance.** Context is scored against the current turn; low-value
  spans are dropped before compression instead of squeezing everything blindly.
- **Transparency.** A local dashboard shows tokens saved, what was trimmed, and
  every gate decision. Nothing is hidden.
- **Reversible.** Originals are cached locally and retrievable on demand (CCR),
  so compression is never lossy in a way you can't undo.
- **No API keys for Copilot.** Opto performs the GitHub → Copilot token exchange
  itself. Your Copilot licence is the only credential needed.
- **Local & enterprise-ready.** Runs entirely on your machine. Content-redacted
  audit log by default. Fully environment-configurable. Handles GitHub Business,
  Enterprise Cloud, and Enterprise Server.

## How it works

Every request flows through one pipeline:

1. **Auth bridge** *(Copilot, optional)* — exchange your GitHub OAuth token for a
   short-lived Copilot bearer token and resolve the licence-correct endpoint
   (Individual / Business / Enterprise). No API key required.
2. **Segment** — split each message into typed spans (code / diff / JSON / log /
   prose), so embedded code or JSON inside a prose message is compressed too.
3. **Score relevance** — rank spans against the latest user turn; drop the
   low-value ones (kept reversibly in the cache).
4. **Compress** — each span goes to a specialised compressor: JSON crusher,
   code/diff trimmer, log deduper + severity filter, prose cleaner.
5. **Quality gate** — estimate content-aware fidelity risk; if it's too high,
   send the request uncompressed instead.
6. **Forward & stream** — attach auth/identity headers, send to the resolved
   upstream, stream the response back unchanged.
7. **Telemetry** — record before/after tokens and every decision for the dashboard.

## Install

Requires **Python 3.10+**.

```bash
git clone https://github.com/emmymareen/opto.git
cd opto
pip install -e .            # add ".[dev]" for the test/lint tools
```

This puts the `opto` command on your PATH.

## Quick start

```bash
# 1 — start the proxy (listens on http://127.0.0.1:8799)
opto proxy

# 2 — point a tool at it (prints the exact env vars)
opto wrap copilot          # or: claude / codex

# 3 — watch the savings
opto stats                 # cumulative totals in the terminal
opto dashboard             # live dashboard at http://127.0.0.1:8800
```

That's the whole loop: start Opto, redirect your tool, work normally.

## Enterprise Copilot — no API key needed

Enterprise Copilot has **no API key**. Your editor signs in with your Copilot
licence and receives a GitHub OAuth token (`ghu_…`); that token is exchanged for
a short-lived bearer token used to call the Copilot API. Opto does this exchange
for you and routes to the correct endpoint for your plan.

```bash
export OPTO_MANAGE_COPILOT_AUTH=1     # let Opto handle the token exchange
opto copilot-auth                     # verify — prints the resolved endpoint
opto proxy                            # compression + auth, one process
```

`opto copilot-auth` is a health check: it discovers your OAuth token (from the
Copilot CLI/editor login, or `OPTO_COPILOT_GITHUB_TOKEN`), performs the exchange,
and reports the endpoint it resolved (e.g. `api.business.githubcopilot.com`). If
it succeeds, your licence works through Opto with zero keys.

**GitHub Enterprise Server (custom domain):**

```bash
export OPTO_GITHUB_HOST=ghe.your-company.com
```

Opto then uses the `…/api/v3/copilot_internal/v2/token` exchange path and the
endpoint advertised for your tenant. Business/Enterprise client-identity headers
(`Editor-Version`, `Editor-Plugin-Version`, `Copilot-Integration-Id`, matching
`User-Agent`) are attached automatically and are overridable via `OPTO_COPILOT_*`
environment variables.

## Integrating each tool

Opto is an OpenAI/Anthropic-compatible proxy, so every tool integrates the same
way: point its endpoint at Opto. `opto wrap <tool>` prints the exact lines.

| Tool | How | Notes |
|------|-----|-------|
| **Copilot CLI** | `export OPENAI_BASE_URL=http://127.0.0.1:8799` | Cleanest path; combine with the auth bridge above. |
| **Codex** | `export OPENAI_BASE_URL=http://127.0.0.1:8799` | OpenAI-format; works out of the box. |
| **Claude Code** | `export ANTHROPIC_BASE_URL=http://127.0.0.1:8799` | Anthropic-format upstream (set `OPTO_UPSTREAM_BASE_URL`). |
| **Any OpenAI client** | base URL → `http://127.0.0.1:8799` | LangChain, LiteLLM, SDKs, etc. |

> **VS Code Copilot extension:** the stock extension pins to GitHub's host and
> resists endpoint overrides. The CLI/proxy path above is the supported route
> today; a VS Code chat-provider extension is on the roadmap.

## The transparency dashboard

```bash
opto dashboard             # http://127.0.0.1:8800
```

Shows cumulative tokens saved, savings by content type, per-request token
accounting, and which requests were compressed, backed off (quality), or held
out (control). Raw prompt content is never displayed or logged when
`OPTO_REDACT_CONTENT_IN_LOGS` is on (the default).

A convenience launcher is included: `./run_dashboard.sh`.

## Configuration

All settings are environment variables prefixed `OPTO_` (or a `.env` file — see
`.env.example`). The most useful:

| Variable | Default | Meaning |
|----------|---------|---------|
| `OPTO_PORT` | `8799` | Proxy port |
| `OPTO_UPSTREAM_BASE_URL` | `https://api.githubcopilot.com` | Where Opto forwards |
| `OPTO_ENABLED` | `true` | Master compression switch |
| `OPTO_MIN_TOKENS_TO_COMPRESS` | `400` | Skip tiny requests |
| `OPTO_TARGET_RATIO` | `0.45` | Keep ~this fraction of tokens |
| `OPTO_RELEVANCE_DROP_THRESHOLD` | `0.12` | Drop spans below this relevance |
| `OPTO_QUALITY_GATE_ENABLED` | `true` | Enable the quality guarantee |
| `OPTO_QUALITY_RISK_THRESHOLD` | `0.7` | Back off above this risk |
| `OPTO_HOLDOUT_FRACTION` | `0.0` | Uncompressed control group |
| `OPTO_MANAGE_COPILOT_AUTH` | `false` | Opto does the Copilot token exchange |
| `OPTO_GITHUB_HOST` | `github.com` | Your GHE domain, if applicable |
| `OPTO_REDACT_CONTENT_IN_LOGS` | `true` | Never log raw prompt content |

## Use as a library

```python
from opto import compress

messages = [{"role": "user", "content": "…big context…"}]
out = compress(messages)

print(out.report.saved_fraction)   # e.g. 0.62
compressed_messages = out.messages
```

## Measured savings

From `benchmarks/run_benchmark.py` on representative workloads:

| Workload                  | Before | After | Saved |
|---------------------------|-------:|------:|------:|
| Code search (open files)  |    802 |   580 |  28%  |
| Tool output (JSON)        |  7,322 |    71 |  99%  |
| Log debugging             |  3,500 |   409 |  88%  |

Numbers come from synthetic-but-realistic inputs; run the benchmark yourself, or
enable a holdout to measure savings on your real traffic.

## Development

```bash
pip install -e ".[dev]"
pytest -q                       # unit tests
ruff check opto tests           # lint
python benchmarks/run_benchmark.py
```

Project layout:

```
opto/
  pipeline.py        orchestrates the stages
  router.py          segment + classify content
  relevance.py       score + drop low-value spans
  compressors/       json_crusher · code · text(+log)
  quality.py         content-aware quality gate + holdout
  cache.py           reversible original store (CCR)
  copilot_auth.py    GitHub -> Copilot token exchange
  proxy/server.py    OpenAI/Anthropic-compatible proxy
  dashboard/server.py transparency dashboard
  telemetry.py       SQLite stats + redacted audit log
  cli.py             proxy · wrap · dashboard · stats · copilot-auth
```

## FAQ

**Does Opto see my code?** It processes requests locally to compress them.
Nothing leaves your machine except the (compressed) request going to the same
upstream your tool would have called anyway. Logs are content-redacted by default.

**Will it make answers worse?** That's what the quality gate exists to prevent —
risky compressions are skipped. Run with a holdout to verify on your own traffic.

**Do I need an OpenAI or Anthropic key for Copilot?** No. Your Copilot licence is
the credential; Opto handles the token exchange.

**Is anything lost?** Originals are cached and reversible within the configured
TTL, so dropped/compressed context can be retrieved.

## License

Apache-2.0 — see [LICENSE](LICENSE).
