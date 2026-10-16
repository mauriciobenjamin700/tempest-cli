"""Tests for the long lines ``fix`` shortens on its own.

Comments and string literals have one rewrite that never changes the
program; these tests pin that it happens, that it keeps the value and
the layout ``ruff format`` accepts, and that everything it cannot prove
safe — a pragma, an f-string, a comment inside a backslash continuation
— is left exactly as it was.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

from tempest_cli import lint, rewrite
from tempest_cli.config import TempestConfig

LIMIT = 79
"""Line length every fixture targets, as in issue #3."""

LONG_TEXT = "a" * 50 + " " + "b" * 20 + " " + "c" * 30
"""A string body with spaces, too long for one line at ``LIMIT``."""


def _value(source: str, name: str) -> object:
    """Evaluate the literal assigned to ``name`` in ``source``.

    Args:
        source (str): A module made of simple assignments.
        name (str): The target to look up.

    Returns:
        object: The assigned value.
    """
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and ast.unparse(node.targets[0]) == name:
            return ast.literal_eval(node.value)
    raise AssertionError(f"{name} is not assigned")


def _rewrite(source: str, *rows: int) -> tuple[str, list[tuple[int, tuple[str, ...]]]]:
    """Run :func:`rewrite.rewrite_source` on ``rows`` at :data:`LIMIT`.

    Args:
        source (str): The file.
        *rows (int): The long rows.

    Returns:
        tuple[str, list[tuple[int, tuple[str, ...]]]]: What
        :func:`rewrite.rewrite_source` returns.
    """
    new, done = rewrite.rewrite_source(source, [(row, LIMIT) for row in rows])
    return new, [(row, tuple(kinds)) for row, kinds in done]


def test_standalone_comment_is_wrapped() -> None:
    source = "def f() -> None:\n    # " + "word " * 20 + "\n    pass\n"
    new, done = _rewrite(source, 2)
    assert done == [(2, ("comment",))]
    comments = [line for line in new.splitlines() if line.strip().startswith("#")]
    assert len(comments) == 2
    assert all(line.startswith("    # ") and len(line) <= LIMIT for line in comments)
    assert " ".join(c.strip()[2:] for c in comments) == ("word " * 20).strip()


def test_trailing_comment_moves_above_its_line() -> None:
    source = "x = 1  # " + "note " * 16 + "\n"
    new, done = _rewrite(source, 1)
    assert done == [(1, ("comment",))]
    assert new.splitlines()[-1] == "x = 1"
    assert new.startswith("# note")


def test_pragma_comment_stays_put() -> None:
    source = "x = 1  # noqa: F401 " + "because " * 10 + "\n"
    assert _rewrite(source, 1) == (source, [])


def test_string_is_split_into_parts_with_the_same_value() -> None:
    source = f'x = "{LONG_TEXT}"\n'
    new, done = _rewrite(source, 1)
    assert done == [(1, ("string",))]
    assert _value(new, "x") == LONG_TEXT
    assert all(len(line) <= LIMIT for line in new.splitlines())


@pytest.mark.parametrize("prefix", ["r", "b", "rb"])
def test_raw_and_bytes_strings_keep_their_prefix(prefix: str) -> None:
    body = "a\\\\b " + LONG_TEXT
    source = f'x = {prefix}"{body}"\n'
    new, done = _rewrite(source, 1)
    assert done == [(1, ("string",))]
    assert _value(new, "x") == _value(source, "x")


@pytest.mark.parametrize(
    "literal",
    [
        f'f"{{y}} {LONG_TEXT}"',
        f'"""{LONG_TEXT}"""',
        '"' + "a" * 90 + '"',
    ],
    ids=["f-string", "triple-quoted", "no-space"],
)
def test_strings_it_cannot_prove_safe_are_left_alone(literal: str) -> None:
    source = f"y = 1\nx = {literal}\n"
    assert _rewrite(source, 2) == (source, [])


