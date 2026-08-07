# supagit

`supagit` is a fail-closed promotion pipeline for projects that publish code
through an ordered sequence of Git branches.

The command, installer, and tests live in [`scripts/`](scripts/). The project
configuration template is [`.supagit.json.example`](.supagit.json.example), and
the agent-specific operating instructions are in
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
If the source repository has moved, run this installer again from its new path.

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

The initializer refuses to overwrite an existing `.supagit.json`. It writes
only backend/branch configuration; it does not install the global command or
store Supabase IDs.

Pass ordered branches when the project does not use the legacy three-stage
layout, for example `supagit init --backend none --branches main`.

## Running

Always inspect the plan first:

```bash
scripts/supagit --dry-run
```

Then run the confirmed pipeline:

```bash
scripts/supagit
```

The pipeline publishes local changes on the first branch, runs configured
checks, migrates the backend configured for each destination branch when
present, promotes each adjacent branch pair, and returns to the first branch.
It requires the main checkout and stops on errors or inconsistencies.

## Output and safety

- Confirmation and commit-message prompts are green.
- Successful completion is green.
- Warnings, errors, aborts, and negative manual-intervention messages are red.
- `NO_COLOR` and `--no-color` disable color; `--color always` forces it.
- The command never uses forced Git operations and does not infer an ambiguous
  deployment target.
