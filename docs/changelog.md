# Changelog

O histórico completo vive no
[`CHANGELOG.md`](https://github.com/mauriciobenjamin700/tempest-cli/blob/main/CHANGELOG.md)
do repositório.

## [0.7.0] — 2026-10-24

### Adicionado

- **`check --rule <CÓDIGO>` e `check --strict` / `--no-strict`, para os
  passos da CLI hospedeira.** O `check` entrega as duas, tipadas num
  `StepOptions`, ao passo que declara o novo
  `CheckStep.run_with_options`; sem nenhum passo assim, a flag sai com
  código `2`. [Detalhes](library.md#opcoes-para-o-passo-rule-e-strict).

## [0.6.0] — 2026-10-20

### Alterado

- **O `test` e o `check` rodam a suíte em paralelo por padrão.** O
  `-n auto` do pytest-xdist, que pedia `--fast`, agora é o que um
  `test` puro faz; `--serial` desliga (para `--lf` / `--ff` ou depurador).
  Medido numa suíte FastAPI de 1136 testes em 12 CPUs: 262 s em série,
  37,6 s em paralelo, mesmo resultado.
  [Detalhes](commands.md#a-suite-em-paralelo-o-padrao).
- **Sem o pytest-xdist, o padrão cai para série em vez de falhar**, com um
  aviso de como instalar; só o `--fast` explícito continua exigindo o
  plugin (código de saída 127).
- `--workers` com `--serial` é erro de uso (código de saída 2).

## [0.5.1] — 2026-10-15

### Corrigido

- **O `fix` explica o E501 que o formatador não resolve.** Linha ainda
  longa depois do `ruff format` (nome pontuado, string, comentário) sai
  com o token, o tipo e a ação que resolve, e o resumo separa o que não
  tem autofix do que o `--unsafe` resolveria. O código de saída não muda.
  [Detalhes](commands.md#e501-que-o-ruff-format-nao-resolve).
- **O `fix` encurta comentário e string longos que o formatador não
  quebra.** Comentário é quebrado no limite e string é partida em pedaços
  concatenados; cada edição só fica se a AST do arquivo for idêntica
  antes e depois. Pragma, f-string, três aspas e palavra longa ficam de
  fora e são explicados. Ligado por padrão.
- **O `fix` relata sobre o arquivo formatado.** As passadas agora são
  `ruff check --fix-only`, `ruff format` e `ruff check`; antes, o
  relatório e o código de saída vinham da passada anterior ao formatador.

## [0.5.0] — 2026-10-13

### Adicionado

- **`extra_steps`: regras do framework dentro do `check`.** O novo
  `CheckStep(name, run)` é um passo que o `check` roda depois do `mypy` e
  antes do `pytest`; `run` recebe o alvo e devolve um código de saída.
  `run_full_check(..., extra_steps=)` e
  `register_commands(app, *, extra_steps=)` aceitam a lista — vazia por
  padrão, então nada muda para quem não passa. O primeiro código diferente
  de `0` para o gate, com ou sem `--fast`.
  [Detalhes](library.md#acrescentar-passos-ao-check).

## [0.4.0] — 2026-09-27

### Adicionado

- **`test --fast` e `check --fast`: a suíte em paralelo.** Roda
  `pytest -n <workers> -p no:cacheprovider [alvo]` com o pytest-xdist;
  `--workers` / `-w` aceita o que o `pytest -n` aceita (inteiro, `auto` —
  o padrão — ou `logical`) e é erro de uso sem `--fast`. O alvo é
  repassado e o código de saída do pytest volta sem tradução. É flag, e
  não subcomando, porque `test fast` continua significando a pasta
  `fast/`. [Detalhes](commands.md#a-suite-em-paralelo-o-padrao).
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
