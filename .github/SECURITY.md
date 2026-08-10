# Security Policy

## Supported versions

Security fixes are applied to the latest commit on the default branch (`main`)
of [`emiliosevilla/supagit`](https://github.com/emiliosevilla/supagit). There
are no numbered release trains yet: install or update with the bootstrap
one-liner or `scripts/install-supagit-global.sh`, then re-run `supagit` so the
self-updater can fast-forward the registered source clone.

| Channel | Supported |
| ------- | --------- |
| `main` (latest) | Yes |
| Older local clones / forks | No — update to current `main` |

## Reporting a vulnerability

**Do not** open a public issue for security problems.

Prefer GitHub’s private reporting flow for this repository:

1. Open https://github.com/emiliosevilla/supagit/security/advisories/new  
   (or **Security → Advisories → Report a vulnerability** on the repo).
2. Describe the issue, impact, and steps to reproduce.
3. Include your environment (OS, `supagit` install path, and whether you used
   the curl bootstrap or a manual clone).

If private vulnerability reporting is not yet enabled on the repo, contact the
maintainer via GitHub (@emiliosevilla) without posting exploit details publicly.

You should receive an acknowledgement when the report is seen. Fix timelines
depend on severity and complexity; coordinated disclosure is preferred.

## Scope

In scope examples:

- Remote code execution or unexpected code execution via the installer,
  bootstrap script, or `supagit` launcher.
- Path traversal, secret leakage, or unsafe handling of Git remotes / hooks
  that could compromise the user machine or a target project repo.
- Failures of fail-closed guarantees that silently discard user work or push
  destructive Git operations without confirmation.

Out of scope examples:

- Issues that only affect a stale local clone that has not updated from
  `origin/main`.
- Social engineering against GitHub accounts.
- Vulnerabilities in third-party tools that `supagit` invokes (`git`, `gh`,
  Supabase CLI) when used outside this project’s wrappers — report those
  upstream.

## Maintainer response

Reports are handled by @emiliosevilla. Please allow reasonable time before any
public disclosure.
