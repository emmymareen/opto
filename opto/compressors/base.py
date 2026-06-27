"""Base compressor interface."""

from __future__ import annotations

from abc import ABC, abstractmethod


class Compressor(ABC):
    """A compressor turns text into a shorter, information-preserving form.

    ``aggressiveness`` is 0..1 (higher = more reduction). Implementations should
    be deterministic so the reversible cache and tests behave predictably.
    """

    name: str = "base"

    @abstractmethod
    def compress(self, text: str, aggressiveness: float = 0.5) -> str:  # pragma: no cover
        ...


class PassThrough(Compressor):
    name = "passthrough"

    def compress(self, text: str, aggressiveness: float = 0.5) -> str:
        return text
