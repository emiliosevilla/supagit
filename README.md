# supagit

`supagit` is a fail-closed promotion pipeline for projects that publish code through an ordered sequence of Git branches. These projects may, or may not, have a backend consisting on Supabase environments. 

The bash command, installer, and tests live in [`scripts/`](scripts/).
The project configuration template is [`.supagit.json.example`](.supagit.json.example), and
the agent-specific skill operating instructions are in
[`docs/supagit-agent-command.md`](docs/supagit-agent-command.md).

## Installation

From this repository, install the global command and agent files with:

```bash
scripts/install-supagit-global.sh
```

The installer updates `~/.local/bin/supagit` and the local skill/command copies.
It records this repository as the source and does not alter a project
repository. It also removes any previous generated launcher and skill files so
there is one command name only.

After the first installation, running `supagit` checks the registered source
against the global copy and updates the skill automatically when it is stale.
At startup it also compares the source-root clone to `origin/main` on GitHub
(`emiliosevilla/supagit`); if behind, it fast-forward pulls, reinstalls, and
re-executes. Set `SUPAGIT_SKIP_UPDATE=1` to skip that check (tests / one-shot
re-exec). If the source repository has moved, run this installer again from its
new path.

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

You may run `supagit` from the main repository or from a linked worktree.
When launched from a linked worktree, promotion uses the main checkout; the
launch path is printed at startup.

Always inspect the plan first:

```bash
scripts/supagit --dry-run
```

Then run the confirmed pipeline:

```bash
scripts/supagit
```

### Sweeper (default)

Unless `--no-sweep` is passed, an interactive menu selects for **this run
only** (not persisted):

1. **Pipeline order** — promotion branches (default: configured branches).
2. **Integrate** — local feature branches to merge into the first pipeline
   branch before promotion (default: eligible locals; `none` skips).

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
| `--no-sweep` | Skip menu and feature integration; still relocate to main checkout when needed and ff-only sync the first branch. |
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

- Confirmation and commit-message prompts are green.
- Successful completion is green.
- Warnings, errors, aborts, and negative manual-intervention messages are red.
- `NO_COLOR` and `--no-color` disable color; `--color always` forces it.
- The command never uses forced Git operations and does not infer an ambiguous
  deployment target.
- Agents must measure layout, worktrees, and status; run `--dry-run` first; and
  obtain explicit confirmation before a mutating run. See
  [`docs/supagit-agent-command.md`](docs/supagit-agent-command.md).
