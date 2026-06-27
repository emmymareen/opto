"""The Opto pipeline — orchestrates relevance → routing → compression → quality gate.

Operates on OpenAI/Copilot-style ``messages`` (list of {role, content}). Returns
the compressed messages plus a :class:`PipelineReport` for telemetry.
"""

from __future__ import annotations

from dataclasses import dataclass

from opto.compressors import get_compressor
from opto.config import Config, get_config
from opto.cache import ReversibleCache
from opto.quality import QualityGate
from opto.relevance import apply_drop, score_chunks
from opto.router import segment
from opto.tokens import count_tokens
from opto.types import Chunk, CompressionResult, PipelineReport


def _aggressiveness_for_target(target_ratio: float) -> float:
    # target_ratio 1.0 -> no compression, 0.05 -> very aggressive
    return round(min(1.0, max(0.0, 1.0 - target_ratio)), 3)


def _latest_user_text(messages: list[dict]) -> str:
    for m in reversed(messages):
        if m.get("role") == "user":
            c = m.get("content")
            if isinstance(c, str):
                return c
            if isinstance(c, list):  # multimodal content parts
                return " ".join(
                    p.get("text", "") for p in c if isinstance(p, dict) and "text" in p
                )
    return ""


@dataclass
class PipelineOutput:
    messages: list[dict]
    report: PipelineReport


class Pipeline:
    def __init__(self, config: Config | None = None, cache: ReversibleCache | None = None):
        self.config = config or get_config()
        self.cache = cache or ReversibleCache(self.config.cache_dir, self.config.cache_ttl_s)
        self.gate = QualityGate(
            enabled=self.config.quality_gate_enabled,
            risk_threshold=self.config.quality_risk_threshold,
            holdout_fraction=self.config.holdout_fraction,
        )

    def run(self, messages: list[dict]) -> PipelineOutput:
        cfg = self.config
        report = PipelineReport()

        original_tokens = sum(count_tokens(_content_str(m)) for m in messages)
        report.original_tokens = original_tokens
        report.compressed_tokens = original_tokens

        if not cfg.enabled or original_tokens < cfg.min_tokens_to_compress:
            report.compressed = False
            report.notes.append("below-min-threshold-or-disabled")
            return PipelineOutput(messages=messages, report=report)

        query = _latest_user_text(messages)
        aggressiveness = _aggressiveness_for_target(cfg.target_ratio)

        # 1) build chunks by segmenting each message into typed spans, so embedded
        #    code/JSON inside prose messages is compressed too. Order is preserved.
        chunks: list[Chunk] = []
        for i, m in enumerate(messages):
            text = _content_str(m)
            if not text.strip():
                continue
            for span_text, kind in segment(text):
                if not span_text:
                    continue
                chunks.append(
                    Chunk(
                        text=span_text,
                        kind=kind,
                        message_index=i,
                        original_tokens=count_tokens(span_text),
                    )
                )

        report.chunks_total = len(chunks)

        # 2) relevance score + drop
        score_chunks(chunks, query)
        apply_drop(chunks, cfg.relevance_drop_threshold)

        # 3) compress surviving chunks
        results: list[CompressionResult] = []
        for ch in chunks:
            if ch.dropped:
                results.append(
                    CompressionResult(
                        compressed_text="",
                        original_text=ch.text,
                        kind=ch.kind,
                        original_tokens=ch.original_tokens,
                        compressed_tokens=0,
                    )
                )
                continue
            compressor = get_compressor(ch.kind)
            compressed = compressor.compress(ch.text, aggressiveness)
            ctok = count_tokens(compressed)
            # never let "compression" make a chunk bigger
            if ctok >= ch.original_tokens:
                compressed, ctok = ch.text, ch.original_tokens
            cache_id = self.cache.store(ch.text) if compressed != ch.text else None
            results.append(
                CompressionResult(
                    compressed_text=compressed,
                    original_text=ch.text,
                    kind=ch.kind,
                    original_tokens=ch.original_tokens,
                    compressed_tokens=ctok,
                    cache_id=cache_id,
                )
            )

        # 4) quality gate
        decision = self.gate.decide(chunks, results)
        report.quality_risk = decision.risk

        if not decision.apply:
            report.compressed = False
            report.held_out = decision.held_out
            report.backed_off = not decision.held_out
            report.notes.append(decision.reason)
            return PipelineOutput(messages=messages, report=report)

        # 5) reassemble compressed spans back into their messages, in order
        new_messages = [dict(m) for m in messages]
        rebuilt: dict[int, list[str]] = {}
        for ch, r in zip(chunks, results):
            idx = ch.message_index
            if ch.dropped:
                cache_id = self.cache.store(ch.text)
                marker = f"[opto: dropped low-relevance context · retrieve id={cache_id}]"
                # only honour the drop if the marker is actually cheaper than the
                # original; otherwise keep the span verbatim (never inflate).
                if count_tokens(marker) < ch.original_tokens:
                    piece = marker
                    report.chunks_dropped += 1
                    report.by_kind[ch.kind.value] = (
                        report.by_kind.get(ch.kind.value, 0)
                        + (ch.original_tokens - count_tokens(marker))
                    )
                else:
                    piece = ch.text
            else:
                piece = r.compressed_text
                report.by_kind[ch.kind.value] = (
                    report.by_kind.get(ch.kind.value, 0) + r.saved_tokens
                )
            rebuilt.setdefault(idx, []).append(piece)

        for idx, pieces in rebuilt.items():
            new_messages[idx]["content"] = "\n".join(pieces)

        report.compressed_tokens = sum(count_tokens(_content_str(m)) for m in new_messages)
        return PipelineOutput(messages=new_messages, report=report)


def _content_str(message: dict) -> str:
    c = message.get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return " ".join(p.get("text", "") for p in c if isinstance(p, dict) and "text" in p)
    return "" if c is None else str(c)


def compress(messages: list[dict], config: Config | None = None) -> PipelineOutput:
    """Convenience one-shot entry point used by the library and proxy."""
    return Pipeline(config=config).run(messages)
