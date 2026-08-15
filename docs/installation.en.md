# Installation

```bash
uv add --dev tempest-cli
```

Or with pip:

```bash
pip install tempest-cli
```

Requires **Python 3.11+**. The only runtime dependency is `typer`.

## Where ruff, mypy and pytest come from

`tempest-cli` does **not** pin any of the three: it runs whatever it
finds, in this order:

1. the executable on `PATH` (activated venv, global install);
2. `uv run <tool>` when `uv` is available — which makes it work in a
   project whose venv was never activated.

If neither resolves, the command exits with **127** naming the missing
tool, instead of raising a traceback.

!!! tip "Why the versions are not pinned"
    A ruff version pinned here would become the ceiling for every
    project installing this package — and upgrading the linter is a
    decision for whoever writes the code, not for whoever packages the
    gate.

If you would rather install all three alongside:

```bash
uv add --dev "tempest-cli[tools]"
```

## Verifying

```bash
tempest-cli --version
tempest-cli check --help
```

## In CI

Every command returns the underlying tool's exit code, so the job reads
it exactly as it would read `ruff` directly:

```yaml
- name: Quality gate
  run: uv run tempest-cli check
```

## Recap

- `uv add --dev tempest-cli`, Python 3.11+, `typer` as the only
  dependency.
- Tools come from the project environment (or through `uv run`).
- A missing tool means exit 127 with a message, not a traceback.
