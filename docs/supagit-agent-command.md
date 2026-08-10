---
name: supagit
description: Publica un proyecto desde la rama de desarrollo hasta producción, detectando las ramas remotas y migrando cada BD antes del código que la utiliza.
---

# `supagit`

The only command name is `supagit`. You may launch it from the main repository
or from a linked worktree; when launched from a linked worktree, promotion runs
from the main checkout while feature work may live in the launch worktree.

## Before running

Measure the repository before any mutating step:

1. Working directory, Git root, current branch, and `git status`.
2. `git worktree list` (linked worktrees and their branches).
3. Read `.supagit.json` in the project root.
4. When feature integration is expected, run `gh auth status` (GitHub CLI must
   be authenticated for the PR merge path).
5. Run `supagit --dry-run` and review the printed plan.
6. Request explicit user confirmation before a non-dry-run run.

If the target project has no `.supagit.json`, `supagit` auto-creates it
(interactive backend prompt, or `--backend none|supabase` under `--yes` /
non-TTY). You may also run `supagit init --backend none` or
`supagit init --backend supabase`. The initializer never overwrites an
existing configuration.

At process start, `supagit` checks the registered GitHub source-root against
`origin/main` and, if behind, pulls ff-only, reinstalls the global skill, and
re-executes (fail-closed if that update cannot complete). The global launcher
also refreshes stale installed files from the registered source. Set
`SUPAGIT_SKIP_UPDATE=1` to skip the GitHub tip check once.

Choose UI language with the startup menu, `--lang en|es`, or `SUPAGIT_LANG`.
With `--yes` / non-TTY, `--lang` or `SUPAGIT_LANG` is required. Confirmations
default to Yes (`[Y/n]` / `[S/n]`).

## Sweeper phase (default)

Unless `--no-sweep` is passed, `supagit` shows an interactive branch menu
(run-scoped; choices are not persisted into `.supagit.json`). The menu and
execution plan are **cyan** (tutor context); user answers are **green**
prompts.

The menu has two labeled blocks:

- **Independent work** — linked worktrees and other local feature branches.
  Checkmarks `[✓]` / `[ ]` (order irrelevant). Enter integrates all checked
  branches; `none` / `ninguno` skips integration. Branches already contained in
  the first pipeline branch appear unchecked with a note and are excluded from
  the Enter default.
- **Main pipeline branches** — promotion order for this run. Numbers `1.`, `2.`,
  … (order matters). Enter keeps the configured default; comma-separated
  numbers or names reorder the pipeline.

Two green prompts follow the menu: integrate first, then pipeline order. After
both, a numbered cyan execution plan is printed, then a green confirmation
(`[Y/n]` / `[S/n]`; Enter = yes).

Selected features are integrated via GitHub pull requests merged into
`pipeline[0]`; the `gh` CLI is required for that path. Dirty feature trees are
committed and pushed first; secrets in staged paths block commits.

After integration (or when integrate is empty), the main checkout is ensured on
the first pipeline branch and that branch is fast-forward synced with its
remote (ff-only; diverged histories fail closed).

## Promotion phase

The pipeline order is: publish local changes on the first branch, run checks,
migrate each configured destination backend when present, merge each adjacent
branch pair, and return to the first branch. With one branch there are no merge
or promotion steps.

Optional cleanup at the end removes merged feature branches and linked worktrees
when the user confirms (`--cleanup` applies without prompting when used with
`--yes`; `--no-cleanup` skips cleanup entirely).

## Non-interactive flags

- `--lang en|es` (or `SUPAGIT_LANG`) sets the UI language; required with `--yes`
  when no TTY language menu is possible.
- `--backend none|supabase` for `init` or auto-init when config is missing.
- `--yes` skips confirmation prompts. With the sweeper enabled (default),
  also pass `--integrate` (or `--integrate none`) and `--pipeline`, or pass
  `--no-sweep`.
- `--no-sweep` skips the menu and feature integration but still relocates to
  the main checkout when needed and fast-forward syncs the first pipeline
  branch before promotion.
- `-m` / `--message` is required with `--yes` when the first branch has changes
  to commit.

## Configuration

The legacy `branches` object can be configured explicitly or left with `null`
values so the command detects `dev`, `pre`, and `prod` among remote branches.
For any other number of stages, use an ordered `branches` list such as
`["main"]` or `["dev", "qa", "production"]`. The command promotes adjacent
entries from left to right and stops if a configured branch is absent or
duplicated. The backend is configured under `backend`: use `provider: none` for
a project without a database, or `provider: supabase` with environment-specific
refs/variables. Supabase detection stops if it cannot identify exactly one ref
for a configured target; it never guesses between projects.

An optional `sweep` block in `.supagit.json` may document PR merge preferences
(`pr_merge_method`, `require_gh`); when absent, behavior is merge via `gh` with
`gh` required.

## Output and safety

**Cyan** is tutor context: explanations before each interactive step, sweeper
menu blocks, the post-menu execution plan, the startup welcome banner, and the
busy spinner. **Green** is where the user types: confirmation prompts, commit
messages, and sweeper answers. After language selection, a short welcome shows
the command name, goal, author, and tips. While a long child command runs, a
cyan same-line spinner shows that supagit is working and that Ctrl+C aborts.
Every interactive `prompt` / `confirm` is preceded by a cyan explanation
(skipped under `--yes` / non-TTY). `NO_COLOR` and `--no-color` disable color;
`--color always` forces it. Warnings, errors, aborts, and other negative
manual-intervention messages are red under the same color policy.

The final success line is green. Final `ERROR` and `ABORTED` lines are red when
the pipeline fails or stops partway through execution.

Error output emitted by a failed child command is also rendered in red, line by
line, before the final error summary.
