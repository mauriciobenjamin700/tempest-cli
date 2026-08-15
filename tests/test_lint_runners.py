"""Tests for the runners: what argv each command actually builds.

The gate is a thin layer over three tools, so what matters is the exact
command line it hands them — the strictness flags, the argument order,
and the exit code coming straight back. Every test here captures argv
instead of running ruff or mypy for real.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from tempest_cli import lint
from tempest_cli.config import TempestConfig


def _on_path_only(name: str, path: str | None = None) -> str | None:
    """Resolve every tool on ``PATH`` and nothing inside an environment.

    Args:
        name (str): The command being looked up.
        path (str | None): The directory :func:`shutil.which` was scoped
            to, or ``None`` for a plain ``PATH`` lookup.

    Returns:
        str | None: ``/usr/bin/<name>`` for a ``PATH`` lookup, ``None``
        for a directory-scoped one.
    """
    return None if path is not None else f"/usr/bin/{name}"


def _uv_only(name: str, path: str | None = None) -> str | None:
    """Resolve only ``uv``, as on a machine with no tool installed anywhere.

    Args:
        name (str): The command being looked up.
        path (str | None): The directory the lookup was scoped to.

    Returns:
        str | None: ``/usr/bin/uv`` for an unscoped ``uv`` lookup, else
        ``None``.
    """
    return "/usr/bin/uv" if name == "uv" and path is None else None


def _capturing_call(captured: list[list[str]]) -> Callable[..., int]:
    """Build a :func:`subprocess.call` stand-in recording every argv.

    Args:
        captured (list[list[str]]): The list each call appends its argv
            to, in call order.

    Returns:
        Callable[..., int]: The stand-in, always reporting success.
    """

    def fake_call(argv: list[str], **_kwargs: Any) -> int:
        """Record ``argv`` instead of spawning anything."""
        captured.append(argv)
        return 0

    return fake_call


def _completed(returncode: int) -> Callable[..., subprocess.CompletedProcess[bytes]]:
    """Build a :func:`subprocess.run` stand-in with a fixed exit code.

    Args:
        returncode (int): The exit code the probe should report.

    Returns:
        Callable[..., subprocess.CompletedProcess[bytes]]: The stand-in.
    """

    def fake_run(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        """Answer the probe without running the shim."""
        return subprocess.CompletedProcess(args=[], returncode=returncode)

    return fake_run


def _shim_only(name: str, path: str | None = None) -> str | None:
    """Resolve every tool to a pyenv shim, as a version manager does.

    Args:
        name (str): The command being looked up.
        path (str | None): The directory the lookup was scoped to.

    Returns:
        str | None: ``/home/u/.pyenv/shims/<name>`` for a ``PATH``
        lookup, ``None`` for a directory-scoped one.
    """
    return None if path is not None else f"/home/u/.pyenv/shims/{name}"


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
    monkeypatch.setattr(shutil, "which", _on_path_only)
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
    monkeypatch.setattr(shutil, "which", _on_path_only)
    assert lint.run_full_check("src", config=TempestConfig()) == 1
    assert len(seen) == 1


def test_exit_code_comes_straight_back(monkeypatch: pytest.MonkeyPatch) -> None:
    """CI reads this the way it would read ruff itself."""
    monkeypatch.setattr(shutil, "which", _on_path_only)
    monkeypatch.setattr(subprocess, "call", lambda *_a, **_k: 3)
    assert lint.run_ruff_check("src") == 3


def test_falls_back_to_uv_run_when_the_tool_is_not_on_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A project venv that was never activated still works."""
    captured: list[list[str]] = []
    monkeypatch.setattr(shutil, "which", _uv_only)

    def fake_call(argv: list[str], **_kwargs: Any) -> int:
        captured.append(argv)
        return 0

    monkeypatch.setattr(subprocess, "call", fake_call)
    lint.run_ruff_check("src")
    assert captured[0][:5] == ["/usr/bin/uv", "run", "--with", "ruff", "ruff"]


