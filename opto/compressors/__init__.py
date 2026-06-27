"""Compressors registry — maps a ContentKind to a compressor implementation."""

from __future__ import annotations

from opto.types import ContentKind
from opto.compressors.base import Compressor, PassThrough
from opto.compressors.code import CodeCompressor
from opto.compressors.json_crusher import JsonCrusher
from opto.compressors.text import TextCompressor

_REGISTRY: dict[ContentKind, Compressor] = {
    ContentKind.CODE: CodeCompressor(),
    ContentKind.DIFF: CodeCompressor(),
    ContentKind.JSON: JsonCrusher(),
    ContentKind.LOG: TextCompressor(log_mode=True),
    ContentKind.PROSE: TextCompressor(),
}

_FALLBACK = PassThrough()


def get_compressor(kind: ContentKind) -> Compressor:
    return _REGISTRY.get(kind, _FALLBACK)


__all__ = [
    "Compressor",
    "PassThrough",
    "CodeCompressor",
    "JsonCrusher",
    "TextCompressor",
    "get_compressor",
]
