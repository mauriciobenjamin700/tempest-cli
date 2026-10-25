# Use as a library

Everything the CLI does is importable. Two situations are worth it.

## Calling the runners from your code

```python
from tempest_cli import load_tempest_config, run_full_check

config = load_tempest_config()
exit_code = run_full_check(".", config=config)
```

Each step is callable on its own too, with the same exit-code contract:

```python
from tempest_cli import (
    TempestConfig,
    run_mypy,
    run_pytest,
    run_ruff_check,
    run_ruff_fix,
    run_ruff_format,
)

strict = TempestConfig(typing_strictness="strict")

run_ruff_check("src", config=strict)      # ruff check + the level's ANN rules
run_ruff_fix("src", unsafe=False, config=strict)
run_ruff_format("src", check=True)        # --check: writes nothing
run_mypy("src", config=strict)
run_pytest("tests/unit")
run_pytest("tests/unit", fast=True, workers="4")   # pytest-xdist: -n 4; without it, 127
run_pytest("tests", fast=True, require_xdist=False)  # without pytest-xdist: serial, with a notice
```

`load_tempest_config(start)` walks up from `start` (the cwd by default)
to the nearest `pyproject.toml` and returns the resolved
`TempestConfig`. `find_pyproject` does the lookup alone, when you want
the path.

## Mounting the gate on your own CLI

A tool that already has its own CLI can expose these commands under its
own name — without copying a single command body:

```python
import typer

from tempest_cli.main import register_commands

cli: typer.Typer = typer.Typer(name="mytool")


@cli.command("deploy")
def deploy() -> None:
    """A command the tool already had."""


register_commands(cli)
```

Now `mytool check`, `mytool lint` and the rest exist, with the same
behavior and the same `[tool.tempest]` reading.

!!! info "This is exactly what `tempest-fastapi-sdk` does"
    The SDK's `tempest check` is this `register_commands` called on its
    app. That is why the two never diverge: there is one
    implementation.

## Adding steps to `check`

`tempest-cli` knows nothing about any framework, on purpose. The
framework does, though: "every service inherits `BaseService`" is a rule
of whoever lays out the project, not of whoever runs ruff. `CheckStep`
is the seam — you write the rule, `check` runs it.

A `CheckStep` has two fields: `name`, the label `check` echoes as
`$ <name>` on stderr, and `run`, a function that takes the `check`
target (the path from the command line, `.` by default) and returns an
exit code — `0` means it passed.

```python
from pathlib import Path

import typer

from tempest_cli import CheckStep
from tempest_cli.main import register_commands


def no_print(target: str) -> int:
    """Fail when a module under ``target`` calls ``print``."""
    offenders: list[str] = [
        f"{path}:{number}: use logging instead of print()"
        for path in sorted(Path(target).rglob("*.py"))
        for number, line in enumerate(path.read_text().splitlines(), start=1)
        if line.lstrip().startswith("print(")
    ]
    for offender in offenders:
        typer.echo(offender, err=True)
    return 1 if offenders else 0


cli: typer.Typer = typer.Typer(name="mytool")


@cli.command("deploy")
def deploy() -> None:
    """A command the tool already had."""


register_commands(cli, extra_steps=[CheckStep(name="no-print", run=no_print)])

if __name__ == "__main__":
    cli()
```

With a module `pkg/a.py` that calls `print("x")`:

```console
$ python mytool.py check pkg
$ ruff check --extend-select ANN001,ANN201,ANN202,ANN205,ANN206 pkg
All checks passed!
$ ruff format --check pkg
1 file already formatted
$ mypy --disallow-untyped-defs --disallow-incomplete-defs pkg
Success: no issues found in 1 source file
$ no-print
pkg/a.py:2: use logging instead of print()
$ echo $?
1
```

The order is `ruff check` → `ruff format --check` → `mypy` → the extra
steps, in list order → `pytest`. An extra step is a static check: it
sits before the suite so it fails in a second, not after it. The
contract is the built-in steps' — the first non-zero code stops the gate
and becomes `check`'s exit code, in parallel or with `--serial`.

!!! tip "The message is yours"
    `check` only echoes the name. What the step prints is what the user
    reads, so name the file, the line and the fix — as `no-print` does
    above.

