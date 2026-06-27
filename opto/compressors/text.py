"""Text / log compressor.

For prose, collapses whitespace and trims obvious filler. For logs (``log_mode``),
deduplicates repeated lines and prioritises higher-severity lines (ERROR/FATAL),
which is where the signal usually is in agent debugging contexts.
"""

from __future__ import annotations

import re
from collections import OrderedDict

_WS = re.compile(r"[ \t]{2,}")
_BLANK_RUN = re.compile(r"\n\s*\n\s*\n+")
_SEVERITY = re.compile(r"(?i)\b(FATAL|ERROR|WARN(?:ING)?|INFO|DEBUG|TRACE)\b")
_SEV_RANK = {"fatal": 5, "error": 4, "warning": 3, "warn": 3, "info": 2, "debug": 1, "trace": 0}


class TextCompressor:
    name = "text"

    def __init__(self, log_mode: bool = False):
        self.log_mode = log_mode

    def compress(self, text: str, aggressiveness: float = 0.5) -> str:
        if not text:
            return text
        if self.log_mode:
            return self._compress_log(text, aggressiveness)
        out = _WS.sub(" ", text)
        out = _BLANK_RUN.sub("\n\n", out)
        return out.strip()

    def _compress_log(self, text: str, aggressiveness: float) -> str:
        lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
        # de-duplicate identical lines, remembering how many times each appeared
        seen: "OrderedDict[str, int]" = OrderedDict()
        for ln in lines:
            seen[ln] = seen.get(ln, 0) + 1

        deduped = []
        for ln, n in seen.items():
            deduped.append(f"{ln}  (×{n})" if n > 1 else ln)

        # at moderate+ aggressiveness, keep only WARN and above (the signal)
        if aggressiveness >= 0.5:
            kept = []
            for ln in deduped:
                m = _SEVERITY.search(ln)
                if not m or _SEV_RANK.get(m.group(1).lower(), 2) >= 3:
                    kept.append(ln)
            dropped = len(deduped) - len(kept)
            if dropped > 0:
                kept.append(f"… {dropped} lower-severity log line(s) elided …")
            deduped = kept

        return "\n".join(deduped)
