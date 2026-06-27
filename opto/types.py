"""Shared data structures used across the Opto pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ContentKind(str, Enum):
    CODE = "code"
    DIFF = "diff"
    JSON = "json"
    LOG = "log"
    PROSE = "prose"


@dataclass
class Chunk:
    """A unit of context flowing through the pipeline."""

    text: str
    kind: ContentKind = ContentKind.PROSE
    # role/message index this chunk came from, for reassembly
    message_index: int = 0
    # 0..1 relevance score assigned by the relevance scorer
    relevance: float = 1.0
    # set True if the relevance stage decided to drop it
    dropped: bool = False
    # original token count, filled in by the pipeline
    original_tokens: int = 0


@dataclass
class CompressionResult:
    """Outcome of compressing a single chunk."""

    compressed_text: str
    original_text: str
    kind: ContentKind
    original_tokens: int
    compressed_tokens: int
    # id under which the original is stored in the reversible cache (if any)
    cache_id: str | None = None

    @property
    def saved_tokens(self) -> int:
        return max(0, self.original_tokens - self.compressed_tokens)

    @property
    def ratio(self) -> float:
        if self.original_tokens == 0:
            return 1.0
        return self.compressed_tokens / self.original_tokens


@dataclass
class PipelineReport:
    """Per-request summary, used for telemetry and the dashboard."""

    original_tokens: int = 0
    compressed_tokens: int = 0
    chunks_total: int = 0
    chunks_dropped: int = 0
    by_kind: dict[str, int] = field(default_factory=dict)  # kind -> tokens saved
    compressed: bool = True
    held_out: bool = False
    quality_risk: float = 0.0
    backed_off: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def saved_tokens(self) -> int:
        return max(0, self.original_tokens - self.compressed_tokens)

    @property
    def saved_fraction(self) -> float:
        if self.original_tokens == 0:
            return 0.0
        return self.saved_tokens / self.original_tokens
