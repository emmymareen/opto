"""Cache alignment.

Anthropic and OpenAI cache the KV state of a *stable prompt prefix* across turns.
If Opto compresses that prefix, it changes byte-for-byte every turn and the cache
never hits — which can cost more than the tokens we saved. CacheAlignment marks the
leading, stable part of the conversation (system prompt and any pinned prefix
messages) as off-limits to compression so the provider cache keeps working.

The win compounds: the prefix is sent uncompressed once, cached by the provider,
then effectively free on subsequent turns — while Opto still compresses the
volatile tail (tool output, recent context) where the real bloat lives.
"""

from __future__ import annotations


def preserved_indices(messages: list[dict], preserve_system: bool, pin_prefix: int) -> set[int]:
    """Return indices of messages that must NOT be compressed to keep the
    provider's prompt-cache prefix stable.

    - ``preserve_system``: keep every leading system message verbatim.
    - ``pin_prefix``: additionally pin this many leading messages (after system)
      verbatim, e.g. a stable few-shot preamble.
    """
    preserved: set[int] = set()
    i = 0
    n = len(messages)

    if preserve_system:
        while i < n and messages[i].get("role") == "system":
            preserved.add(i)
            i += 1

    pinned = 0
    while i < n and pinned < pin_prefix:
        preserved.add(i)
        i += 1
        pinned += 1

    return preserved
