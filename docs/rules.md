# Ajustando as regras

O `tempest-cli` **não tem regras próprias**. Ele chama o `ruff` e o
`mypy`, e essas duas leem a configuração delas do seu `pyproject.toml` —
`[tool.ruff]` e `[tool.mypy]`. Ligar, desligar e afrouxar regra é
configurar as ferramentas, exatamente como você faria sem o gate.

A única coisa que o `tempest-cli` acrescenta é o
[`typing_strictness`](configuration.md), que **soma** algumas flags. Esta
página mostra como conviver com as duas coisas.

## O caso que assusta

Você instala o gate num projeto Django e roda:

```console
$ tc type
manage.py:4: error: Skipping analyzing "django.core.management": module is installed, but missing library stubs or py.typed marker  [import-untyped]
config/urls.py:1: error: Skipping analyzing "django.contrib": module is installed, but missing library stubs or py.typed marker  [import-untyped]
apps/event/models.py:1: error: Skipping analyzing "django.db": module is installed, but missing library stubs or py.typed marker  [import-untyped]
apps/event/models.py:7: error: Function is missing a return type annotation  [no-untyped-def]
apps/event/migrations/0001_initial.py:6: error: Need type annotation for "dependencies"  [var-annotated]
Found 7 errors in 4 files (checked 8 source files)
```

Parece que o seu código está podre. Não está. Olhe a coluna do código do
erro:

- `import-untyped` — o **Django** não publica anotações de tipo. Não é o
  seu código; é o mypy avisando que não sabe nada sobre a biblioteca.
- `var-annotated` numa **migration** — arquivo gerado pelo Django, que
  ninguém escreveu à mão nem vai anotar.
- `no-untyped-def` no `models.py` — esse é seu, e é legítimo.

Um achado real, seis de ruído. Vamos calar o ruído sem perder o achado.

!!! tip "Todos os exemplos desta página foram rodados"
    Os números de antes e depois vêm de um projeto Django de exemplo com
    `manage.py`, `config/`, um app com `models.py` e uma migration — o
    mesmo formato de qualquer projeto Django.

## 1. Bibliotecas sem anotação

O mypy reclama de toda importação de pacote que não publica tipos. A
resposta é dizer isso a ele, uma vez, por pacote:

```toml
[[tool.mypy.overrides]]
module = ["django.*"]
ignore_missing_imports = true
```

```console
$ tc type
apps/event/models.py:7: error: Function is missing a return type annotation  [no-untyped-def]
apps/event/migrations/0001_initial.py:6: error: Need type annotation for "dependencies"  [var-annotated]
Found 2 errors in 2 files (checked 8 source files)
```

Sete viraram dois. O `module` aceita vários padrões, então uma tabela só
dá conta do projeto inteiro:

```toml
[[tool.mypy.overrides]]
module = ["django.*", "celery.*", "boto3.*", "requests_toolbelt.*"]
ignore_missing_imports = true
```

