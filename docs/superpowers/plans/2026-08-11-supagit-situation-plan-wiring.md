# Situation Plan Wiring (Section 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface Situation cures inside the cyan execution plan, fail closed on `blocked` findings before Confirm / `--yes` continue, and run the same preflight on the `--no-sweep` path in `Pipeline.run`.

**Architecture:** Keep measurement/classify in `supagit_situation.py`. Add pure helpers for blocked-error text and ordered plan cure lines. Extend `render_execution_plan` to accept an optional `Situation` and weave fast-forward cure steps in the design order (publish → feature ff → integrate → pipeline0 ff → promote). Pipeline builds Situation once, prints preflight, raises on blocked, then passes Situation into the plan renderer. **No phase reorder and no cure execution yet** (Section 3+).

**Tech Stack:** Python 3 stdlib, existing `unittest`, `supagit_i18n.t`.

**Spec:** `docs/superpowers/specs/2026-08-11-supagit-situation-resilience-design.md` (design item 2).

## Global Constraints

- Python 3 stdlib only — no new dependencies.
- No `stash`, force-push, auto-rebase, or `reset --hard` while dirty.
- Cyan = tutor context; plan Confirm remains the interactive gate (`force_confirm=True`).
- `--yes` still refuses `blocked` (never auto-heal diverge).
- Supabase hardening out of scope.
- Agent must not `git commit` / `git push` unless the user explicitly asks; commit steps below are for the human.

---

## File map

| File | Responsibility |
|------|----------------|
| `scripts/supagit_situation.py` | `format_blocked_error`, `plan_cure_lines`, fix `publish_only` preflight key |
| `scripts/supagit_menu.py` | `render_execution_plan(..., situation=None)` weaves cure lines |
| `scripts/supagit_i18n.py` | plan_ff / publish_only / blocked-error keys (en+es) |
| `scripts/supagit.py` | return Situation from preflight; raise on blocked; pass into plan; preflight on `--no-sweep` |
| `scripts/test_supagit_situation.py` | unit tests for blocked + plan cure lines |
| `scripts/test_supagit_sweep.py` / `test_supagit.py` | orchestration: plan includes ff; blocked raises; no_sweep preflight |

---

### Task 1: i18n keys for plan cures + blocked errors + publish_only

**Files:**
- Modify: `scripts/supagit_i18n.py`

**Keys (en + es):**
- `plan_ff_item`: `"Fast-forward {branch} to {upstream}"`
- `plan_ff_feature_item`: `"Fast-forward {branch} to {upstream} before integrating"`
- `situation_finding_publish_only`: dirty pipeline0 without behind
- `situation_error_diverged`: fail-closed body with `git fetch` + `git log --oneline --left-right {upstream}...{branch}` (placeholders: `branch`, `upstream`)
- `situation_error_dirty_feature`: instruct commit on feature first (placeholders: `branch`)

- [ ] **Step 1:** Add keys to both `en` and `es` dicts.
- [ ] **Step 2:** No test yet — Task 2 covers render.

---

### Task 2: Situation helpers — blocked error + plan cure lines

**Files:**
- Modify: `scripts/supagit_situation.py`
- Modify: `scripts/test_supagit_situation.py`

**Interfaces:**
- Produces: `format_blocked_error(finding: Finding, *, branch: str, upstream: str | None) -> str`
- Produces: `plan_cure_lines(situation: Situation, *, remote: str) -> tuple[str, ...]`  
  Ordered **extra** lines for SAFE_CURE only:
  - feature `ff_only` → `plan_ff_feature_item`
  - pipeline0 `ff_only` or `publish_then_ff` → `plan_ff_item` (ff part only; publish stays in menu plan)
  - `publish_only` / `info` → no extra cure line
- Fix `_FINDING_I18N` to map `publish_only`

- [ ] **Step 1: Failing tests**

