# tempest-cli

One command for the quality gate of any Python project — `ruff`, `mypy`
and `pytest` — with the typing strictness living in `pyproject.toml`
instead of spread across four Makefile targets.

Framework-agnostic on purpose: Django, Flask, Litestar, FastAPI, a
library, a script. There are two runtime dependencies: `typer` and
`ruff` — the latter ships along, so the gate runs the moment you install
it.

```bash
uv add --dev tempest-cli
tempest-cli check
tc check          # the same, through the short alias
```

```console
$ tempest-cli check
$ ruff check --extend-select ANN001,ANN201,ANN202,ANN205,ANN206 .
All checks passed!
$ ruff format --check .
10 files already formatted
$ mypy --disallow-untyped-defs --disallow-incomplete-defs .
Success: no issues found in 10 source files
$ pytest
59 passed in 0.98s
```

## Why it exists

The four commands are always the same, and every project rewrites them
slightly differently — a Makefile here, a `tox.ini` there, a CI job that
drifts from what runs locally. `tempest-cli check` is the **same** gate
in both places, and `--strictness` turns "how much typing do we enforce"
into a versioned value rather than a flag someone remembered to pass.

!!! info "Where it came from"
    This package was extracted from
    [`tempest-fastapi-sdk`](https://github.com/mauriciobenjamin700/tempest-fastapi-sdk),
    where the same gate shipped as `tempest check`. Getting it meant
    installing FastAPI, SQLAlchemy, Alembic and Pydantic — **38.7 MB**
    of dependencies and roughly **0.5 s of import time** per invocation,
    for four commands that touch none of it.

    `tempest check` keeps working: the SDK depends on this package and
    registers the same commands. There is one implementation.

## What is here

<div class="grid cards" markdown>

- **[Installation »](installation.md)** — installing, and where ruff,
  mypy and pytest come from.
- **[Commands »](commands.md)** — all eight, what each runs and returns.
- **[Typing strictness »](configuration.md)** — the three levels, what
  each adds, and why `ANN401` is never enabled.
- **[PR descriptions »](pr-prompt.md)** — the prompt that makes an AI
  write the PR description from the branch's own diff.
- **[Use as a library »](library.md)** — calling the runners from your
  code and mounting the gate on your own CLI.
- **[Reference »](reference.md)** — signatures generated from the
  docstrings.

</div>

## Recap

- One command (`check`) runs lint, formatting, types and tests, in that
  order, stopping at the first failure.
- The strictness level is project configuration, with a per-run
  override.
- No web framework is installed alongside — the package has a test that
  asserts it.
