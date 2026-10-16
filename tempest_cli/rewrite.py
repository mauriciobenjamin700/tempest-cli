"""Shorten the long lines ``ruff format`` leaves alone, when it is safe to.

Two of the overflows :mod:`tempest_cli.residuals` names have one right
answer that never changes what the program does, and the formatter keeps
it once written:

- **comments** are wrapped at the limit — a trailing one first moves to
  its own lines above the code it annotates;
- **string literals** are split at their spaces into implicitly
  concatenated parts inside parentheses, which Python joins back into
  the very same value.

Everything else — a dotted name, a single long name, an expression —
needs a decision (an alias, a table, a rename), and splitting it by hand
is undone by the next ``ruff format``, so it is left to the explanation.

Every rewrite is proven before it is written: the file is parsed before
and after, and the edit is kept only when both ASTs are identical.
Comments do not reach the AST and implicit concatenation is folded into
one constant by the parser, so a correct rewrite always passes; anything
else — an escape sequence cut in half, a comment pushed into a
backslash continuation — fails the check and the line is left as it
was.

Internal to the ``fix`` command; not part of the public surface.
"""

from __future__ import annotations

import ast
import io
import re
import textwrap
import tokenize
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from tempest_cli.residuals import LINE_TOO_LONG, display_path, parse_report

RewriteKind = Literal["comment", "string"]
"""What a rewrite changed on a long line."""

PRAGMA = re.compile(
    r"\b(noqa|type:\s*ignore|fmt:|pragma|pyright:|mypy:|ruff:|isort:|nosec|pylint:)",
    re.IGNORECASE,
)
"""Comments addressed to a tool, which must stay on the line they govern."""

ENCODING_COOKIE = re.compile(r"coding[:=]")
"""The PEP 263 encoding declaration, valid only on the first two lines."""

COMMENT_MARKER = re.compile(r"#+:?")
"""The leading ``#`` run of a comment, ``#:`` attribute docs included."""

STRING_PREFIXES: frozenset[str] = frozenset({"", "r", "b", "u", "br", "rb"})
"""Lower-cased prefixes of the literals that are split; f/t-strings are not."""

STRING_INDENT = 4
"""Indentation ``ruff format`` gives the parts of a parenthesized string."""


@dataclass(frozen=True)
class Rewrite:
    """A long line shortened in place.

    Attributes:
        path (str): File holding the line, as ruff reported it.
        row (int): 1-based number of the line before the rewrite.
        kinds (tuple[RewriteKind, ...]): What was changed on it.
    """

    path: str
    row: int
    kinds: tuple[RewriteKind, ...]


def _same_program(before: ast.Module, source: str) -> bool:
    """Tell whether ``source`` parses to the same AST as ``before``.

    Args:
        before (ast.Module): The original file's AST.
        source (str): The rewritten file.

    Returns:
        bool: True when ``source`` parses and its AST dump matches.
    """
    try:
        after = ast.parse(source)
    except (SyntaxError, ValueError):
        return False
    return ast.dump(after) == ast.dump(before)


def _indent_of(line: str) -> str:
    """Return the leading whitespace of ``line``.

    Args:
        line (str): A physical line.

    Returns:
        str: Its indentation.
    """
    return line[: len(line) - len(line.lstrip())]


def _wrap_comment(
    comment: str,
    indent: str,
    limit: int,
) -> list[str] | None:
    """Wrap one comment into lines no longer than ``limit``.

    Args:
        comment (str): The comment token, ``#`` included.
        indent (str): Indentation every wrapped line starts with.
        limit (int): Maximum line length.

    Returns:
        list[str] | None: The wrapped lines, without line endings, or
        ``None`` when the comment is a tool pragma, has no text, or holds
        a word too long to fit.
    """
    if PRAGMA.search(comment):
        return None
    marker_match = COMMENT_MARKER.match(comment)
    if marker_match is None:
        return None
    marker = marker_match.group() + " "
    body = comment[marker_match.end() :].strip()
    width = limit - len(indent) - len(marker)
    if not body or width <= 0:
        return None
    wrapped = textwrap.wrap(
        body,
        width=width,
        break_long_words=False,
        break_on_hyphens=False,
    )
    if any(len(part) > width for part in wrapped):
        return None
    return [f"{indent}{marker}{part}" for part in wrapped]


