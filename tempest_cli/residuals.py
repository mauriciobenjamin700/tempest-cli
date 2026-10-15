"""Explain what ``fix`` leaves behind once both ruff passes have run.

``ruff check`` reports a residual E501 the same way whether a line is
long because nobody ran the formatter or because the formatter ran and
found nowhere to break it. After ``fix`` only the second case is left,
and the bare ``Line too long (94 > 79)`` reads as a misconfigured
``line-length`` rather than as a limit of ``ruff format``. This module
turns ruff's JSON report into the explanation the raw diagnostic lacks:
which token overflows, why the formatter will not split it, and how many
residual violations have no autofix at all.

Internal to the ``fix`` command; not part of the public surface.
"""

from __future__ import annotations

import io
import json
import os
import tokenize
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

LINE_TOO_LONG = "E501"
"""Ruff code of the line-length rule this module reclassifies."""

OverflowKind = Literal["dotted-name", "name", "string", "comment", "expression"]
"""What sits at the column where a residual long line crosses the limit."""

STRING_TOKENS: frozenset[str] = frozenset(
    {
        "STRING",
        "FSTRING_START",
        "FSTRING_MIDDLE",
        "FSTRING_END",
        "TSTRING_START",
        "TSTRING_MIDDLE",
        "TSTRING_END",
    }
)
"""Token names that belong to a string literal, f-strings and t-strings included.

Looked up by name because the f-string tokens only exist from Python
3.12 and the t-string ones from 3.14.
"""

ADVICE: Mapping[OverflowKind, str] = {
    "dotted-name": (
        "ruff format never splits a dotted name, and drops parentheses that "
        "do not make the line fit. Shorten the expression: import or alias "
        "the attribute, move the choice into a table or constant, or lower "
        "the indentation."
    ),
    "name": (
        "ruff format cannot split a single name. Rename it, or lower the "
        "indentation it sits at."
    ),
    "string": (
        "ruff format does not split string literals. Break it into "
        "implicitly concatenated parts inside parentheses."
    ),
    "comment": (
        "ruff format does not wrap comments. Wrap it by hand, or move the "
        "explanation into the docstring."
    ),
    "expression": (
        "ruff format found no split point on this line. Restructure the "
        "expression: extract a variable or lower the indentation."
    ),
}
"""The action suggested for each kind of overflow."""


@dataclass(frozen=True)
class LongLine:
    """A residual E501 classified by the token that overflows.

    Attributes:
        path (str): File holding the line, as ruff reported it.
        row (int): 1-based line number.
        kind (OverflowKind): What sits at the overflow column.
        token (str): The overflowing token — the whole dotted chain for a
            dotted name — or an empty string when there is none to show.
    """

    path: str
    row: int
    kind: OverflowKind
    token: str


@dataclass(frozen=True)
class Residuals:
    """Residual violations split by what can still fix them.

    Attributes:
        long_lines (list[LongLine]): Every E501, classified.
        manual (int): Violations with no autofix at all.
        unsafe (int): Violations ``fix --unsafe`` would resolve.
        safe (int): Violations with a safe fix ruff was told not to apply
            (an ``unfixable`` entry in the project's ruff config).
    """

    long_lines: list[LongLine]
    manual: int
    unsafe: int
    safe: int


def _dotted_chain(
    tokens: Sequence[tokenize.TokenInfo],
    index: int,
) -> list[tokenize.TokenInfo]:
    """Collect the run of adjacent ``NAME`` / ``.`` tokens around ``index``.

    Adjacent means no whitespace between them: ``a.b.c`` is one chain,
    ``a . b`` is not — the formatter treats the latter the same way, but
    the token text would no longer be what the reader typed.

    Args:
        tokens (Sequence[tokenize.TokenInfo]): Tokens of one physical line.
        index (int): Position of a ``NAME`` or ``.`` token in ``tokens``.

    Returns:
        list[tokenize.TokenInfo]: The chain, in source order.
    """

    def links(token: tokenize.TokenInfo) -> bool:
        """Tell whether ``token`` can be part of a dotted chain.

        Args:
            token (tokenize.TokenInfo): The token to test.

        Returns:
            bool: True for a ``NAME`` or a ``.`` operator.
        """
        return token.type == tokenize.NAME or token.string == "."

    start = index
    while (
        start > 0
        and links(tokens[start - 1])
        and tokens[start - 1].end == tokens[start].start
    ):
        start -= 1
    end = index
    while (
        end + 1 < len(tokens)
        and links(tokens[end + 1])
        and tokens[end].end == tokens[end + 1].start
    ):
        end += 1
    return list(tokens[start : end + 1])


