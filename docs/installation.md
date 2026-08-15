# Instalação

```bash
uv add --dev tempest-cli
```

Ou com pip:

```bash
pip install tempest-cli
```

Requer **Python 3.11+**. A única dependência de runtime é o `typer`.

## De onde vêm o ruff, o mypy e o pytest

O `tempest-cli` **não** fixa versão de nenhum dos três: ele executa o que
encontrar, nesta ordem:

1. o executável no `PATH` (venv ativado, instalação global);
2. `uv run <ferramenta>`, quando o `uv` está disponível — o que faz
   funcionar num projeto cuja venv nunca foi ativada.

Se nenhum dos dois resolver, o comando sai com **127** e diz qual
ferramenta faltou, em vez de estourar um traceback.

!!! tip "Por que não fixar as versões"
    Uma versão de ruff fixada aqui viraria o teto de todo projeto que
    instalasse este pacote — e atualizar o linter é decisão de quem
    escreve o código, não de quem empacota o gate.

Se você prefere instalar as três junto:

```bash
uv add --dev "tempest-cli[tools]"
```

## Verificando

```bash
tempest-cli --version
tempest-cli check --help
```

## Em CI

Cada comando devolve o código de saída da ferramenta por baixo, então o
job lê exatamente como leria o `ruff` direto:

```yaml
- name: Quality gate
  run: uv run tempest-cli check
```

## Recap

- `uv add --dev tempest-cli`, Python 3.11+, só o `typer` de dependência.
- As ferramentas vêm do ambiente do projeto (ou via `uv run`).
- Ferramenta ausente = saída 127 com mensagem, não traceback.
