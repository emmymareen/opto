"""Code/diff compressor.

Copilot context is dominated by source files and diffs. This compressor removes
the low-signal parts a model rarely needs verbatim — comment blocks, blank-line
runs, and long unchanged hunks — while preserving signatures and structure.

For Python it uses the standard-library AST to do structure-aware compression:
it keeps imports, class/function signatures, decorators, and docstring first
lines, and collapses function bodies to a placeholder. This is far safer and more
effective than regex because it understands the code. For other languages (and if
the Python source doesn't parse) it falls back to the conservative regex path.
The reversible cache always holds the original for exact retrieval.
"""

from __future__ import annotations

import ast
import re

_BLANK_RUN = re.compile(r"\n[ \t]*\n[ \t]*\n+")
_TRAILING_WS = re.compile(r"[ \t]+\n")
# whole-line comments for common languages
_LINE_COMMENT = re.compile(r"^\s*(#|//|--)\s?.*$")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def _looks_like_diff(text: str) -> bool:
    head = text[:2000]
    return ("@@ " in head) or head.startswith(("diff --git", "--- ", "+++ "))


class CodeCompressor:
    name = "code"

    def _compress_python_ast(self, source: str) -> str | None:
        """Return a structure-only view of Python source, or None if it can't be
        parsed (callers fall back to regex). Keeps imports, signatures, decorators
        and docstring first lines; replaces bodies with a one-line placeholder."""
        try:
            tree = ast.parse(source)
        except (SyntaxError, ValueError):
            return None

        lines: list[str] = []

        def render(node: ast.AST, indent: int) -> None:
            pad = "    " * indent
            for child in getattr(node, "body", []):
                if isinstance(child, (ast.Import, ast.ImportFrom)):
                    try:
                        lines.append(pad + ast.unparse(child))
                    except Exception:
                        pass
                elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    for dec in child.decorator_list:
                        try:
                            lines.append(pad + "@" + ast.unparse(dec))
                        except Exception:
                            pass
                    prefix = "async def" if isinstance(child, ast.AsyncFunctionDef) else "def"
                    try:
                        args = ast.unparse(child.args)
                    except Exception:
                        args = "..."
                    lines.append(f"{pad}{prefix} {child.name}({args}):")
                    doc = ast.get_docstring(child)
                    if doc:
                        lines.append(f'{pad}    """{doc.splitlines()[0]}"""')
                    lines.append(f"{pad}    ...  # opto: body elided")
                elif isinstance(child, ast.ClassDef):
                    for dec in child.decorator_list:
                        try:
                            lines.append(pad + "@" + ast.unparse(dec))
                        except Exception:
                            pass
                    try:
                        bases = ", ".join(ast.unparse(b) for b in child.bases)
                    except Exception:
                        bases = ""
                    header = f"{pad}class {child.name}" + (f"({bases})" if bases else "") + ":"
                    lines.append(header)
                    doc = ast.get_docstring(child)
                    if doc:
                        lines.append(f'{pad}    """{doc.splitlines()[0]}"""')
                    render(child, indent + 1)
                elif isinstance(child, ast.Assign):
                    # keep module/class-level constants (often referenced)
                    try:
                        lines.append(pad + ast.unparse(child))
                    except Exception:
                        pass

        render(tree, 0)
        if not lines:
            return None
        return "\n".join(lines)

    def compress(self, text: str, aggressiveness: float = 0.5) -> str:
        if not text:
            return text

        # Structure-aware path for Python at higher aggressiveness.
        if aggressiveness >= 0.5 and not _looks_like_diff(text):
            ast_out = self._compress_python_ast(text)
            if ast_out is not None and len(ast_out) < len(text):
                return ast_out

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
        if not any(ln.startswith(("+", "-", "@@")) for ln in lines):
            return text
        keep = [False] * len(lines)
        for i, ln in enumerate(lines):
            if ln.startswith(("+", "-", "@@", "diff ", "index ")):
                for j in range(max(0, i - context), min(len(lines), i + context + 1)):
                    keep[j] = True
        out, folded = [], 0
        for i, ln in enumerate(lines):
            if keep[i]:
                if folded:
                    out.append(f"  … {folded} unchanged line(s) …")
                    folded = 0
                out.append(ln)
            else:
                folded += 1
        if folded:
            out.append(f"  … {folded} unchanged line(s) …")
        return "\n".join(out)
