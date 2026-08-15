# Changelog

O histórico completo vive no
[`CHANGELOG.md`](https://github.com/mauriciobenjamin700/tempest-cli/blob/main/CHANGELOG.md)
do repositório.

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
