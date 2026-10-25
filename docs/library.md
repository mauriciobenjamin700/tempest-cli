# Usar como biblioteca

Tudo que a CLI faz está importável. Duas situações valem a pena.

## Chamar os runners do seu código

```python
from tempest_cli import load_tempest_config, run_full_check

config = load_tempest_config()
exit_code = run_full_check(".", config=config)
```

Cada etapa também é chamável isolada, com o mesmo contrato de código de
saída:

```python
from tempest_cli import (
    TempestConfig,
    run_mypy,
    run_pytest,
    run_ruff_check,
    run_ruff_fix,
    run_ruff_format,
)

strict = TempestConfig(typing_strictness="strict")

run_ruff_check("src", config=strict)      # ruff check + regras ANN do nível
run_ruff_fix("src", unsafe=False, config=strict)
run_ruff_format("src", check=True)        # --check: não escreve
run_mypy("src", config=strict)
run_pytest("tests/unit")
run_pytest("tests/unit", fast=True, workers="4")   # pytest-xdist: -n 4; sem ele, 127
run_pytest("tests", fast=True, require_xdist=False)  # sem pytest-xdist: série, com aviso
```

`load_tempest_config(start)` procura o `pyproject.toml` mais próximo
subindo a partir de `start` (o cwd por padrão) e devolve o
`TempestConfig` resolvido. `find_pyproject` faz só a busca, quando você
quer o caminho.

## Montar o gate na sua própria CLI

Uma ferramenta que já tem CLI própria pode expor estes comandos sob o
nome dela — sem copiar corpo de comando nenhum:

```python
import typer

from tempest_cli.main import register_commands

cli: typer.Typer = typer.Typer(name="minhaferramenta")


@cli.command("deploy")
def deploy() -> None:
    """Um comando que a ferramenta já tinha."""


register_commands(cli)
```

Agora `minhaferramenta check`, `minhaferramenta lint` e os demais
existem, com o mesmo comportamento e a mesma leitura de
`[tool.tempest]`.

!!! info "É exatamente o que o `tempest-fastapi-sdk` faz"
    O `tempest check` do SDK é este `register_commands` chamado no app
    dele. Por isso os dois nunca divergem: há uma implementação só.

## Acrescentar passos ao `check`

O `tempest-cli` não sabe nada de framework, e é de propósito. Mas o
framework sabe: "todo service herda `BaseService`" é regra de quem monta
o projeto, não de quem roda o ruff. O `CheckStep` é a costura — você
escreve a regra, o `check` roda.

Um `CheckStep` tem dois campos: `name`, o rótulo que o `check` ecoa como
`$ <name>` no stderr, e `run`, uma função que recebe o alvo do `check`
(o caminho da linha de comando, `.` por padrão) e devolve um código de
saída — `0` é passou.

```python
from pathlib import Path

import typer

from tempest_cli import CheckStep
from tempest_cli.main import register_commands


def no_print(target: str) -> int:
    """Fail when a module under ``target`` calls ``print``."""
    offenders: list[str] = [
        f"{path}:{number}: use logging instead of print()"
        for path in sorted(Path(target).rglob("*.py"))
        for number, line in enumerate(path.read_text().splitlines(), start=1)
        if line.lstrip().startswith("print(")
    ]
    for offender in offenders:
        typer.echo(offender, err=True)
    return 1 if offenders else 0


cli: typer.Typer = typer.Typer(name="minhaferramenta")


@cli.command("deploy")
def deploy() -> None:
    """Um comando que a ferramenta já tinha."""


register_commands(cli, extra_steps=[CheckStep(name="no-print", run=no_print)])

if __name__ == "__main__":
    cli()
```

Com um módulo `pkg/a.py` que chama `print("x")`:

```console
$ python minhaferramenta.py check pkg
$ ruff check --extend-select ANN001,ANN201,ANN202,ANN205,ANN206 pkg
All checks passed!
$ ruff format --check pkg
1 file already formatted
$ mypy --disallow-untyped-defs --disallow-incomplete-defs pkg
Success: no issues found in 1 source file
$ no-print
pkg/a.py:2: use logging instead of print()
$ echo $?
1
```

A ordem é `ruff check` → `ruff format --check` → `mypy` → os passos
extras, na ordem da lista → `pytest`. Passo extra é checagem estática:
fica antes da suíte para falhar em um segundo, não depois dela. O
contrato é o dos passos embutidos — o primeiro código diferente de `0`
para o gate e vira o código de saída do `check`, em paralelo ou com `--serial`.

