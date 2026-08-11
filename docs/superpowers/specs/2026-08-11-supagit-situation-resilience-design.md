# Spec: supagit Situation resilience (Git / self-update)

## Objective

Make `supagit` read messy real-world Git layouts and apply **safe** countermeasures after confirmation, while **failing closed** on destructive or ambiguous cases — without becoming an automatic rebase/force/stash engine.

**User:** developers running promotion pipelines whose repos are rarely “clean on the right branch with remotes perfectly aligned.”

**Success:** given dirty trees, remote-ahead branches, wrong checkouts, open PRs, or a diverged tool install, `supagit` either (a) proposes and executes a safe cure after green Confirm, or (b) stops with a cyan diagnosis and exact recovery commands — and never silently destroys work.

## ASSUMPTIONS (approved in brainstorming)

1. Philosophy **C**: safe cures → propose + Confirm + execute; destructive/ambiguous → fail-closed with actionable diagnosis.
2. Wave 1 scope **2**: **target project Git** + **supagit self-update** clone. Not Supabase hardening.
3. Dirty on `pipeline[0]` + remote movement → **publish/commit first, then ff-only** (standard “commit before pull”; no stash). Reorder relative to today’s ff-then-publish path.
4. Feature branch only **behind** upstream → Confirm → **ff-only**; **diverged** → fail-closed (no auto-rebase).
5. Situation reading **C**: **preflight summary + per-phase re-measure gates**.
6. Implementation approach **2**: module `Situation` + preflight + policy (not ad-hoc patches only; not a full FSM).
7. Hard bans remain: no `git stash`, no `git push --force`, no auto-rebase, no `reset --hard` while the worktree is dirty.
8. Python 3 **stdlib only**; keep cyan/green tutor UX and existing `--dry-run` / `--yes` semantics.
9. Existing `gh pr create` URL parsing (no `--json`) stays; Situation must not reintroduce unsupported `gh` flags.

## Deferred (explicit backlog)

- **Supabase hardening** (failed mid-migration, ambiguous refs, CLI auth, remote DB drift): **pending — separate spec later.** Do not expand wave 1 into backend recovery.

## Out of scope (wave 1)

- Auto-resolving merge conflicts
- Rewriting history / interactive rebase
- Changing GitHub branch protection or rulesets
- Human shell UX outside `supagit` (zsh paste, editor merge messages)

## Commands (verification)

```bash
cd /path/to/supagit
SUPAGIT_SKIP_UPDATE=1 python3 -m unittest scripts.test_supagit scripts.test_supagit_sweep scripts.test_supagit_situation -v
SUPAGIT_SKIP_UPDATE=1 scripts/supagit --dry-run --lang en
```

## Project structure

```
scripts/supagit_situation.py     → Situation measure + classify + render (new)
scripts/supagit_sweep.py         → ff_sync / integrate consume Situation policy
scripts/supagit_update.py        → self-update diverge handling
scripts/supagit.py               → preflight hook + phase reorder + gates
scripts/test_supagit_situation.py → unit tests for Situation (new)
docs/superpowers/specs/…         → this design
docs/superpowers/plans/…         → implementation plans per section
```

## Architecture (Section 1 — approved)

### Situation snapshot

A measured (not guessed) snapshot of:

| Field group | Contents |
|-------------|----------|
| Checkout | current branch or detached; whether dirty; optional sensitive-path hit |
| Sync | per relevant ref (`pipeline[0]`, selected integrate branches, their upstreams): `in_sync` / `ahead_only` / `behind_only` / `diverged` / `no_upstream` |
| Worktrees | which path holds which branch (or none) |
| GitHub | `gh` ready yes/no; open PR number for head→base if any |
| Self-update | source-root vs `origin/main`: ok / behind / diverged / missing |

### Policy classes

