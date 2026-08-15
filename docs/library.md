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
- Código de saída é o da ferramenta, igual na CLI e na chamada direta.
