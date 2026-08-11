# Tasks: supagit

Last updated: 2026-08-12

## Open

- [ ] Supabase hardening (deferred backlog)
  - Spec/backlog: `docs/superpowers/backlog/2026-08-11-supabase-hardening.md`
  - Ask before implementing (ambiguous refs, migrate diagnosis, credential UX)

## Done (recent)

- [x] Situation resilience wave 1 (Sections 1–7) — merged through PR #19
  - Spec: `docs/superpowers/specs/2026-08-11-supagit-situation-resilience-design.md`
  - Plans removed after completion (`docs/superpowers/plans/` cleared)
- [x] Tutor menu / checkout flex
- [x] Coche escoba sweeper
- [x] Lang / auto-init / self-update (`docs/superpowers/specs/2026-08-10-supagit-lang-autoupdate-autoinit.md`)

## Notes

- No linked git worktrees beyond the main checkout (`git worktree list` → only `main`).
- Local branch `work` may still exist for PR flow; delete when idle if desired.
- Completed implementation plans under `docs/superpowers/plans/` were deleted; keep specs + backlog.
