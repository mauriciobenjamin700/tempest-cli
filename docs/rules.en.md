# Tuning the rules

`tempest-cli` has **no rules of its own**. It calls `ruff` and `mypy`,
and those two read their configuration from your `pyproject.toml` —
`[tool.ruff]` and `[tool.mypy]`. Turning a rule on, off or down is
configuring the tools, exactly as you would without the gate.

The only thing `tempest-cli` adds is
[`typing_strictness`](configuration.md), which **adds** a few flags. This
page shows how to live with both.

## The scary first run

You install the gate in a Django project and run it:

```console
$ tc type
manage.py:4: error: Skipping analyzing "django.core.management": module is installed, but missing library stubs or py.typed marker  [import-untyped]
config/urls.py:1: error: Skipping analyzing "django.contrib": module is installed, but missing library stubs or py.typed marker  [import-untyped]
apps/event/models.py:1: error: Skipping analyzing "django.db": module is installed, but missing library stubs or py.typed marker  [import-untyped]
apps/event/models.py:7: error: Function is missing a return type annotation  [no-untyped-def]
apps/event/migrations/0001_initial.py:6: error: Need type annotation for "dependencies"  [var-annotated]
Found 7 errors in 4 files (checked 8 source files)
```

It reads like your code is rotten. It is not. Look at the error code:

- `import-untyped` — **Django** publishes no type information. That is
  not your code; it is mypy saying it knows nothing about the library.
- `var-annotated` in a **migration** — a file Django generated, that
  nobody wrote by hand and nobody will annotate.
- `no-untyped-def` in `models.py` — that one is yours, and it is real.

One real finding, six of noise. Let's silence the noise without losing
the finding.

!!! tip "Every example on this page was run"
    The before/after numbers come from a sample Django project with
    `manage.py`, `config/`, one app with a `models.py`, and a migration —
    the shape of any Django project.

## 1. Libraries with no type information

mypy complains about every import of a package that publishes no types.
The answer is to tell it so, once, per package:

```toml
[[tool.mypy.overrides]]
module = ["django.*"]
ignore_missing_imports = true
```

```console
$ tc type
apps/event/models.py:7: error: Function is missing a return type annotation  [no-untyped-def]
apps/event/migrations/0001_initial.py:6: error: Need type annotation for "dependencies"  [var-annotated]
Found 2 errors in 2 files (checked 8 source files)
```

Seven became two. `module` takes several patterns, so one table covers
the whole project:

```toml
[[tool.mypy.overrides]]
module = ["django.*", "celery.*", "boto3.*", "requests_toolbelt.*"]
ignore_missing_imports = true
```

