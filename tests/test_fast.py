"""Tests for ``test --fast`` / ``check --fast``: the parallel pytest run.

Three things matter: the argv handed to pytest, the preflight that asks
*pytest's* interpreter whether pytest-xdist is importable, and the exit
code coming straight back. Most tests capture argv; the ones named
``real`` spawn an interpreter or pytest itself, because the probe and
the plugin wiring are only proven by running them.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from tempest_cli import lint
from tempest_cli import main as main_module
from tempest_cli.config import TempestConfig

runner = CliRunner()


def _fake_env(tmp_path: Path) -> Path:
    """Lay out a virtualenv-like ``bin`` with a pytest script and a python.

    Args:
        tmp_path (Path): Pytest's per-test directory.

    Returns:
        Path: The path of the fake ``pytest`` console script, whose
        shebang names the sibling ``python``.
    """
    bin_dir = tmp_path / "env" / "bin"
    bin_dir.mkdir(parents=True)
    python = bin_dir / "python"
    python.write_text("")
    script = bin_dir / "pytest"
    script.write_text(f"#!{python}\nimport pytest\n")
    return script


def _probe_answering(
    returncode: int,
) -> Callable[..., subprocess.CompletedProcess[bytes]]:
    """Build a :func:`subprocess.run` stand-in for the module probe.

    Args:
        returncode (int): ``0`` for "importable", ``1`` for "missing".

    Returns:
        Callable[..., subprocess.CompletedProcess[bytes]]: The stand-in.
    """

    def fake_run(argv: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        """Answer the probe without spawning an interpreter."""
        return subprocess.CompletedProcess(args=argv, returncode=returncode)

    return fake_run


@pytest.fixture
def fake_pytest(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Resolve ``pytest`` to a fake script, and nothing else anywhere.

    Args:
        monkeypatch (pytest.MonkeyPatch): Pytest's patcher.
        tmp_path (Path): Pytest's per-test directory.

    Returns:
        Path: The fake pytest script every lookup resolves to.
    """
    script = _fake_env(tmp_path)

    def which(name: str, path: str | None = None) -> str | None:
        """Resolve pytest on PATH only; every environment lookup misses."""
        if path is None and name in {"pytest", "ruff", "mypy"}:
            return str(script) if name == "pytest" else f"/usr/bin/{name}"
        return None

    monkeypatch.setattr(shutil, "which", which)
    return script


@pytest.fixture
def calls(
    monkeypatch: pytest.MonkeyPatch,
    fake_pytest: Path,
) -> list[list[str]]:
    """Capture every argv the runners execute, with xdist reported present.

    Args:
        monkeypatch (pytest.MonkeyPatch): Pytest's patcher.
        fake_pytest (Path): The fake pytest script.

    Returns:
        list[list[str]]: The captured argv lists, in call order.
    """
    captured: list[list[str]] = []

    def fake_call(argv: list[str], **_kwargs: Any) -> int:
        """Record ``argv`` instead of spawning anything."""
        captured.append(argv)
        return 0

    monkeypatch.setattr(subprocess, "call", fake_call)
    monkeypatch.setattr(subprocess, "run", _probe_answering(0))
    return captured


def _never_called(*_args: Any, **_kwargs: Any) -> int:
    """Fail the test if a tool is spawned.

    Raises:
        pytest.fail.Exception: Always.
    """
    pytest.fail("no tool should run when pytest-xdist is missing")


def test_fast_adds_workers_and_disables_the_cache(calls: list[list[str]]) -> None:
    assert lint.run_pytest(None, fast=True) == 0
    assert calls[0][1:] == ["-n", "auto", "-p", "no:cacheprovider"]


def test_fast_forwards_workers_and_target(calls: list[list[str]]) -> None:
    lint.run_pytest("tests/unit", fast=True, workers="4")
    assert calls[0][1:] == ["-n", "4", "-p", "no:cacheprovider", "tests/unit"]


def test_serial_run_carries_no_xdist_flag(calls: list[list[str]]) -> None:
    """Without ``fast`` the argv is what ``run_pytest`` always built."""
    lint.run_pytest("tests/unit", workers="4")
    assert calls[0][1:] == ["tests/unit"]


def test_fast_exit_code_comes_straight_back(
    monkeypatch: pytest.MonkeyPatch,
    fake_pytest: Path,
) -> None:
    monkeypatch.setattr(subprocess, "run", _probe_answering(0))
    monkeypatch.setattr(subprocess, "call", lambda *_a, **_k: 3)
    assert lint.run_pytest(None, fast=True) == 3


