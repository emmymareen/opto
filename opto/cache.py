"""Reversible compression cache (CCR).

Originals are stored locally keyed by a content hash so the model — or a human
auditor — can retrieve the exact pre-compression text on demand. This is what
makes Opto's compression safe: nothing is ever truly lost.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path


class ReversibleCache:
    def __init__(self, cache_dir: Path, ttl_s: int = 86_400):
        self.cache_dir = Path(cache_dir)
        self.ttl_s = ttl_s
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, cache_id: str) -> Path:
        return self.cache_dir / f"{cache_id}.json"

    def store(self, original: str) -> str:
        """Store ``original`` and return a short retrieval id."""
        cache_id = hashlib.sha256(original.encode("utf-8")).hexdigest()[:16]
        payload = {"id": cache_id, "ts": time.time(), "original": original}
        self._path(cache_id).write_text(json.dumps(payload), encoding="utf-8")
        return cache_id

    def retrieve(self, cache_id: str) -> str | None:
        p = self._path(cache_id)
        if not p.exists():
            return None
        try:
            payload = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None
        if time.time() - payload.get("ts", 0) > self.ttl_s:
            p.unlink(missing_ok=True)
            return None
        return payload.get("original")

    def purge_expired(self) -> int:
        removed = 0
        now = time.time()
        for p in self.cache_dir.glob("*.json"):
            try:
                payload = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                p.unlink(missing_ok=True)
                removed += 1
                continue
            if now - payload.get("ts", 0) > self.ttl_s:
                p.unlink(missing_ok=True)
                removed += 1
        return removed
