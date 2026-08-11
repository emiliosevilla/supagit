# Situation Feature FF (Section 4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Before integrating a feature branch, fast-forward it when clean and `behind_only` — in that feature’s worktree when present, without checking out the feature onto `pipeline[0]`’s tree.

**Architecture:** Extend `ff_sync_branch` with optional `cwd` and a no-checkout update path (`merge-base --is-ancestor` + `update-ref`) when HEAD in `cwd` is not the target branch. Call it from `integrate_branch` only when the feature worktree is clean (dirty features still use the existing commit path; dirty+behind remains preflight-`blocked`). Pipeline already passes `info.worktree_path or self.root` as `cwd`.

**Tech Stack:** Python 3 stdlib, existing `unittest`, `supagit_i18n.t`.

**Spec:** `docs/superpowers/specs/2026-08-11-supagit-situation-resilience-design.md` (design item 4).

## Global Constraints

- Never ff / `reset --hard` while the **checked-out** target branch’s worktree is dirty.
- Never `git checkout` a feature onto the main promotion checkout just to sync it.
- No stash / force-push / auto-rebase.
- Agent must not `git commit` / `git push` unless the user explicitly asks.

---

## File map

| File | Responsibility |
|------|----------------|
| `scripts/supagit_sweep.py` | `ff_sync_branch(..., cwd=)`; no-checkout ff; `integrate_branch` calls ff when clean |
| `scripts/test_supagit_sweep.py` | Dirty/cwd/behind/integrate ordering tests |
| `scripts/supagit_i18n.py` | Optional clearer error if checkout/update-ref blocked (only if needed) |

---

### Task 1: `ff_sync_branch` accepts `cwd` + no-checkout ff

**Files:**
- Modify: `scripts/supagit_sweep.py`
- Modify: `scripts/test_supagit_sweep.py`

**Behavior:**
1. Optional `cwd: Path | None = None`; pass through to every `run_git` / helper that needs it (`_fetch_remote_branch`, `ahead_behind`, status, merge, reset, update-ref).
2. Dirty gate: only if `branch --show-current` in that cwd equals `branch` (otherwise the branch cannot have a dirty index in that cwd).
3. If already on `branch`: existing `merge --ff-only` path (and existing clean-tree `reset --hard` recovery).
4. If **not** on `branch`: do **not** checkout. When `remote_only > 0` and `local_only == 0`:
   - `merge-base --is-ancestor {branch} {remote_ref}` must succeed
   - `update-ref refs/heads/{branch} {remote_ref}` (skip when `dry_run`)
   - Verify `rev-parse {branch}` == `rev-parse {remote_ref}`
5. Diverge / nothing-behind behavior unchanged.

- [ ] **Step 1: Failing tests**
  - Fake runner: cwd passed to status/fetch when provided.
  - Not-on-branch + behind_only → `update-ref`, never `checkout` / `merge`.
  - On-branch + dirty → still raises; no fetch.
- [ ] **Step 2: Implement**
- [ ] **Step 3: Existing FfSyncTests green** (real-git tests still on-branch)

---

### Task 2: `integrate_branch` syncs clean features before push/PR

**Files:**
- Modify: `scripts/supagit_sweep.py` `integrate_branch`
- Modify: `scripts/test_supagit_sweep.py`

**Behavior:**
```
if contained: fail
gh ready + github remote
status = porcelain(cwd)
if dirty:
    commit_dirty_tree(...)
else:
    ff_sync_branch(run_git, branch, remote, dry_run=dry_run, cwd=cwd)
push_branch(...)
find/create/merge PR
fetch base
```

- [ ] **Step 1: Failing test** — clean integrate sees `ff_sync` / fetch-for-feature before push; dirty integrate does not call update-ref/merge for ff.
- [ ] **Step 2: Implement**
- [ ] **Step 3: Existing integrate tests updated for extra git calls (status already present; allow ff no-op when ahead counts `0\t0`)**

---

### Task 3: Verification

```bash
SUPAGIT_SKIP_UPDATE=1 python3 -m unittest scripts.test_supagit scripts.test_supagit_sweep scripts.test_supagit_situation
```

- [ ] Human PR from `work` → `main` (`gh pr merge N --merge --admin` with real number).

---

## Spec coverage (Section 4 only)

| Spec item | Task |
|-----------|------|
| Feature `behind_only` → ff in correct worktree/checkout | Task 1–2 |
| Never checkout feature onto wrong tree | Task 1 |
| Dirty feature+behind blocked | Already Section 1/2 preflight; ff dirty gate when on branch |
| Empty PR / gh create preflight | **Section 6** |
| Self-update diverge | **Section 5** |

## Self-review notes

- `ff_sync_first_branch` keeps default `cwd=None` → `_sweep_git` uses `self.root` (pipeline0), unchanged.
- Integrate tests that fake `run_git` must return ahead/behind `0\t0` (or handle `rev-list`) so ff no-ops after status clean.
