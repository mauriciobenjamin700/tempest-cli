# tempest-cli

Um comando para o gate de qualidade de qualquer projeto Python — `ruff`,
`mypy` e `pytest` —, com o rigor de tipagem morando no `pyproject.toml`
em vez de espalhado por quatro alvos de Makefile.

Agnóstico de framework de propósito: Django, Flask, Litestar, FastAPI,
uma biblioteca, um script. As dependências de runtime são duas: o
`typer` e o `ruff` — que já vem junto, para o gate rodar assim que
instala.

```bash
uv add --dev tempest-cli
tempest-cli check
tc check          # o mesmo, pelo apelido curto
```

```console
$ tempest-cli check
$ ruff check --extend-select ANN001,ANN201,ANN202,ANN205,ANN206 .
All checks passed!
$ ruff format --check .
10 files already formatted
$ mypy --disallow-untyped-defs --disallow-incomplete-defs .
Success: no issues found in 10 source files
$ pytest
59 passed in 0.98s
```

## Por que isso existe

Os quatro comandos são sempre os mesmos, e cada projeto os reescreve um
pouco diferente — um Makefile aqui, um `tox.ini` ali, um job de CI que
desliza do que roda na máquina. `tempest-cli check` é o **mesmo** gate
nos dois lugares, e `--strictness` transforma "quanto de tipagem a gente
cobra" num valor versionado, não numa flag que alguém lembrou de passar.

!!! info "De onde veio"
    Este pacote foi extraído do
    [`tempest-fastapi-sdk`](https://github.com/mauriciobenjamin700/tempest-fastapi-sdk),
    onde o mesmo gate era o `tempest check`. Para tê-lo era preciso
    instalar FastAPI, SQLAlchemy, Alembic e Pydantic — **38,7 MB** de
    dependências e cerca de **0,5 s de import** por invocação, para
    quatro comandos que não tocam em nada disso.

    O `tempest check` continua funcionando: o SDK depende deste pacote e
    registra os mesmos comandos. Há uma implementação só.

## O que tem aqui

<div class="grid cards" markdown>

- **[Instalação »](installation.md)** — instalar, e de onde vêm o ruff,
  o mypy e o pytest.
- **[Comandos »](commands.md)** — os oito, o que cada um roda e o que
  devolve.
- **[Rigor de tipagem »](configuration.md)** — os três níveis, o que
  cada um acrescenta e por que `ANN401` nunca entra.
- **[Ajustando as regras »](rules.md)** — ligar, desligar e afrouxar
  regra pelo `pyproject.toml`; a receita que deixa um Django legado
  verde.
- **[Descrições de PR »](pr-prompt.md)** — o prompt que faz uma IA
  escrever a descrição do PR a partir do diff da branch.
- **[Usar como biblioteca »](library.md)** — chamar os runners do seu
  código e montar o gate na sua própria CLI.
- **[Referência »](reference.md)** — assinaturas geradas das docstrings.

</div>

## Recap

- Um comando (`check`) roda lint, formatação, tipos e testes, nessa
  ordem, parando na primeira falha.
- O nível de rigor é configuração do projeto, com override por execução.
- Nenhum framework web é instalado junto — o pacote tem um teste que
  garante isso.
