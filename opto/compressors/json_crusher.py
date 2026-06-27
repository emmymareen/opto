"""JSON crusher.

Tool outputs and API responses are often verbose JSON with huge repeated arrays.
This compressor re-serialises JSON compactly and, for long homogeneous arrays,
keeps a representative sample plus a count of what was elided. Falls back to the
original text if parsing fails.
"""

from __future__ import annotations

import json

_MAX_ARRAY_KEEP = 5  # at aggressiveness 0.5


class JsonCrusher:
    name = "json"

    def compress(self, text: str, aggressiveness: float = 0.5) -> str:
        s = text.strip()
        try:
            data = json.loads(s)
        except Exception:
            return text

        keep = max(1, int(_MAX_ARRAY_KEEP * (1.0 - aggressiveness) * 2) or 1)
        crushed = self._crush(data, keep)
        # compact separators remove all incidental whitespace
        return json.dumps(crushed, separators=(",", ":"), ensure_ascii=False)

    def _crush(self, obj, keep: int):
        if isinstance(obj, list):
            if len(obj) > keep * 2:
                head = [self._crush(x, keep) for x in obj[:keep]]
                head.append(f"… +{len(obj) - keep} more items elided …")
                return head
            return [self._crush(x, keep) for x in obj]
        if isinstance(obj, dict):
            return {k: self._crush(v, keep) for k, v in obj.items()}
        return obj
