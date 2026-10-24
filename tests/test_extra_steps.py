"""Tests for ``extra_steps``: the seam a framework adds its rules through.

Every test records tool runs and extra steps in one shared log, so the
order between them is asserted directly rather than inferred.
"""

from __future__ import annotations

import dataclasses
import shutil
import subprocess
from functools import partial
from typing import Any

import pytest
import typer
from typer.testing import CliRunner

import tempest_cli
from tempest_cli import CheckStep, StepOptions, lint
from tempest_cli import main as main_module
from tempest_cli.config import TempestConfig

runner = CliRunner()


def _on_path_only(name: str, path: str | None = None) -> str | None:
    """Resolve every tool on ``PATH`` and nothing inside an environment.

    Args:
        name (str): The command being looked up.
        path (str | None): The directory the lookup was scoped to.

    Returns:
        str | None: ``/usr/bin/<name>`` for a ``PATH`` lookup, ``None``
        for a directory-scoped one.
    """
    return None if path is not None else f"/usr/bin/{name}"


@pytest.fixture
def log(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record every tool run, by tool name, in call order.

    The xdist preflight is answered as "present", so ``fast=True`` runs
    reach the steps without probing a real interpreter.

    Args:
        monkeypatch (pytest.MonkeyPatch): Pytest's patcher.

    Returns:
        list[str]: The shared log tools and extra steps append to.
    """
    entries: list[str] = []

    def fake_call(argv: list[str], **_kwargs: Any) -> int:
        """Record the tool name instead of spawning anything."""
        entries.append(argv[0].rsplit("/", 1)[-1])
        return 0

    monkeypatch.setattr(subprocess, "call", fake_call)
    monkeypatch.setattr(shutil, "which", _on_path_only)
    monkeypatch.setattr(lint, "_xdist_missing", lambda: None)
    return entries


def _step(
    log: list[str],
    name: str,
    code: int = 0,
    targets: list[str] | None = None,
) -> CheckStep:
    """Build a step that records itself in ``log`` and returns ``code``.

    Args:
        log (list[str]): The shared log.
        name (str): The step name, also what it appends to ``log``.
        code (int): The exit code the step reports.
        targets (list[str] | None): When given, every target the step is
            called with is appended here.

    Returns:
        CheckStep: The recording step.
    """

    def run(target: str) -> int:
        """Record the call and report ``code``."""
        log.append(name)
        if targets is not None:
            targets.append(target)
        return code

    return CheckStep(name=name, run=run)


def test_check_step_is_exported_from_the_package() -> None:
    assert "CheckStep" in tempest_cli.__all__
    assert tempest_cli.CheckStep is CheckStep


def test_check_step_is_frozen() -> None:
    step = CheckStep(name="x", run=lambda _target: 0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        step.name = "y"  # type: ignore[misc]


def test_without_extras_the_gate_is_unchanged(log: list[str]) -> None:
    assert lint.run_full_check("src", config=TempestConfig()) == 0
    assert log == ["ruff", "ruff", "mypy", "pytest"]


def test_extras_run_after_mypy_and_before_pytest_in_order(log: list[str]) -> None:
    targets: list[str] = []
    steps = [_step(log, "layers", targets=targets), _step(log, "services")]
    assert lint.run_full_check("src", extra_steps=steps) == 0
    assert log == ["ruff", "ruff", "mypy", "layers", "services", "pytest"]
    assert targets == ["src"]


def test_extras_run_under_fast_too(log: list[str]) -> None:
    steps = [_step(log, "layers")]
    assert lint.run_full_check("src", fast=True, extra_steps=steps) == 0
    assert log == ["ruff", "ruff", "mypy", "layers", "pytest"]


def test_a_failing_extra_stops_the_gate_and_its_code_comes_back(
    log: list[str],
) -> None:
    """Nothing after the failing step runs — neither extras nor pytest."""
    steps = [_step(log, "layers", code=3), _step(log, "services")]
    assert lint.run_full_check("src", extra_steps=steps) == 3
    assert log == ["ruff", "ruff", "mypy", "layers"]


def test_a_failing_tool_stops_before_the_extras(
    monkeypatch: pytest.MonkeyPatch,
    log: list[str],
) -> None:
    def failing_call(argv: list[str], **_kwargs: Any) -> int:
        """Record the tool and fail."""
        log.append(argv[0].rsplit("/", 1)[-1])
        return 1

    monkeypatch.setattr(subprocess, "call", failing_call)
    assert lint.run_full_check("src", extra_steps=[_step(log, "layers")]) == 1
    assert log == ["ruff"]


def test_each_extra_is_announced_on_stderr(
    log: list[str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    lint.run_full_check("src", extra_steps=[_step(log, "layers")])
    lines = capsys.readouterr().err.splitlines()
    assert lines[3] == "$ layers"
    assert lines[4].startswith("$ pytest")


def _host_with(steps: list[CheckStep]) -> typer.Typer:
    """Build a host CLI that mounts the gate with ``steps``.

    Args:
        steps (list[CheckStep]): The extra steps handed to
            :func:`tempest_cli.main.register_commands`.

    Returns:
        typer.Typer: The host application.
    """
    host: typer.Typer = typer.Typer(name="host")

    @host.callback()
    def _root() -> None:
        """Keep ``check`` a subcommand of the host."""

    main_module.register_commands(host, extra_steps=steps)
    return host


@pytest.mark.parametrize("flags", [[], ["--fast"]])
def test_register_commands_hands_the_extras_to_check(
    log: list[str],
    flags: list[str],
) -> None:
    host = _host_with([_step(log, "layers")])
    result = runner.invoke(host, ["check", "src", *flags])
    assert result.exit_code == 0, result.output
    assert log == ["ruff", "ruff", "mypy", "layers", "pytest"]


def test_register_commands_propagates_a_failing_extra(log: list[str]) -> None:
    host = _host_with([_step(log, "layers", code=4)])
    result = runner.invoke(host, ["check", "src"])
    assert result.exit_code == 4
    assert log == ["ruff", "ruff", "mypy", "layers"]


def test_the_steps_stay_on_the_app_they_were_given_to(log: list[str]) -> None:
    """The executable's own ``check`` gains nothing from another host."""
    _host_with([_step(log, "layers")])
    result = runner.invoke(main_module.app, ["check", "src"])
    assert result.exit_code == 0, result.output
    assert log == ["ruff", "ruff", "mypy", "pytest"]


def _options_step(
    seen: list[StepOptions], *, code: int = 0, name: str = "layers"
) -> CheckStep:
    """Build a step that records the options ``check`` handed it.

    Args:
        seen (list[StepOptions]): Grows by the options of each run.
        code (int): Exit code the step returns.
        name (str): The step label.

    Returns:
        CheckStep: A step declaring ``run_with_options``.
    """
    return CheckStep(
        name=name,
        run=lambda _target: 99,
        run_with_options=partial(_record_options, seen, code),
    )


def _record_options(
    seen: list[StepOptions], code: int, _target: str, options: StepOptions
) -> int:
    """Record the options and return ``code``.

    Args:
        seen (list[StepOptions]): The record.
        code (int): Exit code to return.
        _target (str): The check target, unused.
        options (StepOptions): What ``check`` parsed.

    Returns:
        int: ``code``.
    """
    seen.append(options)
    return code


def test_check_hands_rule_and_strict_to_the_steps_that_read_them(
    log: list[str],
) -> None:
    seen: list[StepOptions] = []
    host = _host_with([_options_step(seen), _step(log, "plain")])
    result = runner.invoke(
        host, ["check", "src", "--rule", "SVC002", "--rule", "IMP002", "--strict"]
    )
    assert result.exit_code == 0, result.output
    assert seen == [StepOptions(rules=("SVC002", "IMP002"), strict=True)]
    assert log == ["ruff", "ruff", "mypy", "plain", "pytest"]


def test_without_options_the_step_still_gets_the_defaults(log: list[str]) -> None:
    seen: list[StepOptions] = []
    host = _host_with([_options_step(seen)])
    result = runner.invoke(host, ["check", "src", "--no-strict"])
    assert result.exit_code == 0, result.output
    assert seen == [StepOptions(rules=(), strict=False)]
    seen.clear()
    assert runner.invoke(host, ["check", "src"]).exit_code == 0
    assert seen == [StepOptions()]
    assert not seen[0].given


def test_rule_without_a_step_that_reads_it_is_refused(log: list[str]) -> None:
    """A typed flag nothing reads would pass the gate while doing nothing."""
    host = _host_with([_step(log, "plain")])
    result = runner.invoke(host, ["check", "src", "--rule", "SVC002"])
    assert result.exit_code == 2
    assert "no step of this check reads --rule" in result.output
    assert log == []


def test_the_step_exit_code_still_stops_the_gate(log: list[str]) -> None:
    seen: list[StepOptions] = []
    host = _host_with([_options_step(seen, code=1)])
    result = runner.invoke(host, ["check", "src", "--strict"])
    assert result.exit_code == 1
    assert log == ["ruff", "ruff", "mypy"]
