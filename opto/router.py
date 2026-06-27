"""Content router — classifies a piece of text so the right compressor handles it."""

from __future__ import annotations

import json
import re

from opto.types import ContentKind

_CODE_HINTS = re.compile(
    r"(def |class |function |import |#include|public |private |=>|;\s*$|{\s*$|</?\w+>)",
    re.MULTILINE,
)
_DIFF_HINTS = re.compile(r"^(diff --git|@@ |\+\+\+ |--- |index [0-9a-f])", re.MULTILINE)
_LOG_HINTS = re.compile(
    r"(?im)^\s*(\[?\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}|DEBUG|INFO|WARN|WARNING|ERROR|FATAL|TRACE)\b"
)


def _looks_like_json(text: str) -> bool:
    s = text.strip()
    if not s or s[0] not in "{[":
        return False
    try:
        json.loads(s)
        return True
    except Exception:
        return False


_FENCE = re.compile(r"```[\w+-]*\n.*?\n```", re.DOTALL)
_JSON_BLOB = re.compile(r"(?<![\w])(\{.{40,}\}|\[.{40,}\])", re.DOTALL)


def segment(text: str) -> list[tuple[str, "ContentKind"]]:
    """Split a message into typed spans so embedded code/JSON inside otherwise
    prose messages still gets compressed. Returns ``[(span_text, kind), ...]``
    whose concatenation reproduces the original text exactly.
    """
    if not text:
        return [(text, ContentKind.PROSE)]

    # locate fenced code blocks and large JSON-looking blobs
    spans: list[tuple[int, int, ContentKind]] = []
    for m in _FENCE.finditer(text):
        spans.append((m.start(), m.end(), classify(m.group(0))))
    for m in _JSON_BLOB.finditer(text):
        if any(s <= m.start() < e for s, e, _ in spans):
            continue
        if _looks_like_json(m.group(0)):
            spans.append((m.start(), m.end(), ContentKind.JSON))

    if not spans:
        return [(text, classify(text))]

    spans.sort()
    out: list[tuple[str, ContentKind]] = []
    cursor = 0
    for start, end, kind in spans:
        if start > cursor:
            out.append((text[cursor:start], classify(text[cursor:start])))
        out.append((text[start:end], kind))
        cursor = end
    if cursor < len(text):
        out.append((text[cursor:], classify(text[cursor:])))
    return out


def classify(text: str) -> ContentKind:
    """Best-effort classification of a chunk's content type."""
    if not text or not text.strip():
        return ContentKind.PROSE

    if _DIFF_HINTS.search(text):
        return ContentKind.DIFF
    if _looks_like_json(text):
        return ContentKind.JSON

    log_hits = len(_LOG_HINTS.findall(text))
    lines = text.count("\n") + 1
    if log_hits >= 3 or (lines >= 5 and log_hits / lines > 0.3):
        return ContentKind.LOG

    code_hits = len(_CODE_HINTS.findall(text))
    if code_hits >= 2 or (lines >= 4 and code_hits / lines > 0.25):
        return ContentKind.CODE

    return ContentKind.PROSE
