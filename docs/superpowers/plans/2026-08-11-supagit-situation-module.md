# Situation Module (Section 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a measured `Situation` model with sync classification, policy tagging, and cyan preflight rendering — the foundation for wave-1 Git/self-update resilience — without yet reordering Pipeline phases or curing branches.

**Architecture:** New stdlib module `scripts/supagit_situation.py` exposes immutable dataclasses + pure helpers that take injected git/`gh` callables. Classification encodes the approved policy table (`safe_cure` / `blocked` / `info`). Rendering produces tutor-cyan text via i18n keys. Section 1 stops at a thin optional hook that can print preflight; mutating cures are later sections.

**Tech Stack:** Python 3 stdlib, existing `unittest`, `supagit_i18n.t`, patterns from `supagit_inventory` / `supagit_sweep`.

**Spec:** `docs/superpowers/specs/2026-08-11-supagit-situation-resilience-design.md` (Section 1 approved).

## Global Constraints

- Python 3 stdlib only — no new dependencies.
- No `stash`, force-push, auto-rebase, or `reset --hard` while dirty (encode as `blocked` / never suggest those as automated cures).
- Do not call unsupported `gh pr create --json`.
- Cyan = tutor context; green Confirm is not required inside this module (Pipeline owns prompts).
- Supabase hardening is out of scope (deferred backlog).
- Agent must not `git commit` / `git push` for the human unless the user explicitly asks; plan commit steps are for the human or an authorized session.

---

## File map

| File | Responsibility |
|------|----------------|
| `scripts/supagit_situation.py` | Types, measure helpers, classify, render_preflight |
| `scripts/test_supagit_situation.py` | Unit tests (fake runners) |
| `scripts/supagit_i18n.py` | Preflight / sync / policy message keys (en+es) |
| `scripts/supagit.py` | Optional: call `render_preflight` after menu (print-only); no phase reorder in Section 1 |
| `scripts/install-supagit-global.sh` | Ensure new module is installed if installer lists scripts explicitly |

---

### Task 1: SyncStatus + classify_sync_counts

**Files:**
- Create: `scripts/supagit_situation.py`
- Create: `scripts/test_supagit_situation.py`

**Interfaces:**
- Produces: `SyncStatus` enum/str union; `classify_sync_counts(ahead: int, behind: int) -> SyncStatus`

- [ ] **Step 1: Write the failing test**

```python
# scripts/test_supagit_situation.py
import importlib.util
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

SPEC = importlib.util.spec_from_file_location("supagit_situation", SCRIPTS / "supagit_situation.py")
SIT = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(SIT)


class ClassifySyncTests(unittest.TestCase):
    def test_in_sync(self) -> None:
        self.assertEqual(SIT.classify_sync_counts(0, 0), SIT.SyncStatus.IN_SYNC)

    def test_ahead_only(self) -> None:
        self.assertEqual(SIT.classify_sync_counts(2, 0), SIT.SyncStatus.AHEAD_ONLY)

    def test_behind_only(self) -> None:
        self.assertEqual(SIT.classify_sync_counts(0, 3), SIT.SyncStatus.BEHIND_ONLY)

    def test_diverged(self) -> None:
        self.assertEqual(SIT.classify_sync_counts(1, 1), SIT.SyncStatus.DIVERGED)

    def test_negative_rejected(self) -> None:
        with self.assertRaises(ValueError):
            SIT.classify_sync_counts(-1, 0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `SUPAGIT_SKIP_UPDATE=1 python3 -m unittest scripts.test_supagit_situation.ClassifySyncTests -v`  
Expected: FAIL (module missing or `classify_sync_counts` missing)

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/supagit_situation.py
from __future__ import annotations

from enum import Enum


class SyncStatus(str, Enum):
    IN_SYNC = "in_sync"
    AHEAD_ONLY = "ahead_only"
    BEHIND_ONLY = "behind_only"
    DIVERGED = "diverged"
    NO_UPSTREAM = "no_upstream"


def classify_sync_counts(ahead: int, behind: int) -> SyncStatus:
    if ahead < 0 or behind < 0:
        raise ValueError(f"ahead/behind must be >= 0 (got {ahead}, {behind})")
    if ahead and behind:
        return SyncStatus.DIVERGED
    if ahead:
        return SyncStatus.AHEAD_ONLY
    if behind:
        return SyncStatus.BEHIND_ONLY
    return SyncStatus.IN_SYNC
```

- [ ] **Step 4: Run test to verify it passes**

Run: `SUPAGIT_SKIP_UPDATE=1 python3 -m unittest scripts.test_supagit_situation.ClassifySyncTests -v`  
Expected: PASS

- [ ] **Step 5: Commit** (human)

