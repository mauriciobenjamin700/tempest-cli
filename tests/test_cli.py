"""Tests for the CLI surface itself: the app, and mounting it elsewhere."""

from __future__ import annotations

import typer
from typer.testing import CliRunner

import tempest_cli
from tempest_cli.main import app, register_commands

runner = CliRunner()

QUALITY_COMMANDS: frozenset[str] = frozenset(
    {"lint", "fix", "format", "fmt-check", "type", "test", "check", "pr-prompt"},
)


def _command_names(application: typer.Typer) -> set[str]:
    """Return the command names registered on a Typer app.

    Args:
        application (typer.Typer): The application to inspect.

    Returns:
        set[str]: Every registered command name.
    """
    return {
        info.name or (info.callback.__name__ if info.callback else "")
        for info in application.registered_commands
    }


def test_app_exposes_every_command() -> None:
    assert _command_names(app) >= QUALITY_COMMANDS


def test_version_flag_prints_the_installed_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert tempest_cli.__version__ in result.stdout


def test_no_args_shows_help() -> None:
    result = runner.invoke(app, [])
    assert "check" in result.stdout
    assert "pr-prompt" in result.stdout


def test_register_commands_mounts_the_gate_on_another_app() -> None:
    """What lets another CLI expose this gate without copying it."""
    host: typer.Typer = typer.Typer(name="host")

    @host.command("unrelated")
    def unrelated() -> None:
        """A command the host already had."""

    register_commands(host)
    names = _command_names(host)
    assert names >= QUALITY_COMMANDS
    assert "unrelated" in names


def test_strictness_flag_rejects_an_unknown_level() -> None:
    """Usage error (exit 2), not a run with the default level."""
    result = runner.invoke(app, ["lint", ".", "--strictness", "paranoid"])
    assert result.exit_code == 2


def test_resolve_config_names_the_allowed_levels() -> None:
    import pytest

    from tempest_cli.main import _resolve_config

    with pytest.raises(typer.BadParameter, match="invalid strictness"):
        _resolve_config(".", "paranoid")
    assert _resolve_config(".", "strict").typing_strictness == "strict"


def test_public_surface_is_importable() -> None:
    """The package doubles as a library, so `__all__` must resolve."""
    for name in tempest_cli.__all__:
        assert hasattr(tempest_cli, name), name


def test_importing_the_package_pulls_no_web_framework() -> None:
    """The whole point of the extraction: no FastAPI, no SQLAlchemy."""
    import subprocess
    import sys

    code = (
        "import sys, tempest_cli, tempest_cli.main;"
        "heavy = {'fastapi', 'sqlalchemy', 'alembic', 'starlette', 'pydantic'};"
        "loaded = {m.split('.')[0] for m in sys.modules};"
        "print(sorted(heavy & loaded))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "[]"
