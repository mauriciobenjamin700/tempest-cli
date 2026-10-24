"""Quality-gate helpers backing ``tempest lint``/``check``/etc."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Literal

import typer

from tempest_cli import residuals, rewrite
from tempest_cli.config import TempestConfig
from tempest_cli.steps import CheckStep, StepOptions

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


def _capture(executable: str, args: list[str]) -> str | None:
    """Run ``executable args`` silently and return what it wrote to stdout.

    Args:
        executable (str): The command to run.
        args (list[str]): Extra arguments to forward.

    Returns:
        str | None: The child's stdout, or ``None`` when the tool cannot
        be found or started.
    """
    argv = resolve_tool(executable)
    if argv is None:
        return None
    try:
        completed = subprocess.run(
            [*argv, *args],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    return completed.stdout


def run_ruff_fix(
    target: str,
    *,
    unsafe: bool = False,
    config: TempestConfig | None = None,
) -> int:
    """Apply every automatic fix ruff can perform, then format the target.

    Runs these passes, so the report describes the file the formatter
    left behind rather than the one it started from:

    1. ``ruff check --fix-only [--unsafe-fixes] <target>`` — autofix
       imports (sort + dedupe), remove unused imports, normalize string
       quotes, drop trailing whitespace, fix the rest of the lint rules
       that have safe (or, with ``unsafe=True``, also unsafe) autofixers.
       ``--fix-only`` keeps it from reporting the leftovers, which the
       formatter may still resolve.
    2. ``ruff format <target>`` — normalize indentation, line length,
       blank lines and trailing newlines.
    3. Long lines the formatter cannot break, shortened where that is
       safe (see :mod:`tempest_cli.rewrite`): ruff's JSON report is read,
       comments past the limit are wrapped and string literals are split
       into implicitly concatenated parts, each edit kept only when the
       file's AST is unchanged. The files touched go through ``ruff
       format`` once more.
    4. ``ruff check <target>`` — the report of what is left, and the exit
       code of the command.

    When the last pass fails, ruff's JSON report of the same target is
    read to explain the leftovers (see :mod:`tempest_cli.residuals`): an
    E501 that survived is one with no mechanical fix — a dotted name, a
    long name, an expression — and is named as such with the action that
    does resolve it, and the residual violations are split into those
    with no autofix and those ``--unsafe`` would fix. The exit code is
    unaffected, so CI still fails on them.

    Args:
        target (str): The path passed verbatim to ruff.
        unsafe (bool): When True, pass ``--unsafe-fixes`` so ruff also
            applies the fixes it would otherwise leave alone.
        config (TempestConfig | None): Resolved ``[tool.tempest]`` config
            controlling the typing-strictness ANN rules layered onto the
            fix and report passes. When ``None`` the default level is used.

    Returns:
        int: ``0`` when nothing is left to fix; otherwise the report pass
        exit code (residual violations), or the format pass exit code
        when the report was clean. ``127`` when ruff cannot be found.
    """
    ann_args = _ruff_ann_args(config)
    fix_args = ["check", "--fix-only", *ann_args]
    if unsafe:
        fix_args.append("--unsafe-fixes")
    fix_args.append(target)
    fix_code = _execute("ruff", fix_args)
    if fix_code == MISSING_TOOL_EXIT_CODE:
        return fix_code
    format_code = _execute("ruff", ["format", target])
    report_args = ["check", *ann_args, "--output-format", "json", "--exit-zero"]
    long_lines = _capture("ruff", [*report_args, target])
    shortened = rewrite.rewrite_long_lines(long_lines) if long_lines else []
    if shortened:
        typer.echo(rewrite.render_rewrites(shortened), err=True, nl=False)
        touched = sorted({item.path for item in shortened})
        reformat_code = _execute("ruff", ["format", "--force-exclude", *touched])
        format_code = format_code or reformat_code
    check_code = _execute("ruff", ["check", *ann_args, target])
    if check_code:
        report = _capture("ruff", [*report_args, target])
        found = residuals.collect_residuals(report) if report is not None else None
        if found is not None:
            typer.echo(residuals.render_residuals(found), err=True, nl=False)
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


ParallelDecision = Literal["parallel", "serial", "stop"]
"""How a requested parallel run proceeds once pytest-xdist was looked for."""

XDIST_INSTALL_HINT = (
    "'uv add --dev pytest-xdist' — or a bundle that carries it, "
    "'uv add --dev \"tempest-cli[tools]\"' or "
    "'uv add --dev \"tempest-fastapi-sdk[tests]\"'"
)
"""How to get pytest-xdist, quoted by both the error and the fallback notice."""


def _xdist_missing() -> list[str] | None:
    """Tell whether the environment pytest runs in lacks pytest-xdist.

    Without the plugin, ``pytest -n auto`` stops at argument parsing with
    ``unrecognized arguments: -n`` — true, but it names neither the
    missing package nor the way to get it. This preflight answers first,
    so the caller can say it in words.

    An unknown answer is not "missing": when pytest cannot be resolved
    (:func:`_execute` reports that with its own message) or its
    interpreter cannot be told, the run proceeds and pytest speaks.

    Returns:
        list[str] | None: The pytest argv prefix when the plugin is
        known to be absent; ``None`` when it is present or its presence
        cannot be told.
    """
    argv = resolve_tool("pytest")
    if argv is None:
        return None
    interpreter = _pytest_interpreter(argv)
    if interpreter is None:
        return None
    if _module_available(interpreter, XDIST_MODULE) is not False:
        return None
    return argv


def _parallel_allowed(*, require_xdist: bool) -> ParallelDecision:
    """Decide how a parallel run proceeds, given whether xdist is present.

    Two policies, picked by ``require_xdist``:

    - **required** (the parallel run was asked for by name, ``--fast``):
      a missing plugin is an error — the fix is printed and
      :data:`MISSING_TOOL_EXIT_CODE` comes back, so nothing runs;
    - **preferred** (parallel is only the default): a missing plugin
      degrades the run to serial, with a one-line notice on stderr
      naming the install command. ``tempest test`` keeps working in a
      project that never installed pytest-xdist, it is just slower.

    Args:
        require_xdist (bool): Whether a missing plugin is an error.

    Returns:
        ParallelDecision: ``"parallel"`` when the plugin is there (or its
        presence cannot be told), ``"serial"`` to fall back, ``"stop"``
        after printing the fix.
    """
    argv = _xdist_missing()
    if argv is None:
        return "parallel"
    where = " ".join(argv)
    if require_xdist:
        typer.echo(
            "error: --fast needs pytest-xdist, which is not installed in the "
            f"environment pytest runs in ({where}). Install it with "
            f"{XDIST_INSTALL_HINT} — and retry, or pass --serial to run the "
            "suite serially.",
            err=True,
        )
        return "stop"
    typer.echo(
        "note: pytest-xdist is not installed in the environment pytest runs "
        f"in ({where}), so the suite runs serially. Install it with "
        f"{XDIST_INSTALL_HINT} — to run it in parallel.",
        err=True,
    )
    return "serial"


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
    require_xdist: bool = True,
) -> int:
    """Invoke ``pytest`` with an optional target.

    With ``fast=True`` the suite is spread across pytest-xdist workers:
    ``-n <workers>`` plus ``-p no:cacheprovider``, since several workers
    writing ``.pytest_cache`` at once is a race that buys nothing. The
    cache is what ``--lf`` / ``--ff`` read, so those belong to serial
    runs. Before spawning, the interpreter pytest runs under is asked
    whether it can import pytest-xdist; what happens when it cannot is
    ``require_xdist``'s call (:func:`_parallel_allowed`).

    Args:
        target (str | None): Optional pytest path filter. ``None`` runs
            the default test suite.
        fast (bool): When True, run the suite in parallel with
            pytest-xdist.
        workers (str): Worker count for ``fast`` — an integer, ``auto``
            (one per CPU core: physical when ``psutil`` is importable) or
            ``logical``, exactly as ``pytest -n`` takes it. Ignored when
            the run is serial.
        require_xdist (bool): With ``fast``, whether a missing
            pytest-xdist stops the run (``True``, the default) or degrades
            it to serial with a notice (``False``, what the CLI passes
            when parallel is only its default).

    Returns:
        int: The pytest exit code, or :data:`MISSING_TOOL_EXIT_CODE` when
        pytest — or a required pytest-xdist — is absent.
    """
    if fast:
        decision = _parallel_allowed(require_xdist=require_xdist)
        if decision == "stop":
            return MISSING_TOOL_EXIT_CODE
        fast = decision == "parallel"
    return _execute("pytest", _pytest_args(target, fast=fast, workers=workers))


def _tool_step(executable: str, args: list[str]) -> tuple[str, Callable[[], int]]:
    """Pair a tool invocation with the label ``check`` echoes for it.

    Args:
        executable (str): The tool to run (``ruff``, ``mypy``, ``pytest``).
        args (list[str]): The arguments handed to it.

    Returns:
        tuple[str, Callable[[], int]]: ``("<executable> <args>", thunk)``,
        where calling the thunk runs the tool and returns its exit code.
    """
    return f"{executable} {' '.join(args)}", lambda: _execute(executable, args)


def _extra_step(
    step: CheckStep, target: str, options: StepOptions
) -> tuple[str, Callable[[], int]]:
    """Pair a caller-supplied step with the label ``check`` echoes for it.

    Args:
        step (CheckStep): The step to run.
        target (str): The path handed to the step.
        options (StepOptions): What ``check --rule`` / ``--strict`` parsed.

    Returns:
        tuple[str, Callable[[], int]]: ``(step.name, thunk)``. The thunk
        calls ``step.run_with_options(target, options)`` when the step
        declares it, ``step.run(target)`` otherwise.
    """
    with_options = step.run_with_options
    if with_options is not None:
        return step.name, lambda: with_options(target, options)
    return step.name, lambda: step.run(target)


def run_full_check(
    target: str,
    *,
    config: TempestConfig | None = None,
    fast: bool = False,
    workers: str = DEFAULT_FAST_WORKERS,
    extra_steps: Sequence[CheckStep] = (),
    require_xdist: bool = True,
    step_options: StepOptions = StepOptions(),
) -> int:
    """Run the entire quality gate sequentially.

    Order: ``ruff check`` → ``ruff format --check`` → ``mypy`` → each of
    ``extra_steps``, in the order given → ``pytest``. Every step is
    announced on stderr as ``$ <command line>`` (``$ <name>`` for an
    extra step) and the gate stops at the first non-zero exit code, so
    failures surface fast. The extra steps sit before ``pytest`` because
    they are static checks: a layering rule should fail in a second, not
    after the whole suite.

    With ``fast=True`` the pytest step runs the way :func:`run_pytest`
    runs it with ``fast=True``. The pytest-xdist preflight happens
    *before* the first step, so a required plugin that is missing fails
    in a second instead of after lint and mypy have already run, and a
    merely preferred one degrades the pytest step to serial up front.

    Args:
        target (str): The path inspected by ruff/mypy and handed to every
            extra step. Pytest always runs against the project's
            configured ``testpaths``.
        config (TempestConfig | None): Resolved ``[tool.tempest]`` config
            controlling the ANN rules and mypy flags layered onto the
            ruff/mypy steps. When ``None`` the default level is used.
        fast (bool): When True, run the pytest step in parallel with
            pytest-xdist.
        workers (str): The ``pytest -n`` value used when ``fast`` is True.
        extra_steps (Sequence[CheckStep]): Caller-supplied steps run
            after ``mypy`` and before ``pytest``. Empty by default, which
            leaves the gate exactly as it was without them.
        require_xdist (bool): With ``fast``, whether a missing
            pytest-xdist stops the gate or degrades the pytest step to
            serial — as in :func:`run_pytest`.
        step_options (StepOptions): Handed to every extra step that
            declares ``run_with_options``; the built-in steps never see it.

    Returns:
        int: The first non-zero exit code — a tool's or an extra step's —
        or ``0`` when every gate passed.
    """
    if fast:
        decision = _parallel_allowed(require_xdist=require_xdist)
        if decision == "stop":
            return MISSING_TOOL_EXIT_CODE
        fast = decision == "parallel"
    resolved = config or TempestConfig()
    steps: list[tuple[str, Callable[[], int]]] = [
        _tool_step("ruff", ["check", *_ruff_ann_args(resolved), target]),
        _tool_step("ruff", ["format", "--check", target]),
        _tool_step("mypy", [*resolved.mypy_flags(), target]),
        *(_extra_step(step, target, step_options) for step in extra_steps),
        _tool_step("pytest", _pytest_args(None, fast=fast, workers=workers)),
    ]
    for label, run in steps:
        typer.echo(f"$ {label}", err=True)
        code = run()
        if code != 0:
            return code
    return 0


__all__: list[str] = [
    "DEFAULT_FAST_WORKERS",
    "MISSING_TOOL_EXIT_CODE",
    "XDIST_INSTALL_HINT",
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