```bash
git add scripts/supagit_situation.py scripts/test_supagit_situation.py
git commit -m "Add SyncStatus classifier for Situation module."
```

---

### Task 2: PolicyClass + classify_finding

**Files:**
- Modify: `scripts/supagit_situation.py`
- Modify: `scripts/test_supagit_situation.py`

**Interfaces:**
- Consumes: `SyncStatus`
- Produces: `PolicyClass` (`SAFE_CURE` / `BLOCKED` / `INFO`); `Finding` dataclass; `classify_ref_finding(sync, *, dirty: bool, role: str) -> Finding`

Roles: `"pipeline0"` | `"feature"` | `"self_update"`.

Rules (encode exactly):
- `DIVERGED` → always `BLOCKED` (any role)
- `BEHIND_ONLY` + not dirty → `SAFE_CURE` (ff-only)
- `BEHIND_ONLY` or `AHEAD_ONLY` + dirty + role `pipeline0` → `SAFE_CURE` with cure id `publish_then_ff` (not ff-while-dirty)
- `BEHIND_ONLY` + dirty + role `feature` → `BLOCKED` until clean/commit on that feature (no stash)
- `IN_SYNC` → `INFO`
- `NO_UPSTREAM` + role feature needing push → `BLOCKED` or `INFO` per tests below (`BLOCKED` if role is feature and we require upstream for sync cures; `INFO` for pipeline0 local-only notes — use `INFO` for `NO_UPSTREAM` in Section 1)

- [ ] **Step 1: Write the failing test**

```python
class PolicyTests(unittest.TestCase):
    def test_diverged_blocked(self) -> None:
        f = SIT.classify_ref_finding(SIT.SyncStatus.DIVERGED, dirty=False, role="pipeline0")
        self.assertEqual(f.policy, SIT.PolicyClass.BLOCKED)
        self.assertEqual(f.cure_id, "stop_diverged")

    def test_behind_clean_safe_ff(self) -> None:
        f = SIT.classify_ref_finding(SIT.SyncStatus.BEHIND_ONLY, dirty=False, role="feature")
        self.assertEqual(f.policy, SIT.PolicyClass.SAFE_CURE)
        self.assertEqual(f.cure_id, "ff_only")

    def test_pipeline0_dirty_behind_publish_then_ff(self) -> None:
        f = SIT.classify_ref_finding(SIT.SyncStatus.BEHIND_ONLY, dirty=True, role="pipeline0")
        self.assertEqual(f.policy, SIT.PolicyClass.SAFE_CURE)
        self.assertEqual(f.cure_id, "publish_then_ff")

    def test_feature_dirty_behind_blocked(self) -> None:
        f = SIT.classify_ref_finding(SIT.SyncStatus.BEHIND_ONLY, dirty=True, role="feature")
        self.assertEqual(f.policy, SIT.PolicyClass.BLOCKED)
        self.assertEqual(f.cure_id, "stop_dirty_feature")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `SUPAGIT_SKIP_UPDATE=1 python3 -m unittest scripts.test_supagit_situation.PolicyTests -v`  
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
from dataclasses import dataclass
from enum import Enum


class PolicyClass(str, Enum):
    SAFE_CURE = "safe_cure"
    BLOCKED = "blocked"
    INFO = "info"


@dataclass(frozen=True)
class Finding:
    policy: PolicyClass
    cure_id: str
    sync: SyncStatus
    dirty: bool
    role: str


def classify_ref_finding(
    sync: SyncStatus, *, dirty: bool, role: str
) -> Finding:
    if sync is SyncStatus.DIVERGED:
        return Finding(PolicyClass.BLOCKED, "stop_diverged", sync, dirty, role)
    if sync is SyncStatus.BEHIND_ONLY and not dirty:
        return Finding(PolicyClass.SAFE_CURE, "ff_only", sync, dirty, role)
    if role == "pipeline0" and dirty and sync in {
        SyncStatus.BEHIND_ONLY,
        SyncStatus.AHEAD_ONLY,
        SyncStatus.IN_SYNC,
    }:
        # Dirty on first branch: publish path; if also behind, publish then ff.
        if sync is SyncStatus.BEHIND_ONLY:
            return Finding(PolicyClass.SAFE_CURE, "publish_then_ff", sync, dirty, role)
        return Finding(PolicyClass.SAFE_CURE, "publish_only", sync, dirty, role)
    if role == "feature" and dirty and sync is SyncStatus.BEHIND_ONLY:
        return Finding(PolicyClass.BLOCKED, "stop_dirty_feature", sync, dirty, role)
    if sync is SyncStatus.BEHIND_ONLY:
        return Finding(PolicyClass.SAFE_CURE, "ff_only", sync, dirty, role)
    return Finding(PolicyClass.INFO, "none", sync, dirty, role)
```

