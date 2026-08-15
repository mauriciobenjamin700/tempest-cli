# tempest-cli

[![PyPI](https://img.shields.io/pypi/v/tempest-cli.svg)](https://pypi.org/project/tempest-cli/)
[![Python](https://img.shields.io/pypi/pyversions/tempest-cli.svg)](https://pypi.org/project/tempest-cli/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Documentação: [Português (BR)](https://mauriciobenjamin700.github.io/tempest-cli/) · [English (US)](https://mauriciobenjamin700.github.io/tempest-cli/en/)**

One command for the quality gate of any Python project — `ruff` +
`mypy` + `pytest`, with a typing-strictness dial that lives in your
`pyproject.toml` instead of in four different Makefile targets.

Framework-agnostic on purpose: Django, Flask, Litestar, FastAPI, a
library, a script. It brings `ruff` along, so the gate runs the moment
you install it; `typer` is the only other runtime dependency.

```bash
uv add --dev tempest-cli

tempest-cli check          # lint + fmt-check + type + test, in order, stops at the first failure
tempest-cli fix            # every ruff autofix, then format
tempest-cli type -s strict # override the configured strictness for one run

tc check                   # `tc` is the short alias for the same program
```

## Why it exists

The four commands are always the same, and every project rewrites them
slightly differently — a Makefile here, a `tox.ini` there, a CI job that
drifts from what runs locally. `tempest-cli check` is the same gate on
your machine and in CI, and `--strictness` makes "how much typing do we
enforce" a value in `pyproject.toml` rather than a flag someone
remembered to pass.

## Commands

| Command | Runs |
| --- | --- |
| `tempest-cli lint` | `ruff check` |
| `tempest-cli fix` | `ruff check --fix` then `ruff format` (`--unsafe` for the risky autofixes) |
| `tempest-cli format` | `ruff format` (writes) |
| `tempest-cli fmt-check` | `ruff format --check` (read-only) |
| `tempest-cli type` | `mypy` |
| `tempest-cli test` | `pytest` |
| `tempest-cli check` | all four, in order, stopping at the first failure |
| `tempest-cli pr-prompt` | builds the prompt that makes an AI write this branch's PR description |

Every command takes an optional path (`tempest-cli lint src/`) and
returns the underlying tool's exit code, so CI reads it exactly as it
would read `ruff` directly.

## Typing strictness

```toml
[tool.tempest]
typing_strictness = "strict"   # lenient | standard | strict
```

The level **adds** flags on top of your own `[tool.ruff]` /
`[tool.mypy]` — it never relaxes what you already configured:

| Level | ruff (extra `ANN` rules) | mypy |
| --- | --- | --- |
| `lenient` | none | none |
| `standard` | `ANN001`, `ANN201`, `ANN202`, `ANN205`, `ANN206` | `--disallow-untyped-defs --disallow-incomplete-defs` |
| `strict` | the above plus `ANN204` | `--strict` |

`ANN401` is never enabled at any level: `Any` is a legitimate
annotation. The levels enforce that things *are* annotated, never that
they avoid `Any`.

Override per run with `--strictness` / `-s`. Absent config means
`standard`.

## PR descriptions from the branch itself

```bash
tempest-cli pr-prompt | claude -p
tempest-cli pr-prompt develop --lang en --out pr_prompt.txt
```

The prompt carries the repository's own pull-request template (or a
bundled PT-BR / EN-US default), the rules that stop a model from handing
back the template with its placeholders intact, and the branch context:
commit subjects, changed files, and a bounded excerpt of each patch.

Diffs are read as `base...head` — the merge-base diff the forge shows —
so commits that landed on the base after the branch started are not
attributed to it. Whatever the bounds leave out is stated inside the
prompt, so a partial diff reads as partial.

## Use it as a library

```python
from tempest_cli import load_tempest_config, run_full_check

config = load_tempest_config()
exit_code = run_full_check(".", config=config)
```

And to expose the same gate from your own CLI, without copying command
bodies:

```python
import typer

from tempest_cli.main import register_commands

cli: typer.Typer = typer.Typer(name="mytool")
register_commands(cli)
```

## Where the tools come from

**`ruff` comes with the package** — six of the eight commands are ruff,
so `lint`, `fix`, `format` and `fmt-check` work straight after
`uv add --dev tempest-cli`, with nothing else to install. It is a static
binary wheel with no Python dependencies of its own, so nothing of its
propagates into your resolution.

`mypy` and `pytest` are deliberately left to you — a mypy bump changes
which errors your code reports, and pytest has to match your plugins and
your suite. Add them yourself, or take the bundle:

```bash
uv add --dev "tempest-cli[tools]"
```

Whatever you pin wins over the bundled ruff. The lookup runs in this
order:

1. the project's environment — `$VIRTUAL_ENV`, then the nearest `.venv`
   up the tree;
2. the environment `tempest-cli` itself runs from (where the bundled
   ruff lives);
3. `PATH`, skipping a pyenv/asdf shim that dispatches nowhere (the one
   that answers `pyenv: ruff: command not found`);
4. `uv run --with <tool> <tool>`, when `uv` is available.

## Relationship with tempest-fastapi-sdk

This package was extracted from
[`tempest-fastapi-sdk`](https://github.com/mauriciobenjamin700/tempest-fastapi-sdk),
where the same gate shipped as `tempest check`. Getting it meant
installing FastAPI, SQLAlchemy, Alembic and Pydantic — 38.7 MB of
dependencies and roughly 0.5 s of import time per invocation, for four
commands that never touch any of it.

`tempest check` keeps working: the SDK depends on this package and
registers the same commands. Both stay in sync because there is now one
implementation.

## License

MIT — see [LICENSE](LICENSE).
