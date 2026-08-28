# supagit

> Give your AI agent back its context.

## What it is

`supagit` is a local Terminal command for releasing a project through Git and
its configured backend migrations. It replaces a long sequence of repetitive
commands with one visible, guided operation.

When an AI agent delegates this operational work to `supagit`, the operation
uses no AI tokens. The tool shows the plan, asks for confirmation, displays
progress, and reports clearly what happened.

## What it is used for

- Inspecting the repository, branches, worktrees, and remote.
- Committing and publishing local work.
- Integrating branches through pull requests or direct Git operations.
- Running configured checks and backend migrations, including Supabase.
- Promoting code through an ordered branch pipeline.
- Showing failures, unexpected states, and successful completion clearly.

## What it is not

- It is not an AI model or an autonomous coding agent.
- It is not a replacement for code review, tests, or CI.
- It is not a database host or a general deployment platform.
- It does not hide changes, stash work, force-push, or reset a dirty worktree.

## How to use it

Run it from the repository you want to release. Do not switch branches first.

```bash
supagit --dry-run
supagit
```

If the project has no `.supagit.json`, initialize it first:

```bash
supagit init --backend none
```

For a project with Supabase migrations, use `--backend supabase` instead.
`supagit` detects the usual `dev`, `pre`, and `prod` pipeline. Any ordered
pipeline can be configured, for example:

```json
"branches": ["dev", "staging", "production"]
```

The command is interactive by default. Useful options include `--yes`,
`--lang`, `--pipeline`, `--integrate`, and `--no-sweep`. Pull-request paths
require the GitHub CLI (`gh`) to be installed and authenticated.

## How to install it

Install the global command from any directory:

```bash
curl -fsSL https://raw.githubusercontent.com/emiliosevilla/supagit/main/scripts/bootstrap.sh | sh
```

The installer downloads the source, installs the global command and agent
skill, and adds `~/.local/bin` to `PATH` when needed. Use `--lang es` for
Spanish installer messages; the command itself supports English and Spanish.

## How to uninstall it

Remove the global command, skill, and agent command:

```bash
rm -f "$HOME/.local/bin/supagit" "$HOME/.claude/commands/supagit.md"
rm -rf "$HOME/.agents/skills/supagit"
```

If you installed with the bootstrap script, also remove its downloaded source
clone:

```bash
rm -rf "$HOME/.local/share/supagit"
```

Finally, remove the `~/.local/bin` export line from `~/.zprofile` if no other
tool uses it.

## Author

Created by [Emilio Sevilla](https://github.com/emiliosevilla).

## License

Released under the [MIT License](LICENSE).

## Further reading

- [Agent guide and safe usage](docs/supagit-agent-command.md)
- [Configuration example](.supagit.json.example)
- [Open and completed tasks](tasks/task.md)
- [Project repository](https://github.com/emiliosevilla/supagit)
