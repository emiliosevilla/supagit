# supagit

`supagit` is a fail-closed promotion pipeline for projects that publish code through an ordered sequence of Git branches. These projects may, or may not, have a backend consisting on Supabase environments. 

The bash command, installer, and tests live in [`scripts/`](scripts/).
The project configuration template is [`.supagit.json.example`](.supagit.json.example), and
the agent-specific skill operating instructions are in
[`docs/supagit-agent-command.md`](docs/supagit-agent-command.md).

## Installation

You need a **local clone** of this repository once. After that, run `supagit`
from any of your projects. Forking is only for proposing changes; it is not
required (and not recommended) for installation — install from
`emiliosevilla/supagit` so auto-updates keep working.

### Option A — one-liner (`curl`)

After the repository is public on GitHub:

```bash
curl -fsSL https://raw.githubusercontent.com/emiliosevilla/supagit/main/scripts/bootstrap.sh | sh
```

Spanish UI during install:

```bash
curl -fsSL https://raw.githubusercontent.com/emiliosevilla/supagit/main/scripts/bootstrap.sh | sh -s -- --lang es
```

That script clones (or fast-forward updates) the source into
`~/.local/share/supagit`, then runs the global installer. Optional overrides:
`SUPAGIT_REPO_URL`, `SUPAGIT_SOURCE_DIR`, `SUPAGIT_BRANCH`.

### Option B — clone, then install

```bash
git clone https://github.com/emiliosevilla/supagit.git
cd supagit
./scripts/install-supagit-global.sh --lang es
```

If you already develop inside a clone of this repo, you can install from that
checkout the same way (`./scripts/install-supagit-global.sh`).

On a TTY the installer asks for language (`(1) English` / `(2) Español`).
Skip the menu with `--lang en|es` or `SUPAGIT_LANG`. Non-TTY defaults to English.
Auto-updates from the global launcher pass `--lang` so they never prompt mid-run.

The installer updates `~/.local/bin/supagit` and the local skill/command copies.
It records the source clone path and does not alter a project repository. It
also removes any previous generated launcher and skill files so there is one
command name only.

After the first installation, running `supagit` checks the registered source
against the global copy and updates the skill automatically when it is stale.
At startup it also compares the source-root clone to `origin/main` on GitHub
(`emiliosevilla/supagit`); if behind, it fast-forward pulls, reinstalls, and
re-executes. Set `SUPAGIT_SKIP_UPDATE=1` to skip that check (tests / one-shot
re-exec). If the source repository has moved, run the installer again from its
new path (or re-run the bootstrap one-liner).

## Configuration

Create `.supagit.json` in the project root, starting from
`.supagit.json.example`. The legacy `branches` object supports automatic
detection of `dev`, `pre`, and `prod`. For any other number of stages, use an
ordered list; each name must exist on the remote:

```json
"branches": ["main"]
```

or:

```json
"branches": ["dev", "qa", "staging", "production"]
```

The list is processed from left to right. One branch runs checks and publishes
that branch without merges; multiple branches create one promotion per adjacent
pair. Missing or duplicate branches stop the pipeline.

The backend is independent from the branch pipeline. For Supabase, prefer
environment variables or environment-specific `.env` files over literal
project refs:

```json
"backend": {
  "provider": "supabase",
  "auto_detect": true,
  "environments": {
    "pre": { "project_ref_env": "SUPABASE_PRE_PROJECT_REF" },
    "prod": { "project_ref_env": "SUPABASE_PROD_PROJECT_REF" }
  }
}
```

Each environment must resolve to exactly one Supabase project. Resolution can
use `project_ref`, `project_ref_env`, `url_env`, role-specific environment
variables, or files such as `.env.staging` and `.env.production`. Missing or
ambiguous targets stop the pipeline; project IDs are never guessed.

For a frontend-only project, use:

```json
{"backend": {"provider": "none"}}
```

This skips database migration checkpoints while retaining checks and code
promotion. The previous `supabase.pruebas_project_ref` and
`supabase.prod_project_ref` fields remain supported for compatibility. Providers
other than `supabase` and `none` are not implemented yet.

## Initialize a project

From the target project repository, create its local ignored configuration with:

```bash
supagit init --backend none
```

For a Supabase project, use:

```bash
supagit init --backend supabase
```

If `.supagit.json` is missing when you run the pipeline, `supagit` auto-creates
it (prompts for backend on a TTY; with `--yes` / non-TTY require `--backend`).
The initializer refuses to overwrite an existing `.supagit.json`. It writes
only backend/branch configuration; it does not install the global command or
store Supabase IDs.

Pass ordered branches when the project does not use the legacy three-stage
layout, for example `supagit init --backend none --branches main`.

## Running

Just run `supagit` from the folder you are in. **Do not** switch branches
first and **do not** copy placeholder text such as `<rama-feature>` into the
shell (zsh treats `<…>` as file redirection and fails).

