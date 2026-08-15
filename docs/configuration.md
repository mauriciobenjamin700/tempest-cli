# Rigor de tipagem

Quanto de tipagem o projeto cobra é uma decisão do projeto — então mora
no `pyproject.toml`, versionada, e não numa flag que alguém lembra de
passar.

```toml
[tool.tempest]
typing_strictness = "strict"   # lenient | standard | strict
```

Sem a chave (ou sem `pyproject.toml`), o nível é `standard`.

## O que cada nível acrescenta

O nível **soma** flags ao que você já configurou em `[tool.ruff]` e
`[tool.mypy]` — nunca afrouxa:

| Nível | ruff (regras `ANN` extras) | mypy |
| --- | --- | --- |
| `lenient` | nenhuma | nenhuma |
| `standard` | `ANN001`, `ANN201`, `ANN202`, `ANN205`, `ANN206` | `--disallow-untyped-defs --disallow-incomplete-defs` |
| `strict` | as acima mais `ANN204` | `--strict` |

- `ANN001` — argumento de função sem anotação
- `ANN201` / `ANN202` — retorno de função pública / privada
- `ANN204` — retorno de método especial (`__init__` e afins)
- `ANN205` / `ANN206` — retorno de staticmethod / classmethod

!!! info "`ANN401` nunca é ligado, em nível nenhum"
    `ANN401` proíbe `Any` em anotação. `Any` é uma anotação legítima —
    às vezes é a única honesta. Os níveis cobram que as coisas **estejam
    anotadas**, nunca que evitem `Any`.

    `ANN002` / `ANN003` (`*args` / `**kwargs`) também ficam de fora: em
    wrapper de passagem viram ruído sem informação.

## Override por execução

```bash
tempest-cli check -s lenient    # antes de um refactor grande
tempest-cli type --strictness strict
```

A flag vence a configuração, e vale só para aquela execução. Um valor
inválido é erro de uso (saída 2) listando os aceitos — nunca cai
silenciosamente no default.

## Subindo o nível aos poucos

Adotar `strict` num projeto legado de uma vez gera centenas de erros e
ninguém arruma. O caminho que funciona:

1. comece em `lenient` e deixe o gate verde;
2. suba para `standard` e conserte o que aparecer;
3. rode `tempest-cli type -s strict` de vez em quando, sem mudar a
   config, para ver o tamanho da dívida;
4. quando a lista couber numa tarde, fixe `strict` no `pyproject.toml`.

## Recap

- `[tool.tempest] typing_strictness` com três níveis; default
  `standard`.
- O nível só acrescenta flags — sua config nunca é afrouxada.
- `--strictness` sobrescreve por execução; valor inválido sai com 2.
- `Any` nunca é proibido.
