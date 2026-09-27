# Instalação

```bash
uv add --dev tempest-cli
```

Ou com pip:

```bash
pip install tempest-cli
```

Requer **Python 3.11+**. Vem com o `ruff` junto — seis dos oito
comandos são ruff, então o gate roda assim que o pacote instala. A outra
dependência de runtime é o `typer`.

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

O **`ruff` já vem junto**: instalou o pacote, `lint`, `fix`, `format` e
`fmt-check` funcionam — nada mais a instalar.

```bash
uv add --dev tempest-cli
tempest-cli fix            # roda agora mesmo
```

O `mypy` e o `pytest` ficam com você. Um bump de mypy muda quais erros o
seu código passa a reportar, e o pytest precisa casar com os seus plugins
e a sua suíte — versão dessas duas é decisão do projeto. Adicione você
mesmo, ou pegue o pacote pronto:

```bash
uv add --dev "tempest-cli[tools]"   # mypy + pytest + pytest-xdist
```

O `pytest-xdist` é o que o [`test --fast`](commands.md#a-suite-em-paralelo-fast)
usa para rodar a suíte em paralelo. O `requires-dist` dele
(`execnet>=2.1`, `pytest>=7.0.0`) não tem teto nenhum, então ele não
aperta a resolução de ninguém.

!!! question "Por que o ruff é dependência e as outras duas não"
    Seis dos oito comandos são ruff — um `tempest-cli` sem ruff é um
    gate que não roda. E o custo é zero: o ruff é um binário estático,
    sem dependência Python nenhuma, então nenhum limite dele entra na
    resolução do seu projeto. Já mypy e pytest atravessam o seu código e
    a sua suíte; fixá-los aqui seria decidir por você.

### A ordem de busca

O que o seu projeto fixa **ganha** do ruff que veio junto. A CLI executa
o que encontrar primeiro, nesta ordem:

1. **o ambiente do projeto** — `$VIRTUAL_ENV`, depois o `.venv` mais
   próximo subindo a árvore;
2. **o ambiente da própria CLI** — onde mora o ruff que veio junto;
3. **o `PATH`** — pulando um *shim* de gerenciador de versão que não
   despacha para lugar nenhum (veja abaixo);
4. **`uv run --with <ferramenta> <ferramenta>`**, quando o `uv` está
   disponível — o ambiente do projeto mais a ferramenta, sem exigir
   ativação nem `uv sync` prévio.

Se nada resolver, o comando sai com **127** e diz qual ferramenta faltou
e como instalá-la, em vez de estourar um traceback.

!!! info "Por que o `PATH` não vem primeiro"
    Em máquina com pyenv/asdf, o diretório `shims` está no `PATH`
    globalmente e tem um stub para toda ferramenta que qualquer versão
    instalada já forneceu. Procurar `ruff` ali acha
    `~/.pyenv/shims/ruff` mesmo quando o projeto não tem ruff nenhum — e
    rodá-lo dá `pyenv: ruff: command not found`. Por isso os ambientes da
    execução ganham do `PATH`, e um shim só é aceito depois de provar que
    despacha (`<ferramenta> --version` saindo `0`).

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

- `uv add --dev tempest-cli`, Python 3.11+, com o `ruff` já junto.
- `mypy` e `pytest` são seus — ou pegue `"tempest-cli[tools]"`.
- Dois executáveis: `tempest-cli` e o apelido `tc`.
- O que o projeto fixa ganha do ruff embutido; depois vêm o `PATH` (sem
  shim morto) e o `uv run --with`.
- Ferramenta ausente = saída 127 com mensagem, não traceback.