You may run from the main repository or from a linked worktree, and from
**any** branch (feature, pipeline, or a detached HEAD with a reachable
commit) as long as the working tree is clean when a move is required. When
launched from a linked worktree, promotion uses the main checkout; the launch
path is printed at startup.

At startup, `supagit` tells you which branch you are on and that you should
not change it yourself. After the sweeper menu confirms the plan, it explains
(cyan) that it must move the checkout to the first pipeline branch and asks
(green) before doing so. A dirty tree that requires that move stops the run
with an actionable message — it never stashes, force-checks out, or discards
your work. If you are already on the first pipeline branch with local
changes, those are committed and published as usual. When the release
finishes, interactive runs offer to return you to the branch you started on.

Always inspect the plan first:

```bash
supagit --dry-run
```

Then run the confirmed pipeline:

```bash
supagit
```

### Sweeper (default)

Unless `--no-sweep` is passed, an interactive menu selects for **this run
only** (not persisted). The menu is printed in **cyan** (tutor context); your
answers are **green** prompts.

The menu has two labeled blocks:

- **Independent work** — linked worktrees and other local feature branches.
  Shown with checkmarks `[✓]` / `[ ]` (order does not matter). Press Enter to
  integrate all checked branches; type `none` to skip integration. Branches
  already contained in the first pipeline branch are shown unchecked with a
  note and are not included in the Enter default.
- **Main pipeline branches** — promotion order for this run. Shown with numbers
  `1.`, `2.`, … (order matters). Press Enter for the configured default order,
  or enter comma-separated numbers or branch names to reorder.

After both prompts, a numbered **execution plan** is printed in cyan, followed
by a green confirmation (`[Y/n]` / `[S/n]`; Enter = yes).

Selected features are integrated through GitHub pull requests merged into the
first pipeline branch. The `gh` CLI must be installed and authenticated. Dirty
feature worktrees are committed and pushed first.

After integration (or when integrate is empty), the main checkout is placed on
the first pipeline branch and that branch is fast-forward synced with its
remote (ff-only; diverged histories stop the run).

### Promotion

The pipeline publishes local changes on the first branch, runs configured
checks, migrates the backend configured for each destination branch when
present, promotes each adjacent branch pair, and returns to the first branch.

### Flags

| Flag | Effect |
|------|--------|
| `--dry-run` | Print the plan without mutating Git or Supabase. |
| `--lang en\|es` | UI language (skips the language menu). Also `SUPAGIT_LANG`. Required with `--yes` / non-TTY. |
| `--backend` | Backend for `init` or auto-init when `.supagit.json` is missing (`none` / `supabase`). |
| `--no-sweep` | Skip menu and feature integration; still explains and relocates the checkout to the first pipeline branch when needed (fail-closed if dirty) and ff-only syncs that branch. |
| `--integrate` | Comma-separated feature branches, or `none` (non-interactive). |
| `--pipeline` | Comma-separated ordered pipeline branches (non-interactive). |
| `--yes` | Skip confirmations; requires `--integrate` and `--pipeline` unless `--no-sweep`. |
| `--cleanup` | Apply optional post-run cleanup without prompting (use with `--yes`). |
| `--no-cleanup` | Skip optional cleanup of merged features and worktrees. |
| `-m` / `--message` | Commit message for the first branch; required with `--yes` when changes exist. |

Confirmations default to Yes: Enter proceeds (`[Y/n]` / Spanish `[S/n]`).

Optional cleanup at the end removes merged feature branches and linked
worktrees when confirmed interactively, or when `--cleanup` is passed.

### Optional sweep configuration

`.supagit.json` may include an optional `sweep` block (see
[`.supagit.json.example`](.supagit.json.example)). When absent, feature
integration uses GitHub merge commits via `gh` and requires `gh` to be available.

## Output and safety

- **Cyan** — tutor explanations, menu context, execution plans, welcome banner,
  and the busy spinner.
- **Green** — where you type: confirmation prompts, commit messages, and
  sweeper answers.
- Successful completion is green.
- Warnings, errors, aborts, and negative manual-intervention messages are red.
- After language selection, a short welcome shows the command name, goal,
  author, and tips.
- While a long command runs, a cyan same-line spinner shows
  `supagit is working… (Ctrl+C to abort)` (Spanish when `--lang es`).
- Every interactive prompt is preceded by a cyan explanation of what will
  happen if you proceed (skipped under `--yes` / non-TTY).
- `NO_COLOR` and `--no-color` disable color; `--color always` forces it.
- The command never uses forced Git operations and does not infer an ambiguous
  deployment target.
- Agents must measure layout, worktrees, and status; run `--dry-run` first; and
  obtain explicit confirmation before a mutating run. See
  [`docs/supagit-agent-command.md`](docs/supagit-agent-command.md).
