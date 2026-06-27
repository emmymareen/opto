"""Quality-guarantee gate — Opto's core safety differentiator.

Compression is only worth doing if answers stay correct. This module estimates a
0..1 "fidelity risk" for a planned compression and decides whether to apply it,
soften it, or pass the request through untouched. It also supports a holdout: a
configurable fraction of requests are deliberately left uncompressed so savings
can be *measured* against a control group rather than only estimated.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from opto.types import Chunk, ContentKind, CompressionResult


@dataclass
class GateDecision:
    apply: bool  # whether to use the compressed version
    held_out: bool  # request was selected as an uncompressed control
    risk: float  # estimated 0..1 fidelity risk
    reason: str


# How lossy is compressing each content kind? Structural/redundancy removal on
# JSON, logs and code (reversible, signature-preserving) carries little fidelity
# risk; summarising unique prose is where real information can be lost.
_LOSSINESS: dict[ContentKind, float] = {
    ContentKind.JSON: 0.12,
    ContentKind.LOG: 0.18,
    ContentKind.CODE: 0.25,
    ContentKind.DIFF: 0.25,
    ContentKind.PROSE: 0.7,
}


def estimate_risk(chunks: list[Chunk], results: list[CompressionResult]) -> float:
    """Content-aware fidelity-risk estimate (0..1).

    Risk for each compressed span = how much we removed × how relevant the span
    is × how lossy that content type is, weighted by the span's share of tokens.
    Dropping a relevant span entirely adds a penalty. Removing redundancy from
    JSON/logs barely moves the needle; summarising relevant prose moves it a lot.
    """
    if not results:
        return 0.0

    total_orig = sum(r.original_tokens for r in results) or 1

    weighted = 0.0
    for ch, r in zip(chunks, results):
        reduction = 1.0 - r.ratio  # fraction removed
        lossiness = _LOSSINESS.get(r.kind, 0.5)
        weighted += reduction * ch.relevance * lossiness * (r.original_tokens / total_orig)

    drop_penalty = 0.0
    for ch in chunks:
        if ch.dropped:
            drop_penalty += ch.relevance * _LOSSINESS.get(ch.kind, 0.5) * 0.4

    return round(min(1.0, weighted + drop_penalty), 4)


class QualityGate:
    def __init__(
        self,
        enabled: bool = True,
        risk_threshold: float = 0.7,
        holdout_fraction: float = 0.0,
        rng: random.Random | None = None,
    ):
        self.enabled = enabled
        self.risk_threshold = risk_threshold
        self.holdout_fraction = holdout_fraction
        self._rng = rng or random.Random()

    def decide(self, chunks: list[Chunk], results: list[CompressionResult]) -> GateDecision:
        if self.holdout_fraction > 0 and self._rng.random() < self.holdout_fraction:
            return GateDecision(
                apply=False, held_out=True, risk=0.0, reason="holdout-control"
            )

        risk = estimate_risk(chunks, results)

        if not self.enabled:
            return GateDecision(apply=True, held_out=False, risk=risk, reason="gate-disabled")

        if risk > self.risk_threshold:
            return GateDecision(
                apply=False,
                held_out=False,
                risk=risk,
                reason=f"risk {risk:.2f} > threshold {self.risk_threshold:.2f}",
            )
        return GateDecision(apply=True, held_out=False, risk=risk, reason="within-threshold")
