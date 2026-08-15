# Instalação

```bash
uv add --dev tempest-cli
```

Ou com pip:

```bash
pip install tempest-cli
```

Requer **Python 3.11+**. A única dependência de runtime é o `typer`.

Ficam instalados **dois executáveis**: `tempest-cli` e o apelido curto
`tc`. São o mesmo programa — tudo nesta documentação vale para os dois.

```bash
tc check        # idêntico a tempest-cli check
```

!!! warning "`tc` também é o `tc(8)` do iproute2"
    Enquanto o ambiente que instalou o pacote estiver no `PATH`, `tc`
    resolve para esta CLI. Para o controlador de tráfego do Linux, chame
    pelo caminho absoluto (`/usr/sbin/tc`) ou use `tempest-cli` e deixe
    o `tc` livre.

## De onde vêm o ruff, o mypy e o pytest

O `tempest-cli` **não** fixa versão de nenhum dos três: ele executa o que
encontrar, nesta ordem:

1. **o ambiente da execução** — o diretório do interpretador que está
   rodando a CLI (onde o extra `[tools]` instala as três), depois
   `$VIRTUAL_ENV`, depois o `.venv` mais próximo subindo a árvore;
2. **o `PATH`** — pulando um *shim* de gerenciador de versão que não
   despacha para lugar nenhum (veja abaixo);
3. **`uv run --with <ferramenta> <ferramenta>`**, quando o `uv` está
   disponível — o ambiente do projeto mais a ferramenta, sem exigir
   ativação nem `uv sync` prévio.

Se nada resolver, o comando sai com **127** e diz qual ferramenta faltou
e como instalá-la, em vez de estourar um traceback.

!!! info "Por que o `PATH` não vem primeiro"
    Em máquina com pyenv/asdf, o diretório `shims` está no `PATH`
    globalmente e tem um stub para toda ferramenta que qualquer versão
    instalada já forneceu. Procurar `ruff` ali acha
    `~/.pyenv/shims/ruff` mesmo quando o projeto não tem ruff nenhum — e
    rodá-lo dá `pyenv: ruff: command not found`. Por isso o ambiente da
    execução ganha do `PATH`, e um shim só é aceito depois de provar que
    despacha (`<ferramenta> --version` saindo `0`).

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
tc --version          # o mesmo programa
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
- Dois executáveis: `tempest-cli` e o apelido `tc`.
- As ferramentas vêm do ambiente da execução, do `PATH` (sem shim morto)
  ou do `uv run --with`.
- Ferramenta ausente = saída 127 com mensagem, não traceback.
