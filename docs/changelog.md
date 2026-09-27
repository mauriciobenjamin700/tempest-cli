# Changelog

O histórico completo vive no
[`CHANGELOG.md`](https://github.com/mauriciobenjamin700/tempest-cli/blob/main/CHANGELOG.md)
do repositório.

## [Unreleased]

### Adicionado

- **`test --fast` e `check --fast`: a suíte em paralelo.** Roda
  `pytest -n <workers> -p no:cacheprovider [alvo]` com o pytest-xdist;
  `--workers` / `-w` aceita o que o `pytest -n` aceita (inteiro, `auto` —
  o padrão — ou `logical`) e é erro de uso sem `--fast`. O alvo é
  repassado e o código de saída do pytest volta sem tradução. É flag, e
  não subcomando, porque `test fast` continua significando a pasta
  `fast/`. [Detalhes](commands.md#a-suite-em-paralelo-fast).
- **pytest-xdist ausente vira frase, não `unrecognized arguments: -n`.**
  O `--fast` pergunta ao interpretador que vai rodar o pytest se ele
  importa o `xdist`; faltando, a mensagem nomeia o pacote e os extras
  (`tempest-cli[tools]`, `tempest-fastapi-sdk[tests]`) e a saída é 127,
  sem traceback. No `check --fast` a checagem vem antes do primeiro passo.
- **`run_pytest` / `run_full_check` ganham `fast=` e `workers=`**
  keyword-only, com default serial.

### Mudado

- **O `[tools]` agora leva `pytest-xdist>=3.8.0`.** Sem teto no
  `requires-dist` (`execnet>=2.1`, `pytest>=7.0.0`).

## [0.3.0] — 2026-08-15

### Mudado

- **O `ruff` agora vem junto com o pacote.** Saiu do extra `[tools]` e
  virou dependência: `uv add --dev tempest-cli` já basta para `lint`,
  `fix`, `format` e `fmt-check` rodarem. Custo zero — o ruff é binário
  estático, sem dependência Python, então nenhum limite dele entra na
  resolução de quem instala. `mypy` e `pytest` continuam de fora de
  propósito; `[tools]` agora instala exatamente esses dois.
- **O ambiente do projeto passa a ser procurado antes do da CLI.** Com o
  ruff embutido, o ambiente da CLI sempre tem um — procurar ali primeiro
  sobrescreveria em silêncio a versão que o projeto fixou quando o
  `tempest-cli` mora fora dele (`uv tool install`, pipx). A ordem agora é
  `$VIRTUAL_ENV` → `.venv` mais próximo → ambiente da CLI → `PATH` →
  `uv run --with`.

## [0.2.0] — 2026-08-15

### Adicionado

- **`tc`**, apelido curto instalado ao lado de `tempest-cli` — mesmo
  programa. Enquanto o ambiente instalador estiver no `PATH`, ele
  sombreia o `tc(8)` do iproute2 (chame `/usr/sbin/tc` para o de rede).

### Corrigido

- **O gate não roda mais um shim morto do pyenv/asdf.** `tempest-cli
  fix` num projeto sem ruff respondia `pyenv: ruff: command not found` e
  saía 127. A busca agora tenta primeiro os ambientes da execução
  (diretório do interpretador da CLI, `$VIRTUAL_ENV`, `.venv` mais
  próximo) e só aceita um shim depois que `<ferramenta> --version` prova
  que ele despacha — o mesmo vale para o próprio `uv`.
- **O fallback do `uv` parou de vazar para o `PATH`.** Era `uv run
  <ferramenta>`, que cai no `PATH` quando o ambiente do projeto não tem
  a ferramenta — voltando ao shim recém-rejeitado. Agora é `uv run
  --with <ferramenta> <ferramenta>`.
- **A mensagem do 127 diz o que instalar** (`uv add --dev ruff`, ou
  `"tempest-cli[tools]"` para as três).

## [0.1.0] — 2026-08-15

Primeira versão. Extraída do
[`tempest-fastapi-sdk`](https://github.com/mauriciobenjamin700/tempest-fastapi-sdk),
onde o mesmo gate era o `tempest check` — alcançável só instalando um SDK
de FastAPI.

### Adicionado

- O gate: `lint`, `fix`, `format`, `fmt-check`, `type`, `test` e
  `check`.
- Rigor de tipagem por `[tool.tempest] typing_strictness`, com override
  `--strictness` por execução.
- `pr-prompt` — o prompt que faz uma IA escrever a descrição do PR.
- Superfície de biblioteca (`run_full_check`, `load_tempest_config`,
  `generate_pr_prompt`, …) e `register_commands(app)` para montar o gate
  em outra CLI.

### Notas

- Única dependência de runtime: `typer`. As ferramentas vêm do ambiente
  do projeto.
- Medido contra o SDK de origem: chegar nesses comandos lá carregava
  38,7 MB de dependências e ~0,5 s de import por invocação. Um teste
  deste pacote garante que importá-lo não puxa framework web nenhum.
