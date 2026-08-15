# PR descriptions

Writing the pull-request description is the step everyone skips when the
branch is finally green — and the result is a PR that says "fix stuff"
over 40 changed files.

Any assistant writes a good description. What it lacks are the two
things that only exist in the repository: **the template** the team
agreed on and **the diff** the branch produced.

```bash
tempest-cli pr-prompt | claude -p
```

## What goes into the prompt

1. **The PR template** — the repository's own when it has one
   (`.github/pull_request_template.md` and the GitHub/GitLab variants),
   otherwise the bundled PT-BR or EN-US default.
2. **The rules** that stop the model from handing back the template with
   its placeholders intact.
3. **The branch context** — commit subjects, the changed-file list and a
   bounded excerpt of each file's patch.

## Usage

```bash
tempest-cli pr-prompt                          # compares against main
tempest-cli pr-prompt develop                  # another base
tempest-cli pr-prompt --head feat/x            # describe another branch
tempest-cli pr-prompt --lang en                # English rules and template
tempest-cli pr-prompt -o pr.txt                # write to a file
tempest-cli pr-prompt -t .github/PR.md         # a specific template
```

The prompt goes to **stdout** and the notices to **stderr**, so the pipe
carries only what matters:

```bash
tempest-cli pr-prompt | claude -p > body.md
```

## `base...head`, not `base..head`

The diff is read as `base...head` — the diff from the *merge base*,
which is what GitHub shows on the PR tab. Commits that landed on the
base **after** the branch started are not attributed to it.

## Bounds, and why they are stated

The commit list and the changed-file list are **always complete**. Only
the patch excerpts are bounded:

```bash
tempest-cli pr-prompt --max-files 10 --max-chars 4000
tempest-cli pr-prompt --max-files 0     # the list only, no patches
tempest-cli pr-prompt --full            # everything, unbounded
```

Whatever was left out is stated **inside the prompt**, so the model
knows it is reading a partial diff. That is the difference between
"summarize this" and "summarize this knowing 30 files are missing".

!!! warning "`--full` does not combine with an explicit bound"
    `--full` already lifts both. Passing `--full --max-files 5` exits
    with 2 naming the flag to drop, instead of silently picking one.

## Binary files

A changed `.png` appears in the file list, never as a patch excerpt — a
binary blob would only burn context.

## Recap

- The prompt joins template + rules + branch diff and goes to stdout.
- `base...head` is the same diff the forge shows.
- Commits and files always complete; patches bounded, and the cut is
  stated in the prompt.
