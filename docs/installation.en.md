# Installation

```bash
uv add --dev tempest-cli
```

Or with pip:

```bash
pip install tempest-cli
```

Requires **Python 3.11+**. It brings `ruff` along — six of the eight
commands are ruff, so the gate runs the moment the package installs. The
other runtime dependency is `typer`.

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

**`ruff` comes with the package**: install it and `lint`, `fix`,
`format` and `fmt-check` already work — nothing else to install.

```bash
uv add --dev tempest-cli
tempest-cli fix            # runs right away
```

`mypy` and `pytest` stay with you. A mypy bump changes which errors your
code starts reporting, and pytest has to match your plugins and your
suite — those versions are the project's call. Add them yourself, or
take the bundle:

```bash
uv add --dev "tempest-cli[tools]"   # mypy + pytest
```

!!! question "Why ruff is a dependency and the other two are not"
    Six of the eight commands are ruff — a `tempest-cli` without ruff is
    a gate that cannot run. And it costs nothing: ruff is a static
    binary with no Python dependencies at all, so no bound of its enters
    your project's resolution. mypy and pytest, in contrast, run through
    your code and your suite; pinning them here would be deciding for
    you.

### The lookup order

What your project pins **wins** over the bundled ruff. The CLI runs the
first thing it finds, in this order:

1. **the project's environment** — `$VIRTUAL_ENV`, then the nearest
   `.venv` up the tree;
2. **the CLI's own environment** — where the bundled ruff lives;
3. **`PATH`** — skipping a version-manager shim that dispatches nowhere
   (see below);
4. **`uv run --with <tool> <tool>`** when `uv` is available — the
   project's environment plus the tool, with no activation and no prior
   `uv sync` required.

If nothing resolves, the command exits with **127**, naming the missing
tool and how to install it, instead of raising a traceback.

!!! info "Why `PATH` does not come first"
    On a pyenv/asdf machine the `shims` directory is on `PATH`
    globally and holds a stub for every tool any installed version ever
    provided. Looking up `ruff` there finds `~/.pyenv/shims/ruff` even
    when the project has no ruff at all — and running it prints
    `pyenv: ruff: command not found`. So the run's own environments win
    over `PATH`, and a shim is only accepted after proving it dispatches
    (`<tool> --version` exiting `0`).

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

- `uv add --dev tempest-cli`, Python 3.11+, `ruff` already included.
- `mypy` and `pytest` are yours — or take `"tempest-cli[tools]"`.
- Two executables: `tempest-cli` and the `tc` alias.
- What the project pins beats the bundled ruff; then come `PATH` (never
  a dead shim) and `uv run --with`.
- A missing tool means exit 127 with a message, not a traceback.
