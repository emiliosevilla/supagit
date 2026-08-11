---
name: supagit
description: Publica un proyecto desde la rama de desarrollo hasta producción, detectando las ramas remotas y migrando cada BD antes del código que la utiliza.
---

# `supagit`

The only command name is `supagit`. You may launch it from the main repository
or from a linked worktree; when launched from a linked worktree, promotion runs
from the main checkout while feature work may live in the launch worktree.

**Never tell the user to `git switch` / `git checkout` before running
`supagit`.** Do not invent shell placeholders such as `<rama-feature>` or
`<branch>` — zsh treats `<…>` as redirection and the user sees a scary
failure that has nothing to do with the project. Launch `supagit` from the
current working directory as-is. The CLI announces the current branch, moves
to `pipeline[0]` after plan confirmation when needed, and (interactively)
offers to return to the starting branch at the end.

## Before running

Measure the repository before any mutating step:

1. Working directory, Git root, current branch, and `git status`.
2. `git worktree list` (linked worktrees and their branches).
3. Read `.supagit.json` in the project root.
4. When feature integration is expected, run `gh auth status` (GitHub CLI must
   be authenticated for the PR merge path).
5. Run `supagit --dry-run` **from the current branch** and review the printed
   plan (no prior branch switch).
6. Request explicit user confirmation before a non-dry-run run.

If the target project has no `.supagit.json`, `supagit` auto-creates it
(interactive backend prompt, or `--backend none|supabase` under `--yes` /
non-TTY). You may also run `supagit init --backend none` or
`supagit init --backend supabase`. The initializer never overwrites an
existing configuration.

At process start, `supagit` checks the registered GitHub source-root against
`origin/main`. If **behind only**, it pulls ff-only, reinstalls the global
skill, and re-executes. If the source clone has **diverged**, the run fails
closed with recovery commands (no forced pull). Fail-closed if a behind-only
update cannot complete. The global launcher also refreshes stale installed
files from the registered source. Set `SUPAGIT_SKIP_UPDATE=1` to skip the
GitHub tip check once.

Choose UI language with the startup menu, `--lang en|es`, or `SUPAGIT_LANG`.
With `--yes` / non-TTY, `--lang` or `SUPAGIT_LANG` is required. Confirmations
default to Yes (`[Y/n]` / `[S/n]`).

## Sweeper phase (default)

Unless `--no-sweep` is passed, `supagit` shows an interactive branch menu
(run-scoped; choices are not persisted into `.supagit.json`). The menu and
execution plan are **cyan** (tutor context). After the welcome banner and cyan
blocks that are not immediately followed by a green decision prompt, a green
**Continue?** / **¿Continuar?** confirmation appears (Enter = yes; `--yes`
skips). Cyan paired with a green answer field (`tutor_prompt` /
`tutor_confirm`) uses that field as the only gate. Under `--dry-run`, routine
Continues are skipped; only the execution-plan gate remains. User answers are
**green** prompts.

The menu has two labeled blocks:

- **Independent work** — linked worktrees and other local feature branches.
  Numbers `1.`, `2.`, … with `[✓]` defaults. Enter integrates `[✓]` branches
  that still need a PR; `0` / `none` skips; otherwise type numbers or names.
  Already-contained branches stay `[✓]` with a note but are skipped on Enter.
- **Main pipeline branches** — promotion order for this run. Separate numbers
  `1.`, `2.`, … (order matters). Enter keeps the configured default;
  comma-separated numbers or names reorder the pipeline.

Two green prompts follow the menu: integrate first, then pipeline order. After
both, a cyan **Situation preflight** lists sync findings and proposed cures
(publish-then-ff, feature ff, etc.). Blocked findings (diverged branch, dirty
feature behind upstream) abort with exact `git`/`gh` commands. Then a numbered
cyan execution plan is printed (cures included), then a green confirmation
(`[Y/n]` / `[S/n]`; Enter = yes).

Selected features are integrated via GitHub pull requests merged into
`pipeline[0]`; the `gh` CLI is required for that path. Dirty feature trees are
committed and pushed first; secrets in staged paths block commits. Clean
features that are behind their upstream are fast-forwarded in the correct
worktree (or by updating the ref without checking the feature out onto
`pipeline[0]`) before `gh pr create`. Empty `base..head` ranges fail before
create.

After plan Confirm, phases run in this order: ensure checkout on
`pipeline[0]` → **publish** local changes on first (clean behind defers to ff)
→ integrate features → **ff_sync** first (refused while dirty; never
`reset --hard` on a dirty tree) → checks / migrate / promote / cleanup.

## Promotion phase

After the sweeper phases above, the pipeline runs checks, migrates each
configured destination backend when present, merges each adjacent branch pair,
and returns to the first branch. With one branch there are no merge or
promotion steps.

Before each promotion into a destination branch, `supagit` queries GitHub branch
rules (`gh api …/rules/branches/{branch}`, with classic protection as fallback).
If a pull-request rule applies, promotion uses a PR (no `--admin` bypass).
Otherwise it uses local merge + push. Non-GitHub remotes always use the direct
path.

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
- `--no-sweep` skips the menu and feature integration but still runs Situation
  preflight for `pipeline[0]`, relocates to the main checkout when needed,
  publishes when appropriate, and fast-forward syncs the first pipeline branch
  before promotion.
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
menu blocks, the post-menu execution plan, and the startup welcome banner.
**Green** is where the user types: confirmation prompts, commit messages, and
sweeper answers — and also the busy spinner. After language selection, a short
welcome shows the command name, goal, author, and tips. While a long child
command runs (including auto-update pull/reinstall), a green same-line spinner
shows that supagit is working and that Ctrl+C aborts.
Every interactive `prompt` / `confirm` is preceded by a cyan explanation
(skipped under `--yes` / non-TTY). `NO_COLOR` and `--no-color` disable color;
`--color always` forces it. Warnings, errors, aborts, and other negative
manual-intervention messages are red under the same color policy.

The final success line is green. Final `ERROR` and `ABORTED` lines are red when
the pipeline fails or stops partway through execution.

Error output emitted by a failed child command is also rendered in red, line by
line, before the final error summary.

Supabase recovery hardening remains deferred:
`docs/superpowers/backlog/2026-08-11-supabase-hardening.md`.
