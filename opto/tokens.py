"""Token counting utilities.

Uses tiktoken when available; falls back to a cheap heuristic so Opto never
hard-fails just because an encoding is missing.
"""

from __future__ import annotations

import functools

try:
    import tiktoken

    _HAS_TIKTOKEN = True
except Exception:  # pragma: no cover - optional dependency path
    _HAS_TIKTOKEN = False


@functools.lru_cache(maxsize=8)
def _encoder(model: str = "cl100k_base"):
    if not _HAS_TIKTOKEN:
        return None
    # The encoding vocab may need to be downloaded on first use; if the network
    # is unavailable (offline / locked-down enterprise env) fall back gracefully.
    for loader in (
        lambda: tiktoken.get_encoding(model),
        lambda: tiktoken.encoding_for_model(model),
        lambda: tiktoken.get_encoding("cl100k_base"),
    ):
        try:
            return loader()
        except Exception:
            continue
    return None


def _heuristic(text: str) -> int:
    return max(1, len(text) // 4)


def count_tokens(text: str, model: str = "cl100k_base") -> int:
    """Return token count for ``text``.

    Falls back to ~4 chars/token when tiktoken is unavailable or its vocab
    cannot be loaded (e.g. offline environments).
    """
    if not text:
        return 0
    enc = _encoder(model)
    if enc is None:
        return _heuristic(text)
    try:
        return len(enc.encode(text))
    except Exception:
        return _heuristic(text)
