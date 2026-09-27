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
- `test --fast` / `check --fast` rodam a suíte com pytest-xdist
  (`-n auto`, `-w N` para escolher); teste que só falha em paralelo se
  confere rodando-o sozinho.
- Código de saída é o da ferramenta; 127 significa ferramenta (ou o
  pytest-xdist do `--fast`) ausente.
