"""Framework-agnostic quality gate for Python projects.

``tempest-cli`` runs ruff, mypy and pytest behind one command, with a
typing-strictness dial read from ``[tool.tempest]`` in the project's
``pyproject.toml`` — and a generator for the prompt that makes an AI fill
a pull-request description from the branch's own diff.

It knows nothing about any web framework. The only runtime dependency is
``typer``; the tools themselves are invoked from the active environment,
so a project pins the ruff and mypy versions it wants.

```bash
tempest-cli check                 # lint + fmt-check + type + test
tempest-cli fix                   # every ruff autofix, then format
tempest-cli type -s strict        # override the configured strictness
tempest-cli pr-prompt | claude -p
```

Everything is importable too, for a project that would rather wire the
gate into its own tooling:

```python
from tempest_cli import load_tempest_config, run_full_check

config = load_tempest_config()
exit_code = run_full_check(".", config=config)
```

And :func:`tempest_cli.main.register_commands` mounts the whole gate onto
an existing :class:`typer.Typer`, so another CLI can expose these
commands under its own name without copying them.
"""

from tempest_cli.config import DEFAULT_TYPING_STRICTNESS as DEFAULT_TYPING_STRICTNESS
from tempest_cli.config import TempestConfig as TempestConfig
from tempest_cli.config import TypingStrictness as TypingStrictness
from tempest_cli.config import find_pyproject as find_pyproject
from tempest_cli.config import load_tempest_config as load_tempest_config
from tempest_cli.lint import resolve_tool as resolve_tool
from tempest_cli.lint import run_full_check as run_full_check
from tempest_cli.lint import run_mypy as run_mypy
from tempest_cli.lint import run_pytest as run_pytest
from tempest_cli.lint import run_ruff_check as run_ruff_check
from tempest_cli.lint import run_ruff_fix as run_ruff_fix
from tempest_cli.lint import run_ruff_format as run_ruff_format
from tempest_cli.pr_prompt import GitError as GitError
from tempest_cli.pr_prompt import PromptLanguage as PromptLanguage
from tempest_cli.pr_prompt import generate_pr_prompt as generate_pr_prompt

__version__: str = "0.1.0"
"""Installed package version."""

__all__: list[str] = [
    "DEFAULT_TYPING_STRICTNESS",
    "GitError",
    "PromptLanguage",
    "TempestConfig",
    "TypingStrictness",
    "__version__",
    "find_pyproject",
    "generate_pr_prompt",
    "load_tempest_config",
    "resolve_tool",
    "run_full_check",
    "run_mypy",
    "run_pytest",
    "run_ruff_check",
    "run_ruff_fix",
    "run_ruff_format",
]