- [ ] **Step 4: Run tests**

Run: `SUPAGIT_SKIP_UPDATE=1 python3 -m unittest scripts.test_supagit_situation -v`  
Expected: PASS

- [ ] **Step 5: Commit** (human)

```bash
git add scripts/supagit_situation.py scripts/test_supagit_situation.py
git commit -m "Classify Situation findings into safe_cure vs blocked."
```

---

### Task 3: BranchSync + parse ahead/behind string

**Files:**
- Modify: `scripts/supagit_situation.py`
- Modify: `scripts/test_supagit_situation.py`

**Interfaces:**
- Produces: `parse_ahead_behind(text: str) -> tuple[int, int]` (strict; malformed → `SituationError`); `BranchSync` dataclass

- [ ] **Step 1: Write the failing test**

```python
class ParseAheadBehindTests(unittest.TestCase):
    def test_ok(self) -> None:
        self.assertEqual(SIT.parse_ahead_behind("2\t5"), (2, 5))

    def test_malformed_raises(self) -> None:
        with self.assertRaises(SIT.SituationError):
            SIT.parse_ahead_behind("nope")
```

- [ ] **Step 2: Run to verify fail** → implement → **Step 4: pass** → **Step 5: commit**

```python
class SituationError(RuntimeError):
    pass


def parse_ahead_behind(text: str) -> tuple[int, int]:
    parts = text.strip().split()
    if len(parts) != 2:
        raise SituationError(f"Malformed ahead/behind counts: {text!r}")
    try:
        return int(parts[0]), int(parts[1])
    except ValueError as exc:
        raise SituationError(f"Malformed ahead/behind counts: {text!r}") from exc


@dataclass(frozen=True)
class BranchSync:
    name: str
    upstream: str | None
    sync: SyncStatus
    ahead: int
    behind: int
    dirty: bool
    worktree_path: str | None
```

---

### Task 4: build_branch_sync via injected git runner

**Files:**
- Modify: `scripts/supagit_situation.py`
- Modify: `scripts/test_supagit_situation.py`

**Interfaces:**
- Consumes: `GitRunner = Callable[..., str]` compatible with sweep style
- Produces: `build_branch_sync(git, name, *, remote: str, role: str, worktree_path: str | None) -> tuple[BranchSync, Finding]`

Behavior:
1. `rev-parse --verify refs/heads/{name}` — missing → `SituationError`
2. Dirty: `status --porcelain` in worktree_path or cwd
3. Upstream: `rev-parse --abbrev-ref {name}@{upstream}` — fail → `NO_UPSTREAM`, finding INFO
4. Else `rev-list --left-right --count {upstream}...{name}` → parse → classify_sync → classify_ref_finding

- [ ] **Step 1: Failing test with fake git**

```python
class BuildBranchSyncTests(unittest.TestCase):
    def test_behind_clean_feature(self) -> None:
        # Counts from `upstream...name`: left=upstream-only (local behind),
        # right=local-only (local ahead) — same as Pipeline.validate_pipeline_head.
        def git(*args, **kwargs):
            cmd = list(args)
            if cmd[:2] == ("rev-parse", "--verify"):
                return "abc\n"
            if cmd[0] == "status":
                return ""
            if cmd[:2] == ("rev-parse", "--abbrev-ref"):
                return "origin/feature\n"
            if cmd[:3] == ("rev-list", "--left-right", "--count"):
                return "2\t0\n"
            raise AssertionError(cmd)

        sync, finding = SIT.build_branch_sync(
            git, "feature", remote="origin", role="feature", worktree_path="/wt"
        )
        self.assertEqual(sync.sync, SIT.SyncStatus.BEHIND_ONLY)
        self.assertEqual(finding.cure_id, "ff_only")
```

Document in code comment: counts from `upstream...name` use **left=upstream-only (behind for local)**, **right=local-only (ahead)** — same as `validate_pipeline_head`.

- [ ] **Steps 2–5:** fail → implement → pass → commit

---

### Task 5: Situation aggregate + render_preflight

**Files:**
- Modify: `scripts/supagit_situation.py`
- Modify: `scripts/supagit_i18n.py` (en+es keys)
- Modify: `scripts/test_supagit_situation.py`

**Interfaces:**
- Produces:
  - `@dataclass Situation`: `current_branch`, `dirty`, `pipeline0: BranchSync | None`, `features: tuple[BranchSync, ...]`, `findings: tuple[Finding, ...]`, `gh_ready: bool | None`, `self_update: SyncStatus | None`
  - `render_preflight(situation: Situation) -> str` (plain text; Pipeline wraps cyan)

