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

!!! tip "`tc` is the short form"
    The package installs `tempest-cli` and `tc` pointing at the same
    program. The examples use the long name; `tc check`, `tc fix` and
    `tc type -s strict` work exactly the same.

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

## The suite in parallel: `--fast`

A suite whose tests are already isolated (a database per test, no global
state) pays the serial time and buys nothing for it. `--fast` spreads the
suite across the cores with
[pytest-xdist](https://pytest-xdist.readthedocs.io/):

```bash
tempest-cli test --fast              # -n auto: one worker per core
tempest-cli test --fast -w 4         # four workers
tempest-cli test tests/unit --fast   # the target is still forwarded
tempest-cli check --fast             # the full gate, with the test step in parallel
```

Underneath it becomes `pytest -n <workers> -p no:cacheprovider [target]`.
`-p no:cacheprovider` is there because several workers writing
`.pytest_cache` at once is a race that buys nothing — and that cache is
what `--lf` / `--ff` read, so those two remain a serial-run affair.

`--workers` (`-w`) takes what `pytest -n` takes: an integer, `auto` (the
default) or `logical`. Without `--fast` it is a usage error (exit 2)
instead of being silently ignored.

!!! info "`auto` counts physical cores when `psutil` is installed"
    pytest-xdist decides: with `psutil` importable, `auto` is the number of
    **physical** cores; without it, the number of logical CPUs. On a machine
    with 6 cores and 12 threads, with `psutil` in the environment, `auto`
    started `created: 6/6 workers`. Want the 12 threads? `-w logical` or
    `-w 12`.

!!! note "Why a flag, not `tempest-cli test fast`"
    `test` already takes a positional path. `test fast` keeps meaning
    "run pytest on the `fast/` folder" — a subcommand by that name would
    break anyone who has one.

### Without pytest-xdist

Before running anything, the CLI asks **the very interpreter that will
run pytest** whether it can import `xdist` — not the CLI's own
interpreter, which under `uv tool install` or pipx lives in a different
environment. When it is missing, the message names what to install and
the exit code is **127**, with no traceback:

```console
$ tempest-cli test --fast
error: --fast needs pytest-xdist, which is not installed in the environment pytest runs in (.venv/bin/pytest). Install it with 'uv add --dev pytest-xdist' — or a bundle that carries it, 'uv add --dev "tempest-cli[tools]"' or 'uv add --dev "tempest-fastapi-sdk[tests]"' — and retry, or drop --fast to run the suite serially.
$ echo $?
127
```

Under `check --fast` the check happens **before** the first step: there
is no point waiting for lint and mypy to finish to learn the tests will
not run.

### A test that fails only in parallel

Parallelism exposes tests that depend on order or on an idle machine:
two tests writing the same file, the same port, a module-level global, a
fixed `sleep` waiting for something that takes longer once every core is
busy. Before treating the failure as a regression, run the test **alone
and serially**:

```bash
tempest-cli test "tests/test_scheduler.py::test_lease_expires"
```

- **It passes alone**: the defect is the test's isolation, not the change
  under review. Fix the test (a file under `tmp_path`, a free port, wait
  on a condition instead of a `sleep`).
- **It fails alone too**: it is a real regression.

## What each returns

The exit code is the tool's own, untranslated:

```bash
tempest-cli lint; echo "exited $?"
```

There is exactly one code of its own: **127**, when the tool is in none
of the places the CLI looks — the run's environment, `PATH`, `uv run
--with` — and the message then names what was missing and how to install
it. The lookup order is in
[Installation](installation.md#where-ruff-mypy-and-pytest-come-from).
The same 127 comes out of `--fast` when pytest-xdist is not in pytest's
environment.

## Recap

- `check` is lint + fmt-check + type + test, in order, stopping at the
  first failure.
- `fix` is the pass that repairs; `--unsafe` only when you will review.
- `test --fast` / `check --fast` run the suite with pytest-xdist
  (`-n auto`, `-w N` to choose); a test that fails only in parallel is
  checked by running it alone.
- Exit codes are the tools'; 127 means a missing tool (or the
  pytest-xdist `--fast` needs).