def test_missing_xdist_names_the_fix_and_reports_127(
    monkeypatch: pytest.MonkeyPatch,
    fake_pytest: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A sentence naming the package, not ``unrecognized arguments: -n``."""
    monkeypatch.setattr(subprocess, "run", _probe_answering(1))
    monkeypatch.setattr(subprocess, "call", _never_called)
    assert lint.run_pytest(None, fast=True) == lint.MISSING_TOOL_EXIT_CODE
    err = capsys.readouterr().err
    assert "pytest-xdist" in err
    assert "tempest-fastapi-sdk[tests]" in err
    assert "tempest-cli[tools]" in err
    assert "Traceback" not in err


def test_an_unanswerable_probe_lets_pytest_speak(
    monkeypatch: pytest.MonkeyPatch,
    fake_pytest: Path,
    calls: list[list[str]],
) -> None:
    """A probe that crashes is not evidence that xdist is missing."""
    monkeypatch.setattr(subprocess, "run", _probe_answering(2))
    assert lint.run_pytest(None, fast=True) == 0
    assert calls[0][1] == "-n"


def test_full_check_fast_runs_pytest_in_parallel(calls: list[list[str]]) -> None:
    assert lint.run_full_check("src", config=TempestConfig(), fast=True) == 0
    assert calls[-1][1:] == ["-n", "auto", "-p", "no:cacheprovider"]


def test_full_check_fast_fails_before_the_first_step(
    monkeypatch: pytest.MonkeyPatch,
    fake_pytest: Path,
) -> None:
    """A missing plugin must not wait for lint and mypy to finish."""
    monkeypatch.setattr(subprocess, "run", _probe_answering(1))
    monkeypatch.setattr(subprocess, "call", _never_called)
    code = lint.run_full_check("src", config=TempestConfig(), fast=True)
    assert code == lint.MISSING_TOOL_EXIT_CODE


def test_interpreter_of_the_uv_fallback_is_the_same_overlay() -> None:
    argv = ["/usr/bin/uv", "run", "--with", "pytest", "pytest"]
    assert lint._pytest_interpreter(argv) == [
        "/usr/bin/uv",
        "run",
        "--with",
        "pytest",
        "python",
    ]


def test_interpreter_comes_from_the_shebang(tmp_path: Path) -> None:
    script = _fake_env(tmp_path)
    assert lint._pytest_interpreter([str(script)]) == [str(script.parent / "python")]


def test_an_env_shebang_is_kept_whole(tmp_path: Path) -> None:
    script = tmp_path / "pytest"
    script.write_text("#!/usr/bin/env python3\n")
    assert lint._pytest_interpreter([str(script)]) == ["/usr/bin/env", "python3"]


def test_a_launcher_without_shebang_falls_back_to_the_sibling_python(
    tmp_path: Path,
) -> None:
    """Windows ``pytest.exe`` has no shebang; ``python.exe`` sits beside it."""
    (tmp_path / "pytest.exe").write_bytes(b"MZ\x90\x00")
    (tmp_path / "python.exe").write_bytes(b"MZ\x90\x00")
    assert lint._pytest_interpreter([str(tmp_path / "pytest.exe")]) == [
        str(tmp_path / "python.exe")
    ]


def test_an_unknown_interpreter_is_none(tmp_path: Path) -> None:
    script = tmp_path / "pytest"
    script.write_text("#!/bin/sh\nexec something\n")
    assert lint._pytest_interpreter([str(script)]) is None
    assert lint._pytest_interpreter([str(tmp_path / "absent")]) is None


def test_real_probe_tells_present_from_missing() -> None:
    """Spawns this interpreter: the probe program itself must be right."""
    assert lint._module_available([sys.executable], "xdist") is True
    assert lint._module_available([sys.executable], "no_such_module_xyz") is False


def test_real_probe_that_cannot_spawn_is_unknown(tmp_path: Path) -> None:
    assert lint._module_available([str(tmp_path / "absent")], "xdist") is None


def _write_suite(root: Path, *, failing: bool) -> None:
    """Write a two-test suite into ``root``.

    Args:
        root (Path): The directory the suite lives in.
        failing (bool): When True, one of the two tests fails.
    """
    (root / "pyproject.toml").write_text("[tool.pytest.ini_options]\n")
    body = "assert 1 == 2" if failing else "assert True"
    (root / "test_sample.py").write_text(
        f"def test_one() -> None:\n    assert True\n\n\n"
        f"def test_two() -> None:\n    {body}\n"
    )


@pytest.mark.parametrize(("failing", "expected"), [(False, 0), (True, 1)])
def test_real_fast_run_spawns_workers_and_propagates_the_exit_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failing: bool,
    expected: int,
) -> None:
    """Run the CLI for real against a tiny suite, with two xdist workers."""
    _write_suite(tmp_path, failing=failing)
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    result = subprocess.run(
        [sys.executable, "-m", "tempest_cli.main", "test", "--fast", "-w", "2"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == expected, result.stdout + result.stderr
    assert "2 workers" in result.stdout
    assert not (tmp_path / ".pytest_cache").exists()


def _capture_runner(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
) -> list[tuple[tuple[Any, ...], dict[str, Any]]]:
    """Replace a runner in ``tempest_cli.lint`` with a recorder.

    Args:
        monkeypatch (pytest.MonkeyPatch): Pytest's patcher.
        name (str): The runner to replace (``run_pytest``,
            ``run_full_check``).

    Returns:
        list[tuple[tuple[Any, ...], dict[str, Any]]]: The recorded
        ``(args, kwargs)`` of every call.
    """
    seen: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def record(*args: Any, **kwargs: Any) -> int:
        """Record the call and report success."""
        seen.append((args, kwargs))
        return 0

    monkeypatch.setattr(lint, name, record)
    return seen


def test_cli_test_fast_forwards_workers_and_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = _capture_runner(monkeypatch, "run_pytest")
    result = runner.invoke(
        main_module.app, ["test", "tests/unit", "--fast", "--workers", "4"]
    )
    assert result.exit_code == 0, result.output
    assert seen == [(("tests/unit",), {"fast": True, "workers": "4"})]


def test_cli_fast_defaults_to_auto(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _capture_runner(monkeypatch, "run_pytest")
    runner.invoke(main_module.app, ["test", "--fast"])
    assert seen == [((None,), {"fast": True, "workers": "auto"})]


def test_a_folder_named_fast_is_still_a_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Why ``--fast`` is a flag: ``tempest test fast`` keeps its meaning."""
    seen = _capture_runner(monkeypatch, "run_pytest")
    runner.invoke(main_module.app, ["test", "fast"])
    assert seen == [(("fast",), {"fast": False, "workers": "auto"})]


def test_cli_workers_without_fast_is_a_usage_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = _capture_runner(monkeypatch, "run_pytest")
    result = runner.invoke(main_module.app, ["test", "--workers", "4"])
    assert result.exit_code == 2
    assert seen == []


@pytest.mark.parametrize("workers", ["many", "-1", "2.5", ""])
def test_cli_rejects_a_worker_count_xdist_would_refuse(
    monkeypatch: pytest.MonkeyPatch,
    workers: str,
) -> None:
    seen = _capture_runner(monkeypatch, "run_pytest")
    result = runner.invoke(main_module.app, ["test", "--fast", "--workers", workers])
    assert result.exit_code == 2
    assert seen == []


@pytest.mark.parametrize("workers", ["auto", "logical", "0", "12"])
def test_cli_accepts_the_xdist_worker_grammar(
    monkeypatch: pytest.MonkeyPatch,
    workers: str,
) -> None:
    seen = _capture_runner(monkeypatch, "run_pytest")
    result = runner.invoke(main_module.app, ["test", "--fast", "-w", workers])
    assert result.exit_code == 0, result.output
    assert seen[0][1]["workers"] == workers


def test_cli_check_fast_reaches_the_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _capture_runner(monkeypatch, "run_full_check")
    result = runner.invoke(main_module.app, ["check", "src", "--fast", "-w", "3"])
    assert result.exit_code == 0, result.output
    args, kwargs = seen[0]
    assert args == ("src",)
    assert kwargs["fast"] is True
    assert kwargs["workers"] == "3"


def test_cli_propagates_the_runner_exit_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(lint, "run_pytest", lambda *_a, **_k: 5)
    assert runner.invoke(main_module.app, ["test", "--fast"]).exit_code == 5


def test_test_help_explains_the_parallel_only_failure() -> None:
    """The help text is the docstring; read it, not Rich's rendering."""
    command = next(
        info for info in main_module.app.registered_commands if info.name == "test"
    )
    assert command.callback is not None
    doc = command.callback.__doc__ or ""
    assert "fails only under --fast" in doc
    assert "tests/test_x.py::test_name" in doc