!!! tip "A mensagem é sua"
    O `check` só ecoa o nome. O que o passo imprime é o que o usuário lê,
    então diga arquivo, linha e a correção — como o `no-print` acima.

Sem a CLI, o mesmo vale para `run_full_check`:

```python
from tempest_cli import CheckStep, run_full_check


def always_passes(target: str) -> int:
    """A step that accepts any target."""
    return 0


exit_code: int = run_full_check(
    ".", extra_steps=[CheckStep(name="always-passes", run=always_passes)]
)
```

`extra_steps` é vazio por padrão: sem ele, o gate é exatamente o de
antes.

### Opções para o passo: `--rule` e `--strict`

Um passo que reporta códigos de regra com severidade (erro que derruba,
aviso que não) quer duas opções que o ruff, o mypy e o pytest não
conhecem: filtrar uma regra e fazer aviso derrubar. O `check` aceita as
duas — `--rule <CÓDIGO>` (repetível) e `--strict` / `--no-strict` — e as
entrega já tipadas num `StepOptions` ao passo que declara
`run_with_options`. O passo nunca lê a linha de comando.

```python
from pathlib import Path

import typer

from tempest_cli import CheckStep, StepOptions
from tempest_cli.main import register_commands

RULES: dict[str, str] = {"BL001": "time.sleep(", "BL002": "os.getenv("}
"""Rule code to the call it reports; BL002 is only a warning."""

WARNINGS: frozenset[str] = frozenset({"BL002"})
"""Codes that fail the step only under --strict."""


def no_blocking_calls(target: str, options: StepOptions) -> int:
    """Report the calls in RULES, filtered by --rule, failing per --strict."""
    selected = set(options.rules) or set(RULES)
    failed = False
    for path in sorted(Path(target).rglob("*.py")):
        for number, line in enumerate(path.read_text().splitlines(), start=1):
            for code in sorted(selected):
                if RULES[code] in line:
                    warning = code in WARNINGS
                    tag = " (warning)" if warning else ""
                    typer.echo(f"{path}:{number}: {code}{tag}", err=True)
                    failed = failed or not warning or bool(options.strict)
    return 1 if failed else 0


def no_blocking_calls_plain(target: str) -> int:
    """The same step, called without options."""
    return no_blocking_calls(target, StepOptions())


cli: typer.Typer = typer.Typer(name="minhaferramenta")


@cli.command("deploy")
def deploy() -> None:
    """Um comando que a ferramenta já tinha."""


register_commands(
    cli,
    extra_steps=[
        CheckStep(
            name="no-blocking-calls",
            run=no_blocking_calls_plain,
            run_with_options=no_blocking_calls,
        )
    ],
)

if __name__ == "__main__":
    cli()
```

Com um `pkg/a.py` que chama `os.getenv(...)` na linha 6 (só o trecho do
passo; saída real):

```console
$ python minhaferramenta.py check pkg
$ no-blocking-calls
pkg/a.py:6: BL002 (warning)
$ pytest -n auto -p no:cacheprovider
...
$ echo $?
0
$ python minhaferramenta.py check pkg --strict
$ no-blocking-calls
pkg/a.py:6: BL002 (warning)
$ echo $?
1
$ python minhaferramenta.py check pkg --rule BL001 --strict
$ no-blocking-calls
$ pytest -n auto -p no:cacheprovider
...
$ echo $?
0
```

- `rules` é uma tupla vazia e `strict` é `None` quando nada foi digitado;
  `StepOptions.given` diz se alguma das duas veio.
- Passo sem `run_with_options` continua recebendo só o alvo, pelo `run`.
- **Opção que ninguém lê é recusada.** Se nenhum passo do `check` declara
  `run_with_options`, `--rule` / `--strict` saem com código `2` antes de
  rodar qualquer passo — um gate que passa ignorando a flag seria pior que
  um erro.

## Gerar o prompt de PR sem a CLI

```python
from pathlib import Path

from tempest_cli import PromptLanguage, generate_pr_prompt

prompt, context, template = generate_pr_prompt(
    base="main",
    head=None,
    cwd=Path("."),
    template=None,
    language=PromptLanguage.PT_BR,
    max_files=20,
    max_chars=8000,
)
print(len(context.commits), "commits;", template.source)
```

`generate_pr_prompt` levanta `GitError` quando o git falha ou uma ref não
resolve.

## Recap

- Runners, config e o gerador de prompt são todos importáveis.
- `register_commands(app)` monta os oito comandos em qualquer `Typer`.
- `extra_steps=[CheckStep(...)]` põe regras suas no `check`, depois do
  `mypy` e antes do `pytest`.
- Código de saída é o da ferramenta, igual na CLI e na chamada direta.
