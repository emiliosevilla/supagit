# Supagit Novice Chaos Resilience — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `supagit` absorb Git/GitHub/Supabase chaos (dirty trees, wrong branches, linked worktrees, diverged histories, deleted remotes, stale auth, merge conflicts, missing config) with near-zero manual intervention. Two non-negotiable invariants:

1. **Install once, run forever:** after a single `curl` from the public repo, typing `supagit` must always run the correct, latest code — no matter what happened to the source clone.
2. **Database before code:** every Supabase `db push` / migration must land **before** any Git merge that would trigger CI deploy. Frontend deploy never outruns its backend.

**Architecture:** Keep the current modular split (`supagit.py` orchestration, `supagit_sweep.py` Git/GitHub actions, `supagit_situation.py` sync policy, `supagit_inventory.py` repo scan, `supagit_menu.py` UX, `supagit_layout.py` layout, `supagit_update.py` self-update, `supagit_i18n.py` copy). Add: (1) a **single self-update + installation authority** that measures the source clone, repairs or re-clones it, and never touches project state; (2) a **launch-worktree status guard** before any pipeline[0] reposition; (3) a **safe sequence for dirty+behind** (rebase-onto-upstream then publish, never commit-while-behind then ff-only); (4) a **GhClient recovery ladder** (login → refresh → merge → auto → admin) and mergeability polling; (5) a **Supabase preflight** mirroring GhClient; (6) **empty/no-diff skip** instead of error; (7) **fetch --prune + sequencer-state detection** at preflight. No new top-level files except focused helpers where a module is already overloaded.

**Tech Stack:** Python 3.11+ (stdlib only), `git` CLI, `gh` CLI, `supabase` CLI, `unittest`.

## Global Constraints

- Fail-closed only when automatic recovery is impossible or destructive; never print “run this git/gh/supabase command yourself” as the primary fix.
- Cyan text explains; green prompts ask. Every green prompt must have a safe default (Enter).
- Never commit `.env*`, `*.pem`, `*.key`, credentials; if detected, exclude + offer `.gitignore` entry instead of aborting the run.
- Worktree rule: never force the same branch into two worktrees; adopt the existing one instead.
- Self-update must never hang on interactive installer prompts (already fixed: installer requires TTY for language menu; keep it).
- All new user-facing strings go through `supagit_i18n.t()`; no hardcoded English in errors.
- Tests: `unittest` in `scripts/test_*.py`; run from `scripts/` with `python3 -m unittest test_supagit_sweep test_supagit`.

---

## File Structure

| File | Responsibility |
|------|----------------|
| `scripts/supagit.py` | Orchestration, `Pipeline.run`, promote/publish/return, launch-worktree guard, Supabase checkpoint ordering |
| `scripts/supagit_sweep.py` | `GhClient` (auth/merge ladder), `integrate_branch`, `ff_sync_branch`, `commit_dirty_tree`, rebase, cleanup |
| `scripts/supagit_situation.py` | Sync classification, `Finding`/`PolicyClass`, cures, sequencer-state detection |
| `scripts/supagit_inventory.py` | Worktree/branch scan, upstream detection, stale-ref hygiene |
| `scripts/supagit_menu.py` | Menu rendering, default integrate/pipeline inference, skip-empty prompts |
| `scripts/supagit_update.py` | Self-update, source-clone health, re-clone/repair, non-interactive installer call |
| `scripts/supagit_i18n.py` | All user-facing strings (en/es) |
| `scripts/install-supagit-global.sh` | Global installer; language must be non-interactive under PIPE; wrapper source validation |
| `scripts/test_supagit.py` | `main`/update/spinner/menu tests |
| `scripts/test_supagit_sweep.py` | Git/PR/worktree/orchestration tests |
| `scripts/test_supagit_situation.py` | Situation policy tests |

---

## Phase 0 — Self-update & installation resilience (highest priority)

The user must be able to forget where supagit lives. The tool owns its source clone and its global installation.

### Task 1: Source-clone health check & repair

**Files:**
- Modify: `scripts/supagit_update.py`
- Modify: `scripts/install-supagit-global.sh` (wrapper source validation)
- Test: `scripts/test_supagit.py`

**Interfaces:**
- Produces: `ensure_healthy_source_root() -> Path`

- [ ] **Step 1: Write failing tests**

```python
# scripts/test_supagit.py
def test_missing_marker_or_source_recreates_clone(self): ...
def test_diverged_source_resets_or_recreates(self): ...
def test_deleted_source_directory_recovers(self): ...
```

