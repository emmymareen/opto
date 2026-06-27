"""Relevance scoring — Opto's "smarter relevance" differentiator.

Rather than blindly compressing everything, we score each context chunk against
the current user turn and let low-value chunks be dropped before compression.

v1 uses a lexical scorer (token overlap + recency + light TF weighting). The
``score_chunks`` signature is stable so an embedding-based scorer can be swapped
in later without touching the pipeline.
"""

from __future__ import annotations

import math
import re
from collections import Counter

from opto.types import Chunk

_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]+")
_STOP = {
    "the", "a", "an", "and", "or", "to", "of", "in", "is", "it", "for", "on",
    "this", "that", "with", "as", "are", "be", "by", "from", "at", "you", "i",
}


def _terms(text: str) -> list[str]:
    return [w.lower() for w in _WORD.findall(text) if w.lower() not in _STOP and len(w) > 1]


def score_chunks(chunks: list[Chunk], query: str) -> list[Chunk]:
    """Assign a 0..1 relevance score to each chunk relative to ``query``.

    Score blends lexical overlap with the query and a mild recency boost (later
    chunks in the conversation tend to matter more). Scores are normalised so the
    most relevant chunk is ~1.0, which keeps the drop threshold intuitive.
    """
    if not chunks:
        return chunks

    q_terms = set(_terms(query))
    n = len(chunks)
    raw: list[float] = []

    for i, ch in enumerate(chunks):
        c_terms = _terms(ch.text)
        if not c_terms:
            raw.append(0.0)
            continue
        counts = Counter(c_terms)
        overlap = sum(counts[t] for t in q_terms if t in counts)
        # length-normalised overlap, dampened so huge chunks don't dominate
        lex = overlap / (1.0 + math.log1p(len(c_terms)))
        recency = (i + 1) / n  # 0..1, later = higher
        raw.append(lex * 0.8 + recency * 0.2)

    hi = max(raw) or 1.0
    for ch, r in zip(chunks, raw):
        ch.relevance = round(min(1.0, r / hi), 4)
    return chunks


def apply_drop(chunks: list[Chunk], threshold: float) -> list[Chunk]:
    """Mark chunks below ``threshold`` as dropped. The most relevant chunk is
    always kept so we never strip a request to nothing."""
    if not chunks:
        return chunks
    keep_idx = max(range(len(chunks)), key=lambda i: chunks[i].relevance)
    for i, ch in enumerate(chunks):
        if i != keep_idx and ch.relevance < threshold:
            ch.dropped = True
    return chunks
