# Comandos

Oito comandos. Todos aceitam um caminho opcional e devolvem o código de
saída da ferramenta por baixo.

| Comando | Roda |
| --- | --- |
| `lint` | `ruff check` |
| `fix` | `ruff check --fix-only`, `ruff format`, encurta comentário/string longos e um `ruff check` final que explica o que sobrou |
| `format` | `ruff format` (escreve) |
| `fmt-check` | `ruff format --check` (só leitura) |
| `type` | `mypy` |
| `test` | `pytest` |
| `check` | os quatro acima, em ordem, parando na primeira falha (uma CLI que monta o gate pode [acrescentar passos](library.md#acrescentar-passos-ao-check) entre o `mypy` e o `pytest`) |
| `pr-prompt` | monta o prompt da descrição do PR — [página própria](pr-prompt.md) |

!!! tip "`tc` é a forma curta"
    O pacote instala `tempest-cli` e `tc` apontando para o mesmo
    programa. Os exemplos usam o nome longo; `tc check`, `tc fix` e
    `tc type -s strict` funcionam igual.

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

O `fix` faz quatro passadas:

1. `ruff check --fix-only` — ordena e deduplica imports, remove imports
   não usados, normaliza aspas.
2. `ruff format` — indentação, comprimento de linha, linhas em branco.
3. Encurta as linhas longas que o formatador não quebra, quando dá para
   fazer isso sem mudar o programa: comentários e strings (veja abaixo).
4. `ruff check` — o relatório do que sobrou, já sobre o arquivo final.

O código de saída é o da última passada: sobrou violação, o `fix` sai
com erro e o CI falha.

!!! warning "`--unsafe` muda comportamento"
    Os autofixes "unsafe" do ruff são os que podem alterar semântica.
    Ficam desligados por padrão. Ligou? Leia o `git diff` antes de
    commitar.

### E501 que o `ruff format` não resolve

Às vezes o `fix` termina assim, mesmo com o `line-length` certo no
`pyproject.toml`:

```python
class AloController:
    def template(self, kind: str) -> str:
        match kind:
            case "waiting":
                user_template = notifications.NOTIFICATION_USER_BODY_ALO_STATUS_CHANGE_WAITING
                return user_template
        return ""
```

```text
E501 Line too long (94 > 79)
  --> controller.py:5:80
```

Não é configuração errada — o `fix` não passa `line-length` nenhum ao
ruff, o valor do projeto já vale. É limite do formatador: ele **não
divide um nome pontuado** (`a.b.C`), e o parêntese que você pôs em volta
(`x = (\n    a.b.C\n)`) some, porque não faz a linha caber. 🤷

#### O que o `fix` encurta sozinho

Dois desses casos têm uma única resposta certa, e o `fix` aplica:

- **comentário** é quebrado no limite; comentário no fim da linha sobe
  para cima do código que ele comenta;
- **string** é partida nos espaços em pedaços concatenados entre
  parênteses — o Python junta tudo de volta no mesmo valor.

```python
# antes
    text = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa bbbbbbbbbbbbbbbb"  # o texto

# depois do fix
    # o texto
    text = (
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa "
        "bbbbbbbbbbbbbbbb"
    )
```

```text
shortened 1 long line(s) ruff format cannot break (comments wrapped, strings split into concatenated parts):
  mod.py:2 [comment+string]
```

!!! check "Só entra o que é provado igual"
    Antes de gravar, o `fix` compara a AST do arquivo antes e depois.
    Comentário não entra na AST e o parser junta string concatenada numa
    constante só, então uma reescrita certa sempre passa. Qualquer outra
    coisa — um `\N{...}` cortado no meio, comentário empurrado para
    dentro de uma continuação com `\` — muda a AST, e a linha fica como
    estava.

Fica de fora, de propósito: comentário de ferramenta (`noqa`,
`type: ignore`, `fmt:`, `pragma`…), que precisa ficar na linha que
governa; f-string e string com três aspas; e palavra mais longa que uma
linha (URL, por exemplo).

#### O que sobra

Nome pontuado, nome longo e expressão não têm reescrita mecânica — e
quebrá-los à mão é desfeito pelo próximo `ruff format`. Para esses, o
`fix` explica cada linha logo abaixo do relatório do ruff:

```text
1 line(s) still too long after ruff format — the line-length setting was applied; the formatter has nowhere to break these:
  controller.py:5 [dotted-name] `notifications.NOTIFICATION_USER_BODY_ALO_STATUS_CHANGE_WAITING`
    ruff format never splits a dotted name, and drops parentheses that do not make the line fit. Shorten the expression: import or alias the attribute, move the choice into a table or constant, or lower the indentation.
1 residual violation(s): 1 with no autofix (edit by hand).
```

O rótulo entre colchetes diz o que está no ponto onde a linha estoura:

| Rótulo | O que é | O que resolve |
| --- | --- | --- |
| `dotted-name` | nome pontuado (`modulo.CONSTANTE`) | alias, tabela/constante, indentação menor |
| `name` | um nome sozinho longo demais | renomear ou indentar menos |
| `string` | string que o `fix` não pôde partir (f-string, três aspas, palavra longa) | partir à mão em pedaços concatenados |
| `comment` | comentário que o `fix` não pôde quebrar (pragma, palavra longa) | quebrar à mão ou levar para a docstring |
| `expression` | qualquer outra coisa | extrair variável ou indentar menos |

A última linha separa o que **não tem autofix** do que o `fix --unsafe`
resolveria — sem ela, `Found 5 errors` não diz se vale rodar de novo.

!!! tip "Leve a escolha para uma tabela"
    No exemplo acima, a indentação vem do `match`. Trocar o `match` por
    um dicionário no nível do módulo tira quatro níveis e a linha cabe
    exatamente em 79, sem alias:

    ```python
    import notifications

    TEMPLATES: dict[str, str] = {
        "waiting": notifications.NOTIFICATION_USER_BODY_ALO_STATUS_CHANGE_WAITING,
    }


    class AloController:
        def template(self, kind: str) -> str:
            return TEMPLATES.get(kind, "")
    ```

!!! note "E o `# noqa: E501`?"
    Funciona, mas esconde o problema até o próximo refactor tirar o
    `noqa` — que foi exatamente como esse caso apareceu. Prefira mudar a
    forma do código.

## Um comando por vez

```bash
tempest-cli lint src/
tempest-cli fmt-check
tempest-cli type meupacote
tempest-cli test tests/unit
```

`test` repassa o caminho ao pytest como filtro; sem argumento, roda a
suíte inteira.

## A suíte em paralelo: `--fast`

Suíte cujos testes já são isolados (banco por teste, nada de estado
global) paga o tempo serial sem comprar nada. `--fast` espalha a suíte
pelos núcleos com o [pytest-xdist](https://pytest-xdist.readthedocs.io/):

```bash
tempest-cli test --fast              # -n auto: um worker por núcleo
tempest-cli test --fast -w 4         # quatro workers
tempest-cli test tests/unit --fast   # o alvo continua sendo repassado
tempest-cli check --fast             # o gate completo, com o passo de teste em paralelo
```

Por baixo, vira `pytest -n <workers> -p no:cacheprovider [alvo]`. O
`-p no:cacheprovider` existe porque vários workers escrevendo
`.pytest_cache` ao mesmo tempo é corrida à toa — e é esse cache que o
`--lf` / `--ff` leem, então esses dois continuam sendo coisa de execução
serial.

`--workers` (`-w`) aceita o que o `pytest -n` aceita: um inteiro, `auto`
(o padrão) ou `logical`. Sem `--fast` ele é erro de uso (saída 2), em vez
de ser ignorado em silêncio.

!!! info "`auto` conta núcleo físico quando o `psutil` está instalado"
    É o pytest-xdist que decide: com `psutil` importável, `auto` é o número
    de núcleos **físicos**; sem ele, o de CPUs lógicas. Numa máquina de 6
    núcleos e 12 threads, com `psutil` no ambiente, `auto` subiu
    `created: 6/6 workers`. Quer as 12 threads? `-w logical` ou `-w 12`.

!!! note "Por que flag, e não `tempest-cli test fast`"
    `test` já recebe um caminho posicional. `test fast` continua
    significando "rode o pytest na pasta `fast/`" — um subcomando com esse
    nome quebraria quem tem essa pasta.

### Sem o pytest-xdist

Antes de rodar qualquer coisa, a CLI pergunta ao **mesmo interpretador
que vai rodar o pytest** se ele importa o `xdist` — não ao interpretador
da própria CLI, que sob `uv tool install` ou pipx mora em outro ambiente.
Faltou, a mensagem diz o que instalar e a saída é **127**, sem traceback:

```console
$ tempest-cli test --fast
error: --fast needs pytest-xdist, which is not installed in the environment pytest runs in (.venv/bin/pytest). Install it with 'uv add --dev pytest-xdist' — or a bundle that carries it, 'uv add --dev "tempest-cli[tools]"' or 'uv add --dev "tempest-fastapi-sdk[tests]"' — and retry, or drop --fast to run the suite serially.
$ echo $?
127
```

No `check --fast` essa checagem acontece **antes** do primeiro passo:
não adianta esperar lint e mypy terminarem para descobrir que o teste
não vai rodar.

### Teste que só falha em paralelo

O paralelismo expõe teste que depende de ordem ou de máquina ociosa:
dois testes escrevendo o mesmo arquivo, a mesma porta, um global de
módulo, um `sleep` fixo esperando algo que, com os núcleos ocupados,
demora mais. Antes de tratar a falha como regressão, rode o teste
**sozinho e em série**:

```bash
tempest-cli test "tests/test_scheduler.py::test_lease_expires"
```

- **Passou sozinho**: o defeito é o isolamento do teste, não a mudança
  em revisão. Conserte o teste (arquivo em `tmp_path`, porta livre,
  espera por condição em vez de `sleep`).
- **Falhou sozinho também**: é regressão de verdade.

## O que cada um devolve

O código de saída é o da ferramenta, sem tradução:

```bash
tempest-cli lint; echo "saiu $?"
```

Só há um código próprio: **127**, quando a ferramenta não está em nenhum
dos lugares onde a CLI procura — ambiente da execução, `PATH`, `uv run
--with` — e aí a mensagem diz qual faltou e como instalá-la. A ordem de
busca está em [Instalação](installation.md#de-onde-vem-o-ruff-o-mypy-e-o-pytest).
O mesmo 127 sai do `--fast` quando o pytest-xdist não está no ambiente do
pytest.

## Recap

- `check` é lint + fmt-check + type + test, nessa ordem, parando na
  primeira falha.
- `fix` é a passada que conserta; `--unsafe` só quando você for revisar.
- Comentário e string longos o `fix` encurta sozinho, com a AST provada
  igual. O E501 que sobra é linha sem reescrita mecânica: o `fix` diz o
  token e a ação — mude a forma do código.
- `test --fast` / `check --fast` rodam a suíte com pytest-xdist
  (`-n auto`, `-w N` para escolher); teste que só falha em paralelo se
  confere rodando-o sozinho.
- Código de saída é o da ferramenta; 127 significa ferramenta (ou o
  pytest-xdist do `--fast`) ausente.