def test_string_inside_an_fstring_field_is_left_alone() -> None:
    source = f"x = f\"{{'{LONG_TEXT}'}}\"\n"
    assert _rewrite(source, 1) == (source, [])


def test_named_escape_is_never_cut() -> None:
    source = 'x = "' + "a" * 60 + ' \\N{LATIN SMALL LETTER A} end"\n'
    new, _done = _rewrite(source, 1)
    assert _value(new, "x") == _value(source, "x")


def test_comment_inside_a_backslash_continuation_is_left_alone() -> None:
    source = "x = 1 + \\\n    2  # " + "note " * 16 + "\n"
    assert _rewrite(source, 2) == (source, [])


def test_trailing_comment_and_string_on_one_line() -> None:
    source = f'x = "{LONG_TEXT}"  # why this text\n'
    new, done = _rewrite(source, 1)
    assert done == [(1, ("comment", "string"))]
    assert new.startswith("# why this text\n")
    assert _value(new, "x") == LONG_TEXT


def test_crlf_endings_are_kept() -> None:
    source = f'y = 1\r\nx = "{LONG_TEXT}"\r\n'
    new, done = _rewrite(source, 2)
    assert done
    assert "\n" not in new.replace("\r\n", "")


def test_source_that_does_not_parse_is_untouched() -> None:
    source = f'x = ("{LONG_TEXT}"\n'
    assert _rewrite(source, 1) == (source, [])


def test_encoding_cookie_is_never_wrapped() -> None:
    source = "# -*- coding: utf-8 -*- " + "x" * 30 + " " + "y" * 30 + "\n"
    assert _rewrite(source, 1) == (source, [])


def test_report_drives_the_rewrite_on_disk(tmp_path: Path) -> None:
    module = tmp_path / "mod.py"
    module.write_text(f'x = "{LONG_TEXT}"\n')
    report = json.dumps(
        [
            {
                "code": "E501",
                "filename": str(module),
                "location": {"row": 1, "column": LIMIT + 1},
            },
            {"code": "F401", "filename": str(module), "location": {"row": 1}},
        ]
    )
    done = rewrite.rewrite_long_lines(report)
    assert done == [rewrite.Rewrite(path=str(module), row=1, kinds=("string",))]
    assert _value(module.read_text(), "x") == LONG_TEXT
    text = rewrite.render_rewrites(done)
    assert "shortened 1 long line(s)" in text
    assert "mod.py:1 [string]" in text


def test_unreadable_file_in_the_report_is_skipped(tmp_path: Path) -> None:
    report = json.dumps(
        [{"code": "E501", "filename": str(tmp_path / "gone.py"), "location": {}}]
    )
    assert rewrite.rewrite_long_lines(report) == []
    assert rewrite.render_rewrites([]) == ""


def test_fix_shortens_strings_and_comments_and_passes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[tool.ruff]\nline-length = 79\n\n[tool.ruff.lint]\nselect = ["E"]\n'
    )
    module = tmp_path / "mod.py"
    module.write_text(
        "def pick(kind: str) -> str:\n"
        "    if kind:\n"
        "        if kind:\n"
        f'            text = "{LONG_TEXT}"  # the text\n'
        "            # " + "word " * 16 + "\n"
        "            return text\n"
        "    return kind\n"
    )
    monkeypatch.chdir(tmp_path)
    lenient = TempestConfig(typing_strictness="lenient")

    assert lint.run_ruff_fix("mod.py", config=lenient) == 0

    err = capfd.readouterr().err
    assert "shortened 2 long line(s)" in err
    namespace: dict[str, object] = {}
    exec(compile(module.read_text(), "mod.py", "exec"), namespace)
    pick = namespace["pick"]
    assert callable(pick)
    assert pick("x") == LONG_TEXT
    formatted = subprocess.run(
        [sys.executable, "-m", "ruff", "format", "--check", "mod.py"],
        capture_output=True,
        check=False,
    )
    assert formatted.returncode == 0
    assert lint.run_ruff_fix("mod.py", config=lenient) == 0
    assert "shortened" not in capfd.readouterr().err
