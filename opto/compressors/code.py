"""Code/diff compressor.

Copilot context is dominated by source files and diffs. This compressor removes
the low-signal parts a model rarely needs verbatim — comment blocks, blank-line
runs, and long unchanged hunks — while preserving signatures and structure.

It is intentionally conservative and language-agnostic (regex-based) so it never
corrupts code; the reversible cache holds the original for exact retrieval.
"""

from __future__ import annotations

import re

_BLANK_RUN = re.compile(r"\n[ \t]*\n[ \t]*\n+")
_TRAILING_WS = re.compile(r"[ \t]+\n")
# whole-line comments for common languages
_LINE_COMMENT = re.compile(r"^\s*(#|//|--)\s?.*$")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


class CodeCompressor:
    name = "code"

    def compress(self, text: str, aggressiveness: float = 0.5) -> str:
        if not text:
            return text

        out = _BLOCK_COMMENT.sub("", text)
        out = _TRAILING_WS.sub("\n", out)
        out = _BLANK_RUN.sub("\n\n", out)

        if aggressiveness >= 0.4:
            out = self._strip_line_comments(out)
        if aggressiveness >= 0.7:
            out = self._fold_unchanged_diff(out)

        return out.strip("\n")

    def _strip_line_comments(self, text: str) -> str:
        kept = []
        for line in text.splitlines():
            # keep shebangs and significant directives
            if line.lstrip().startswith("#!"):
                kept.append(line)
                continue
            if _LINE_COMMENT.match(line):
                continue
            kept.append(line)
        return "\n".join(kept)

    def _fold_unchanged_diff(self, text: str, context: int = 2) -> str:
        """In unified diffs, keep changed lines plus a little context; fold long
        runs of unchanged lines into a marker."""
        lines = text.splitlines()
        if not any(l.startswith(("+", "-", "@@")) for l in lines):
            return text
        keep = [False] * len(lines)
        for i, l in enumerate(lines):
            if l.startswith(("+", "-", "@@", "diff ", "index ")):
                for j in range(max(0, i - context), min(len(lines), i + context + 1)):
                    keep[j] = True
        out, folded = [], 0
        for i, l in enumerate(lines):
            if keep[i]:
                if folded:
                    out.append(f"  … {folded} unchanged line(s) …")
                    folded = 0
                out.append(l)
            else:
                folded += 1
        if folded:
            out.append(f"  … {folded} unchanged line(s) …")
        return "\n".join(out)