- [ ] **Step 2: Run** → current code raises `UpdateError("no_source")` or `error_self_update_diverged`.
- [ ] **Step 3: Implement** — If `~/.agents/skills/supagit/source-root` is missing/unreadable or points to a deleted/moved path, or `assert_github_source` fails, or sync is DIVERGED/AHEAD: do **not** tell the user to fix their clone. Instead, clone `https://github.com/emiliosevilla/supagit` (shallow) into `~/.supagit/source`, rewrite the marker, and run the installer from there. Only fail if the clone itself fails (network/repo gone).
- [ ] **Step 4: Run tests green.**
- [ ] **Step 5: Commit** `feat: self-healing supagit source clone (re-clone on missing/dirty/diverged)`.

### Task 2: Single self-update authority in Python

**Files:**
- Modify: `scripts/supagit_update.py`
- Modify: `scripts/install-supagit-global.sh` (strip Python update logic from wrapper)
- Test: `scripts/test_supagit.py`

- [ ] **Step 1:** Failing test: wrapper’s `cmp` dance reinstalls stale code even when Python already updated.
- [ ] **Step 2:** Run → double-update / stale-code reinstall.
- [ ] **Step 3:** Wrapper only `exec python3 ~/.agents/skills/supagit/supagit.py "$@"`. All update decisions live in `maybe_self_update_and_reexec` → `pull_and_reinstall`. Keep `[build: YYYY-MM-DD]` marker on every reinstall so users can see freshness.
- [ ] **Step 4:** Green.
- [ ] **Step 5:** Commit `refactor: move self-update decision entirely into supagit_update.py`.

### Task 3: Install curl path validation

**Files:**
- Modify: `scripts/install-supagit-global.sh`
- Modify: `docs/install.sh` or public repo bootstrap if present
- Test: `scripts/test_supagit.py` (installer invocation)

- [ ] **Step 1:** Failing test: installer run from a directory that is not a supagit clone still writes a broken marker.
- [ ] **Step 2:** Run → marker points at wrong repo.
- [ ] **Step 3:** Installer validates `$repo_root/scripts/supagit.py` and `git remote get-url origin` matches `github.com/emiliosevilla/supagit`; otherwise abort with a clear “run the curl from the repo README” message.
- [ ] **Step 4:** Green.
- [ ] **Step 5:** Commit `fix: validate source repo before installing global supagit`.

---

## Phase 1 — Database-before-merge invariant

### Task 4: Backend checkpoint for pipeline[0] before any integrate

**Files:**
- Modify: `scripts/supagit.py:1834-1877` (`Pipeline.run`)
- Modify: `scripts/supagit.py:1085-1111` (`database_checkpoint`)
- Test: `scripts/test_supagit_sweep.py`

**Interfaces:**
- Consumes: `Pipeline._backend_target_for_branch`, `database_checkpoint`
- Produces: new ordering in `run()`

- [ ] **Step 1: Write failing test**

```python
def test_pipeline0_db_checkpoint_runs_before_feature_merges(self):
    # with backend=supabase, migrate of pipeline[0] must precede sweep_features
    ...
```

- [ ] **Step 2: Run** → today `sweep_features` runs before any `database_checkpoint`.
- [ ] **Step 3: Implement** — Before `commit_and_publish_dev` / `sweep_features`, resolve the first backend target (branch = `pipeline[0]`) and run `database_checkpoint(pipeline[0], ref)` if provider is supabase. Then, in the promotion loop, run the checkpoint for `target` **before** `promote(source, target)` (this already happens; keep it).
- [ ] **Step 4: Green.**
- [ ] **Step 5: Commit** `fix: run Supabase migrate for pipeline[0] before any feature merge`.

### Task 5: Fail-closed when Supabase checkpoint fails

**Files:**
- Modify: `scripts/supagit.py:1085-1111`
- Modify: `scripts/supagit.py:1861-1869`
- Test: `scripts/test_supagit_sweep.py`

- [ ] **Step 1:** Failing test: `database_checkpoint` exits non-zero → pipeline must abort, not continue to merge.
- [ ] **Step 2:** Run → current code may proceed depending on exception type.
- [ ] **Step 3:** Wrap `run_raw` in `database_checkpoint` to raise `ShipError` on any failure; `run()` must not catch-and-continue past it.
- [ ] **Step 4:** Green.
- [ ] **Step 5:** Commit `fix: abort pipeline when database checkpoint fails`.

---