def _split_string(
    token: tokenize.TokenInfo,
    indent: str,
    limit: int,
) -> str | None:
    """Split a string literal into parenthesized, concatenated parts.

    Each part ends at a space and keeps it, so the parts concatenate to
    the original value. A part never ends in a backslash, which keeps a
    raw string's last quote unescaped.

    Args:
        token (tokenize.TokenInfo): A single-line ``STRING`` token.
        indent (str): Indentation of the line the literal sits on.
        limit (int): Maximum line length.

    Returns:
        str | None: The replacement text, newlines included, or ``None``
        when the literal is triple-quoted, an f/t-string, has no space to
        split at, or holds a word too long for one part.
    """
    text = token.string
    quote_at = next((i for i, char in enumerate(text) if char in "'\""), -1)
    prefix = text[:quote_at]
    quote = text[quote_at] if quote_at >= 0 else ""
    if (
        quote_at < 0
        or prefix.lower() not in STRING_PREFIXES
        or text[quote_at : quote_at + 3] == quote * 3
    ):
        return None
    body = text[quote_at + 1 : -1]
    part_indent = indent + " " * STRING_INDENT
    width = limit - len(part_indent) - len(prefix) - 2 - 1
    words = re.findall(r"\S+\s*|\s+", body)
    parts: list[str] = []
    current = ""
    for word in words:
        if current and len(current) + len(word) > width:
            parts.append(current)
            current = ""
        current += word
    parts.append(current)
    if len(parts) < 2 or any(len(part) > width for part in parts):
        return None
    lines = [f"{part_indent}{prefix}{quote}{part}{quote}" for part in parts]
    return "(\n" + "\n".join(lines) + f"\n{indent})"


def _apply_split(
    source: str,
    token: tokenize.TokenInfo,
    replacement: str,
) -> list[str]:
    """Put a split string in place of its token on one line.

    Args:
        source (str): The line, or the code part of it before a comment.
        token (tokenize.TokenInfo): The string token being replaced.
        replacement (str): The text from :func:`_split_string`.

    Returns:
        list[str]: The resulting physical lines.
    """
    start, end = token.start[1], token.end[1]
    return (source[:start] + replacement + source[end:]).split("\n")


def _nested_in_fstring(tokens: Sequence[tokenize.TokenInfo]) -> set[int]:
    """Find the tokens that sit inside an f-string or t-string.

    From Python 3.12 the tokenizer yields the literals inside a
    replacement field as tokens of their own. Splitting one of them puts
    a newline inside the field, which parses on 3.12 but not on 3.11 —
    the AST check would pass on the interpreter running the CLI while
    breaking the project's own floor.

    Args:
        tokens (Sequence[tokenize.TokenInfo]): Every token of the file.

    Returns:
        set[int]: Indexes, into ``tokens``, of the nested tokens.
    """
    nested: set[int] = set()
    depth = 0
    for index, token in enumerate(tokens):
        name = tokenize.tok_name[token.type]
        if name.endswith("STRING_START"):
            depth += 1
        elif name.endswith("STRING_END"):
            depth -= 1
        elif depth:
            nested.add(index)
    return nested


def _candidates(
    line: str,
    tokens: Sequence[tokenize.TokenInfo],
    limit: int,
) -> list[tuple[list[str], tuple[RewriteKind, ...]]]:
    """List the ways to shorten one long line, most complete first.

    Args:
        line (str): The physical line, without its line ending.
        tokens (Sequence[tokenize.TokenInfo]): The tokens that start and
            end on this line.
        limit (int): Maximum line length.

    Returns:
        list[tuple[list[str], tuple[RewriteKind, ...]]]: Each candidate
        replacement, as lines without endings, with what it changed.
    """
    comment = next(
        (t for t in tokens if t.type == tokenize.COMMENT and t.end[1] > limit),
        None,
    )
    code = line
    comment_lines: list[str] | None = None
    if comment is not None:
        before = line[: comment.start[1]]
        indent = _indent_of(line)
        comment_lines = _wrap_comment(comment.string, indent, limit)
        if comment_lines is not None and before.strip():
            code = before.rstrip()
        elif comment_lines is not None:
            code = ""
    string_text: str | None = None
    string_token: tokenize.TokenInfo | None = None
    if len(code) > limit:
        string_token = next(
            (
                t
                for t in tokens
                if t.type == tokenize.STRING
                and t.end[1] > limit
                and t.end[1] <= len(code)
            ),
            None,
        )
        if string_token is not None:
            string_text = _split_string(string_token, _indent_of(line), limit)

    found: list[tuple[list[str], tuple[RewriteKind, ...]]] = []
    if comment_lines is not None and string_token and string_text is not None:
        split_code = _apply_split(code, string_token, string_text)
        found.append(([*comment_lines, *split_code], ("comment", "string")))
    if comment_lines is not None:
        found.append(([*comment_lines, *([code] if code else [])], ("comment",)))
    if string_token is not None and string_text is not None:
        found.append((_apply_split(line, string_token, string_text), ("string",)))
    return found


