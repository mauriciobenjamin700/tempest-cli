# Typing strictness

How much typing a project enforces is the project's decision — so it
lives in `pyproject.toml`, versioned, not in a flag someone remembers to
pass.

```toml
[tool.tempest]
typing_strictness = "strict"   # lenient | standard | strict
```

Without the key (or without a `pyproject.toml`), the level is
`standard`.

## What each level adds

The level **adds** flags on top of what you already configured in
`[tool.ruff]` and `[tool.mypy]` — it never relaxes them:

| Level | ruff (extra `ANN` rules) | mypy |
| --- | --- | --- |
| `lenient` | none | none |
| `standard` | `ANN001`, `ANN201`, `ANN202`, `ANN205`, `ANN206` | `--disallow-untyped-defs --disallow-incomplete-defs` |
| `strict` | the above plus `ANN204` | `--strict` |

- `ANN001` — unannotated function argument
- `ANN201` / `ANN202` — public / private function return
- `ANN204` — special-method return (`__init__` and friends)
- `ANN205` / `ANN206` — staticmethod / classmethod return

!!! info "`ANN401` is never enabled, at any level"
    `ANN401` forbids `Any` in an annotation. `Any` is a legitimate
    annotation — sometimes the only honest one. The levels enforce that
    things **are annotated**, never that they avoid `Any`.

    `ANN002` / `ANN003` (`*args` / `**kwargs`) are left out too: on a
    passthrough wrapper they are noise carrying no information.

!!! tip "And the rules themselves?"
    This knob only moves typing. Turning any other rule on, off or down
    — including silencing mypy's complaints about untyped libraries,
    the ones that make the first run look alarming — belongs to
    **[Tuning the rules](rules.md)**.

## Per-run override

```bash
tempest-cli check -s lenient    # before a large refactor
tempest-cli type --strictness strict
```

The flag beats the configuration and applies to that run only. An
invalid value is a usage error (exit 2) listing what is accepted — it
never falls back to the default silently.

## Raising the level gradually

Adopting `strict` on a legacy project at once produces hundreds of
errors and nobody fixes them. The path that works:

1. start at `lenient` and get the gate green;
2. move to `standard` and fix what shows up;
3. run `tempest-cli type -s strict` now and then, without changing the
   config, to size the debt;
4. when the list fits in an afternoon, pin `strict` in
   `pyproject.toml`.

## Recap

- `[tool.tempest] typing_strictness` with three levels; `standard` by
  default.
- A level only adds flags — your config is never relaxed.
- `--strictness` overrides per run; an invalid value exits 2.
- `Any` is never forbidden.