| Class | Meaning | UX |
|-------|---------|-----|
| `safe_cure` | Standard, reversible-enough Git practice | Cyan explain → green Confirm → execute |
| `blocked` | Would risk data loss or wrong-branch mutation | `ShipError` with exact next commands |
| `info` | Notable but no action required | Cyan only |

### Policy table (wave 1)

| Finding | Class | Cure / stop |
|---------|--------|-------------|
| Clean tree + branch `behind_only` vs upstream | `safe_cure` | ff-only |
| Dirty on `pipeline[0]` + remote behind/ahead | `safe_cure` (ordered) | publish/commit first → then ff-only; **never** ff or `reset --hard` while dirty |
| Feature `behind_only` vs its upstream | `safe_cure` | ff-only on that branch in the correct worktree/checkout |
| Any `diverged` (ahead+behind) | `blocked` | Stop; show `rev-list` counts + manual options (no auto-rebase) |
| Commit target branch ≠ HEAD / wrong worktree | `blocked` or `safe_cure` if a clean checkout move is allowed by existing relocate rules | Never commit on the wrong branch |
| Open PR head→base already exists | `safe_cure` / info | Reuse PR (existing behavior) |
| `gh` missing / unauthenticated when PR required | `blocked` | Existing `ensure_ready` messaging |
| Self-update `behind_only` | `safe_cure` | Existing pull ff-only + reinstall + re-exec |
| Self-update `diverged` | `blocked` | Do not ff-only; tell user to fix source clone |
| Empty / no commits to integrate (not ancestor-contained case already handled) | `blocked` | Fail before `gh pr create` with clear text |

### Runtime flow

```
language / welcome
  → (self-update gate, Situation-aware)
  → menu selection
  → measure Situation (project)
  → cyan preflight (findings + proposed cures)
  → cyan execution plan (includes cures)
  → green plan Confirm (force under --dry-run)
  → phases with re-measure gates:
       ensure checkout → publish-if-dirty-on-first (before ff)
       → integrate features (sync feature if behind_only)
       → ff_sync first (only if clean)
       → … promote / cleanup
```

### Error handling

- Map policy `blocked` → `ShipError` / `SweepError` with i18n keys and concrete `git`/`gh` commands in the message body.
- `--dry-run`: still measure + print preflight + plan; execute no mutating cures; plan Confirm still forced.
- `--yes`: skip Confirm for `safe_cure` only when flags already imply non-interactive intent; still refuse `blocked` (never auto-heal diverge under `--yes`).

### Testing strategy

- Pure unit tests for classify/render with fake git runners (no network).
- Orchestration tests: dirty+behind refuses ff until publish path; diverge blocks; feature behind schedules ff-only; wrong-branch commit blocked.
- Keep existing suites green.

### Boundaries

**Always do:** measure before mutate; re-measure at gates; fail closed on diverge; preserve tutor colors.

**Ask first:** expanding cures to rebase/stash; changing merge method defaults; Supabase recovery.

**Never do:** stash, force-push, auto-rebase, `reset --hard` on dirty trees; unsupported `gh` flags.

## Later design sections (wave-1 follow-ons)

Git + self-update items 2–6 are implemented on `main`. Item 7 (this docs/backlog
pass) lands with the matching plan under `docs/superpowers/plans/`.

2. ~~Wire preflight into `Pipeline.run` and plan rendering~~  
3. ~~Reorder publish ↔ ff_sync; harden `ff_sync` dirty gate~~  
4. ~~Feature integrate: correct worktree/checkout + behind_only ff~~  
5. ~~Self-update diverge Situation~~  
6. ~~Empty-PR / gh create preflight~~  
7. Docs (README + agent skill) + backlog note for Supabase  

Supabase recovery hardening remains deferred:
`docs/superpowers/backlog/2026-08-11-supabase-hardening.md`.

## Relationship to prior specs

- Extends fail-closed rules from `2026-08-09` coche-escoba plan and tutor/checkout amendments.
- Does not replace tutor menu UX; preflight is an additional cyan block before the plan.
