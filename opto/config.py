"""Configuration for Opto.

All settings are environment-driven (prefix ``OPTO_``) so Opto can be deployed in
enterprise environments without code changes. A config file can also be layered in.
"""

from __future__ import annotations

import functools
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OPTO_", env_file=".env", extra="ignore")

    # ---- Proxy ----
    host: str = Field(default="127.0.0.1", description="Proxy bind host.")
    port: int = Field(default=8799, description="Proxy bind port.")
    upstream_base_url: str = Field(
        default="https://api.githubcopilot.com",
        description="Upstream LLM endpoint Opto forwards to.",
    )
    request_timeout_s: float = Field(default=120.0, description="Upstream request timeout.")

    # ---- Copilot auth bridge ----
    manage_copilot_auth: bool = Field(
        default=False,
        description="If true, Opto performs the GitHub->Copilot token exchange itself "
        "and routes to the discovered endpoint (needed for enterprise Copilot "
        "when the client can't hand Opto a usable token).",
    )
    github_host: str = Field(
        default="github.com",
        description="GitHub host for token exchange (set to your GHE domain if applicable).",
    )

    # ---- Compression ----
    enabled: bool = Field(default=True, description="Master switch for compression.")
    min_tokens_to_compress: int = Field(
        default=400,
        description="Skip compression entirely for requests smaller than this.",
    )
    target_ratio: float = Field(
        default=0.45,
        ge=0.05,
        le=1.0,
        description="Aim to keep this fraction of original tokens (0.45 = ~55% saved).",
    )

    # ---- Cache alignment ----
    align_cache: bool = Field(
        default=True,
        description="Keep the stable prompt prefix uncompressed so provider KV "
        "caches keep hitting (compressing it would bust the cache every turn).",
    )
    preserve_system: bool = Field(
        default=True, description="Never compress leading system messages."
    )
    pin_prefix_messages: int = Field(
        default=0, description="Additionally pin this many leading messages verbatim."
    )

    # ---- Relevance ----
    relevance_drop_threshold: float = Field(
        default=0.12,
        ge=0.0,
        le=1.0,
        description="Chunks scoring below this (0..1) are dropped before compression.",
    )

    # ---- Quality guarantee ----
    quality_gate_enabled: bool = Field(default=True)
    quality_risk_threshold: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="If estimated fidelity risk exceeds this, back off / pass through.",
    )
    holdout_fraction: float = Field(
        default=0.0,
        ge=0.0,
        le=0.5,
        description="Fraction of requests left UNCOMPRESSED as a measured control group.",
    )

    # ---- Reversible cache (CCR) ----
    cache_dir: Path = Field(default=Path(".opto/cache"))
    cache_ttl_s: int = Field(default=86_400, description="How long originals stay retrievable.")

    # ---- Telemetry / enterprise ----
    audit_log_path: Path = Field(
        default=Path(".opto/audit.jsonl"),
        description="Append-only JSONL audit log of every request decision.",
    )
    telemetry_db: Path = Field(default=Path(".opto/telemetry.sqlite"))
    redact_content_in_logs: bool = Field(
        default=True,
        description="Enterprise default: never write raw prompt content to logs/telemetry.",
    )

    def ensure_dirs(self) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
        self.telemetry_db.parent.mkdir(parents=True, exist_ok=True)


@functools.lru_cache(maxsize=1)
def get_config() -> Config:
    return Config()
