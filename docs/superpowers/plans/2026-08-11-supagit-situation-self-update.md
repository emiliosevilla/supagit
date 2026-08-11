# Situation Self-Update Diverge (Section 5) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Treat a diverged registered supagit source clone as **blocked**: do not run `git pull --ff-only`; raise a clear `UpdateError` with recovery commands. Keep behind-only auto-update (ff-only + reinstall + re-exec) unchanged.

**Architecture:** Measure `origin/main...HEAD` as `(remote_only, local_only)`. Classify with `supagit_situation.classify_sync_counts`. `needs_update` is true only for `behind_only`. Before pull (and in `maybe_self_update` / main gate), `diverged` raises; `ahead_only` / `in_sync` skip update.

**Tech Stack:** Python 3 stdlib, `supagit_situation`, `supagit_i18n.t`, `unittest`.

**Spec:** `docs/superpowers/specs/2026-08-11-supagit-situation-resilience-design.md` (item 5).

## Global Constraints

- No auto-rebase / force-push / stash on the source clone.
- Do not ff-only when diverged.
- `SUPAGIT_SKIP_UPDATE=1` still skips the whole gate.
- Agent must not `git commit` / `git push` unless the user explicitly asks.

---

## File map

| File | Responsibility |
|------|----------------|
| `scripts/supagit_update.py` | `sync_counts`, diverge guard, `needs_update` = behind_only only |
| `scripts/supagit_i18n.py` | `error_self_update_diverged` (en+es) |
| `scripts/test_supagit.py` | Unit tests for behind / ahead / diverge / in_sync |

---

### Task 1: i18n error for diverged source clone

**Keys:** `error_self_update_diverged` with `{path}`, `{remote}`, `{branch}` — include `cd {path}`, `git fetch`, `git log --oneline --left-right {remote}/{branch}...HEAD`.

- [ ] Add en + es.

---

### Task 2: Measure both sides; block diverge; needs_update = behind_only

**Interfaces:**
- `sync_counts(source_root, remote=..., branch=...) -> tuple[int, int]` → `(remote_only, local_only)` after fetch
- `commits_behind` → keep as `sync_counts(...)[0]` for callers, or update call sites
- `needs_update` → `classify_sync_counts(local_only=..., ahead from local) == BEHIND_ONLY`  
  Note: `rev-list {remote}/{branch}...HEAD` → left=remote_only (behind), right=local_only (ahead). So `classify_sync_counts(ahead=local_only, behind=remote_only)`.
- `ensure_self_update_allowed(source_root)` or inline in `needs_update` / `pull_and_reinstall`: if `DIVERGED`, raise `UpdateError(t(...))`
- `pull_and_reinstall`: call ensure before pull (defense in depth)

- [ ] **Step 1: Failing tests**
  - `2\t0` → needs_update True
  - `0\t0` → False
  - `0\t3` → False (ahead only)
  - `1\t1` → needs_update False **and** calling ensure/pull/needs path that checks diverge raises with fetch/log hints
- [ ] **Step 2: Implement**
- [ ] **Step 3: Existing skip-env / behind tests still pass**

---

### Task 3: Verification

```bash
SUPAGIT_SKIP_UPDATE=1 python3 -m unittest scripts.test_supagit scripts.test_supagit_sweep scripts.test_supagit_situation
```

Human: PR from `work` → `main`; merge with real PR number (not `<N>`).

---

## Spec coverage (Section 5 only)

| Spec item | Task |
|-----------|------|
| Self-update `behind_only` → ff + reinstall | unchanged path via `needs_update` |
| Self-update `diverged` → blocked + fix source clone | Task 2 |
| Empty PR preflight | **Section 6** |
| Docs / skill | **Section 7** |

## Self-review notes

- Main already wraps `UpdateError` in `ShipError`; bilingual key via `t()` is enough.
- Do not populate `Situation.self_update` in this section unless a one-line hook is trivial; startup gate is the required behavior.