## Phase 2 — Correctness fixes (broken “safe” cures)

### Task 6: Fix `publish_then_ff` divergence trap

**Files:**
- Modify: `scripts/supagit_situation.py:284-291`
- Modify: `scripts/supagit.py:995-1013` (`commit_and_publish_dev`)
- Modify: `scripts/supagit.py:1788-1798` (`ff_sync_first_branch` order note)
- Test: `scripts/test_supagit_situation.py`, `scripts/test_supagit_sweep.py`

- [ ] **Step 1: Write failing test** — dirty pipeline0 + behind upstream must rebase, not commit-then-ff-only.
- [ ] **Step 2: Run** → `publish_skip_push_behind` leaves ahead+behind.
- [ ] **Step 3: Implement** — when dirty + behind: commit → `git pull --rebase` (or `fetch` + `rebase origin/dev`) → push → verify 0/0. Keep `ff_only` for clean-behind.
- [ ] **Step 4: Green.**
- [ ] **Step 5: Commit** `fix: rebase dirty-behind pipeline[0] before publish`.

### Task 7: Cure dirty launch worktree before any early return

**Files:**
- Modify: `scripts/supagit.py:1625-1629` (`ensure_checkout_on_first_branch`)
- Test: `scripts/test_supagit_sweep.py`

- [ ] **Step 1:** Failing test — main on `pipeline[0]`, launch worktree dirty on feature → must auto-commit feature and auto-add to integrate.
- [ ] **Step 2:** Run → current code returns early and ignores launch dirt.
- [ ] **Step 3:** Implement: measure `launch_root` status/branch first; if dirty feature, run `_commit_dirty_before_reposition` and `_extend_integrate_after_pre_commit` before returning.
- [ ] **Step 4:** Green.
- [ ] **Step 5:** Commit `fix: commit dirty launch worktree before pipeline[0] early return`.

### Task 8: Skip empty / already-contained integrates instead of erroring

**Files:**
- Modify: `scripts/supagit_sweep.py:772-775` (`error_nothing_to_integrate`)
- Modify: `scripts/supagit_sweep.py:640-648` (`assert_commits_for_pr` empty range)
- Test: `scripts/test_supagit_sweep.py::IntegrateBranchTests`

- [ ] **Step 1:** Failing tests: `contained_in_first=True` and empty `base..head` both abort.
- [ ] **Step 2:** Run → raises.
- [ ] **Step 3:** Return a `SweepResult(skipped=True, reason="already merged")` / log “nothing to merge” and continue.
- [ ] **Step 4:** Green.
- [ ] **Step 5:** Commit `feat: skip empty or contained integrates silently`.

---

## Phase 3 — Git / worktree resilience

### Task 9: Adopt worktree that holds promote target

**Files:**
- Modify: `scripts/supagit.py:1194-1203` (`_promote_direct` locked branch)
- Test: `scripts/test_supagit_sweep.py`

- [ ] **Step 1:** Failing test: promote `dev→main` while `main` is checked out in another worktree → must adopt instead of `error_first_branch_in_worktree`.
- [ ] **Step 2:** Run → fails.
- [ ] **Step 3:** Use `_cwd_for_branch(target)`; if held elsewhere, set `target_cwd` to that worktree and continue (no checkout).
- [ ] **Step 4:** Green.
- [ ] **Step 5:** Commit `fix: adopt worktree holding promote target`.

### Task 10: Auto-rescue detached HEAD / dirty detached

**Files:**
- Modify: `scripts/supagit.py:1633-1660`
- Modify: `scripts/supagit_i18n.py` (new keys)
- Test: `scripts/test_supagit_sweep.py`

- [ ] **Step 1:** Failing tests: dirty detached → asks for manual stash; unreachable detached → tells `git switch -c`.
- [ ] **Step 2:** Run → manual instructions.
- [ ] **Step 3:** Auto `git switch -c supagit-rescue-<sha>` then commit/reposition; update copy to “I rescued HEAD as branch X”.
- [ ] **Step 4:** Green.
- [ ] **Step 5:** Commit `feat: auto-rescue detached HEAD into rescue branch`.

### Task 11: Fetch --prune + sequencer-state preflight

**Files:**
- Modify: `scripts/supagit.py:842-863` (`preflight_repo`)
- Modify: `scripts/supagit_inventory.py:174-181` (stale upstreams)
- Modify: `scripts/supagit_situation.py` (add `sequencer_state` detector)
- Test: `scripts/test_supagit_sweep.py`

