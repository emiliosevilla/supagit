# supagit

`supagit` is a fail-closed promotion pipeline for projects that publish code
through an ordered sequence of Git branches. A Supabase backend is optional.

The CLI, installer, and tests live in [`scripts/`](scripts/). Project config
template: [`.supagit.json.example`](.supagit.json.example).

| Doc | Purpose |
|-----|---------|
| [`docs/supagit-agent-command.md`](docs/supagit-agent-command.md) | Agent skill / how to run `supagit` safely |
| [`tasks/task.md`](tasks/task.md) | Open and recently finished work |
| [`docs/superpowers/backlog/2026-08-11-supabase-hardening.md`](docs/superpowers/backlog/2026-08-11-supabase-hardening.md) | Deferred Supabase recovery backlog |

## Installation

Preferred: the one-liner. You may run it from **any directory** — including
outside a Git repository. It only installs the global `supagit` command (clone
under `~/.local/share/supagit` + `~/.local/bin`). Forking is only for proposing
changes — install from `emiliosevilla/supagit` so auto-updates keep working.

### Option A — one-liner (`curl`) — recommended

```bash
curl -fsSL https://raw.githubusercontent.com/emiliosevilla/supagit/main/scripts/bootstrap.sh | sh
```

Spanish UI during install:

```bash
curl -fsSL https://raw.githubusercontent.com/emiliosevilla/supagit/main/scripts/bootstrap.sh | sh -s -- --lang es
```

Optional overrides: `SUPAGIT_REPO_URL`, `SUPAGIT_SOURCE_DIR`, `SUPAGIT_BRANCH`.

After install, ensure `~/.local/bin` is on your `PATH`, then open a terminal
**inside the project you want to publish** (a Git repo with a remote) and run
`supagit`. If that project has no `.supagit.json`, `supagit` helps you create
one. Merging independent work via pull requests requires the GitHub CLI (`gh`)
to be installed and authenticated.

### Option B — clone, then install

```bash
git clone https://github.com/emiliosevilla/supagit.git
cd supagit
./scripts/install-supagit-global.sh --lang es
```

If you already develop inside a clone of this repo, install from that checkout
the same way (`./scripts/install-supagit-global.sh`).

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
(`emiliosevilla/supagit`). If **behind only**, it fast-forward pulls, reinstalls,
and re-executes. If the source clone has **diverged** from `origin/main`, the
run stops with recovery commands (it does not force a pull). Set
`SUPAGIT_SKIP_UPDATE=1` to skip that check (tests / one-shot re-exec). If the
source repository has moved, run the installer again from its new path (or
re-run the bootstrap one-liner).

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

The backend is independent from the branch pipeline and is **optional**.

Installing `supagit` (the global CLI) does **not** connect to Supabase, does
**not** upload your credentials, and does **not** grant the tool author access
to your projects. Database steps only run when **your** project’s
`.supagit.json` sets `"backend": { "provider": "supabase" }` and you already
have the Supabase CLI logged in on **your** machine. Project refs come from
**your** environment (or local `.env*` files); prefer naming env vars instead
of putting refs in the committed JSON:

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

If the project has no database migrations in this pipeline (frontend-only or
you will migrate elsewhere), use:

```json
{"backend": {"provider": "none"}}
```

This skips database checkpoints while retaining checks and code promotion. The
previous `supabase.pruebas_project_ref` and `supabase.prod_project_ref` fields
remain supported for compatibility. Providers other than `supabase` and `none`
are not implemented yet.

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
commit). When a move to the first pipeline branch is required, uncommitted
changes on a named feature branch are committed there first; a dirty detached
HEAD still fails closed. When launched from a linked worktree, promotion uses
the main checkout; the launch path is printed at startup.

At startup, `supagit` tells you which branch you are on and that you should
not change it yourself. After the sweeper menu and Situation preflight, the
cyan execution plan is confirmed (green). Then, if the checkout is on another
branch with uncommitted changes, those changes are committed on that branch
first (message prompt, or `-m` with `--yes`). After that it moves the checkout
to the first pipeline branch when needed (cyan explain + green confirm). A
dirty detached HEAD, or a commit blocked by secrets, still stops the run with
an actionable message — it never stashes, force-checks out, or discards your
work. Local changes already on the first pipeline branch are published in the
publish phase. When the release finishes, interactive runs offer to return you
to the branch you started on.

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
only** (not persisted). The menu and execution plan are printed in **cyan**
(tutor context). After the welcome banner and after cyan blocks that are **not**
immediately followed by a green decision prompt, `supagit` asks a green
**Continue?** / **¿Continuar?** (`[Y/n]` / `[S/n]`; Enter = yes). When cyan is
paired with a green answer field (`tutor_prompt` / `tutor_confirm`), that field
is the only gate — no extra Continue?. Under `--dry-run`, routine Continues are
skipped so the preview can reach the plan without extra gates; only the
numbered **execution plan** still asks for confirmation. User answers to
questions (commit message, branch picks, etc.) are also **green** prompts.

The menu has two labeled blocks:

- **Independent work** — linked worktrees and other local feature branches.
  Numbered `1.`, `2.`, … with checkmarks `[✓]`. Press Enter to integrate every
  `[✓]` branch that is **not** already contained in the first pipeline branch;
  type numbers (e.g. `1,3`), names, or `0` / `none` to skip. Branches already
  contained stay `[✓]` with a note (“already included…”) so you see them, but
  Enter does not open a new pull request for them.
- **Main pipeline branches** — promotion order for this run. Shown with their
  own numbers `1.`, `2.`, … (order matters; these numbers apply only to the
  pipeline prompt). Press Enter for the configured default order, or enter
  comma-separated numbers or branch names to reorder.

