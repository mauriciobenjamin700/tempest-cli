# Changelog

All notable changes to **tempest-cli** are listed below.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] — 2026-08-15

### Added

- **`tc`, the short alias.** The package now installs a second console
  script pointing at the same entry point, so `tc check` is `tempest-cli
  check`. While the installing environment is on `PATH`, `tc` shadows
  iproute2's `tc(8)`; call the traffic controller as `/usr/sbin/tc` when
  you need it.

### Fixed

- **The gate no longer runs a dead pyenv/asdf shim.** `tempest-cli fix`
  in a project whose environment has no ruff answered `pyenv: ruff:
  command not found` and exited 127 — the lookup took the first `PATH`
  hit, and on a version-manager machine that hit is a shim that exists
  for every tool any installed interpreter ever provided. The lookup now
  searches the environments that belong to the run first (the CLI's own
  interpreter directory, `$VIRTUAL_ENV`, the nearest `.venv`), accepts a
  shim only after `<tool> --version` proves it dispatches, and applies
  the same check to `uv` itself.

- **The `uv` fallback stopped leaking back to `PATH`.** It ran `uv run
  <tool>`, which falls back to `PATH` when the project environment has
  no such tool — landing on the very shim that had just been rejected.
  It is now `uv run --with <tool> <tool>`, so the tool is always present
  in the run's overlay; a version pinned by the project still wins,
  since uv resolves the overlay against the project's requirements.

- **The 127 message names the fix.** It now says what to install
  (`uv add --dev ruff`, or `"tempest-cli[tools]"` for the set) instead
  of only reporting that `PATH` and `uv` came up empty.

## [0.1.0] — 2026-08-15

First release. Extracted from
[`tempest-fastapi-sdk`](https://github.com/mauriciobenjamin700/tempest-fastapi-sdk),
where the same gate shipped as `tempest check` — reachable only by
installing a FastAPI SDK.

### Added

- **The quality gate**: `lint`, `fix`, `format`, `fmt-check`, `type`,
  `test` and `check`, over `ruff` / `mypy` / `pytest`. Each returns the
  underlying tool's exit code; `check` runs the four in order and stops
  at the first failure.

- **Typing strictness as configuration**, read from `[tool.tempest]
  typing_strictness` in `pyproject.toml` (`lenient` | `standard` |
  `strict`, defaulting to `standard`), with a `--strictness` / `-s`
  override per run. Levels only ever **add** flags on top of the
  project's own `[tool.ruff]` / `[tool.mypy]`. `ANN401` is never enabled
  at any level: `Any` is a legitimate annotation.

- **`pr-prompt`** — builds the prompt that makes an AI write a branch's
  pull-request description, carrying the repository's own PR template
  (or a bundled PT-BR / EN-US default), the rules that stop a model from
  returning the template unfilled, and the branch context read as
  `base...head`.

- **A library surface**: `run_full_check`, `run_ruff_check`,
  `run_ruff_fix`, `run_ruff_format`, `run_mypy`, `run_pytest`,
  `load_tempest_config`, `find_pyproject`, `generate_pr_prompt`.

- **`register_commands(app)`** mounts the whole gate onto an existing
  `typer.Typer`, so another CLI exposes these commands under its own
  name without copying a body. `tempest-fastapi-sdk` uses exactly this,
  which is what keeps `tempest check` and `tempest-cli check` identical.

### Notes

- The only runtime dependency is `typer`. `ruff`, `mypy` and `pytest`
  are invoked from the active environment (or through `uv run` when they
  are not on `PATH`), so the project pins the versions it wants. The
  `[tools]` extra installs all three for whoever prefers that.
- Measured against the SDK it came from: reaching these commands there
  loaded 38.7 MB of dependencies and about 0.5 s of import time per
  invocation — for four commands that touch none of it. A test in this
  package asserts that importing it pulls no web framework.
