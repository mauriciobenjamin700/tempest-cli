# Commands

Eight commands. All take an optional path and return the underlying
tool's exit code.

| Command | Runs |
| --- | --- |
| `lint` | `ruff check` |
| `fix` | `ruff check --fix` then `ruff format` |
| `format` | `ruff format` (writes) |
| `fmt-check` | `ruff format --check` (read-only) |
| `type` | `mypy` |
| `test` | `pytest` |
| `check` | the four above, in order, stopping at the first failure |
| `pr-prompt` | builds the PR-description prompt — [its own page](pr-prompt.md) |

## The full gate

```bash
tempest-cli check              # the whole project
tempest-cli check src/         # a single path
tempest-cli check -s strict    # with raised typing strictness for this run
```

The order is deliberate: **lint → formatting → types → tests**. What
fails fastest and is cheapest to fix comes first, and the run stops at
the first failure — there is no point running the whole suite when the
imports are unsorted.

## Fixing what can be fixed

```bash
tempest-cli fix                # safe autofixes + formatting
tempest-cli fix --unsafe       # also ruff's risky autofixes
```

`fix` makes two passes: `ruff check --fix` (sorts and dedupes imports,
drops unused ones, normalizes quotes) and then `ruff format`
(indentation, line length, blank lines).

!!! warning "`--unsafe` can change behavior"
    Ruff's "unsafe" autofixes are the ones that may alter semantics.
    They are off by default. Turned them on? Read the `git diff` before
    committing.

## One at a time

```bash
tempest-cli lint src/
tempest-cli fmt-check
tempest-cli type mypackage
tempest-cli test tests/unit
```

`test` forwards the path to pytest as a filter; with no argument it runs
the whole suite.

## What each returns

The exit code is the tool's own, untranslated:

```bash
tempest-cli lint; echo "exited $?"
```

There is exactly one code of its own: **127**, when the tool is not on
`PATH` and `uv` is not either — the message then names what was missing.

## Recap

- `check` is lint + fmt-check + type + test, in order, stopping at the
  first failure.
- `fix` is the pass that repairs; `--unsafe` only when you will review.
- Exit codes are the tools'; 127 means a missing tool.
