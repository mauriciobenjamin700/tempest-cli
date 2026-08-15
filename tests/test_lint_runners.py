"""Tests for the runners: what argv each command actually builds.

The gate is a thin layer over three tools, so what matters is the exact
command line it hands them — the strictness flags, the argument order,
and the exit code coming straight back. Every test here captures argv
instead of running ruff or mypy for real.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import Any

import pytest

from tempest_cli import lint
from tempest_cli.config import TempestConfig


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Capture every argv the runners would execute.

    Args:
        monkeypatch (pytest.MonkeyPatch): Pytest's patcher.

    Returns:
        list[list[str]]: The captured argv lists, in call order.
    """
    captured: list[list[str]] = []

    def fake_call(argv: list[str], **_kwargs: Any) -> int:
        captured.append(argv)
        return 0

    monkeypatch.setattr(subprocess, "call", fake_call)
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    return captured


def test_ruff_check_passes_ann_rules_of_the_level(calls: list[list[str]]) -> None:
    lint.run_ruff_check("src", config=TempestConfig(typing_strictness="strict"))
    argv = calls[0]
    assert argv[0].endswith("ruff")
    assert argv[1] == "check"
    assert "--extend-select" in argv
    codes = argv[argv.index("--extend-select") + 1]
    assert "ANN204" in codes
    assert "ANN401" not in codes
    assert argv[-1] == "src"


def test_lenient_adds_no_ann_rules(calls: list[list[str]]) -> None:
    lint.run_ruff_check("src", config=TempestConfig(typing_strictness="lenient"))
    assert "--extend-select" not in calls[0]


def test_ruff_fix_runs_check_then_format(calls: list[list[str]]) -> None:
    lint.run_ruff_fix("src", unsafe=False, config=TempestConfig())
    assert [argv[1] for argv in calls] == ["check", "format"]
    assert "--fix" in calls[0]
    assert "--unsafe-fixes" not in calls[0]


def test_unsafe_opts_into_the_risky_autofixes(calls: list[list[str]]) -> None:
    lint.run_ruff_fix("src", unsafe=True, config=TempestConfig())
    assert "--unsafe-fixes" in calls[0]


def test_format_check_is_read_only(calls: list[list[str]]) -> None:
    lint.run_ruff_format("src", check=True)
    assert "--check" in calls[0]
    lint.run_ruff_format("src", check=False)
    assert "--check" not in calls[1]


def test_mypy_flags_follow_the_level(calls: list[list[str]]) -> None:
    lint.run_mypy("pkg", config=TempestConfig(typing_strictness="strict"))
    assert "--strict" in calls[0]
    calls.clear()
    lint.run_mypy("pkg", config=TempestConfig(typing_strictness="standard"))
    assert "--disallow-untyped-defs" in calls[0]
    assert "--strict" not in calls[0]


def test_pytest_forwards_an_optional_path(calls: list[list[str]]) -> None:
    lint.run_pytest(None)
    assert calls[0][1:] == []
    calls.clear()
    lint.run_pytest("tests/unit")
    assert calls[0][-1] == "tests/unit"


def test_full_check_runs_the_four_gates_in_order(calls: list[list[str]]) -> None:
    exit_code = lint.run_full_check("src", config=TempestConfig())
    assert exit_code == 0
    tools = [argv[0].rsplit("/", 1)[-1] for argv in calls]
    assert tools == ["ruff", "ruff", "mypy", "pytest"]


def test_full_check_stops_at_the_first_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failing lint must not be followed by three more tool runs."""
    seen: list[str] = []

    def fake_call(argv: list[str], **_kwargs: Any) -> int:
        seen.append(argv[0])
        return 1

    monkeypatch.setattr(subprocess, "call", fake_call)
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    assert lint.run_full_check("src", config=TempestConfig()) == 1
    assert len(seen) == 1


def test_exit_code_comes_straight_back(monkeypatch: pytest.MonkeyPatch) -> None:
    """CI reads this the way it would read ruff itself."""
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(subprocess, "call", lambda *_a, **_k: 3)
    assert lint.run_ruff_check("src") == 3


def test_falls_back_to_uv_run_when_the_tool_is_not_on_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A project venv that was never activated still works."""
    captured: list[list[str]] = []
    monkeypatch.setattr(
        shutil,
        "which",
        lambda name: "/usr/bin/uv" if name == "uv" else None,
    )

    def fake_call(argv: list[str], **_kwargs: Any) -> int:
        captured.append(argv)
        return 0

    monkeypatch.setattr(subprocess, "call", fake_call)
    lint.run_ruff_check("src")
    assert captured[0][:3] == ["/usr/bin/uv", "run", "ruff"]


def test_missing_tool_reports_127(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neither the tool nor uv: a named failure, not a traceback."""
    monkeypatch.setattr(shutil, "which", lambda _name: None)

    def never_called(*_args: Any, **_kwargs: Any) -> int:
        """Fail if a runner is reached with no tool available."""
        pytest.fail("subprocess.call should not run when nothing resolves")

    monkeypatch.setattr(subprocess, "call", never_called)
    assert lint.run_ruff_check("src") == 127
