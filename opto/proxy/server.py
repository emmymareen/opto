"""OpenAI-compatible compression proxy.

Drop-in: point any OpenAI/Copilot-compatible client at this server's base URL.
Opto compresses the request body's ``messages`` through the pipeline, forwards to
the configured upstream, and streams the response straight back. Developers keep
working normally — this runs entirely in the background.
"""

from __future__ import annotations

import json

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from opto.config import Config, get_config
from opto.pipeline import Pipeline
from opto.telemetry import Telemetry

# headers we must not forward verbatim to the upstream
_HOP_BY_HOP = {
    "host", "content-length", "connection", "keep-alive", "transfer-encoding",
    "upgrade", "proxy-authenticate", "proxy-authorization", "te", "trailers",
}


def create_app(config: Config | None = None) -> FastAPI:
    cfg = config or get_config()
    cfg.ensure_dirs()
    app = FastAPI(title="Opto", version="0.1.0")
    pipeline = Pipeline(config=cfg)
    telemetry = Telemetry(cfg.telemetry_db, cfg.audit_log_path, redact=cfg.redact_content_in_logs)

    app.state.config = cfg
    app.state.pipeline = pipeline
    app.state.telemetry = telemetry

    @app.get("/healthz")
    async def healthz():
        return {"status": "ok", "version": app.version, "upstream": cfg.upstream_base_url}

    @app.get("/opto/stats")
    async def stats():
        return telemetry.summary()

    @app.api_route("/{path:path}", methods=["POST"])
    async def proxy(path: str, request: Request):
        raw = await request.body()
        body = _safe_json(raw)

        # Only chat-completions style payloads have messages to compress.
        if isinstance(body, dict) and isinstance(body.get("messages"), list):
            out = pipeline.run(body["messages"])
            telemetry.record(out.report)
            body["messages"] = out.messages
            forward_body = json.dumps(body).encode("utf-8")
        else:
            forward_body = raw

        url = cfg.upstream_base_url.rstrip("/") + "/" + path
        headers = {
            k: v for k, v in request.headers.items() if k.lower() not in _HOP_BY_HOP
        }
        params = dict(request.query_params)
        stream_requested = isinstance(body, dict) and body.get("stream") is True

        client = httpx.AsyncClient(timeout=cfg.request_timeout_s)

        if stream_requested:
            async def event_stream():
                try:
                    async with client.stream(
                        "POST", url, content=forward_body, headers=headers, params=params
                    ) as resp:
                        async for chunk in resp.aiter_raw():
                            yield chunk
                finally:
                    await client.aclose()

            return StreamingResponse(event_stream(), media_type="text/event-stream")

        try:
            resp = await client.post(url, content=forward_body, headers=headers, params=params)
            return JSONResponse(
                content=_safe_json(resp.content),
                status_code=resp.status_code,
            )
        finally:
            await client.aclose()

    return app


def _safe_json(raw: bytes | str):
    try:
        return json.loads(raw)
    except Exception:
        return raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