i18n keys (minimum):
- `situation_preflight_header`
- `situation_finding_ff_only`
- `situation_finding_publish_then_ff`
- `situation_finding_stop_diverged`
- `situation_finding_stop_dirty_feature`
- `situation_finding_none` / ok line
- Spanish equivalents

- [ ] **Step 1: Failing render test**

```python
class RenderPreflightTests(unittest.TestCase):
    def setUp(self) -> None:
        import supagit_i18n
        supagit_i18n.set_lang("en")

    def test_lists_blocked_and_safe(self) -> None:
        findings = (
            SIT.Finding(SIT.PolicyClass.BLOCKED, "stop_diverged", SIT.SyncStatus.DIVERGED, False, "pipeline0"),
            SIT.Finding(SIT.PolicyClass.SAFE_CURE, "ff_only", SIT.SyncStatus.BEHIND_ONLY, False, "feature"),
        )
        sit = SIT.Situation(
            current_branch="dev",
            dirty=False,
            pipeline0=None,
            features=(),
            findings=findings,
            gh_ready=True,
            self_update=SIT.SyncStatus.IN_SYNC,
        )
        text = SIT.render_preflight(sit)
        self.assertIn("diverg", text.lower())
        self.assertIn("fast-forward", text.lower())
```

- [ ] **Steps 2–5:** implement keys + render → pass → commit

---

### Task 6: Thin Pipeline hook (print-only)

**Files:**
- Modify: `scripts/supagit.py` (`run_branch_menu` after selection / before plan, or start of apply path)
- Modify: `scripts/test_supagit_sweep.py` or `scripts/test_supagit.py` — assert `explain`/`print` receives preflight when Situation built
- Modify: `scripts/install-supagit-global.sh` if needed so `supagit_situation.py` is on the install path (installer copies repo scripts dir — verify)

**Behavior (Section 1 only):**
- After menu selection is known, build a **minimal** Situation for `pipeline[0]` + selected integrate branches (reuse inventory dirty flags where possible; call `build_branch_sync` with `self.git`).
- `self.explain(render_preflight(sit), ask_continue=False)` so cyan shows without extra Continue? (plan Confirm remains the gate).
- On `SituationError`, raise `ShipError`.
- **Do not** reorder ff/publish yet; **do not** auto-execute cures.

- [ ] **Step 1: Failing orchestration test** — mock `build_situation_for_selection` / patch render to a sentinel and assert it appears in explain messages during `run_branch_menu`.

- [ ] **Steps 2–5:** wire → pass full suites → commit

```bash
SUPAGIT_SKIP_UPDATE=1 python3 -m unittest scripts.test_supagit scripts.test_supagit_sweep scripts.test_supagit_situation
git add scripts/supagit.py scripts/supagit_situation.py scripts/supagit_i18n.py scripts/test_*.py scripts/install-supagit-global.sh
git commit -m "Show Situation preflight after sweeper menu selection."
```

---

### Task 7: Section 1 verification + docs pointer

- [ ] **Step 1: Run full verification**

```bash
SUPAGIT_SKIP_UPDATE=1 python3 -m unittest scripts.test_supagit scripts.test_supagit_sweep scripts.test_supagit_situation
```

Expected: OK

- [ ] **Step 2: Manual dry-run smoke** (human)

```bash
SUPAGIT_SKIP_UPDATE=1 scripts/supagit --dry-run --lang en
```

Expected: after menu answers, cyan preflight block appears before execution plan; no mutations.

- [ ] **Step 3: Confirm installer ships module**

```bash
grep -n situation scripts/install-supagit-global.sh || ls "$(git rev-parse --show-toplevel)/scripts/supagit_situation.py"
```

If installer copies whole `scripts/` via source-root, document that in the commit message; if it allowlists files, add `supagit_situation.py`.

- [ ] **Step 4: Commit docs if not already** (human)

```bash
git add docs/superpowers/specs/2026-08-11-supagit-situation-resilience-design.md docs/superpowers/plans/2026-08-11-supagit-situation-module.md
git commit -m "Document Situation resilience spec and Section 1 plan."
```

---

## Spec coverage (Section 1 only)

| Spec item | Task |
|-----------|------|
| SyncStatus / counts | Task 1, 3 |
| Policy table encode | Task 2 |
| BranchSync measure | Task 4 |
| Situation + preflight render | Task 5 |
| Preflight in flow (cyan, no mutate) | Task 6 |
| Deferred Supabase | Spec only — no task |
| Reorder publish/ff, feature ff execute, self-update diverge cure | **Not Section 1** — later plan |

## Self-review notes

- No TBD steps; cure **execution** intentionally omitted from Section 1.
- Ahead/behind tuple order documented to match existing Pipeline.
- i18n required before render tests that call `t()`.
