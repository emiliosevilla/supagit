# Backlog: Supabase hardening (deferred)

**Status:** deferred — not part of wave-1 Situation resilience (Git + self-update).  
**Spec pointer:** `docs/superpowers/specs/2026-08-11-supagit-situation-resilience-design.md` (boundaries: *Ask first* for Supabase recovery).

## Why deferred

Wave 1 focused on fail-closed Git promotion and tool self-update. Supabase already
stops on missing/ambiguous project refs and never guesses IDs. Richer **recovery**
UX was explicitly parked so Git cures could ship first.

## Candidate work (ask before implementing)

1. **Ambiguous / missing ref recovery** — clearer diagnosis when env vars, `.env*`,
   or `project_ref` fields disagree; exact next commands to set one ref.
2. **Migrate failure diagnosis** — map common Supabase CLI failures to actionable
   cyan/red tutor text (auth expired, wrong linked project, pending migration
   conflicts) without auto-mutating remote DB state beyond the existing checkpoint.
3. **Credential / env repair UX** — guide re-login / re-link without storing secrets
   in `.supagit.json` or the global installer.
4. **Dry-run honesty** — ensure `--dry-run` never implies a migration succeeded
   when the CLI would have been skipped or would have failed closed.

## Non-goals (unless separately approved)

- Auto-choosing among multiple Supabase projects.
- Storing personal access tokens in the repo or in the global skill install.
- Silent retries that hide migration failure.

## When to pull this in

Prefer a dedicated brainstorming + design pass after wave-1 Git resilience has
soaked in production use, or when a concrete migrate/ref incident needs product
changes beyond clearer error strings already possible in the Git path.
