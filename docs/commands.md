# Comandos

Oito comandos. Todos aceitam um caminho opcional e devolvem o código de
saída da ferramenta por baixo.

| Comando | Roda |
| --- | --- |
| `lint` | `ruff check` |
| `fix` | `ruff check --fix` e depois `ruff format` |
| `format` | `ruff format` (escreve) |
| `fmt-check` | `ruff format --check` (só leitura) |
| `type` | `mypy` |
| `test` | `pytest` |
| `check` | os quatro acima, em ordem, parando na primeira falha |
| `pr-prompt` | monta o prompt da descrição do PR — [página própria](pr-prompt.md) |

## O gate completo

```bash
tempest-cli check              # o projeto todo
tempest-cli check src/         # só um caminho
tempest-cli check -s strict    # com rigor de tipagem elevado nesta execução
```

A ordem é deliberada: **lint → formatação → tipos → testes**. O que falha
mais rápido e é mais barato de corrigir vem primeiro, e a execução para
na primeira falha — não adianta rodar a suíte inteira se o import está
desordenado.

## Corrigindo o que dá para corrigir

```bash
tempest-cli fix                # autofixes seguros + formatação
tempest-cli fix --unsafe       # inclui os autofixes de risco do ruff
```

O `fix` faz duas passadas: `ruff check --fix` (ordena e deduplica
imports, remove imports não usados, normaliza aspas) e depois `ruff
format` (indentação, comprimento de linha, linhas em branco).

!!! warning "`--unsafe` muda comportamento"
    Os autofixes "unsafe" do ruff são os que podem alterar semântica.
    Ficam desligados por padrão. Ligou? Leia o `git diff` antes de
    commitar.

## Um comando por vez

```bash
tempest-cli lint src/
tempest-cli fmt-check
tempest-cli type meupacote
tempest-cli test tests/unit
```

`test` repassa o caminho ao pytest como filtro; sem argumento, roda a
suíte inteira.

## O que cada um devolve

O código de saída é o da ferramenta, sem tradução:

```bash
tempest-cli lint; echo "saiu $?"
```

Só há um código próprio: **127**, quando a ferramenta não está no `PATH`
e o `uv` também não — aí a mensagem diz qual faltou.

## Recap

- `check` é lint + fmt-check + type + test, nessa ordem, parando na
  primeira falha.
- `fix` é a passada que conserta; `--unsafe` só quando você for revisar.
- Código de saída é o da ferramenta; 127 significa ferramenta ausente.
