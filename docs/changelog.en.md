# Changelog

The full history lives in the repository's
[`CHANGELOG.md`](https://github.com/mauriciobenjamin700/tempest-cli/blob/main/CHANGELOG.md).

## [0.3.0] — 2026-08-15

### Changed

- **`ruff` now ships with the package.** It left the `[tools]` extra for
  the runtime dependencies, so `uv add --dev tempest-cli` is enough for
  `lint`, `fix`, `format` and `fmt-check` to run. The cost is nil: ruff
  is a static binary wheel with no Python dependencies of its own, so no
  bound of its reaches a consumer's resolution. `mypy` and `pytest` stay
  out on purpose; `[tools]` now installs exactly those two.
- **The project's environment is searched before the CLI's own.** With
  ruff bundled, the CLI's environment always has one — looking there
  first would silently override a version the project pinned whenever
  `tempest-cli` lives apart from it (`uv tool install`, pipx). The order
  is now `$VIRTUAL_ENV` → nearest `.venv` → the CLI's environment →
  `PATH` → `uv run --with`.

## [0.2.0] — 2026-08-15

### Added

- **`tc`**, a short alias installed next to `tempest-cli` — the same
  program. While the installing environment is on `PATH` it shadows
  iproute2's `tc(8)` (call `/usr/sbin/tc` for the network one).

### Fixed

- **The gate no longer runs a dead pyenv/asdf shim.** `tempest-cli fix`
  in a project without ruff answered `pyenv: ruff: command not found`
  and exited 127. The lookup now searches the run's own environments
  first (the CLI's interpreter directory, `$VIRTUAL_ENV`, the nearest
  `.venv`) and accepts a shim only after `<tool> --version` proves it
  dispatches — the same check applies to `uv` itself.
- **The `uv` fallback stopped leaking back to `PATH`.** It was `uv run
  <tool>`, which falls back to `PATH` when the project environment has
  no such tool — landing on the shim just rejected. It is now `uv run
  --with <tool> <tool>`.
- **The 127 message names the fix** (`uv add --dev ruff`, or
  `"tempest-cli[tools]"` for the set).

## [0.1.0] — 2026-08-15

First release. Extracted from
[`tempest-fastapi-sdk`](https://github.com/mauriciobenjamin700/tempest-fastapi-sdk),
where the same gate shipped as `tempest check` — reachable only by
installing a FastAPI SDK.

### Added

- The gate: `lint`, `fix`, `format`, `fmt-check`, `type`, `test` and
  `check`.
- Typing strictness through `[tool.tempest] typing_strictness`, with a
  `--strictness` override per run.
- `pr-prompt` — the prompt that makes an AI write the PR description.
- A library surface (`run_full_check`, `load_tempest_config`,
  `generate_pr_prompt`, …) and `register_commands(app)` to mount the
  gate on another CLI.

### Notes

- The only runtime dependency is `typer`. The tools come from the
  project environment.
- Measured against the SDK it came from: reaching these commands there
  loaded 38.7 MB of dependencies and ~0.5 s of import time per
  invocation. A test in this package asserts that importing it pulls no
  web framework.