```python
def test_format_blocked_diverged_includes_commands(self) -> None:
    f = SIT.Finding(SIT.PolicyClass.BLOCKED, "stop_diverged", SIT.SyncStatus.DIVERGED, False, "pipeline0")
    text = SIT.format_blocked_error(f, branch="dev", upstream="origin/dev")
    self.assertIn("git fetch", text)
    self.assertIn("origin/dev...dev", text)

def test_plan_cure_lines_orders_feature_then_pipeline0_ff(self) -> None:
    # situation with feature ff_only + pipeline0 publish_then_ff
    lines = SIT.plan_cure_lines(sit, remote="origin")
    self.assertEqual(len(lines), 2)
    self.assertIn("feature", lines[0].lower())
    self.assertIn("fast-forward", lines[1].lower())
```

- [ ] **Step 2: Implement until green**
- [ ] **Step 3: Human commit** (after Task 3–4 or per slice)

---

### Task 3: Weave Situation into `render_execution_plan`

**Files:**
- Modify: `scripts/supagit_menu.py`
- Modify: `scripts/test_supagit_sweep.py` (or menu tests)

**Behavior:**
```
header
→ publish (if remote)   # first when dirty/behind; always listed as today
→ for each integrate branch: optional feature ff cure line, then integrate item
→ else plan_none_integrate
→ pipeline0 ff cure line (if any)
→ promote pairs
```

Use `situation.features` / `situation.pipeline0` / `situation.findings` to match branches to cures. If `situation is None`, keep today’s plan (no ff lines) for backward-compatible call sites.

- [ ] **Step 1: Failing test** — with a Situation that has pipeline0 `behind_only`, plan text contains fast-forward and places it **after** integrate / none-integrate and **before** promote.
- [ ] **Step 2: Implement**
- [ ] **Step 3: Run** `SUPAGIT_SKIP_UPDATE=1 python3 -m unittest scripts.test_supagit_sweep.MenuRenderTests` (or equivalent)

---

### Task 4: Pipeline wiring — blocked raise, plan Situation, `--no-sweep` preflight

**Files:**
- Modify: `scripts/supagit.py`
- Modify: `scripts/test_supagit.py` / `scripts/test_supagit_sweep.py`

**Behavior:**
1. `_explain_situation_preflight` returns `Situation`.
2. After printing preflight, if any finding has `policy == BLOCKED`, raise `ShipError(format_blocked_error(...))` using branch/upstream from `pipeline0` / matching `features`.
3. Interactive `run_branch_menu`: pass returned Situation into `render_execution_plan`.
4. `Pipeline.run` `--no-sweep` path: after building selection, call `_explain_situation_preflight` (blocked still fails closed). Do **not** add a new plan Confirm for `--no-sweep` (unchanged UX gate).

- [ ] **Step 1: Failing tests** — blocked diverge raises; no_sweep path calls preflight; interactive plan explain includes ff when behind.
- [ ] **Step 2: Implement**
- [ ] **Step 3: Full suite**

```bash
SUPAGIT_SKIP_UPDATE=1 python3 -m unittest scripts.test_supagit scripts.test_supagit_sweep scripts.test_supagit_situation
```

---

### Task 5: Section 2 verification

- [ ] **Step 1:** Full unittest suite OK (command above).
- [ ] **Step 2:** Human dry-run smoke: behind clean `pipeline[0]` shows preflight + plan ff line before Confirm; diverged branch aborts with recovery commands.
- [ ] **Step 3:** Human opens PR from `work` → `main` (`gh pr merge --merge --admin` when ready).

---

## Spec coverage (Section 2 only)

| Spec item | Task |
|-----------|------|
| Cyan execution plan includes cures | Task 2–3 |
| Fail-closed blocked with actionable commands | Task 2, 4 |
| Preflight in `Pipeline.run` (`--no-sweep`) | Task 4 |
| `--dry-run` still measures + prints; no mutate | unchanged (print-only) |
| Phase reorder publish↔ff / execute cures | **Not Section 2** |

## Self-review notes

- Execution order of Pipeline phases stays `ff_sync` then `commit_and_publish` until Section 3; plan text already describes the *intended* order so Confirm matches the design.
- `publish_only` preflight gap from Section 1 is closed here.