def rewrite_source(
    source: str,
    targets: Sequence[tuple[int, int]],
) -> tuple[str, list[tuple[int, tuple[RewriteKind, ...]]]]:
    """Shorten the given long lines of one file where that is safe.

    Args:
        source (str): The whole file.
        targets (Sequence[tuple[int, int]]): ``(row, limit)`` per long
            line — the 1-based row and the line length it must fit in.

    Returns:
        tuple[str, list[tuple[int, tuple[RewriteKind, ...]]]]: The new
        source (``source`` itself when nothing changed) and the rows
        rewritten, with what changed on each.
    """
    try:
        original = ast.parse(source)
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except (SyntaxError, ValueError, tokenize.TokenError):
        return source, []
    nested = _nested_in_fstring(tokens)
    newline = "\r\n" if "\r\n" in source else "\n"
    lines = source.splitlines(keepends=True)
    done: list[tuple[int, tuple[RewriteKind, ...]]] = []
    for row, limit in sorted(set(targets), reverse=True):
        if not 1 <= row <= len(lines) or limit <= 0:
            continue
        if row <= 2 and ENCODING_COOKIE.search(lines[row - 1]):
            continue
        raw = lines[row - 1]
        ending = raw[len(raw.rstrip("\r\n")) :]
        line = raw[: len(raw) - len(ending)]
        on_row = [
            t
            for index, t in enumerate(tokens)
            if t.start[0] == row == t.end[0] and index not in nested
        ]
        for replacement, kinds in _candidates(line, on_row, limit):
            block = newline.join(replacement) + ending
            candidate = [*lines[: row - 1], block, *lines[row:]]
            if _same_program(original, "".join(candidate)):
                lines = candidate
                done.append((row, kinds))
                break
    return "".join(lines), sorted(done)


def rewrite_long_lines(report: str) -> list[Rewrite]:
    """Shorten, in place, every long line a ruff JSON report names.

    Files are read and written as UTF-8 with their line endings kept; a
    file that cannot be read or does not parse is left untouched.

    Args:
        report (str): ``ruff check --output-format json`` of the target,
            taken after ``ruff format``.

    Returns:
        list[Rewrite]: The lines rewritten, by file and row.
    """
    diagnostics = parse_report(report) or []
    targets: defaultdict[str, list[tuple[int, int]]] = defaultdict(list)
    for diagnostic in diagnostics:
        if diagnostic.get("code") != LINE_TOO_LONG:
            continue
        location = diagnostic.get("location") or {}
        targets[str(diagnostic.get("filename", ""))].append(
            (int(location.get("row", 0)), int(location.get("column", 0)) - 1)
        )
    rewrites: list[Rewrite] = []
    for path, rows in sorted(targets.items()):
        file = Path(path)
        try:
            with file.open(encoding="utf-8", newline="") as handle:
                source = handle.read()
        except (OSError, UnicodeDecodeError):
            continue
        new_source, done = rewrite_source(source, rows)
        if not done:
            continue
        with file.open("w", encoding="utf-8", newline="") as handle:
            handle.write(new_source)
        rewrites.extend(Rewrite(path=path, row=row, kinds=kinds) for row, kinds in done)
    return rewrites


def render_rewrites(rewrites: Sequence[Rewrite]) -> str:
    """Render the note ``fix`` prints about the lines it shortened.

    Args:
        rewrites (Sequence[Rewrite]): The lines rewritten.

    Returns:
        str: The text, ending in a newline, or an empty string when
        nothing was rewritten.
    """
    if not rewrites:
        return ""
    lines = [
        f"shortened {len(rewrites)} long line(s) ruff format cannot break "
        "(comments wrapped, strings split into concatenated parts):"
    ]
    lines.extend(
        f"  {display_path(item.path)}:{item.row} [{'+'.join(item.kinds)}]"
        for item in rewrites
    )
    return "\n".join(lines) + "\n"


__all__: list[str] = [
    "Rewrite",
    "RewriteKind",
    "render_rewrites",
    "rewrite_long_lines",
    "rewrite_source",
]
