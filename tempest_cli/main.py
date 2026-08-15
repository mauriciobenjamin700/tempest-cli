"""Typer entry point for the ``tempest-cli`` quality gate.

The commands are registered through :func:`register_commands`, which
takes any :class:`typer.Typer` — the executable's own app is built by
calling it on a fresh one. That is what lets another CLI (the
``tempest-fastapi-sdk`` one, for instance) expose the very same gate
under its own name without copying a single command body: one call, and
``lint`` / ``fix`` / ``format`` / ``fmt-check`` / ``type`` / ``test`` /
``check`` / ``pr-prompt`` behave identically in both.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, cast, get_args

import typer

from tempest_cli import lint as lint_module
from tempest_cli import pr_prompt as pr_prompt_module
from tempest_cli.config import TempestConfig, TypingStrictness, load_tempest_config


def _strictness_option() -> typer.models.OptionInfo:
    """Build a fresh ``--strictness`` option.

    A new :class:`typer.models.OptionInfo` per command is required —
    sharing a single instance across commands breaks Typer's option
    parsing.

    Returns:
        typer.models.OptionInfo: The configured option.
    """
    return cast(
        "typer.models.OptionInfo",
        typer.Option(
            "--strictness",
            "-s",
            help=(
                "Typing strictness for this run: lenient | standard | strict. "
                "Overrides [tool.tempest] typing_strictness in pyproject.toml."
            ),
        ),
    )


def _resolve_config(target: str, strictness: str | None) -> TempestConfig:
    """Resolve the typing config, applying a CLI ``--strictness`` override.

    Args:
        target (str): The path being linted; its directory anchors the
            ``pyproject.toml`` lookup.
        strictness (str | None): The ``--strictness`` flag value, or
            ``None`` to use ``[tool.tempest]`` / the default.

    Returns:
        TempestConfig: The resolved config.

    Raises:
        typer.BadParameter: When ``strictness`` is not a valid level.
    """
    if strictness is None:
        return load_tempest_config(Path(target))
    allowed = get_args(TypingStrictness)
    if strictness not in allowed:
        allowed_str = ", ".join(allowed)
        raise typer.BadParameter(
            f"invalid strictness {strictness!r}; expected one of {allowed_str}."
        )
    return TempestConfig(typing_strictness=cast(TypingStrictness, strictness))


def register_commands(app: typer.Typer) -> None:
    """Register the quality gate on an existing Typer application.

    Args:
        app (typer.Typer): The application to extend. Its own name and
            help text are left untouched; only commands are added.

    Example:
        ```python
        import typer

        from tempest_cli.main import register_commands

        cli: typer.Typer = typer.Typer(name="mytool")
        register_commands(cli)
        ```
    """

    @app.command("lint")
    def lint_cmd(
        target: Annotated[
            str,
            typer.Argument(help="Path to lint. Defaults to the current directory."),
        ] = ".",
        strictness: Annotated[str | None, _strictness_option()] = None,
    ) -> None:
        """Run ``ruff check`` on the target."""
        config = _resolve_config(target, strictness)
        raise typer.Exit(lint_module.run_ruff_check(target, config=config))

    @app.command("fix")
    def fix_cmd(
        target: Annotated[
            str,
            typer.Argument(help="Path to fix. Defaults to the current directory."),
        ] = ".",
        unsafe: Annotated[
            bool,
            typer.Option(
                "--unsafe",
                help=(
                    "Also apply ruff's unsafe autofixes (rules with possible "
                    "behavior changes). Off by default — review the diff after "
                    "enabling."
                ),
            ),
        ] = False,
        strictness: Annotated[str | None, _strictness_option()] = None,
    ) -> None:
        """Apply every ruff autofix + format the target in one pass.

        Equivalent to running ``ruff check --fix`` followed by ``ruff
        format``: sorts and dedupes imports, drops unused imports,
        normalizes string quotes, removes trailing whitespace, normalizes
        indentation, line length and blank lines.
        """
        config = _resolve_config(target, strictness)
        raise typer.Exit(lint_module.run_ruff_fix(target, unsafe=unsafe, config=config))

    @app.command("format")
    def format_cmd(
        target: Annotated[
            str,
            typer.Argument(help="Path to format. Defaults to the current directory."),
        ] = ".",
    ) -> None:
        """Run ``ruff format`` on the target (writes files)."""
        raise typer.Exit(lint_module.run_ruff_format(target, check=False))

    @app.command("fmt-check")
    def fmt_check_cmd(
        target: Annotated[
            str,
            typer.Argument(help="Path to inspect. Defaults to the current directory."),
        ] = ".",
    ) -> None:
        """Run ``ruff format --check`` on the target (read-only)."""
        raise typer.Exit(lint_module.run_ruff_format(target, check=True))

    @app.command("type")
    def type_cmd(
        target: Annotated[
            str,
            typer.Argument(help="Package/path to type-check."),
        ] = ".",
        strictness: Annotated[str | None, _strictness_option()] = None,
    ) -> None:
        """Run ``mypy`` against the target."""
        config = _resolve_config(target, strictness)
        raise typer.Exit(lint_module.run_mypy(target, config=config))

    @app.command("test")
    def test_cmd(
        target: Annotated[
            str | None,
            typer.Argument(help="Optional pytest path filter."),
        ] = None,
    ) -> None:
        """Run ``pytest`` (forwarding the optional path argument)."""
        raise typer.Exit(lint_module.run_pytest(target))

    @app.command("check")
    def check_cmd(
        target: Annotated[
            str,
            typer.Argument(help="Path to inspect. Defaults to the current directory."),
        ] = ".",
        strictness: Annotated[str | None, _strictness_option()] = None,
    ) -> None:
        """Run the full quality gate (lint + fmt-check + type + test)."""
        config = _resolve_config(target, strictness)
        raise typer.Exit(lint_module.run_full_check(target, config=config))

    @app.command("pr-prompt")
    def pr_prompt_cmd(
        ctx: typer.Context,
        base: Annotated[
            str,
            typer.Argument(
                help="Base ref the pull request targets. When the local ref is "
                "missing, 'origin/<base>' is tried before failing.",
            ),
        ] = pr_prompt_module.DEFAULT_BASE,
        head: Annotated[
            str | None,
            typer.Option(
                "--head",
                help="Branch to describe. Defaults to the checked-out one "
                "(the short sha when HEAD is detached).",
            ),
        ] = None,
        out: Annotated[
            Path | None,
            typer.Option(
                "--out",
                "-o",
                help="Write the prompt to this file instead of stdout.",
            ),
        ] = None,
        template: Annotated[
            Path | None,
            typer.Option(
                "--template",
                "-t",
                help="Template to fill in. Wins over the repository's own "
                "template and over the bundled default.",
            ),
        ] = None,
        language: Annotated[
            pr_prompt_module.PromptLanguage,
            typer.Option(
                "--lang",
                "-l",
                help="Language of the instructions and of the bundled template. "
                "A repository template is always used as written.",
            ),
        ] = pr_prompt_module.PromptLanguage.PT_BR,
        full: Annotated[
            bool,
            typer.Option(
                "--full",
                help="Excerpt every changed file, with its whole patch. Lifts "
                "both bounds at once; cannot be combined with --max-files / "
                "--max-chars.",
            ),
        ] = False,
        max_files: Annotated[
            int,
            typer.Option(
                "--max-files",
                min=0,
                help="How many files contribute a patch excerpt, most-changed "
                "first. 0 keeps the file list and drops every patch.",
            ),
        ] = pr_prompt_module.DEFAULT_MAX_FILES,
        max_chars: Annotated[
            int,
            typer.Option(
                "--max-chars",
                min=1,
                help="Characters kept per patch (cut on a line boundary).",
            ),
        ] = pr_prompt_module.DEFAULT_MAX_CHARS,
        target: Annotated[
            str,
            typer.Option(
                "--path",
                "-p",
                help="Directory inside the repository to read. Defaults to the "
                "current working directory.",
            ),
        ] = ".",
    ) -> None:
        """Build the prompt that makes an AI fill this branch's PR description.

        The prompt carries three things: the pull-request template (the
        repository's own when it has one, otherwise the bundled PT-BR /
        EN-US default), the rules that stop the model from returning the
        template with its placeholders still in it, and the branch
        context — commit subjects, the changed-file list and a bounded
        excerpt of each file's patch.

        It goes to stdout, so it pipes into whichever assistant you run::

            tempest-cli pr-prompt | claude -p
            tempest-cli pr-prompt develop --lang en --out pr_prompt.txt

        Diffs are read as ``base...head`` — the merge-base diff the forge
        shows on the pull request — so commits that landed on the base
        after the branch started are not attributed to it.

        The commit list and the changed-file list are always complete;
        only the patch excerpts are bounded, and whatever ``--max-files``
        / ``--max-chars`` leave out is stated inside the prompt, so a
        partial diff reads as partial instead of as the whole change.
        ``--full`` lifts both bounds for a branch small enough to send
        whole.

        Raises:
            typer.Exit: ``2`` when ``--full`` is combined with an explicit
                bound, when git fails or when a ref does not resolve;
                ``1`` when the comparison holds no commit and no changed
                file.
        """
        if full:
            conflicting = [
                name
                for option, name in (
                    ("max_files", "--max-files"),
                    ("max_chars", "--max-chars"),
                )
                if getattr(ctx.get_parameter_source(option), "name", "")
                == "COMMANDLINE"
            ]
            if conflicting:
                typer.secho(
                    f"error: --full already lifts every bound; drop "
                    f"{' and '.join(conflicting)}.",
                    fg="red",
                    err=True,
                )
                raise typer.Exit(2)

        try:
            prompt, context, resolved = pr_prompt_module.generate_pr_prompt(
                base=base,
                head=head,
                cwd=Path(target).expanduser(),
                template=template,
                language=language,
                max_files=None if full else max_files,
                max_chars=None if full else max_chars,
            )
        except pr_prompt_module.GitError as exc:
            typer.secho(f"error: {exc}", fg="red", err=True)
            raise typer.Exit(2) from exc

        if not context.commits and not context.files:
            typer.secho(
                f"error: `{context.head}` adds nothing over `{context.base}` — "
                "no commits and no changed files. Check the base ref.",
                fg="red",
                err=True,
            )
            raise typer.Exit(1)

        if out is not None:
            destination = out.expanduser()
            destination.write_text(prompt, encoding="utf-8")
            typer.secho(f"wrote {destination}", fg="green", err=True)
        else:
            typer.echo(prompt, nl=False)

        typer.secho(f"template: {resolved.source}", fg="cyan", err=True)
        omitted = (
            f", {context.omitted_files} file(s) without a patch"
            if context.omitted_files
            else ""
        )
        typer.secho(
            f"{len(context.commits)} commit(s), {len(context.files)} changed "
            f"file(s), {len(context.excerpts)} excerpt(s){omitted}.",
            fg="cyan",
            err=True,
        )


def _print_version(value: bool) -> None:
    """Print the package version and exit.

    Args:
        value (bool): True when ``--version`` is passed.

    Raises:
        typer.Exit: Always when ``value`` is True.
    """
    if value:
        from tempest_cli import __version__

        typer.echo(f"tempest-cli {__version__}")
        raise typer.Exit()


app: typer.Typer = typer.Typer(
    name="tempest-cli",
    help=(
        "Quality gate for any Python project — ruff, mypy and pytest behind "
        "one command, with a typing-strictness dial read from "
        "[tool.tempest] in pyproject.toml."
    ),
    no_args_is_help=True,
    add_completion=False,
)
register_commands(app)


@app.callback()
def _root(
    _version: Annotated[
        bool,
        typer.Option(
            "--version",
            "-v",
            callback=_print_version,
            is_eager=True,
            help="Show the installed version and exit.",
        ),
    ] = False,
) -> None:
    """Run the quality gate."""


def main() -> None:
    """Console-script entry point."""
    app()


if __name__ == "__main__":  # pragma: no cover - manual invocation only
    main()
