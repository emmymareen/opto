"""GitHub Copilot authentication bridge.

Enterprise Copilot has no API key. Authentication works like this:

  1. The editor/CLI holds a GitHub OAuth token (``ghu_…``) granted by the user's
     Copilot licence.
  2. That token is exchanged at ``/copilot_internal/v2/token`` for a short-lived
     bearer token (~30 min) plus the correct API endpoint (``endpoints.api``),
     which differs for Individual vs Business vs Enterprise.
  3. API calls use ``Authorization: Bearer <short-lived-token>`` and must carry
     client-identity headers (Editor-Version, Copilot-Integration-Id, …) that
     Business/Enterprise validate.

This module discovers the OAuth token, performs and caches the exchange (with
refresh-before-expiry), and exposes the base URL + headers Opto needs to forward
authenticated requests. No API key is ever required from the user.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

# Default client identity. Overridable via OPTO_COPILOT_* env so Opto can mimic
# whatever editor the org has authorised.
DEFAULT_INTEGRATION_ID = os.getenv("OPTO_COPILOT_INTEGRATION_ID", "vscode-chat")
DEFAULT_EDITOR_VERSION = os.getenv("OPTO_COPILOT_EDITOR_VERSION", "vscode/1.99.0")
DEFAULT_PLUGIN_VERSION = os.getenv("OPTO_COPILOT_PLUGIN_VERSION", "copilot-chat/0.26.0")
DEFAULT_USER_AGENT = os.getenv("OPTO_COPILOT_USER_AGENT", "GitHubCopilotChat/0.26.0")


class CopilotAuthError(RuntimeError):
    pass


def _config_dirs() -> list[Path]:
    dirs = []
    if os.getenv("XDG_CONFIG_HOME"):
        dirs.append(Path(os.environ["XDG_CONFIG_HOME"]) / "github-copilot")
    home = Path.home()
    dirs.append(home / ".config" / "github-copilot")
    # macOS sometimes uses Application Support
    dirs.append(home / "Library" / "Application Support" / "github-copilot")
    return dirs


def discover_oauth_token() -> str | None:
    """Find the user's GitHub Copilot OAuth (``ghu_``) token.

    Order: explicit env var, then the files the official Copilot editors/CLI write
    (``apps.json`` / ``hosts.json``). Returns ``None`` if nothing usable is found.
    """
    for var in ("OPTO_COPILOT_GITHUB_TOKEN", "GITHUB_COPILOT_TOKEN", "GH_COPILOT_TOKEN"):
        tok = os.getenv(var)
        if tok:
            return tok

    for d in _config_dirs():
        for fname in ("apps.json", "hosts.json"):
            p = d / fname
            if not p.exists():
                continue
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            token = _extract_token(data)
            if token:
                return token
    return None


def _extract_token(data: dict) -> str | None:
    # apps.json: { "github.com:Iv1.xxx": {"oauth_token": "ghu_...", ...}, ... }
    # hosts.json: { "github.com": {"oauth_token": "ghu_...", ...}, ... }
    if not isinstance(data, dict):
        return None
    for value in data.values():
        if isinstance(value, dict) and value.get("oauth_token"):
            return value["oauth_token"]
    return None


def _token_endpoint(github_host: str) -> str:
    host = github_host.strip().rstrip("/")
    if host in ("github.com", "api.github.com", ""):
        return "https://api.github.com/copilot_internal/v2/token"
    # GitHub Enterprise Server custom domain
    host = host.replace("https://", "").replace("http://", "")
    return f"https://{host}/api/v3/copilot_internal/v2/token"


@dataclass
class CopilotSession:
    """A cached, auto-refreshing Copilot API session."""

    oauth_token: str
    github_host: str = "github.com"
    integration_id: str = DEFAULT_INTEGRATION_ID
    editor_version: str = DEFAULT_EDITOR_VERSION
    plugin_version: str = DEFAULT_PLUGIN_VERSION
    user_agent: str = DEFAULT_USER_AGENT

    _bearer: str | None = field(default=None, init=False)
    _expires_at: float = field(default=0.0, init=False)
    _api_base: str | None = field(default=None, init=False)

    # refresh this many seconds before the token actually expires
    _skew_s: int = 120

    def _needs_refresh(self) -> bool:
        return self._bearer is None or time.time() >= (self._expires_at - self._skew_s)

    def refresh(self, client: httpx.Client | None = None) -> None:
        owns = client is None
        client = client or httpx.Client(timeout=20.0)
        try:
            resp = client.get(
                _token_endpoint(self.github_host),
                headers={
                    "Authorization": f"token {self.oauth_token}",
                    "Accept": "application/json",
                    "User-Agent": self.user_agent,
                    "Editor-Version": self.editor_version,
                    "Editor-Plugin-Version": self.plugin_version,
                },
            )
        finally:
            if owns:
                client.close()

        if resp.status_code == 404:
            raise CopilotAuthError(
                "Token exchange returned 404 — the OAuth token may lack a Copilot "
                "licence, or the enterprise host/path is wrong."
            )
        if resp.status_code >= 400:
            raise CopilotAuthError(
                f"Token exchange failed ({resp.status_code}): {resp.text[:200]}"
            )

        data = resp.json()
        self._bearer = data.get("token")
        self._expires_at = float(data.get("expires_at", time.time() + 1500))
        # Endpoint differs Individual/Business/Enterprise — never hardcode.
        endpoints = data.get("endpoints") or {}
        self._api_base = endpoints.get("api") or "https://api.githubcopilot.com"
        if not self._bearer:
            raise CopilotAuthError("Token exchange response contained no token.")

    def bearer(self, client: httpx.Client | None = None) -> str:
        if self._needs_refresh():
            self.refresh(client)
        return self._bearer  # type: ignore[return-value]

    def api_base(self, client: httpx.Client | None = None) -> str:
        if self._needs_refresh():
            self.refresh(client)
        return self._api_base  # type: ignore[return-value]

    def auth_headers(self, client: httpx.Client | None = None) -> dict[str, str]:
        """Headers Opto must attach to every forwarded Copilot request."""
        return {
            "Authorization": f"Bearer {self.bearer(client)}",
            "Editor-Version": self.editor_version,
            "Editor-Plugin-Version": self.plugin_version,
            "Copilot-Integration-Id": self.integration_id,
            "User-Agent": self.user_agent,
            "Openai-Intent": "conversation-edits",
        }


def build_session_from_environment(github_host: str = "github.com") -> CopilotSession | None:
    """Convenience: discover the OAuth token and return a session, or None."""
    token = discover_oauth_token()
    if not token:
        return None
    return CopilotSession(oauth_token=token, github_host=github_host)