Without the CLI, the same holds for `run_full_check`:

```python
from tempest_cli import CheckStep, run_full_check


def always_passes(target: str) -> int:
    """A step that accepts any target."""
    return 0


exit_code: int = run_full_check(
    ".", extra_steps=[CheckStep(name="always-passes", run=always_passes)]
)
```

`extra_steps` is empty by default: without it, the gate is exactly what
it was.

### Options for the step: `--rule` and `--strict`

A step that reports rule codes with a severity (an error that fails, a
warning that does not) wants two options ruff, mypy and pytest do not know:
filtering one rule and making warnings fail. `check` takes both —
`--rule <CODE>` (repeatable) and `--strict` / `--no-strict` — and hands
them, already typed, in a `StepOptions` to the step that declares
`run_with_options`. The step never reads the command line.

```python
from pathlib import Path

import typer

from tempest_cli import CheckStep, StepOptions
from tempest_cli.main import register_commands

RULES: dict[str, str] = {"BL001": "time.sleep(", "BL002": "os.getenv("}
"""Rule code to the call it reports; BL002 is only a warning."""

WARNINGS: frozenset[str] = frozenset({"BL002"})
"""Codes that fail the step only under --strict."""


def no_blocking_calls(target: str, options: StepOptions) -> int:
    """Report the calls in RULES, filtered by --rule, failing per --strict."""
    selected = set(options.rules) or set(RULES)
    failed = False
    for path in sorted(Path(target).rglob("*.py")):
        for number, line in enumerate(path.read_text().splitlines(), start=1):
            for code in sorted(selected):
                if RULES[code] in line:
                    warning = code in WARNINGS
                    tag = " (warning)" if warning else ""
                    typer.echo(f"{path}:{number}: {code}{tag}", err=True)
                    failed = failed or not warning or bool(options.strict)
    return 1 if failed else 0


def no_blocking_calls_plain(target: str) -> int:
    """The same step, called without options."""
    return no_blocking_calls(target, StepOptions())


cli: typer.Typer = typer.Typer(name="mytool")


@cli.command("deploy")
def deploy() -> None:
    """A command the tool already had."""


register_commands(
    cli,
    extra_steps=[
        CheckStep(
            name="no-blocking-calls",
            run=no_blocking_calls_plain,
            run_with_options=no_blocking_calls,
        )
    ],
)

if __name__ == "__main__":
    cli()
```

With a `pkg/a.py` calling `os.getenv(...)` on line 6 (the step's part
only; real output):

```console
$ python mytool.py check pkg
$ no-blocking-calls
pkg/a.py:6: BL002 (warning)
$ pytest -n auto -p no:cacheprovider
...
$ echo $?
0
$ python mytool.py check pkg --strict
$ no-blocking-calls
pkg/a.py:6: BL002 (warning)
$ echo $?
1
$ python mytool.py check pkg --rule BL001 --strict
$ no-blocking-calls
$ pytest -n auto -p no:cacheprovider
...
$ echo $?
0
```

- `rules` is an empty tuple and `strict` is `None` when nothing was typed;
  `StepOptions.given` tells whether either came in.
- A step without `run_with_options` still gets only the target, through
  `run`.
- **An option nothing reads is refused.** When no step of the `check`
  declares `run_with_options`, `--rule` / `--strict` exit `2` before any
  step runs — a gate that passes while ignoring the flag would be worse
  than an error.

## Generating the PR prompt without the CLI

```python
from pathlib import Path

from tempest_cli import PromptLanguage, generate_pr_prompt

prompt, context, template = generate_pr_prompt(
    base="main",
    head=None,
    cwd=Path("."),
    template=None,
    language=PromptLanguage.EN_US,
    max_files=20,
    max_chars=8000,
)
print(len(context.commits), "commits;", template.source)
```

`generate_pr_prompt` raises `GitError` when git fails or a ref does not
resolve.

## Recap

- Runners, config and the prompt generator are all importable.
- `register_commands(app)` mounts the eight commands on any `Typer`.
- `extra_steps=[CheckStep(...)]` puts your own rules in `check`, after
  `mypy` and before `pytest`.
- Exit codes are the tools', identical from the CLI and from a direct
  call.
