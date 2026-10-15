"""Tests for what ``fix`` says about the violations it cannot resolve.

An E501 that survives ``ruff format`` is one the formatter has nowhere
to break, and the raw ``Line too long`` reads as a misconfigured
``line-length``. These tests pin the classification of the overflowing
token, the split between "no autofix" and "``--unsafe`` would fix it",
and — against the real ruff — that ``fix`` names the line and the action
while keeping the exit code non-zero.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tempest_cli import lint, residuals
from tempest_cli.config import TempestConfig

DOTTED = "notifications.NOTIFICATION_USER_BODY_ALO_STATUS_CHANGE_WAITING"

CASE_SOURCE = f"""import notifications


def pick(kind: str) -> str:
    match kind:
        case "waiting":
            if kind:
                user_template = (
                    {DOTTED}
                )
                return user_template
    return kind
"""
"""The ``alofans-api`` case from issue #3: a parenthesised dotted name."""


def _diagnostic(
    path: Path,
    row: int,
    *,
    code: str = "E501",
    column: int = 80,
    fix: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one entry of ruff's JSON report.

    Args:
        path (Path): The reported file.
        row (int): 1-based line number.
        code (str): The rule code.
        column (int): 1-based column of the violation.
        fix (dict[str, Any] | None): The ``fix`` object, or ``None``.

    Returns:
        dict[str, Any]: The diagnostic.
    """
    return {
        "code": code,
        "filename": str(path),
        "location": {"row": row, "column": column},
        "fix": fix,
    }


def test_dotted_name_is_named_whole() -> None:
    source = f"x = 1\n                user_template = {DOTTED}\n"
    kind, token = residuals.classify_overflow(source, 2, 80)
    assert kind == "dotted-name"
    assert token == DOTTED


def test_single_long_name_is_a_name() -> None:
    name = "a" * 90
    kind, token = residuals.classify_overflow(f"x = {name}\n", 1, 80)
    assert (kind, token) == ("name", name)


def test_string_literal_is_a_string() -> None:
    literal = '"' + "a" * 50 + " " + "b" * 40 + '"'
    kind, token = residuals.classify_overflow(f"text = {literal}\n", 1, 80)
    assert (kind, token) == ("string", literal)


def test_line_inside_a_triple_quoted_string_is_a_string() -> None:
    source = 'x = """\n' + "word " * 20 + '\n"""\n'
    kind, _token = residuals.classify_overflow(source, 2, 80)
    assert kind == "string"


def test_comment_is_a_comment() -> None:
    comment = "# " + "word " * 20
    kind, token = residuals.classify_overflow(f"x = 1  {comment}\n", 1, 80)
    assert (kind, token) == ("comment", comment)


def test_anything_else_is_an_expression() -> None:
    source = "x = (" + "1 + " * 30 + "1)\n"
    kind, token = residuals.classify_overflow(source, 1, 80)
    assert (kind, token) == ("expression", "")


def test_source_that_does_not_tokenize_is_an_expression() -> None:
    assert residuals.classify_overflow("x = (\n", 1, 3) == ("expression", "")


def test_residuals_split_by_what_can_still_fix_them(tmp_path: Path) -> None:
    module = tmp_path / "mod.py"
    module.write_text(f"x = 1\n                user_template = {DOTTED}\n")
    report = json.dumps(
        [
            _diagnostic(module, 2),
            _diagnostic(module, 1, code="F841", fix={"applicability": "unsafe"}),
            _diagnostic(module, 1, code="X1", fix={"applicability": "display-only"}),
            _diagnostic(module, 1, code="X2", fix={"applicability": "safe"}),
        ]
    )
    found = residuals.collect_residuals(report)
    assert found is not None
    assert (found.manual, found.unsafe, found.safe) == (2, 1, 1)
    assert found.long_lines == [
        residuals.LongLine(path=str(module), row=2, kind="dotted-name", token=DOTTED)
    ]
    text = residuals.render_residuals(found)
    assert f"[dotted-name] `{DOTTED}`" in text
    assert residuals.ADVICE["dotted-name"] in text
    assert "4 residual violation(s): 2 with no autofix" in text
    assert "1 fixable with `fix --unsafe`" in text
    assert "1 with a fix marked unfixable in config" in text


def test_unreadable_file_is_an_expression(tmp_path: Path) -> None:
    report = json.dumps([_diagnostic(tmp_path / "gone.py", 3)])
    found = residuals.collect_residuals(report)
    assert found is not None
    assert found.long_lines[0].kind == "expression"


def test_report_that_is_not_ruff_json_is_ignored() -> None:
    assert residuals.collect_residuals("not json") is None
    assert residuals.collect_residuals("{}") is None


def test_nothing_left_renders_nothing() -> None:
    empty = residuals.Residuals(long_lines=[], manual=0, unsafe=0, safe=0)
    assert residuals.render_residuals(empty) == ""


def test_clean_report_skips_the_json_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda name, path=None: None if path else name)
    monkeypatch.setattr(subprocess, "call", lambda *_a, **_k: 0)

    def never_run(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("the JSON pass ran on a clean report")

    monkeypatch.setattr(subprocess, "run", never_run)
    assert lint.run_ruff_fix("src", config=TempestConfig()) == 0


def test_missing_ruff_stops_before_formatting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name, path=None: None)
    assert lint.run_ruff_fix("src") == lint.MISSING_TOOL_EXIT_CODE


def test_fix_names_the_unbreakable_line_and_still_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[tool.ruff]\nline-length = 79\n\n[tool.ruff.lint]\nselect = ["E"]\n'
    )
    module = tmp_path / "mod.py"
    module.write_text(CASE_SOURCE)
    monkeypatch.chdir(tmp_path)

    code = lint.run_ruff_fix(
        "mod.py", config=TempestConfig(typing_strictness="lenient")
    )

    err = capfd.readouterr().err
    assert code != 0
    assert DOTTED in module.read_text().splitlines()[7]
    assert f"mod.py:8 [dotted-name] `{DOTTED}`" in err
    assert residuals.ADVICE["dotted-name"] in err
    assert "1 residual violation(s): 1 with no autofix" in err
