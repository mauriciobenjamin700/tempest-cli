# Changelog

O histórico completo vive no
[`CHANGELOG.md`](https://github.com/mauriciobenjamin700/tempest-cli/blob/main/CHANGELOG.md)
do repositório.

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
