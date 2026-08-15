"""Quality-gate helpers backing ``tempest lint``/``check``/etc."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import typer

from tempest_cli.config import TempestConfig

SHIM_PROBE_TIMEOUT_SECONDS = 20.0
"""Seconds allowed for the ``<tool> --version`` probe of a version-manager shim."""


def _ruff_ann_args(config: TempestConfig | None) -> list[str]:
    """Build the ruff ``--extend-select`` args for ``config``'s level.

    Args:
        config (TempestConfig | None): The resolved config, or ``None``
            to use the default level.

    Returns:
        list[str]: ``["--extend-select", "ANN001,..."]`` for a level that
        adds ANN rules, or ``[]`` for the lenient level.
    """
    codes = (config or TempestConfig()).ruff_ann_select()
    if not codes:
        return []
    return ["--extend-select", ",".join(codes)]


def _environment_dirs() -> list[Path]:
    """Return the executable directories searched ahead of ``PATH``.

    ``PATH`` is a poor first answer on a machine running a version
    manager: pyenv/asdf put their shim directory on it globally, so a
    lookup finds ``~/.pyenv/shims/ruff`` even when the project's own
    environment has no ruff at all. The environments below are the ones
    that actually belong to the run, so they are consulted first:

    1. ``$VIRTUAL_ENV`` — the activated environment;
    2. the nearest ``.venv`` walking up from the working directory — a
       project environment that was never activated;
    3. the directory of the interpreter running this CLI.

    The project comes before the interpreter on purpose. ``ruff`` ships
    as a dependency of this package, so the CLI's own environment always
    has one; a project that pins its own must still get the version it
    pinned, with the bundled one serving only as the fallback for a
    project that pins nothing. When the CLI is installed *into* the
    project (the common case) all three point at the same directory and
    the order is moot — it only decides for ``uv tool install`` / pipx,
    where the CLI lives in an environment of its own.

    Returns:
        list[Path]: Existing directories, in preference order, without
        duplicates.
    """
    roots: list[Path] = []
    virtual_env = os.environ.get("VIRTUAL_ENV")
    if virtual_env:
        roots.extend((Path(virtual_env) / "bin", Path(virtual_env) / "Scripts"))
    try:
        cwd = Path.cwd()
    except OSError:
        cwd = None
    if cwd is not None:
        for directory in (cwd, *cwd.parents):
            candidate = directory / ".venv"
            if candidate.is_dir():
                roots.extend((candidate / "bin", candidate / "Scripts"))
                break
    roots.append(Path(sys.executable).parent)
    seen: set[Path] = set()
    ordered: list[Path] = []
    for root in roots:
        if root not in seen and root.is_dir():
            seen.add(root)
            ordered.append(root)
    return ordered


def _is_shim(path: Path) -> bool:
    """Report whether ``path`` looks like a version-manager shim.

    pyenv, asdf and rbenv all install their shims into a directory named
    ``shims``. A shim is a stub that exists for every tool any installed
    interpreter version ever provided, so its presence says nothing
    about whether the command can actually run right now.

    Args:
        path (Path): The resolved executable path.

    Returns:
        bool: True when the executable sits in a ``shims`` directory.
    """
    return path.parent.name == "shims"


def _shim_runs(path: Path) -> bool:
    """Report whether a shim actually dispatches to a real executable.

    Runs ``<path> --version`` and reads the exit code. A pyenv shim for
    a tool missing from the selected version prints ``pyenv: ruff:
    command not found`` and exits non-zero — running the gate through it
    would fail with that message instead of falling back to a runner
    that works.

    Args:
        path (Path): The shim to probe.

    Returns:
        bool: True when the probe exits ``0``. False on a non-zero exit,
        a timeout, or an OS-level failure to spawn.
    """
    try:
        completed = subprocess.run(
            [str(path), "--version"],
            capture_output=True,
            timeout=SHIM_PROBE_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


def _path_lookup(executable: str) -> str | None:
    """Find ``executable`` on ``PATH``, rejecting a shim that goes nowhere.

    Args:
        executable (str): The command name to look up.

    Returns:
        str | None: The resolved path, or ``None`` when the command is
        absent or resolves to a shim that does not dispatch.
    """
    found = shutil.which(executable)
    if found is None:
        return None
    path = Path(found)
    if _is_shim(path) and not _shim_runs(path):
        return None
    return found


def resolve_tool(executable: str) -> list[str] | None:
    """Return an argv prefix invoking ``executable`` or ``None`` when absent.

    Public because callers outside the gate need the same lookup — the
    SDK's OpenAPI code generator formats what it emits with the project's
    own ruff, and reimplementing the environment/``uv run`` fallback
    there would be a second answer to the same question.

    Preference order:

    1. the environments that belong to this run (see
       :func:`_environment_dirs`): the CLI's own interpreter directory,
       ``$VIRTUAL_ENV``, then the nearest ``.venv``;
    2. ``executable`` on ``PATH`` — skipped when it resolves to a
       version-manager shim that does not dispatch anywhere;
    3. ``uv run --with <executable> <executable>`` when ``uv`` is on the
       ``PATH``: the project's own environment plus the tool, without
       requiring activation or a prior ``uv sync``.

    Step 3 carries ``--with`` on purpose. A plain ``uv run ruff`` falls
    back to ``PATH`` when the project environment has no ruff — landing
    right back on the dead shim this lookup just rejected. ``--with``
    puts the tool in the run's own overlay, so the command is always the
    one that runs. When the project pins a version, uv resolves the
    overlay against the project's requirements, so the pin still wins.

    Args:
        executable (str): The command name (``ruff``/``mypy``/``pytest``).

    Returns:
        list[str] | None: argv prefix to extend with extra arguments, or
        ``None`` when no runner could be found.
    """
    for directory in _environment_dirs():
        local = shutil.which(executable, path=str(directory))
        if local is not None:
            return [local]
    direct = _path_lookup(executable)
    if direct is not None:
        return [direct]
    uv = _path_lookup("uv")
    if uv is not None:
        return [uv, "run", "--with", executable, executable]
    return None


def _execute(executable: str, args: list[str]) -> int:
    """Run ``executable args`` and return its exit code.

    Args:
        executable (str): The command to run.
        args (list[str]): Extra arguments to forward.

    Returns:
        int: The child process exit code. Returns ``127`` when neither
        the executable nor ``uv`` is available.
    """
    argv = resolve_tool(executable)
    if argv is None:
        typer.echo(
            f"error: '{executable}' was not found in this project's environment, "
            f"on PATH, and 'uv' is unavailable to run it. "
            f"Install it with 'uv add --dev {executable}' — or the whole set "
            f"with 'uv add --dev \"tempest-cli[tools]\"' — and retry.",
            err=True,
        )
        return 127
    return subprocess.call([*argv, *args])


def run_ruff_check(target: str, *, config: TempestConfig | None = None) -> int:
    """Invoke ``ruff check <target>`` with the configured ANN rules.

    Args:
        target (str): The path passed verbatim to ruff.
        config (TempestConfig | None): Resolved ``[tool.tempest]`` config
            controlling the typing-strictness ANN rules layered on. When
            ``None`` the default level is used.

    Returns:
        int: The ruff exit code.
    """
    return _execute("ruff", ["check", *_ruff_ann_args(config), target])


def run_ruff_fix(
    target: str,
    *,
    unsafe: bool = False,
    config: TempestConfig | None = None,
) -> int:
    """Apply every automatic fix ruff can perform, then format the target.

    Runs in two passes so the second one sees the rewritten file:

    1. ``ruff check --fix [--unsafe-fixes] <target>`` — autofix imports
       (sort + dedupe), remove unused imports, normalize string quotes,
       drop trailing whitespace, fix the rest of the lint rules that
       have safe (or, with ``unsafe=True``, also unsafe) autofixers.
    2. ``ruff format <target>`` — normalize indentation, line length,
       blank lines and trailing newlines.

    Both passes always run. ``ruff check --fix`` exits non-zero whenever
    *any* residual violation remains that it cannot autofix (an
    over-length string/comment, an undefined name, etc.) — even though
    it already rewrote everything it could. Short-circuiting on that
    exit code would skip ``ruff format`` entirely, leaving the file
    un-wrapped and its extra blank lines intact. So the formatter runs
    unconditionally; the lint exit code is surfaced afterwards so CI
    still fails on the leftover issues.

    Args:
        target (str): The path passed verbatim to ruff.
        unsafe (bool): When True, pass ``--unsafe-fixes`` so ruff also
            applies the fixes it would otherwise leave alone.
        config (TempestConfig | None): Resolved ``[tool.tempest]`` config
            controlling the typing-strictness ANN rules layered onto the
            fix pass. When ``None`` the default level is used.

    Returns:
        int: ``0`` when both passes succeed with nothing left to fix;
        otherwise the lint pass exit code (residual violations), or the
        format pass exit code when the lint pass was clean.
    """
    check_args = ["check", "--fix", *_ruff_ann_args(config)]
    if unsafe:
        check_args.append("--unsafe-fixes")
    check_args.append(target)
    check_code = _execute("ruff", check_args)
    format_code = _execute("ruff", ["format", target])
    return check_code or format_code


def run_ruff_format(target: str, *, check: bool) -> int:
    """Invoke ``ruff format`` (write or check-only).

    Args:
        target (str): The path passed verbatim to ruff.
        check (bool): When True, run ``ruff format --check`` (read-only).

    Returns:
        int: The ruff exit code.
    """
    args = ["format"]
    if check:
        args.append("--check")
    args.append(target)
    return _execute("ruff", args)


def run_mypy(target: str, *, config: TempestConfig | None = None) -> int:
    """Invoke ``mypy <target>`` with the configured strictness flags.

    Args:
        target (str): The path passed verbatim to mypy.
        config (TempestConfig | None): Resolved ``[tool.tempest]`` config
            controlling the mypy strictness flags layered on top of the
            project's ``[tool.mypy]``. When ``None`` the default level is
            used.

    Returns:
        int: The mypy exit code.
    """
    flags = (config or TempestConfig()).mypy_flags()
    return _execute("mypy", [*flags, target])


def run_pytest(target: str | None) -> int:
    """Invoke ``pytest`` with an optional target.

    Args:
        target (str | None): Optional pytest path filter. ``None`` runs
            the default test suite.

    Returns:
        int: The pytest exit code.
    """
    args = [target] if target else []
    return _execute("pytest", args)


def run_full_check(target: str, *, config: TempestConfig | None = None) -> int:
    """Run the entire quality gate sequentially.

    Order: ``ruff check`` → ``ruff format --check`` → ``mypy`` → ``pytest``.
    Stops at the first non-zero exit code so failures surface fast.

    Args:
        target (str): The path inspected by ruff/mypy. Pytest always runs
            against the project's configured ``testpaths``.
        config (TempestConfig | None): Resolved ``[tool.tempest]`` config
            controlling the ANN rules and mypy flags layered onto the
            ruff/mypy steps. When ``None`` the default level is used.

    Returns:
        int: The first non-zero exit code, or ``0`` when every gate passed.
    """
    resolved = config or TempestConfig()
    steps: list[tuple[str, list[str]]] = [
        ("ruff", ["check", *_ruff_ann_args(resolved), target]),
        ("ruff", ["format", "--check", target]),
        ("mypy", [*resolved.mypy_flags(), target]),
        ("pytest", []),
    ]
    for executable, args in steps:
        typer.echo(f"$ {executable} {' '.join(args)}", err=True)
        code = _execute(executable, args)
        if code != 0:
            return code
    return 0


__all__: list[str] = [
    "resolve_tool",
    "run_full_check",
    "run_mypy",
    "run_pytest",
    "run_ruff_check",
    "run_ruff_fix",
    "run_ruff_format",
]


if __name__ == "__main__":  # pragma: no cover - manual invocation only
    sys.exit(run_full_check("."))