def classify_overflow(
    source: str,
    row: int,
    column: int,
) -> tuple[OverflowKind, str]:
    """Classify the token sitting where a long line crosses the limit.

    Args:
        source (str): The whole file, as the formatter left it.
        row (int): 1-based line number of the long line.
        column (int): 1-based column of the first character past the
            limit — the ``location.column`` ruff reports for E501.

    Returns:
        tuple[OverflowKind, str]: The kind and the token text. A file
        that does not tokenize, or a column past every token, comes back
        as ``("expression", "")``.
    """
    offset = column - 1
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except (tokenize.TokenError, SyntaxError):
        return "expression", ""
    for token in tokens:
        if tokenize.tok_name[token.type] in STRING_TOKENS and (
            token.start[0] < row <= token.end[0]
        ):
            return "string", token.string.splitlines()[0]
    line = [token for token in tokens if token.start[0] == row == token.end[0]]
    for index, token in enumerate(line):
        if token.end[1] <= offset:
            continue
        name = tokenize.tok_name[token.type]
        if name == "COMMENT":
            return "comment", token.string
        if name in STRING_TOKENS:
            return "string", token.string
        if token.type == tokenize.NAME or token.string == ".":
            chain = _dotted_chain(line, index)
            text = "".join(part.string for part in chain)
            return ("dotted-name" if "." in text else "name"), text
        return "expression", ""
    return "expression", ""


def _applicability(diagnostic: Mapping[str, Any]) -> str:
    """Read how a diagnostic's fix may be applied.

    Args:
        diagnostic (Mapping[str, Any]): One entry of ruff's JSON report.

    Returns:
        str: ``"safe"``, ``"unsafe"``, or ``"none"`` for no fix or a
        display-only one.
    """
    fix = diagnostic.get("fix")
    if not isinstance(fix, Mapping):
        return "none"
    applicability = fix.get("applicability")
    if applicability in ("safe", "unsafe"):
        return str(applicability)
    return "none"


def collect_residuals(report: str) -> Residuals | None:
    """Parse ``ruff check --output-format json`` into :class:`Residuals`.

    Each E501 file is read once, as the formatter left it, to classify
    the overflowing token; a file that cannot be read is classified as
    ``expression``.

    Args:
        report (str): ruff's JSON report.

    Returns:
        Residuals | None: The split, or ``None`` when ``report`` is not
        the JSON list ruff writes.
    """
    try:
        diagnostics = json.loads(report)
    except json.JSONDecodeError:
        return None
    if not isinstance(diagnostics, list):
        return None
    sources: dict[str, str | None] = {}
    long_lines: list[LongLine] = []
    counts: dict[str, int] = {"none": 0, "unsafe": 0, "safe": 0}
    for diagnostic in diagnostics:
        if not isinstance(diagnostic, Mapping):
            continue
        counts[_applicability(diagnostic)] += 1
        if diagnostic.get("code") != LINE_TOO_LONG:
            continue
        path = str(diagnostic.get("filename", ""))
        location = diagnostic.get("location") or {}
        row = int(location.get("row", 0))
        column = int(location.get("column", 0))
        if path not in sources:
            try:
                sources[path] = Path(path).read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                sources[path] = None
        source = sources[path]
        kind, token = (
            classify_overflow(source, row, column)
            if source is not None
            else ("expression", "")
        )
        long_lines.append(LongLine(path=path, row=row, kind=kind, token=token))
    return Residuals(
        long_lines=long_lines,
        manual=counts["none"],
        unsafe=counts["unsafe"],
        safe=counts["safe"],
    )


def _display_path(path: str) -> str:
    """Shorten ``path`` to a cwd-relative form when it lives below the cwd.

    Args:
        path (str): The path ruff reported (absolute).

    Returns:
        str: The relative path, or ``path`` unchanged when it is outside
        the working directory or on another drive.
    """
    try:
        relative = os.path.relpath(path)
    except ValueError:
        return path
    return path if relative.startswith("..") else relative


def render_residuals(residuals: Residuals) -> str:
    """Render the explanation ``fix`` prints after ruff's own report.

    Args:
        residuals (Residuals): The parsed residual violations.

    Returns:
        str: The text, ending in a newline, or an empty string when
        there is nothing to explain.
    """
    total = residuals.manual + residuals.unsafe + residuals.safe
    if total == 0:
        return ""
    lines: list[str] = []
    if residuals.long_lines:
        lines.append(
            f"{len(residuals.long_lines)} line(s) still too long after "
            "ruff format — the line-length setting was applied; the "
            "formatter has nowhere to break these:"
        )
        for long_line in residuals.long_lines:
            shown = f" `{long_line.token}`" if long_line.token else ""
            lines.append(
                f"  {_display_path(long_line.path)}:{long_line.row} "
                f"[{long_line.kind}]{shown}"
            )
            lines.append(f"    {ADVICE[long_line.kind]}")
    parts = [f"{residuals.manual} with no autofix (edit by hand)"]
    if residuals.unsafe:
        parts.append(f"{residuals.unsafe} fixable with `fix --unsafe`")
    if residuals.safe:
        parts.append(f"{residuals.safe} with a fix marked unfixable in config")
    lines.append(f"{total} residual violation(s): {', '.join(parts)}.")
    return "\n".join(lines) + "\n"


__all__: list[str] = [
    "ADVICE",
    "LINE_TOO_LONG",
    "LongLine",
    "OverflowKind",
    "Residuals",
    "classify_overflow",
    "collect_residuals",
    "render_residuals",
]
