# Changelog

The full history lives in the repository's
[`CHANGELOG.md`](https://github.com/mauriciobenjamin700/tempest-cli/blob/main/CHANGELOG.md).

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
