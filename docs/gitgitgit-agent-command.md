---
name: gitgitgit
description: Publica un proyecto desde la rama de desarrollo hasta producción, detectando las ramas remotas y migrando cada BD antes del código que la utiliza.
---

# `gitgitgit`

Use the main repository, not a linked worktree. The only command name is
`gitgitgit`.

Before running it, the agent must measure the working directory, Git root,
branch, status, and worktrees; read `.gitgitgit.json`; run
`gitgitgit --dry-run`; and request explicit confirmation.

If the target project has no `.gitgitgit.json`, initialize it from the target
repository with `gitgitgit init --backend none` or
`gitgitgit init --backend supabase`. The initializer never overwrites an
existing configuration.

The global launcher checks the registered source before starting the skill. If
the installed files are stale, it updates the global skill automatically; if
the source cannot be found, it stops with an error instead of running a known
outdated copy silently.

The legacy `branches` object can be configured explicitly or left with `null`
values so the command detects `dev`, `pre`, and `prod` among remote branches.
For any other number of stages, use an ordered `branches` list such as
`["main"]` or `["dev", "qa", "production"]`. The command promotes adjacent
entries from left to right and stops if a configured branch is absent or
duplicated. The backend is configured under `backend`: use `provider: none` for
a project without a database, or `provider: supabase` with environment-specific
refs/variables. Supabase detection stops if it cannot identify exactly one ref
for a configured target; it never guesses between projects.

The pipeline order is: publish local changes on the first branch, run checks,
migrate each configured destination backend when present, merge each adjacent
branch pair, and return to the first branch. With one branch there are no merge
or promotion steps.

Confirmation prompts and commit-message prompts are green when a TTY is
available. `NO_COLOR` and `--no-color` disable color; `--color always` forces
it. Warnings, errors, aborts, and other negative manual-intervention messages
are red under the same color policy.

The final success line is green. Final `ERROR` and `ABORTED` lines are red when
the pipeline fails or stops partway through execution.

Error output emitted by a failed child command is also rendered in red, line by
line, before the final error summary.
