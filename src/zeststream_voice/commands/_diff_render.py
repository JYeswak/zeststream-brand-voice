"""Unified-diff renderer for the WRITE quadrant side-by-side view.

Uses :mod:`difflib` (stdlib) and opt-in ANSI colors. No third-party deps —
keeps ``zv rewrite`` usable over SSH and in CI without terminal quirks.

The renderer is intentionally line-granular (unified_diff), not word-level:
the killer-demo asks "what changed?" at the sentence/paragraph level, which
matches how clients read rewrites.
"""

from __future__ import annotations

import difflib
import os
import sys

# ANSI color codes (only applied when use_color=True).
_GREEN = "\033[32m"
_RED = "\033[31m"
_CYAN = "\033[36m"
_DIM = "\033[2m"
_RESET = "\033[0m"


def _supports_color(stream=None) -> bool:
    """Heuristic: honor NO_COLOR, require a TTY, allow FORCE_COLOR override."""
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    stream = stream or sys.stdout
    try:
        return stream.isatty()
    except Exception:
        return False


def render_diff(
    before: str,
    after: str,
    *,
    use_color: bool | None = None,
    before_label: str = "BEFORE",
    after_label: str = "AFTER",
    context: int = 3,
) -> str:
    """Return a unified diff string.

    Parameters
    ----------
    before, after:
        The two text blocks to compare.
    use_color:
        ``None`` autodetects (respects ``NO_COLOR`` / ``FORCE_COLOR`` / tty).
        Pass ``True`` / ``False`` to force.
    before_label, after_label:
        Shown in the diff header.
    context:
        Lines of unchanged context around each hunk (difflib default is 3).

    Returns
    -------
    str
        The rendered diff. Empty string if the two texts are identical.
    """
    if before == after:
        return ""

    if use_color is None:
        use_color = _supports_color()

    before_lines = before.splitlines(keepends=True)
    after_lines = after.splitlines(keepends=True)

    # splitlines(keepends=True) drops the final newline if the string didn't
    # end with one — that's fine for diffing. unified_diff handles the rest.
    diff_iter = difflib.unified_diff(
        before_lines,
        after_lines,
        fromfile=before_label,
        tofile=after_label,
        n=context,
    )

    out_parts: list[str] = []
    for line in diff_iter:
        # Ensure every emitted line ends with \n so terminal rendering is
        # well-formed even if the source text has missing trailing newlines.
        if not line.endswith("\n"):
            line = line + "\n"
        if not use_color:
            out_parts.append(line)
            continue
        if line.startswith("+++") or line.startswith("---"):
            out_parts.append(f"{_CYAN}{line}{_RESET}")
        elif line.startswith("@@"):
            out_parts.append(f"{_DIM}{line}{_RESET}")
        elif line.startswith("+"):
            out_parts.append(f"{_GREEN}{line}{_RESET}")
        elif line.startswith("-"):
            out_parts.append(f"{_RED}{line}{_RESET}")
        else:
            out_parts.append(line)
    return "".join(out_parts)
