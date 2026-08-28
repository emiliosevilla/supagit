# supagit

> A complete project release in one Terminal command.

When an AI agent performs Git and backend operations manually, it spends time
and tokens writing commands, explaining each step, and checking the result.
`supagit` runs that operational work locally: it uses no AI tokens for the
operation.

Type this in the project directory:

```bash
supagit
```

`supagit` covers the full release flow: Git inspection, commits, pushes,
pull-request integration, branch promotion, checks, and configured backend
migrations. It shows the plan, asks for confirmation, and reports clearly what
happened.

## Why supagit

- No AI tokens for the operational flow.
- One visible command instead of a long sequence of Git and backend steps.
- Clear feedback when something fails, changes unexpectedly, or succeeds.
- Pull requests when GitHub branch rules require them.
- Backend migrations, including Supabase migrations, when the project configures them.
- Fail-closed behavior: no forced pushes, hidden stashes, or destructive resets.
- English or Spanish prompts, with a spinner for long-running work.

`supagit` works carefully: it stops on ambiguous states and does not hide
changes or force a push. Its goal is to turn a long, repetitive process into
one visible and controllable action.

## Quick start

Install the global command:

```bash
curl -fsSL https://raw.githubusercontent.com/emiliosevilla/supagit/main/scripts/bootstrap.sh | sh
```

Run it from the repository you want to release:

```bash
cd path/to/your-project
supagit init --backend none
supagit --dry-run
supagit
```

For a project with Supabase migrations, use `supagit init --backend supabase`.
If `.supagit.json` already exists, skip `init`.

## How it works

`supagit` detects the usual `dev`, `pre`, and `prod` pipeline, or uses an
ordered list defined by the project, for example:

```json
"branches": ["dev", "staging", "production"]
```

Each run:

1. Inspects the project and shows the plan.
2. Integrates the selected work.
3. Runs the configured checks.
4. Applies the required migrations, when configured.
5. Promotes changes through the branches in the defined order.

The process is interactive by default. Automation options include `--yes`,
`--lang`, `--pipeline`, `--integrate`, and `--no-sweep`.

## More information

- [Agent guide and safe usage](docs/supagit-agent-command.md)
- [Configuration example](.supagit.json.example)
- [Open and completed tasks](tasks/task.md)
- [MIT License](LICENSE)

Ideas, issues, and improvements are welcome on
[GitHub](https://github.com/emiliosevilla/supagit).