- [ ] **Step 1:** Failing tests: stale `origin/work` after remote delete; repo in `MERGE_HEAD`/`REBASE_HEAD` at start.
- [ ] **Step 2:** Run → stale refs mislabel sync / sequencer ignored.
- [ ] **Step 3:** `git fetch --prune` at preflight; detect `.git/MERGE_HEAD`, `REBASE_HEAD`, `CHERRY_PICK_HEAD`; offer abort/continue in tutor before any mutation.
- [ ] **Step 4:** Green.
- [ ] **Step 5:** Commit `feat: fetch --prune and detect mid-merge/rebase at preflight`.

### Task 12: Secrets guard — exclude + .gitignore, not abort

**Files:**
- Modify: `scripts/supagit.py:909-926` (`_reject_sensitive_paths`)
- Modify: `scripts/supagit_sweep.py:563-571`
- Test: `scripts/test_supagit_sweep.py`

- [ ] **Step 1:** Failing test: dirty tree with `.env.local` → run aborts.
- [ ] **Step 2:** Run → fail.
- [ ] **Step 3:** Exclude sensitive paths from `git add`, append to `.gitignore` (confirm once), commit the rest; only abort if everything is sensitive.
- [ ] **Step 4:** Green.
- [ ] **Step 5:** Commit `feat: exclude secrets and gitignore them instead of aborting`.

---

## Phase 4 — GitHub / PR self-healing

### Task 13: GhClient auth ladder — login → refresh → status

**Files:**
- Modify: `scripts/supagit_sweep.py:344-391` (`ensure_ready`)
- Test: `scripts/test_supagit_sweep.py::GhClientTests`

- [ ] **Step 1:** Failing test: refresh fails → still tells user to run `gh auth login`.
- [ ] **Step 2:** Run → manual instruction.
- [ ] **Step 3:** On refresh failure and TTY, launch `gh auth login -h github.com` (web/device) once, then re-verify; only then fail.
- [ ] **Step 4:** Green.
- [ ] **Step 5:** Commit `feat: interactive gh auth login fallback in ensure_ready`.

### Task 14: Merge strategy ladder + mergeability polling

**Files:**
- Modify: `scripts/supagit_sweep.py:472-522` (`merge_pr`)
- Modify: `scripts/supagit_sweep.py:833-844` (CONFLICTING/UNKNOWN handling)
- Modify: `scripts/supagit.py:1252-1262` (`_promote_via_pr`)
- Test: `scripts/test_supagit_sweep.py`

- [ ] **Step 1:** Failing tests: `UNKNOWN` proceeds immediately; policy error always `--admin` first.
- [ ] **Step 2:** Run → flaky / always admin.
- [ ] **Step 3:** Ladder: `merge` → `--auto` → `--admin`; poll `pr_mergeable` (3×, backoff) when `UNKNOWN`; on `CONFLICTING`, rebase onto base and push before retry.
- [ ] **Step 4:** Green.
- [ ] **Step 5:** Commit `feat: merge ladder and mergeability polling`.

### Task 15: Rebase-conflict UX inside supagit

**Files:**
- Modify: `scripts/supagit_sweep.py:697-755` (`rebase_branch_onto`)
- Modify: `scripts/supagit_i18n.py`
- Test: `scripts/test_supagit_sweep.py`

- [ ] **Step 1:** Failing test: rebase conflict → abort + manual instructions.
- [ ] **Step 2:** Run → abort.
- [ ] **Step 3:** Keep rebase state, list conflicted files, open `$EDITOR`/tutor loop, `git add` + `rebase --continue` on user confirm; abort only on explicit cancel.
- [ ] **Step 4:** Green.
- [ ] **Step 5:** Commit `feat: guided rebase conflict resolution`.

---

## Phase 5 — Supabase / migrations hardening

### Task 16: Supabase preflight mirroring GhClient

**Files:**
- Modify: `scripts/supagit.py:842-863` (`preflight_repo`)
- Create: `scripts/supagit_supabase.py` (or extend `supagit_sweep.py` if it stays small)
- Test: `scripts/test_supagit_sweep.py` or new `test_supagit_supabase.py`

**Interfaces:**
- Produces: `ensure_supabase_ready(cli, *, dry_run) -> None`

- [ ] **Step 1:** Failing test: provider=supabase but CLI missing/not logged in → failure appears only at checkpoint.
- [ ] **Step 2:** Run → late failure.
- [ ] **Step 3:** `shutil.which("supabase")`, auth probe (`supabase projects list`), interactive `supabase login` once on TTY; tutor install hint if missing.
- [ ] **Step 4:** Green.
- [ ] **Step 5:** Commit `feat: supabase CLI auth preflight`.

