# Descrições de PR

Escrever a descrição do pull request é o passo que todo mundo pula
quando a branch finalmente fica verde — e o resultado é um PR que diz
"ajustes" sobre 40 arquivos alterados.

Qualquer assistente escreve uma boa descrição. O que falta a ele são as
duas coisas que só existem no repositório: **o template** que o time
combinou e **o diff** que a branch produziu.

```bash
tempest-cli pr-prompt | claude -p
```

## O que entra no prompt

1. **O template de PR** — o do próprio repositório quando existe
   (`.github/pull_request_template.md` e variantes de GitHub/GitLab),
   senão o padrão embutido em PT-BR ou EN-US.
2. **As regras** que impedem o modelo de devolver o template com os
   placeholders intactos.
3. **O contexto da branch** — assuntos dos commits, lista de arquivos
   alterados e um trecho limitado do patch de cada um.

## Uso

```bash
tempest-cli pr-prompt                          # compara com main
tempest-cli pr-prompt develop                  # outra base
tempest-cli pr-prompt --head feat/x            # descreve outra branch
tempest-cli pr-prompt --lang en                # instruções e template em inglês
tempest-cli pr-prompt -o pr.txt                # grava em arquivo
tempest-cli pr-prompt -t .github/PR.md         # template específico
```

O prompt vai para o **stdout** e os avisos para o **stderr**, então o
pipe carrega só o que interessa:

```bash
tempest-cli pr-prompt | claude -p > corpo.md
```

## `base...head`, não `base..head`

O diff é lido como `base...head` — o diff a partir do *merge-base*, que é
o que o GitHub mostra na aba do PR. Commits que entraram na base **depois**
que a branch começou não são atribuídos a ela.

## Limites, e por que eles são declarados

A lista de commits e a de arquivos alterados são **sempre completas**. Só
os trechos de patch são limitados:

```bash
tempest-cli pr-prompt --max-files 10 --max-chars 4000
tempest-cli pr-prompt --max-files 0     # só a lista, sem patch nenhum
tempest-cli pr-prompt --full            # tudo, sem limite
```

O que ficou de fora é dito **dentro do prompt**, para o modelo saber que
está lendo um diff parcial. É a diferença entre "resuma isto" e "resuma
isto sabendo que faltam 30 arquivos".

!!! warning "`--full` não combina com limite explícito"
    `--full` já levanta os dois limites. Passar `--full --max-files 5`
    sai com 2 dizendo qual flag remover, em vez de escolher uma em
    silêncio.

## Arquivos binários

Um `.png` alterado entra na lista de arquivos, nunca como trecho de
patch — um blob binário só gastaria contexto.

## Recap

- O prompt junta template + regras + diff da branch e vai para o stdout.
- `base...head` é o mesmo diff que a forge mostra.
- Commits e arquivos sempre completos; patches limitados, e o corte é
  declarado no prompt.
