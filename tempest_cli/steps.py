"""Extra steps a caller adds to ``check``.

``tempest-cli`` knows nothing about any framework, so the rules a
framework wants enforced — "every service inherits ``BaseService``",
for instance — cannot live here. :class:`CheckStep` is the seam: a
caller builds one per rule and hands them to
:func:`tempest_cli.lint.run_full_check` or
:func:`tempest_cli.main.register_commands`, and ``check`` runs them
between ``mypy`` and ``pytest``, with the same stop-at-first-failure
contract as the built-in steps.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class CheckStep:
    """A step ``check`` runs after ``mypy`` and before ``pytest``.

    The step owns its own output: whatever ``run`` prints is what the
    user reads, so a failing step should name the file, the line and the
    fix. ``check`` echoes ``$ <name>`` to stderr before calling it, the
    way it echoes the command line of every built-in step.

    Attributes:
        name (str): Label echoed as ``$ <name>`` before the step runs.
        run (Callable[[str], int]): Called with the ``check`` target
            (the path given on the command line, ``.`` by default);
            returns an exit code, ``0`` meaning the step passed. A
            non-zero code stops the gate and becomes its exit code.

    Example:
        ```python
        from tempest_cli import CheckStep, run_full_check


        def no_todo(target: str) -> int:
            return 0


        exit_code: int = run_full_check(
            ".", extra_steps=[CheckStep(name="no-todo", run=no_todo)]
        )
        ```
    """

    name: str
    run: Callable[[str], int]


__all__: list[str] = ["CheckStep"]
