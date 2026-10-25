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
class StepOptions:
    """Options of ``check`` that only the extra steps read.

    ``check --rule <CODE>`` and ``check --strict`` mean nothing to ruff,
    mypy or pytest; they are for a step that reports rule codes with a
    severity. ``tempest-cli`` parses them and hands them over as typed
    values, so a step never parses the command line itself.

    Attributes:
        rules (tuple[str, ...]): Rule codes to report, as typed (``--rule``
            repeated). Empty means every rule.
        strict (bool | None): ``--strict`` / ``--no-strict``. ``None`` when
            neither was typed, so the step falls back to its own default.
    """

    rules: tuple[str, ...] = ()
    strict: bool | None = None

    @property
    def given(self) -> bool:
        """Tell whether any option was typed.

        Returns:
            bool: ``True`` when ``--rule`` or ``--strict`` / ``--no-strict``
            was passed.
        """
        return bool(self.rules) or self.strict is not None


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
        run_with_options (Callable[[str, StepOptions], int] | None): Called
            instead of ``run`` when set, with the target and the
            :class:`StepOptions` ``check`` parsed. ``None`` (the default)
            marks a step with no options; ``check --rule`` refuses to run
            when no step declares this.

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
    run_with_options: Callable[[str, StepOptions], int] | None = None


__all__: list[str] = ["CheckStep", "StepOptions"]
