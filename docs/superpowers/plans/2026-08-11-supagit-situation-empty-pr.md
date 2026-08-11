# Situation Empty-PR Preflight (Section 6) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fail closed **before** `gh pr create` when `head` has no commits not already in `base` (empty integrate/promote PR), with a clear i18n message. Reuse of an already-open PR stays unchanged.

**Architecture:** Add `assert_commits_for_pr(run_git, *, head, base, remote, cwd, dry_run)` in `supagit_sweep.py`: fetch `remote/base`, compute `rev-list --count {remote}/{base}..{head}` (fallback to local `base` if remote ref missing), raise `SweepError` when count is 0. Call it from `integrate_branch` only when `find_open_pr` returns `None`, and from the promote path before `create_promote_pr`. Improve the existing `contained_in_first` error to the same i18n key family.

**Tech Stack:** Python 3 stdlib, `supagit_i18n.t`, `unittest`.

**Spec:** `docs/superpowers/specs/2026-08-11-supagit-situation-resilience-design.md` (item 6).

## Global Constraints

- Do not call unsupported `gh pr create --json`.
- Never invent commits; only refuse empty creates.
- Agent must not `git commit` / `git push` unless the user explicitly asks.

---

## File map

| File | Responsibility |
|------|----------------|
| `scripts/supagit_sweep.py` | `assert_commits_for_pr`; wire into integrate (+ promote helper if clean) |
| `scripts/supagit.py` | Call assert before `create_promote_pr` if not already inside GhClient |
| `scripts/supagit_i18n.py` | `error_empty_pr` / `error_nothing_to_integrate` en+es |
| `scripts/test_supagit_sweep.py` | Empty create blocked; nonempty / open-PR reuse still OK |

---

### Task 1: i18n keys

- `error_empty_pr`: `"No commits to integrate from {head} into {base} (empty PR). Omit this branch or add commits first."`
- Optionally unify contained message: `error_nothing_to_integrate` same idea with contained note.

- [ ] Add en + es.

---

### Task 2: `assert_commits_for_pr`

```python
def assert_commits_for_pr(
    run_git: GitRunner,
    *,
    head: str,
    base: str,
    remote: str,
    cwd: Path,
    dry_run: bool,
) -> int:
    """Return commit count head is ahead of base; raise SweepError if zero."""
```

Steps inside:
1. Try fetch `refs/heads/{base}:refs/remotes/{remote}/{base}` (ignore dry_run for fetch? Prefer fetch even in dry_run for accurate measure; if fetch fails and local `base` exists, use local).
2. Choose `base_ref = remote/base` if `rev-parse --verify` works else `base`.
3. `count = int(run_git("rev-list", "--count", f"{base_ref}..{head}", cwd=cwd))`
4. If `count == 0`: raise `SweepError(t("error_empty_pr", head=head, base=base))`
5. Return count.

- [ ] Failing unit tests with fake git.
- [ ] Implement.

---

### Task 3: Wire into integrate + promote

**integrate_branch:** after push, `find_open_pr`; if `None`, `assert_commits_for_pr(...)` then `create_pr`.

**contained_in_first:** raise `SweepError(t("error_nothing_to_integrate", branch=branch, base=base))` (pass base into message — already have `base` param).

**promote:** in `supagit.py` before `create_promote_pr`, call assert with main checkout cwd (`self.root`), head=`source`, base=`target`.

- [ ] Tests: empty integrate never calls create_pr; open PR skips assert/create.
- [ ] Full suite green.

---

### Task 4: Verification

```bash
SUPAGIT_SKIP_UPDATE=1 python3 -m unittest scripts.test_supagit scripts.test_supagit_sweep scripts.test_supagit_situation
```

Human PR from `work` → `main`; merge with **real** PR number.

---

## Spec coverage (Section 6 only)

| Spec item | Task |
|-----------|------|
| Empty / no commits → blocked before `gh pr create` | Task 2–3 |
| Contained ancestor case | Task 3 i18n |
| Docs / skill + Supabase backlog | **Section 7** |

## Self-review notes

- Open PR reuse must not require a positive commit count check (PR may already exist).
- Dry-run should still measure and refuse empty creates so the plan Confirm is honest.