!!! info "A alternativa melhor, quando existe"
    Muitas bibliotecas têm pacote de stubs oficial —
    [`django-stubs`](https://pypi.org/project/django-stubs/),
    `types-requests`, `types-redis`. Instalar o stub é melhor que calar o
    aviso: você ganha checagem de verdade na fronteira com a biblioteca,
    em vez de um buraco. Comece calando para o gate ficar verde, e troque
    por stubs quando puder.

## 2. Código gerado

Migration não é código que alguém escreveu — cobrar tipagem dela é
cobrar de um gerador. Duas formas, dependendo do que você quer:

=== "Checa, mas não reporta"

    ```toml
    [[tool.mypy.overrides]]
    module = ["*.migrations.*"]
    ignore_errors = true
    ```

    O mypy ainda lê os arquivos (o que importa: outros módulos importam
    modelos que as migrations referenciam), só não reporta erro neles.

=== "Nem olha"

    ```toml
    [tool.mypy]
    exclude = ["migrations/"]
    ```

    Mais rápido, e o relatório passa a dizer `checked 6 source files` em
    vez de `8`. Use quando o diretório for realmente descartável.

!!! warning "O `module` casa com o *módulo*, não com o caminho"
    `*.migrations.*` só funciona se as pastas tiverem `__init__.py` — o
    que é o caso em qualquer app Django. Numa pasta sem `__init__.py`, o
    mypy não monta o nome do módulo e o padrão não casa; aí use o
    `exclude`, que trabalha em cima do caminho.

Do lado do ruff, o equivalente:

```toml
[tool.ruff]
extend-exclude = ["*/migrations/*"]     # nem lê

[tool.ruff.lint.per-file-ignores]
"*/migrations/*" = ["ANN", "E501"]      # lê, ignora só essas regras
```

## 3. Desligando uma regra do ruff

Regra que não faz sentido no seu framework sai pelo `ignore`:

```toml
[tool.ruff.lint]
ignore = ["RUF012"]
```

(`RUF012` pede `ClassVar` em atributo de classe mutável — em model
Django, ruído garantido.)

!!! danger "A pegadinha: `ignore` não desliga as regras `ANN` do nível"
    O `typing_strictness` acrescenta as regras `ANN` pela **linha de
    comando** (`--extend-select ANN001,ANN201,…`), e no ruff a linha de
    comando vence o `ignore` do arquivo. Ou seja:

    ```toml
    [tool.ruff.lint]
    ignore = ["ANN201"]      # ❌ não tem efeito no nível standard/strict
    ```

    ```console
    $ tc lint
    ANN201 Missing return type annotation for public function `label`
    Found 3 errors.
    ```

    Duas saídas que **funcionam**:

    ```toml
    [tool.ruff.lint.per-file-ignores]
    "apps/event/models.py" = ["ANN201"]   # ✅ per-file-ignores vence
    ```

    ou assumir o conjunto inteiro — a próxima seção.

## 4. Assumindo o conjunto de regras

Se você quer decidir tudo, ponha o nível em `lenient`: ele para de somar
qualquer flag, e o que vale passa a ser só o seu `pyproject.toml`.

```toml
[tool.tempest]
typing_strictness = "lenient"

[tool.ruff.lint]
select = ["E", "F", "I", "ANN001"]
```

```console
$ tc lint
All checks passed!
```

O gate continua sendo um comando só; as regras passaram a ser 100% suas.

## 5. Receita completa: projeto Django

Cole isso no `pyproject.toml` de um projeto Django recém-adotado:

```toml
[tool.tempest]
typing_strictness = "standard"

[tool.ruff]
extend-exclude = ["*/migrations/*"]

[tool.ruff.lint]
ignore = ["RUF012"]

[[tool.mypy.overrides]]
module = ["django.*"]
ignore_missing_imports = true

[[tool.mypy.overrides]]
module = ["*.migrations.*"]
ignore_errors = true
```

O antes e o depois, no projeto de exemplo:

```console
$ tc type          # antes
Found 7 errors in 4 files (checked 8 source files)

$ tc type          # depois
apps/event/models.py:7: error: Function is missing a return type annotation  [no-untyped-def]
Found 1 error in 1 file (checked 8 source files)
```

Sobrou **um** — e é o achado de verdade. Anote a função:

```python
def label(self) -> str:
    return self.name
```

```console
$ tc lint
All checks passed!
$ tc type
Success: no issues found in 8 source files
```

Esse é o estado que você quer: o gate verde num projeto que não foi
escrito pensando nele, com uma dívida real a menos.

## Quem lê o quê

| Chave no `pyproject.toml` | Quem lê | O que faz |
| --- | --- | --- |
| `[tool.ruff]`, `[tool.ruff.lint]` | ruff | seleção de regras, exclusões, `per-file-ignores` |
| `[tool.mypy]`, `[[tool.mypy.overrides]]` | mypy | rigor, exclusões, regras por módulo |
| `[tool.pytest.ini_options]` | pytest | `testpaths`, `addopts`, marcadores |
| `[tool.tempest] typing_strictness` | tempest-cli | **soma** flags `ANN` ao ruff e de rigor ao mypy |

As três primeiras são a configuração normal das ferramentas — valem
igual se um dia você trocar o `tc check` por chamadas soltas.

## Recap

- As regras são do `ruff` e do `mypy`; o gate só as invoca.
- Import de biblioteca sem tipos: `ignore_missing_imports` por módulo —
  ou instale os stubs.
- Código gerado: `ignore_errors` / `exclude` no mypy, `extend-exclude` /
  `per-file-ignores` no ruff.
- `ignore` **não** derruba as regras `ANN` do nível; `per-file-ignores`
  derruba, e `typing_strictness = "lenient"` devolve o controle inteiro.
- Um projeto Django legado fica verde com nove linhas de `pyproject.toml`
  — sem esconder o que era achado de verdade.
