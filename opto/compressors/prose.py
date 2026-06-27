"""Extractive prose summarizer.

v1's prose handling was whitespace-only, so plain-English context barely shrank.
This adds a dependency-free extractive summarizer: it splits prose into sentences,
scores each by normalised word-frequency (a classic, robust heuristic), and keeps
the top-ranked sentences in their original order. It's lossy-but-faithful — it
selects real sentences rather than paraphrasing, so it never invents text.

A pluggable abstractive backend (an open-source model) can be slotted in via
``set_prose_model``; if none is set, the extractive path is used. This keeps Opto
fully offline by default while leaving a clean seam for a trained compressor.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Callable

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")
_WORD = re.compile(r"[A-Za-z][A-Za-z0-9'_-]+")
_STOP = {
    "the", "a", "an", "and", "or", "to", "of", "in", "is", "it", "for", "on",
    "this", "that", "with", "as", "are", "be", "by", "from", "at", "we", "you",
    "i", "but", "not", "have", "has", "was", "were", "will", "can", "if", "so",
}

# optional abstractive backend: text, ratio -> compressed text
_PROSE_MODEL: Callable[[str, float], str] | None = None


def set_prose_model(fn: Callable[[str, float], str] | None) -> None:
    """Register an abstractive prose backend (e.g. a local open-source model)."""
    global _PROSE_MODEL
    _PROSE_MODEL = fn


def _sentences(text: str) -> list[str]:
    parts = _SENT_SPLIT.split(text.strip())
    return [p.strip() for p in parts if p.strip()]


def extractive_summary(text: str, keep_ratio: float) -> str:
    """Keep the top ``keep_ratio`` of sentences by word-frequency score, preserving
    original order. Short inputs are returned unchanged."""
    sents = _sentences(text)
    if len(sents) <= 3:
        return text.strip()

    freq: Counter[str] = Counter()
    for s in sents:
        for w in _WORD.findall(s.lower()):
            if w not in _STOP and len(w) > 2:
                freq[w] += 1
    if not freq:
        return text.strip()
    peak = max(freq.values())

    scored: list[tuple[int, float]] = []
    for idx, s in enumerate(sents):
        words = [w for w in _WORD.findall(s.lower()) if w not in _STOP and len(w) > 2]
        if not words:
            scored.append((idx, 0.0))
            continue
        score = sum(freq[w] / peak for w in words) / (1.0 + math.log1p(len(words)))
        scored.append((idx, score))

    keep_n = max(3, int(round(len(sents) * keep_ratio)))
    keep_n = min(keep_n, len(sents))
    top = sorted(scored, key=lambda t: t[1], reverse=True)[:keep_n]
    keep_idx = sorted(i for i, _ in top)

    kept = [sents[i] for i in keep_idx]
    elided = len(sents) - len(kept)
    out = " ".join(kept)
    if elided > 0:
        out += f" [opto: {elided} lower-salience sentence(s) elided]"
    return out


def compress_prose(text: str, aggressiveness: float = 0.5) -> str:
    if not text or not text.strip():
        return text
    keep_ratio = max(0.2, 1.0 - aggressiveness)  # more aggressive -> keep less
    if _PROSE_MODEL is not None:
        try:
            return _PROSE_MODEL(text, keep_ratio)
        except Exception:
            pass  # fall back to extractive on any backend failure
    # only summarize meaningfully long prose; otherwise just tidy whitespace
    if len(text) < 400:
        return re.sub(r"[ \t]{2,}", " ", text).strip()
    return extractive_summary(text, keep_ratio)