After both prompts, `supagit` measures a **Situation** report (cyan preflight:
sync findings and proposed cures such as publish-then-ff or feature
fast-forward). Blocked cases (diverged histories, dirty feature behind upstream,
empty PR) stop with actionable commands. Then a numbered **execution plan** is
printed in cyan (including those cures), followed by a green confirmation
(`[Y/n]` / `[S/n]`; Enter = yes).

Selected features are integrated through GitHub pull requests merged into the
first pipeline branch. The `gh` CLI must be installed and authenticated. Dirty
feature worktrees are committed and pushed first. Clean feature branches that
are behind their upstream are fast-forwarded in the correct worktree (or via
ref update without checking them out onto `pipeline[0]`) before opening a PR.
Empty `base..head` ranges are refused before `gh pr create`.

Phase order after plan Confirm:

1. If the current branch is not the first pipeline branch and has uncommitted
   changes, **commit** them on that branch (then the tree is clean enough to move).
   If that commit leaves the feature ahead of `pipeline[0]`, the run **adds it to
   integrate** even if the menu had skipped it as already contained.
2. Ensure checkout on the first pipeline branch.
3. **Publish** local changes on that branch (commit/push when needed). A clean
   tree that is only behind defers sync to the ff step.
4. **Integrate** selected features (with feature ff when behind-only).
5. **Fast-forward** the first pipeline branch to its remote (ff-only; refused
   while the worktree is dirty; never `reset --hard` on a dirty tree).
6. Checks, optional migrations, promote adjacent pairs, optional cleanup.

### Promotion

The pipeline runs checks, migrates the backend configured for each destination
branch when present, promotes each adjacent branch pair, and returns to the
first pipeline branch. (Local publish on the first branch already ran before
feature integrate / ff, as above.)

For each promotion into a destination branch, `supagit` asks GitHub (via `gh`)
whether that branch is protected by an active **ruleset** or classic branch
protection that **requires a pull request**:

- **Protected (PR required)** — opens or reuses a PR `source → target`, merges
  it with `gh`, and never uses admin bypass. If reviews/code owners block the
  merge, the run stops with instructions to approve and re-run.
- **Unprotected / direct push allowed** — local `git merge` + `git push` as
  before.
- **Non-GitHub remotes** — always the direct merge+push path.

Public vs private visibility is reported in the cyan tutor text; it does not
by itself change the mode (only branch rules do).

### Flags

| Flag | Effect |
|------|--------|
| `--dry-run` | Preview the plan without mutating Git or Supabase. Skips routine Continue? gates; still confirms at the execution plan. |
| `--lang en\|es` | UI language (skips the language menu). Also `SUPAGIT_LANG`. Required with `--yes` / non-TTY. |
| `--backend` | Backend for `init` or auto-init when `.supagit.json` is missing (`none` / `supabase`). |
| `--no-sweep` | Skip menu and feature integration; still runs Situation preflight for the first pipeline branch, commits dirty work on the current feature when a move is needed, explains and relocates the checkout, publishes when appropriate, and ff-only syncs that branch. |
| `--integrate` | Comma-separated feature branches, or `none` (non-interactive). |
| `--pipeline` | Comma-separated ordered pipeline branches (non-interactive). |
| `--yes` | Skip confirmations; requires `--integrate` and `--pipeline` unless `--no-sweep`. |
| `--cleanup` | Apply optional post-run cleanup without prompting (use with `--yes`). |
| `--no-cleanup` | Skip optional cleanup of merged features and worktrees. |
| `-m` / `--message` | Commit message for the first branch; required with `--yes` when changes exist. |

Confirmations default to Yes: Enter proceeds (`[Y/n]` / Spanish `[S/n]`).

Optional cleanup at the end removes merged feature branches and linked
worktrees when confirmed interactively, or when `--cleanup` is passed.
Local branches are deleted only after verifying they are contained in the
first pipeline branch; if plain `-d` refuses because a stale upstream
(`origin/work`) is behind, cleanup force-deletes (`-D`) after that check.

### Optional sweep configuration

`.supagit.json` may include an optional `sweep` block (see
[`.supagit.json.example`](.supagit.json.example)). When absent, feature
integration uses GitHub merge commits via `gh` and requires `gh` to be available.

## Output and safety

- **Cyan** — tutor explanations, menu context, Situation preflight, execution
  plans, and welcome banner.
- **Green** — where you type: confirmation prompts, commit messages, sweeper
  answers, and the busy spinner.
- Successful completion is green.
- Warnings, errors, aborts, and negative manual-intervention messages are red.
- After language selection, a short welcome shows the command name, goal,
  author, and tips.
- While a long command runs (including auto-update pull/reinstall), a green
  same-line spinner shows `supagit is working… (Ctrl+C to abort)` (Spanish when
  `--lang es`).
- Every interactive prompt is preceded by a cyan explanation of what will
  happen if you proceed (skipped under `--yes` / non-TTY).
- `NO_COLOR` and `--no-color` disable color; `--color always` forces it.
- The command never uses forced Git operations and does not infer an ambiguous
  deployment target. It will not stash, force-push, auto-rebase, or
  `reset --hard` while the worktree is dirty; diverged histories and empty PRs
  fail closed with recovery text.
- Agents must measure layout, worktrees, and status; run `--dry-run` first; and
  obtain explicit confirmation before a mutating run. See
  [`docs/supagit-agent-command.md`](docs/supagit-agent-command.md).
- Open product backlog (Supabase recovery UX) lives under
  [`docs/superpowers/backlog/`](docs/superpowers/backlog/); track status in
  [`tasks/task.md`](tasks/task.md).
