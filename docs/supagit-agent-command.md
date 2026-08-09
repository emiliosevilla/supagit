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

If the target project has no `.supagit.json`, initialize it from the target
repository with `supagit init --backend none` or
`supagit init --backend supabase`. The initializer never overwrites an
existing configuration.

The global launcher checks the registered source before starting the skill. If
the installed files are stale, it updates the global skill automatically; if
the source cannot be found, it stops with an error instead of running a known
outdated copy silently.

## Sweeper phase (default)

Unless `--no-sweep` is passed, `supagit` shows an interactive branch menu
(run-scoped; choices are not persisted into `.supagit.json`):

1. **Pipeline order** — ordered promotion branches for this run (default: config
   branches, e.g. dev → pre → prod).
2. **Integrate** — local feature branches to merge into the first pipeline
   branch before promotion (default: non-contained locals; `none` skips).

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

Confirmation prompts and commit-message prompts are green when a TTY is
available. `NO_COLOR` and `--no-color` disable color; `--color always` forces
it. Warnings, errors, aborts, and other negative manual-intervention messages
are red under the same color policy.

The final success line is green. Final `ERROR` and `ABORTED` lines are red when
the pipeline fails or stops partway through execution.

Error output emitted by a failed child command is also rendered in red, line by
line, before the final error summary.
