# Installation

```bash
uv add --dev tempest-cli
```

Or with pip:

```bash
pip install tempest-cli
```

Requires **Python 3.11+**. The only runtime dependency is `typer`.

It installs **two executables**: `tempest-cli` and the short alias `tc`.
They are the same program — everything in these docs applies to both.

```bash
tc check        # identical to tempest-cli check
```

!!! warning "`tc` is also iproute2's `tc(8)`"
    While the environment that installed the package is on `PATH`, `tc`
    resolves to this CLI. For Linux traffic control, call it by absolute
    path (`/usr/sbin/tc`) — or use `tempest-cli` and leave `tc` alone.

## Where ruff, mypy and pytest come from

`tempest-cli` does **not** pin any of the three: it runs whatever it
finds, in this order:

1. **the environments of the run** — the directory of the interpreter
   running the CLI (where the `[tools]` extra installs all three), then
   `$VIRTUAL_ENV`, then the nearest `.venv` up the tree;
2. **`PATH`** — skipping a version-manager shim that dispatches nowhere
   (see below);
3. **`uv run --with <tool> <tool>`** when `uv` is available — the
   project's environment plus the tool, with no activation and no prior
   `uv sync` required.

If nothing resolves, the command exits with **127**, naming the missing
tool and how to install it, instead of raising a traceback.

!!! info "Why `PATH` does not come first"
    On a pyenv/asdf machine the `shims` directory is on `PATH`
    globally and holds a stub for every tool any installed version ever
    provided. Looking up `ruff` there finds `~/.pyenv/shims/ruff` even
    when the project has no ruff at all — and running it prints
    `pyenv: ruff: command not found`. So the run's own environment wins
    over `PATH`, and a shim is only accepted after proving it dispatches
    (`<tool> --version` exiting `0`).

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
tc --version          # the same program
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
- Two executables: `tempest-cli` and the `tc` alias.
- Tools come from the run's environment, from `PATH` (never a dead
  shim), or through `uv run --with`.
- A missing tool means exit 127 with a message, not a traceback.
