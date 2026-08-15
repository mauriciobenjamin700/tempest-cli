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
- Exit codes are the tools', identical from the CLI and from a direct
  call.
