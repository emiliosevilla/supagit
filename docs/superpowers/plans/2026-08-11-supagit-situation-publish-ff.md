# Situation Publish/FF Reorder (Section 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run publish-on-first before feature integrate and before `ff_sync`, and refuse fast-forward (and any `reset --hard` recovery) while the worktree is dirty — matching the Situation design order and “never ff/reset-hard while dirty”.

**Architecture:** Harden `ff_sync_branch` with an early porcelain dirty gate. Reorder `Pipeline.run` to `commit_and_publish_dev` → `sweep_features` → `ff_sync_first_branch`. Adjust `commit_and_publish_dev` so a **clean + behind_only** tree defers sync to `ff_sync` instead of treating remote-ahead counts as “unpublished commits” and failing `_assert_dev_synced`. After a dirty commit, if the branch is still behind/diverged vs remote, skip push and leave sync to `ff_sync` (which fail-closes on diverge without destroying work). Feature-behind ff execute remains Section 4.

**Tech Stack:** Python 3 stdlib, existing `unittest`, `supagit_i18n.t`.

**Spec:** `docs/superpowers/specs/2026-08-11-supagit-situation-resilience-design.md` (design item 3).

## Global Constraints

- Python 3 stdlib only.
- No `stash`, force-push, auto-rebase.
- Never start ff-only or `reset --hard` while porcelain is dirty.
- Cyan/green tutor UX unchanged.
- Agent must not `git commit` / `git push` unless the user explicitly asks; commit steps below are for the human.

---

## File map

| File | Responsibility |
|------|----------------|
| `scripts/supagit_sweep.py` | Dirty gate at start of `ff_sync_branch` |
| `scripts/supagit.py` | Reorder phases; publish deferrals for behind |
| `scripts/supagit_i18n.py` | Dirty-ff and defer-behind message keys (en+es) |
| `scripts/test_supagit_sweep.py` | Dirty-ff unit test; run() phase order assertion |
| `scripts/test_supagit.py` | Publish clean-behind deferral if tested at Pipeline layer |

---

### Task 1: i18n for dirty ff + publish defer behind

**Files:**
- Modify: `scripts/supagit_i18n.py`

**Keys (en + es):**
- `error_ff_dirty`: worktree dirty; commit/publish first; include branch name.
- `publish_defer_behind`: clean local `{branch}` is behind `{remote}/{branch}`; fast-forward will sync (no push).

- [ ] **Step 1:** Add keys to both language dicts.

---

### Task 2: Dirty gate in `ff_sync_branch`

**Files:**
- Modify: `scripts/supagit_sweep.py`
- Modify: `scripts/test_supagit_sweep.py`

**Behavior:**
1. Before fetch/merge, `run_git("status", "--porcelain")`; if non-empty → `SweepError` using `t("error_ff_dirty", branch=branch)` (or English fallback string if sweep must stay i18n-light — prefer `t()` like other user-facing paths; if sweep historically uses raw English, match existing SweepError style and keep message actionable).
2. Existing diverge / ff-only / `reset --hard` on failed merge paths unchanged **after** the clean gate (recovery only runs when we started clean).

Check how other SweepErrors are phrased in this module; stay consistent (many are raw English today). Prefer adding i18n via Pipeline when wrapping, or import `t` in sweep if already used.

- [ ] **Step 1: Failing test** — fake/temp repo with dirty file; `ff_sync_branch` raises; assert message mentions dirty / commit; assert no `merge`/`reset` invoked (or no tip change).
- [ ] **Step 2: Implement gate**
- [ ] **Step 3: Existing FfSyncTests still pass**

---

### Task 3: `commit_and_publish_dev` deferrals

**Files:**
- Modify: `scripts/supagit.py` (`commit_and_publish_dev`)
- Test: `scripts/test_supagit.py` or sweep orchestration

**Behavior when status clean:**
- Parse `rev-list --left-right --count {remote}/{dev}...{dev}` → `remote_only`, `local_only`.
- `0 0` → existing “already synchronized” return (keep `_assert_dev_synced` or equivalent).
- `remote_only > 0` and `local_only == 0` → print defer-behind message; **return without push/assert failure**.
- `local_only > 0` and `remote_only == 0` → existing publish-existing path.
- both `> 0` → `ShipError` diverge (fail closed).

**Behavior after dirty commit (before push):**
- Re-measure ahead/behind.
- If `remote_only > 0` (behind or diverged): skip push; print that sync follows / cannot push until reconciled; return **without** `_assert_dev_synced` (ff phase or diverge error comes next).
- Else: existing push + `_assert_dev_synced`.

- [ ] **Step 1: Tests** for clean-behind deferral (mock `git`).
- [ ] **Step 2: Implement**

---

### Task 4: Reorder `Pipeline.run`

**Files:**
- Modify: `scripts/supagit.py` `run()`
- Modify: `scripts/test_supagit_sweep.py` order test (~`ff_sync_first_branch` / `commit_and_publish_dev` indices)

**New phase order after validate/inventory:**
```
commit_and_publish_dev()
if integrate: sweep_features(...)
ff_sync_first_branch()
_assert_dev_synced()
… checks / promote …
```

- [ ] **Step 1: Update order test** — assert `commit_and_publish_dev` index < `ff_sync_first_branch` index; if integrate is stubbed, still assert publish before ff.
- [ ] **Step 2: Reorder `run()`**
- [ ] **Step 3: Full suite**

```bash
SUPAGIT_SKIP_UPDATE=1 python3 -m unittest scripts.test_supagit scripts.test_supagit_sweep scripts.test_supagit_situation
```

---

### Task 5: Section 3 verification

- [ ] Full unittest OK.
- [ ] Human: dry-run on dirty first branch shows plan publish-then-ff; live path refuses ff while dirty if somehow reached.
- [ ] Human: PR from `work` → `main`.

---

## Spec coverage (Section 3 only)

| Spec item | Task |
|-----------|------|
| Never ff / reset-hard while dirty | Task 2 |
| publish before ff on pipeline[0] | Task 3–4 |
| Runtime order publish → integrate → ff | Task 4 |
| Feature behind_only execute in worktree | **Section 4** |
| Self-update diverge | **Section 5** |

## Self-review notes

- Dirty+behind after commit often becomes **diverged**; ff then fail-closes without wiping the new commit. Preflight still labels `publish_then_ff` as the intended ordering; true content merge remains manual (no auto-rebase) per spec boundaries.
- Plan text from Section 2 already lists publish before pipeline0 ff; execution now matches.