def test_missing_tool_reports_127(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neither the tool nor uv: a named failure, not a traceback."""
    monkeypatch.setattr(shutil, "which", lambda _name, path=None: None)

    def never_called(*_args: Any, **_kwargs: Any) -> int:
        """Fail if a runner is reached with no tool available."""
        pytest.fail("subprocess.call should not run when nothing resolves")

    monkeypatch.setattr(subprocess, "call", never_called)
    assert lint.run_ruff_check("src") == 127


def test_the_project_environment_wins_over_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A tool in the run's own environment beats whatever PATH offers.

    PATH is global and, on a pyenv/asdf machine, points at shims for
    every interpreter version ever installed. The environment actually
    running the gate is the one whose ruff the project pinned.
    """
    monkeypatch.setattr(lint, "_environment_dirs", lambda: [Path("/proj/.venv/bin")])
    monkeypatch.setattr(
        shutil,
        "which",
        lambda name, path=None: (
            f"{path}/{name}" if path is not None else f"/home/u/.pyenv/shims/{name}"
        ),
    )
    captured: list[list[str]] = []
    monkeypatch.setattr(subprocess, "call", _capturing_call(captured))
    lint.run_ruff_check("src")
    assert captured[0][0] == "/proj/.venv/bin/ruff"


def test_a_dead_shim_is_skipped_in_favour_of_uv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`pyenv: ruff: command not found` must not be the gate's answer.

    pyenv installs a shim for every tool any installed version ever
    provided, so the shim is on PATH even when the selected version has
    no ruff. Running it prints that message and exits non-zero — the
    lookup has to notice and fall through to a runner that works.
    """
    monkeypatch.setattr(lint, "_environment_dirs", list)
    monkeypatch.setattr(
        shutil,
        "which",
        lambda name, path=None: (
            None
            if path is not None
            else ("/usr/bin/uv" if name == "uv" else f"/home/u/.pyenv/shims/{name}")
        ),
    )
    monkeypatch.setattr(subprocess, "run", _completed(127))
    captured: list[list[str]] = []
    monkeypatch.setattr(subprocess, "call", _capturing_call(captured))
    lint.run_ruff_check("src")
    assert captured[0][:5] == ["/usr/bin/uv", "run", "--with", "ruff", "ruff"]


def test_a_working_shim_is_used(monkeypatch: pytest.MonkeyPatch) -> None:
    """A shim that dispatches to a real ruff is a legitimate answer."""
    monkeypatch.setattr(lint, "_environment_dirs", list)
    monkeypatch.setattr(shutil, "which", _shim_only)
    monkeypatch.setattr(subprocess, "run", _completed(0))
    captured: list[list[str]] = []
    monkeypatch.setattr(subprocess, "call", _capturing_call(captured))
    lint.run_ruff_check("src")
    assert captured[0][0] == "/home/u/.pyenv/shims/ruff"


def test_a_dead_shim_without_uv_reports_127(monkeypatch: pytest.MonkeyPatch) -> None:
    """No environment, a dead shim, no uv: the named 127, not the shim."""
    monkeypatch.setattr(lint, "_environment_dirs", list)
    monkeypatch.setattr(shutil, "which", _shim_only)
    monkeypatch.setattr(subprocess, "run", _completed(127))

    def never_called(*_args: Any, **_kwargs: Any) -> int:
        """Fail if the dead shim is executed anyway."""
        pytest.fail("a shim that does not dispatch must never be executed")

    monkeypatch.setattr(subprocess, "call", never_called)
    assert lint.run_ruff_check("src") == 127


def test_a_shim_probe_that_cannot_spawn_is_not_runnable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An OSError or timeout on the probe counts as "does not run"."""

    def explode(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        """Simulate a shim that cannot even be spawned."""
        raise OSError("Exec format error")

    monkeypatch.setattr(subprocess, "run", explode)
    assert lint._shim_runs(Path("/home/u/.pyenv/shims/ruff")) is False


def test_environment_dirs_prefers_the_project_over_the_cli_itself(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A pinned ruff must win over the one shipped with this package.

    `ruff` is a dependency of tempest-cli, so the CLI's own environment
    always has one. Searching it first would silently override the
    version a project pinned whenever the CLI lives elsewhere
    (`uv tool install` / pipx).
    """
    interpreter_dir = tmp_path / "cli-env" / "bin"
    interpreter_dir.mkdir(parents=True)
    active = tmp_path / "active"
    (active / "bin").mkdir(parents=True)
    monkeypatch.setattr(sys, "executable", str(interpreter_dir / "python"))
    monkeypatch.setenv("VIRTUAL_ENV", str(active))
    monkeypatch.chdir(tmp_path)
    dirs = lint._environment_dirs()
    assert dirs[0] == active / "bin"
    assert dirs.index(interpreter_dir) > dirs.index(active / "bin")


def test_environment_dirs_finds_an_unactivated_venv(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A `.venv` up the tree counts even with nothing activated."""
    project = tmp_path / "project"
    (project / ".venv" / "bin").mkdir(parents=True)
    (project / "src").mkdir()
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    monkeypatch.chdir(project / "src")
    assert project / ".venv" / "bin" in lint._environment_dirs()


def test_ruff_ships_with_the_package() -> None:
    """Installing tempest-cli must be enough to run the ruff commands.

    Six of the eight commands are ruff. Reading the requirement from the
    installed distribution, not from ``pyproject.toml``, is what proves
    a user actually receives it.
    """
    from importlib.metadata import requires

    declared = requires("tempest-cli") or []
    runtime = [item for item in declared if "extra ==" not in item]
    assert any(item.startswith("ruff") for item in runtime), runtime
    assert not any(item.startswith(("mypy", "pytest")) for item in runtime), runtime