### Task 17: Branch↔environment mapping that matches pipeline names

**Files:**
- Modify: `scripts/supagit.py:1304-1313` (`_backend_target_for_branch`)
- Modify: `scripts/supagit.py:313-362` (`_auto_create_config`)
- Test: `scripts/test_supagit_sweep.py`

- [ ] **Step 1:** Failing test: custom pipeline `["main","production"]` → no migrate for `production`.
- [ ] **Step 2:** Run → soft skip.
- [ ] **Step 3:** Init/auto-create keys `environments` by actual branch names; resolve by exact branch, never legacy `pre`/`prod` index guess; refuse soft-skip when provider=supabase and a destination lacks ref.
- [ ] **Step 4:** Green.
- [ ] **Step 5:** Commit `fix: map supabase environments to real pipeline branch names`.

### Task 18: Migration state verification before promote

**Files:**
- Modify: `scripts/supagit.py:1085-1111` (`database_checkpoint`)
- Modify: `scripts/supagit.py:1861-1869` (run loop)
- Test: `scripts/test_supagit_sweep.py`

- [ ] **Step 1:** Failing test: migrate destination succeeds but remote drift vs local migrations is not checked before promote.
- [ ] **Step 2:** Run → promote proceeds.
- [ ] **Step 3:** After push, compare local `supabase/migrations` filenames to remote list; block promote on mismatch; surface migrate lines in `render_execution_plan` via `plan_migrate_item`.
- [ ] **Step 4:** Green.
- [ ] **Step 5:** Commit `feat: verify migration state before promote`.

---

## Phase 6 — UX: infer defaults, remove expert prompts

### Task 19: Skip integrate/pipeline prompts when defaults are unambiguous

**Files:**
- Modify: `scripts/supagit.py:1393-1420`
- Modify: `scripts/supagit_menu.py`
- Test: `scripts/test_supagit_sweep.py::OrchestrationTests`

- [ ] **Step 1:** Failing test: single pending feature + single pipeline branch → still prompts twice.
- [ ] **Step 2:** Run → prompts.
- [ ] **Step 3:** If only one pending `[✓]`, Enter-only single confirm “Merge feature X into dev?”; if one pipeline branch, skip order prompt entirely.
- [ ] **Step 4:** Green.
- [ ] **Step 5:** Commit `feat: skip prompts when choice is unambiguous`.

### Task 20: `--yes` with inferred defaults

**Files:**
- Modify: `scripts/supagit.py` (`_require_noninteractive_selection`, `run_branch_menu`)
- Test: `scripts/test_supagit_sweep.py`

- [ ] **Step 1:** Failing test: `--yes` without `--integrate`/`--pipeline` fails even when defaults are obvious.
- [ ] **Step 2:** Run → `yes_need_flags` error.
- [ ] **Step 3:** Infer `default_integrate_names` + configured pipeline when flags absent; only require explicit flags when ambiguity exists.
- [ ] **Step 4:** Green.
- [ ] **Step 5:** Commit `feat: allow --yes with inferred integrate/pipeline defaults`.

---

## Self-Review

**Spec coverage:**
- Install/update resilience → Tasks 1–3
- db push before merges → Tasks 4–5
- Dirty launch worktree → Task 7
- `publish_then_ff` broken → Task 6
- Adopt promote-target worktree → Task 9
- Detached rescue → Task 10
- Stale refs / sequencer → Task 11
- Secrets abort → Task 12
- gh auth login missing → Task 13
- Merge ladder / UNKNOWN / CONFLICTING → Tasks 14–15
- Supabase CLI/auth/branch mapping/migration verify → Tasks 16–18
- Expert prompts / `--yes` friction → Tasks 19–20
- Empty/contained skip → Task 8

**Placeholder scan:** No TBD/TODO; every step names files/tests.

**Type consistency:** `Finding`, `PolicyClass`, `SweepResult` (existing), `GhClient`, `ensure_supabase_ready` are used consistently.

**Gaps I’m still flagging:** interactive `gh auth login` and `supabase login` need a TTY strategy for Cursor-launched shells; rebase-conflict editor loop needs a clear cancel path. Both are noted in their tasks.

---

**Plan complete and saved to `docs/superpowers/plans/2026-08-12-supagit-novice-chaos-resilience.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

**Which approach?**
