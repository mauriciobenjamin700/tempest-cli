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

MODULE_PROBE_TIMEOUT_SECONDS = 120.0
"""Seconds allowed for probing whether pytest's interpreter can import a module.

Generous on purpose: through the ``uv run --with pytest`` fallback the
probe is the first thing to touch the project environment, so it may
pay for a resolution and a sync before the import even starts.
"""

DEFAULT_FAST_WORKERS = "auto"
"""Worker count ``--fast`` hands to ``pytest -n`` when none is given.

``auto`` is pytest-xdist's own keyword for one worker per CPU core:
physical cores when ``psutil`` is importable, logical CPUs otherwise.
"""

XDIST_MODULE = "xdist"
"""Import name of pytest-xdist, the plugin that provides ``pytest -n``."""

MISSING_TOOL_EXIT_CODE = 127
"""Exit code reported when a tool, or a plugin ``--fast`` needs, is absent."""

_MODULE_PROBE_SOURCE = (
    "import importlib.util, sys; "
    "sys.exit(0 if importlib.util.find_spec(sys.argv[1]) else 1)"
)
"""Program run inside pytest's interpreter to locate a module by name."""


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
        return MISSING_TOOL_EXIT_CODE
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


def _shebang_interpreter(script: Path) -> list[str] | None:
    """Read the interpreter a console script's shebang names.

    Args:
        script (Path): The console script (``.../bin/pytest``).

    Returns:
        list[str] | None: The argv prefix of that interpreter — the
        Python path itself, or ``[env, python3]`` for an ``env`` shebang
        — or ``None`` when the file has no usable shebang (a Windows
        ``.exe`` launcher, a ``/bin/sh`` trampoline, an unreadable file).
    """
    try:
        with script.open("rb") as handle:
            first_line = handle.readline(4096)
    except OSError:
        return None
    if not first_line.startswith(b"#!"):
        return None
    parts = first_line[2:].decode("utf-8", errors="replace").split()
    if not parts:
        return None
    if Path(parts[0]).name == "env" and len(parts) > 1:
        return parts
    if Path(parts[0]).name.startswith("python"):
        return [parts[0]]
    return None


def _pytest_interpreter(argv: list[str]) -> list[str] | None:
    """Return the argv prefix of the Python that ``argv`` runs pytest under.

    The ``--fast`` preflight has to ask *that* interpreter whether it can
    import pytest-xdist. The CLI's own interpreter is the wrong one to
    ask: under ``uv tool install`` or pipx the CLI lives in an
    environment of its own, and with the ``uv run --with pytest``
    fallback pytest runs in the project's environment plus an overlay.

    Resolution, by the shape :func:`resolve_tool` returned:

    - ``uv run --with pytest pytest`` → the same command with ``python``
      in place of the final ``pytest``, so the probe sees the exact
      environment the suite will;
    - a script path → the interpreter its shebang names, else the
      ``python`` sitting next to it (a virtualenv's ``bin``/``Scripts``).

    Args:
        argv (list[str]): The pytest argv prefix from :func:`resolve_tool`.

    Returns:
        list[str] | None: The interpreter argv prefix, or ``None`` when
        it cannot be told — the caller then skips the preflight and lets
        pytest report for itself.
    """
    if len(argv) > 1:
        return [*argv[:-1], "python"]
    script = Path(argv[0])
    from_shebang = _shebang_interpreter(script)
    if from_shebang is not None:
        return from_shebang
    for name in ("python", "python3", "python.exe"):
        sibling = script.parent / name
        if sibling.is_file():
            return [str(sibling)]
    return None