!!! info "The better answer, where it exists"
    Many libraries ship an official stub package —
    [`django-stubs`](https://pypi.org/project/django-stubs/),
    `types-requests`, `types-redis`. Installing the stubs beats silencing
    the warning: you get real checking at the boundary with the library
    instead of a hole. Silence it to get the gate green, then swap in
    stubs when you can.

## 2. Generated code

A migration is not code someone wrote — demanding annotations from it is
demanding them from a generator. Two ways, depending on what you want:

=== "Check it, report nothing"

    ```toml
    [[tool.mypy.overrides]]
    module = ["*.migrations.*"]
    ignore_errors = true
    ```

    mypy still reads the files — which matters, since other modules
    import models the migrations reference — it just reports no error in
    them.

=== "Don't even look"

    ```toml
    [tool.mypy]
    exclude = ["migrations/"]
    ```

    Faster, and the report starts saying `checked 6 source files` instead
    of `8`. Use it when the directory really is disposable.

!!! warning "`module` matches the *module*, not the path"
    `*.migrations.*` only works when the directories have `__init__.py` —
    which is the case in any Django app. In a directory without one,
    mypy never builds the module name and the pattern misses; use
    `exclude` there, which works on the path.

On the ruff side, the equivalents:

```toml
[tool.ruff]
extend-exclude = ["*/migrations/*"]     # never reads them

[tool.ruff.lint.per-file-ignores]
"*/migrations/*" = ["ANN", "E501"]      # reads them, ignores those rules
```

## 3. Turning a ruff rule off

A rule that makes no sense in your framework goes into `ignore`:

```toml
[tool.ruff.lint]
ignore = ["RUF012"]
```

(`RUF012` asks for `ClassVar` on a mutable class attribute — in a Django
model, guaranteed noise.)

!!! danger "The catch: `ignore` does not turn off the level's `ANN` rules"
    `typing_strictness` adds the `ANN` rules through the **command
    line** (`--extend-select ANN001,ANN201,…`), and in ruff the command
    line wins over the config's `ignore`. So:

    ```toml
    [tool.ruff.lint]
    ignore = ["ANN201"]      # ❌ no effect at the standard/strict level
    ```

    ```console
    $ tc lint
    ANN201 Missing return type annotation for public function `label`
    Found 3 errors.
    ```

    Two ways out that **do** work:

    ```toml
    [tool.ruff.lint.per-file-ignores]
    "apps/event/models.py" = ["ANN201"]   # ✅ per-file-ignores wins
    ```

    or take over the whole rule set — the next section.

## 4. Owning the rule set

If you want to decide everything, put the level on `lenient`: it stops
adding any flag, and what runs is only your `pyproject.toml`.

```toml
[tool.tempest]
typing_strictness = "lenient"

[tool.ruff.lint]
select = ["E", "F", "I", "ANN001"]
```

```console
$ tc lint
All checks passed!
```

The gate is still one command; the rules are now entirely yours.

## 5. The full recipe: a Django project

Paste this into the `pyproject.toml` of a Django project you just
adopted the gate in:

```toml
[tool.tempest]
typing_strictness = "standard"

[tool.ruff]
extend-exclude = ["*/migrations/*"]

[tool.ruff.lint]
ignore = ["RUF012"]

[[tool.mypy.overrides]]
module = ["django.*"]
ignore_missing_imports = true

[[tool.mypy.overrides]]
module = ["*.migrations.*"]
ignore_errors = true
```

Before and after, in the sample project:

```console
$ tc type          # before
Found 7 errors in 4 files (checked 8 source files)

$ tc type          # after
apps/event/models.py:7: error: Function is missing a return type annotation  [no-untyped-def]
Found 1 error in 1 file (checked 8 source files)
```

**One** left — and it is the real finding. Annotate the function:

```python
def label(self) -> str:
    return self.name
```

```console
$ tc lint
All checks passed!
$ tc type
Success: no issues found in 8 source files
```

That is the state you want: a green gate on a project that was never
written with it in mind, and one real piece of debt fewer.

## Who reads what

| Key in `pyproject.toml` | Read by | What it does |
| --- | --- | --- |
| `[tool.ruff]`, `[tool.ruff.lint]` | ruff | rule selection, exclusions, `per-file-ignores` |
| `[tool.mypy]`, `[[tool.mypy.overrides]]` | mypy | strictness, exclusions, per-module rules |
| `[tool.pytest.ini_options]` | pytest | `testpaths`, `addopts`, markers |
| `[tool.tempest] typing_strictness` | tempest-cli | **adds** `ANN` flags to ruff and strictness flags to mypy |

The first three are the tools' ordinary configuration — they hold just
the same if you ever swap `tc check` for calling the tools directly.

## Recap

- The rules belong to `ruff` and `mypy`; the gate only invokes them.
- Untyped library imports: `ignore_missing_imports` per module — or
  install the stubs.
- Generated code: `ignore_errors` / `exclude` in mypy,
  `extend-exclude` / `per-file-ignores` in ruff.
- `ignore` does **not** drop the level's `ANN` rules;
  `per-file-ignores` does, and `typing_strictness = "lenient"` hands the
  whole set back to you.
- A legacy Django project goes green with nine lines of
  `pyproject.toml` — without hiding what was a real finding.
