# Situation Docs + Supabase Backlog (Section 7) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (or edit docs directly). Checkbox steps for tracking.

**Goal:** Document wave-1 Situation resilience in README and the agent skill, and leave an explicit Supabase-hardening backlog note (out of scope for wave 1).

**Architecture:** Docs-only. No runtime code changes. Skill source remains `docs/supagit-agent-command.md` (installer copies it to `SKILL.md`).

**Spec:** `docs/superpowers/specs/2026-08-11-supagit-situation-resilience-design.md` (item 7).

## Global Constraints

- Match implemented behavior (Sections 1–6); do not document unbuilt cures (rebase/stash).
- Agent must not `git commit` / `git push` unless the user explicitly asks.

---

## File map

| File | Responsibility |
|------|----------------|
| `README.md` | User-facing Situation / phase-order / self-update / empty-PR notes |
| `docs/supagit-agent-command.md` | Agent skill: preflight, phase order, fail-closed rules |
| `docs/superpowers/backlog/2026-08-11-supabase-hardening.md` | Deferred Supabase recovery backlog |
| `docs/superpowers/specs/2026-08-11-supagit-situation-resilience-design.md` | Mark follow-ons 2–7 as shipped; point to backlog |
| `docs/superpowers/plans/2026-08-11-supagit-situation-docs.md` | This plan |

---

### Task 1: README

Update auto-update (diverged source fails closed), sweeper flow (cyan Situation preflight; plan includes cures), phase order **publish → integrate → ff**, feature behind ff, empty PR refuse, safety bullets (no ff/`reset --hard` while dirty).

- [ ] Edit README sections Installation / Running / Output and safety.

### Task 2: Agent skill

Same behavioral updates; keep “never invent `<placeholders>`” and measure-before-mutate.

- [ ] Edit `docs/supagit-agent-command.md`.

### Task 3: Supabase backlog + spec pointer

- [ ] Create backlog note listing deferred items (ambiguous ref recovery, migrate failure diagnosis, credential/env repair UX) — **ask before implementing**.
- [ ] Update design spec “Later design sections” to note wave-1 Git items shipped; Supabase deferred to backlog.

### Task 4: Human PR

```bash
git switch -C work
# add docs…
git commit -m "Document Situation resilience and defer Supabase hardening."
git push -u origin work --force-with-lease
gh pr create …
# merge with real PR number
```

---

## Spec coverage (Section 7 only)

| Spec item | Task |
|-----------|------|
| Docs README + agent skill | Task 1–2 |
| Supabase backlog note | Task 3 |