def _module_available(interpreter: list[str], module: str) -> bool | None:
    """Ask ``interpreter`` whether it can import ``module``.

    Runs :func:`importlib.util.find_spec` inside that interpreter, which
    locates the module without importing it.

    Args:
        interpreter (list[str]): The interpreter argv prefix.
        module (str): The top-level import name.

    Returns:
        bool | None: True when the module resolves, False when it does
        not, ``None`` when the probe itself could not run (spawn failure,
        timeout, an exit code other than ``0``/``1``).
    """
    try:
        completed = subprocess.run(
            [*interpreter, "-c", _MODULE_PROBE_SOURCE, module],
            capture_output=True,
            timeout=MODULE_PROBE_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode == 0:
        return True
    if completed.returncode == 1:
        return False
    return None


def _missing_xdist_code() -> int:
    """Check that the environment pytest runs in can import pytest-xdist.

    Without the plugin, ``pytest -n auto`` stops at argument parsing with
    ``unrecognized arguments: -n`` — true, but it names neither the
    missing package nor the way to get it. This preflight answers first,
    in words.

    An unknown answer is not a failure: when pytest cannot be resolved
    (:func:`_execute` reports that with its own message) or its
    interpreter cannot be told, the run proceeds and pytest speaks.

    Returns:
        int: ``0`` when the plugin is present or its presence cannot be
        told; :data:`MISSING_TOOL_EXIT_CODE` after printing the fix when
        it is absent.
    """
    argv = resolve_tool("pytest")
    if argv is None:
        return 0
    interpreter = _pytest_interpreter(argv)
    if interpreter is None:
        return 0
    if _module_available(interpreter, XDIST_MODULE) is not False:
        return 0
    typer.echo(
        "error: --fast needs pytest-xdist, which is not installed in the "
        f"environment pytest runs in ({' '.join(argv)}). Install it with "
        "'uv add --dev pytest-xdist' — or a bundle that carries it, "
        "'uv add --dev \"tempest-cli[tools]\"' or "
        "'uv add --dev \"tempest-fastapi-sdk[tests]\"' — and retry, "
        "or drop --fast to run the suite serially.",
        err=True,
    )
    return MISSING_TOOL_EXIT_CODE


def _pytest_args(target: str | None, *, fast: bool, workers: str) -> list[str]:
    """Build the arguments handed to pytest.

    Args:
        target (str | None): Optional path filter, forwarded last.
        fast (bool): When True, spread the suite with pytest-xdist.
        workers (str): The ``-n`` value used when ``fast`` is True.

    Returns:
        list[str]: ``[target]`` for a serial run, or
        ``["-n", workers, "-p", "no:cacheprovider", target]`` for a fast
        one (``target`` omitted when ``None``).
    """
    args = ["-n", workers, "-p", "no:cacheprovider"] if fast else []
    if target:
        args.append(target)
    return args


def run_pytest(
    target: str | None,
    *,
    fast: bool = False,
    workers: str = DEFAULT_FAST_WORKERS,
) -> int:
    """Invoke ``pytest`` with an optional target.

    With ``fast=True`` the suite is spread across pytest-xdist workers:
    ``-n <workers>`` plus ``-p no:cacheprovider``, since several workers
    writing ``.pytest_cache`` at once is a race that buys nothing. The
    cache is what ``--lf`` / ``--ff`` read, so those belong to serial
    runs. Before spawning, the interpreter pytest runs under is asked
    whether it can import pytest-xdist; when it cannot, the fix is
    printed and nothing runs.

    Args:
        target (str | None): Optional pytest path filter. ``None`` runs
            the default test suite.
        fast (bool): When True, run the suite in parallel with
            pytest-xdist.
        workers (str): Worker count for ``fast`` — an integer, ``auto``
            (one per CPU core: physical when ``psutil`` is importable) or
            ``logical``, exactly as ``pytest -n`` takes it. Ignored when
            ``fast`` is False.

    Returns:
        int: The pytest exit code, or :data:`MISSING_TOOL_EXIT_CODE` when
        pytest — or, with ``fast``, pytest-xdist — is absent.
    """
    if fast:
        code = _missing_xdist_code()
        if code != 0:
            return code
    return _execute("pytest", _pytest_args(target, fast=fast, workers=workers))


def run_full_check(
    target: str,
    *,
    config: TempestConfig | None = None,
    fast: bool = False,
    workers: str = DEFAULT_FAST_WORKERS,
) -> int:
    """Run the entire quality gate sequentially.

    Order: ``ruff check`` → ``ruff format --check`` → ``mypy`` → ``pytest``.
    Stops at the first non-zero exit code so failures surface fast.

    With ``fast=True`` the pytest step runs the way :func:`run_pytest`
    runs it with ``fast=True``. The pytest-xdist preflight happens
    *before* the first step, so a missing plugin fails in a second
    instead of after lint and mypy have already run.

    Args:
        target (str): The path inspected by ruff/mypy. Pytest always runs
            against the project's configured ``testpaths``.
        config (TempestConfig | None): Resolved ``[tool.tempest]`` config
            controlling the ANN rules and mypy flags layered onto the
            ruff/mypy steps. When ``None`` the default level is used.
        fast (bool): When True, run the pytest step in parallel with
            pytest-xdist.
        workers (str): The ``pytest -n`` value used when ``fast`` is True.

    Returns:
        int: The first non-zero exit code, or ``0`` when every gate passed.
    """
    if fast:
        code = _missing_xdist_code()
        if code != 0:
            return code
    resolved = config or TempestConfig()
    steps: list[tuple[str, list[str]]] = [
        ("ruff", ["check", *_ruff_ann_args(resolved), target]),
        ("ruff", ["format", "--check", target]),
        ("mypy", [*resolved.mypy_flags(), target]),
        ("pytest", _pytest_args(None, fast=fast, workers=workers)),
    ]
    for executable, args in steps:
        typer.echo(f"$ {executable} {' '.join(args)}", err=True)
        code = _execute(executable, args)
        if code != 0:
            return code
    return 0


__all__: list[str] = [
    "DEFAULT_FAST_WORKERS",
    "MISSING_TOOL_EXIT_CODE",
    "XDIST_MODULE",
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
