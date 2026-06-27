"""Transparency dashboard — shows tokens saved, what was trimmed, and gate decisions.

Reads from the same telemetry store the proxy writes to. Content is never shown
(redacted by default); only aggregate metrics and per-request token accounting.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from opto.config import get_config
from opto.telemetry import Telemetry

_PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>Opto — Transparency</title>
<style>
 body{font-family:system-ui,Segoe UI,Roboto,sans-serif;margin:0;background:#0f1115;color:#e8eaed}
 header{padding:20px 28px;border-bottom:1px solid #232733}
 h1{margin:0;font-size:20px} h1 span{color:#6ee7b7}
 .grid{display:flex;flex-wrap:wrap;gap:16px;padding:24px 28px}
 .card{background:#171a21;border:1px solid #232733;border-radius:12px;padding:18px 20px;min-width:170px}
 .card .k{font-size:12px;color:#9aa4b2;text-transform:uppercase;letter-spacing:.04em}
 .card .v{font-size:26px;font-weight:600;margin-top:6px}
 table{width:calc(100% - 56px);margin:0 28px 28px;border-collapse:collapse;font-size:13px}
 th,td{text-align:right;padding:8px 10px;border-bottom:1px solid #232733}
 th:first-child,td:first-child{text-align:left}
 .tag{padding:2px 8px;border-radius:999px;font-size:11px}
 .ok{background:#0f3d2e;color:#6ee7b7}.off{background:#3d2f0f;color:#fcd34d}.ctl{background:#1e2a3d;color:#93c5fd}
</style></head><body>
<header><h1>Opto <span>Transparency</span> &nbsp;·&nbsp; what got compressed & why</h1></header>
<div class="grid" id="cards"></div>
<table id="rows"><thead><tr>
 <th>#</th><th>Original</th><th>Compressed</th><th>Saved</th><th>Saved %</th>
 <th>Dropped</th><th>Risk</th><th>Status</th></tr></thead><tbody></tbody></table>
<script>
async function load(){
 const s = await (await fetch('/api/summary')).json();
 const cards = [
  ['Requests', s.requests],
  ['Original tokens', s.original_tokens.toLocaleString()],
  ['Saved tokens', s.saved_tokens.toLocaleString()],
  ['Saved', (s.saved_fraction*100).toFixed(1)+'%'],
  ['Backed off', s.backed_off],
  ['Held out', s.held_out],
 ];
 document.getElementById('cards').innerHTML = cards.map(
   ([k,v])=>`<div class="card"><div class="k">${k}</div><div class="v">${v}</div></div>`).join('');
 const rows = await (await fetch('/api/recent')).json();
 const tb = document.querySelector('#rows tbody');
 tb.innerHTML = rows.map(r=>{
   let tag = '<span class="tag ok">compressed</span>';
   if(r.held_out) tag='<span class="tag ctl">control</span>';
   else if(r.backed_off) tag='<span class="tag off">backed off</span>';
   else if(!r.compressed) tag='<span class="tag off">skipped</span>';
   return `<tr><td>${r.id}</td><td>${r.original_tokens.toLocaleString()}</td>
    <td>${r.compressed_tokens.toLocaleString()}</td><td>${r.saved_tokens.toLocaleString()}</td>
    <td>${(r.saved_fraction*100).toFixed(0)}%</td><td>${r.chunks_dropped}</td>
    <td>${r.quality_risk.toFixed(2)}</td><td>${tag}</td></tr>`;
 }).join('');
}
load(); setInterval(load, 4000);
</script></body></html>"""


def create_dashboard() -> FastAPI:
    cfg = get_config()
    cfg.ensure_dirs()
    tel = Telemetry(cfg.telemetry_db, cfg.audit_log_path, redact=cfg.redact_content_in_logs)
    app = FastAPI(title="Opto Dashboard", version="0.1.0")

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return _PAGE

    @app.get("/api/summary")
    async def summary():
        return JSONResponse(tel.summary())

    @app.get("/api/recent")
    async def recent():
        return JSONResponse(tel.recent(limit=100))

    return app
