# Tutor Mode + Novice Sweeper Menu Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add cyan tutor explanations before every green interactive prompt, and redesign the sweeper menu for Git novices (checks for independent work, numbers for pipeline, two prompts, cyan plan + green confirm).

**Architecture:** Keep colour application in `Pipeline` (`explain` / `tutor_prompt` / `tutor_confirm`). Keep menu classification, rendering (plain text), and parsing in `supagit_menu.py`. All user-facing strings go through `supagit_i18n.t`. Interactive call sites in `supagit.py` switch to tutor helpers. No new third-party deps.

**Tech Stack:** Python 3 stdlib, existing unittest suites (`scripts/test_supagit.py`, `scripts/test_supagit_sweep.py`), ANSI colours via existing `colour_enabled` / `colour_text`.

## Global Constraints

- Cyan (`\033[36m`) = tutor/context only; green = input only; red = warnings/errors (existing).
- Before every interactive `confirm`/`prompt` (when not skipped by `--yes`/`dry_run` confirm short-circuit), print a cyan explanation.
- Sweeper: two blocks (independent worktrees + other local work with checks; main pipeline branches with numbers 1..N); integrate prompt first, then pipeline order; then cyan plan + green confirm.
- Enter defaults: all eligible `[✓]` integrate; pipeline = configured order; confirm Enter = yes (`[Y/n]` / `[S/n]`).
- Contained non-pipeline branches: shown `[ ]` with plain note; not in default integrate; explicit select → `MenuError`.
- Integrate answers use names / `none`/`ninguno` — not pipeline slot numbers.
- Pipeline answers use numbers scoped to the pipeline block only, or branch names.
- `--yes` still requires `--integrate` and `--pipeline` (or `--no-sweep`); no interactive menu.
- Python 3 stdlib only; respect `--color` / `--no-color` / `NO_COLOR`.
- Spec: `docs/superpowers/specs/2026-08-10-supagit-tutor-menu-design.md`
- Prefer single-line `git commit -m "..."` (no heredoc) if the environment allows git writes; otherwise print the exact commands for the human.

## File Structure

| File | Responsibility |
|------|----------------|
| `scripts/supagit.py` | `CYAN`, `explain`, `tutor_prompt`, `tutor_confirm`; wire all interactive sites; rewrite `run_branch_menu` order |
| `scripts/supagit_menu.py` | Classify branches, render menu text, parse integrate/pipeline, render execution plan text |
| `scripts/supagit_i18n.py` | New `explain_*` keys, rewritten integrate/pipeline prompts, menu section titles, plan lines, `ninguno` |
| `scripts/test_supagit.py` | Tutor colour tests |
| `scripts/test_supagit_sweep.py` | Menu render/parse/plan tests; update obsolete “number 4 = feature” case |
| `README.md`, `docs/supagit-agent-command.md` | Brief UX docs |

---

### Task 1: Cyan constant + tutor helpers on Pipeline

**Files:**
- Modify: `scripts/supagit.py` (colour constants near `GREEN`/`RED`; methods near `confirm`/`prompt`)
- Test: `scripts/test_supagit.py`

**Interfaces:**
- Consumes: existing `colour_enabled`, `colour_text`, `t`, `Options.color`, `confirm`, `prompt`
- Produces: `CYAN = "\033[36m"`; `Pipeline.explain(message: str) -> None`; `Pipeline.tutor_prompt(explanation: str, prompt_message: str) -> str`; `Pipeline.tutor_confirm(explanation: str, confirm_message: str) -> None`

- [ ] **Step 1: Write the failing tests**

Add to `scripts/test_supagit.py` (inside a class that sets lang `en` in `setUp` if needed):

```python
def test_explain_uses_cyan_when_color_forced(self) -> None:
    pipeline = MODULE.Pipeline.__new__(MODULE.Pipeline)
    pipeline.options = MODULE.Options(False, False, None, None, "always")
    with patch("builtins.print") as mocked_print:
        pipeline.explain("Tutor text")
    mocked_print.assert_called_once_with(
        f"{MODULE.CYAN}Tutor text{MODULE.RESET}"
    )

def test_tutor_confirm_prints_cyan_then_green_confirm(self) -> None:
    pipeline = MODULE.Pipeline.__new__(MODULE.Pipeline)
    pipeline.options = MODULE.Options(False, False, None, None, "always")
    with patch("builtins.print") as mocked_print, patch("builtins.input", return_value="") as mocked_input:
        pipeline.tutor_confirm("Will publish main.", "Continue?")
    mocked_print.assert_called_once_with(
        f"{MODULE.CYAN}Will publish main.{MODULE.RESET}"
    )
    prompt = mocked_input.call_args.args[0]
    self.assertTrue(prompt.startswith(MODULE.Pipeline.GREEN))
    self.assertIn("[Y/n]", prompt)
    self.assertIn("Continue?", prompt)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `SUPAGIT_SKIP_UPDATE=1 python3 scripts/test_supagit.py TestClassName.test_explain_uses_cyan_when_color_forced TestClassName.test_tutor_confirm_prints_cyan_then_green_confirm -v`  
(Replace `TestClassName` with the class you added them to, e.g. `I18nAndUpdateTests` or a new `TutorUiTests`.)

Expected: FAIL (`CYAN` / `explain` missing)

- [ ] **Step 3: Minimal implementation**

In `scripts/supagit.py`:

```python
CYAN = "\033[36m"
```

On `Pipeline` class (keep `GREEN = GREEN` class attrs; also expose `CYAN` on module and class if tests use `MODULE.CYAN`):

```python
def explain(self, message: str) -> None:
    print(colour_text(message, CYAN, self._colour_enabled()))

def tutor_prompt(self, explanation: str, prompt_message: str) -> str:
    self.explain(explanation)
    return self.prompt(prompt_message)

def tutor_confirm(self, explanation: str, confirm_message: str) -> None:
    self.explain(explanation)
    self.confirm(confirm_message)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: same as Step 2  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/supagit.py scripts/test_supagit.py
git commit -m "Add cyan tutor helpers before green prompts"
```

---

### Task 2: i18n keys for tutor + menu sections

**Files:**
- Modify: `scripts/supagit_i18n.py`
- Test: `scripts/test_supagit.py` (small key presence / Spanish spot-check)

**Interfaces:**
- Consumes: existing `_MESSAGES` / `t`
- Produces: keys listed below in both `en` and `es` catalogs

Required keys (exact names):

```
explain_backend
explain_commit_message
explain_commit_publish
explain_publish_existing
explain_migrate
explain_promote
explain_cleanup
explain_pipeline
explain_integrate
explain_pipeline_order
menu_section_worktrees
menu_section_other_work
menu_section_pipeline
menu_check_on
menu_check_off
menu_note_contained
menu_note_dirty
menu_note_worktree
integrate_prompt          # rewrite: ask which independent work to merge; Enter = all checked; none/ninguno = skip
pipeline_order_prompt     # rewrite: ask pipeline order; Enter = default {default}
confirm_plan              # keep short: Continue? / ¿Continuar?
plan_header
plan_integrate_item       # "Integrate {branch} into {base} (GitHub PR merge)"
plan_publish_item
plan_migrate_item
plan_promote_item
plan_none_integrate
integrate_none_tokens     # not needed as message; document none/ninguno in parser
error_contained_integrate # "Branch {branch} is already included in {base}; omit it or leave blank for defaults."
```

English copy must be novice-plain (no “features” as a product term; say “independent work branches” / “worktrees”). Spanish must match meaning.

- [ ] **Step 1: Write failing test**

```python
def test_tutor_i18n_keys_exist_in_en_and_es(self) -> None:
    keys = (
        "explain_integrate",
        "menu_section_worktrees",
        "menu_section_pipeline",
        "plan_header",
        "error_contained_integrate",
    )
    for lang in ("en", "es"):
        MODULE.supagit_i18n.set_lang(lang)
        for key in keys:
            text = MODULE.t(key, branch="x", base="dev", default="dev → pre")
            self.assertNotEqual(text, key, msg=f"missing {lang}:{key}")
```

- [ ] **Step 2: Run test — expect FAIL** (key returned unchanged)

- [ ] **Step 3: Add all keys to `en` and `es` in `supagit_i18n.py`**

Include format fields used above. Example EN:

```python
"explain_integrate": (
    "Optional: merge independent work into the first pipeline branch before publishing.\n"
    "Checked items [✓] are selected if you press Enter. Type none to skip."
),
"menu_section_worktrees": "── Independent worktrees ──",
"menu_section_other_work": "── Other local work branches (no worktree) ──",
"menu_section_pipeline": "── Main local and remote repository branches ──",
"menu_check_on": "[✓]",
"menu_check_off": "[ ]",
"menu_note_contained": "already included in {base}",
"integrate_prompt": (
    "Independent work to merge (names, Enter = all checked, none = skip): "
),
"pipeline_order_prompt": (
    "Pipeline order (numbers/names, Enter = {default}): "
),
"plan_header": "This is what I will do:",
"plan_integrate_item": "Integrate {branch} into {base} via a GitHub pull request",
"error_contained_integrate": (
    "Branch {branch} is already included in {base}; omit it or press Enter for defaults."
),
```

Mirror in `es` (use `ninguno` in integrate prompt text).

- [ ] **Step 4: Run test — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add scripts/supagit_i18n.py scripts/test_supagit.py
git commit -m "Add i18n strings for tutor mode and sweeper menu"
```

---

### Task 3: Menu classification + render (checks vs numbers)

**Files:**
- Modify: `scripts/supagit_menu.py`
- Test: `scripts/test_supagit_sweep.py`

**Interfaces:**
- Consumes: `RepoInventory`, `BranchInfo`, `t` (import from `supagit_i18n`)
- Produces:
  - `classify_menu_branches(inventory) -> tuple[list[BranchInfo], list[BranchInfo], list[BranchInfo]]`  
    returns `(worktrees, other_work, pipeline)` where worktrees = non-pipeline with `has_worktree`, other_work = non-pipeline without worktree, pipeline = `is_pipeline` preserving inventory order among pipeline members (or config order if easier: filter inventory.branches).
  - `render_sweeper_menu(inventory) -> str` plain text (no ANSI)
  - Deprecate/remove instructional English lines from old `render_branch_menu`; either replace body to call `render_sweeper_menu` or delete and update callers.

Render rules:
- Worktree / other_work lines: `{check} {name}` plus optional notes (`menu_note_worktree` with path, dirty, contained).
- `check` = `menu_check_on` if not `contained_in_first` else `menu_check_off` + contained note with `base=inventory.first_branch`.
- Pipeline lines: `{n}. {name}` starting at 1; optional ahead/behind in plain words if already available (keep short).
- No old tag soup `[pipeline, worktree, contained]`.

- [ ] **Step 1: Write failing tests**

```python
def test_render_sweeper_menu_uses_checks_and_pipeline_numbers(self) -> None:
    inv = _fake_inventory()
    text = supagit_menu.render_sweeper_menu(inv)
    self.assertIn("[✓]", text)
    self.assertIn("feature/x", text)
    self.assertIn("[ ]", text)  # contained "old"
    self.assertIn("old", text)
    self.assertRegex(text, r"(?m)^1\. dev")
    self.assertRegex(text, r"(?m)^2\. pre")
    self.assertRegex(text, r"(?m)^3\. prod")
    self.assertNotIn("Pipeline order (comma-separated", text)
    self.assertNotIn("[pipeline", text)

def test_classify_puts_worktree_before_other_work(self) -> None:
    inv = _fake_inventory()
    worktrees, other, pipeline = supagit_menu.classify_menu_branches(inv)
    self.assertEqual([b.name for b in worktrees], ["feature/x"])
    self.assertEqual([b.name for b in other], ["old"])
    self.assertEqual([b.name for b in pipeline], ["dev", "pre", "prod"])
```

- [ ] **Step 2: Run — expect FAIL**

Run: `SUPAGIT_SKIP_UPDATE=1 python3 scripts/test_supagit_sweep.py MenuTests.test_render_sweeper_menu_uses_checks_and_pipeline_numbers -v`

- [ ] **Step 3: Implement `classify_menu_branches` + `render_sweeper_menu`**

Use `t(...)` for section headers and notes. Keep `render_branch_menu` as alias to `render_sweeper_menu` temporarily if needed for one release cycle, or update caller in Task 5 only.

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add scripts/supagit_menu.py scripts/test_supagit_sweep.py
git commit -m "Render sweeper menu with checks and pipeline numbers"
```

---

### Task 4: Parse integrate (names) + pipeline (scoped numbers)

**Files:**
- Modify: `scripts/supagit_menu.py`
- Test: `scripts/test_supagit_sweep.py`

**Interfaces:**
- Consumes: `classify_menu_branches`, `default_integrate_names`, `MenuError`
- Produces:
  - `parse_integrate_line(inventory, line: str) -> tuple[str, ...]`
  - `parse_pipeline_line(inventory, line: str, default_pipeline: Sequence[str]) -> tuple[str, ...]`
  - Update `parse_menu_responses` to: integrate via `parse_integrate_line`, pipeline via `parse_pipeline_line` (argument order can stay `pipeline_line, integrate_line` for less churn, or swap — if kept, document that interactive caller passes integrate first into the integrate param).

Rules for `parse_integrate_line`:
- blank → `default_integrate_names(inventory)`
- `none` / `ninguno` (case-insensitive) → `()`
- else resolve comma tokens as **names only** (if token is digit → `MenuError` explaining numbers are only for pipeline order)
- if name is pipeline → `MenuError` (cannot integrate pipeline branch)
- if `contained_in_first` → `MenuError` using `t("error_contained_integrate", ...)`

Rules for `parse_pipeline_line`:
- blank → `tuple(default_pipeline)`
- tokens: digits map to **pipeline block only** (`classify_menu_branches(...)[2]`, 1-based); names resolve among inventory but must be pipeline members
- at least one branch required

Update obsolete test that used `integrate_line="4"`:

```python
def test_numbers_reorder_pipeline_and_pick_features(self) -> None:
    inv = _fake_inventory()
    selection = supagit_menu.parse_menu_responses(
        inv,
        pipeline_line="1,3,2",
        integrate_line="feature/x",
        default_pipeline=("dev", "pre", "prod"),
    )
    self.assertEqual(selection.pipeline, ("dev", "prod", "pre"))
    self.assertEqual(selection.integrate, ("feature/x",))
```

Add:

```python
def test_integrate_rejects_digit_token(self) -> None:
    inv = _fake_inventory()
    with self.assertRaises(supagit_menu.MenuError):
        supagit_menu.parse_integrate_line(inv, "4")

def test_integrate_rejects_contained_explicit(self) -> None:
    inv = _fake_inventory()
    with self.assertRaises(supagit_menu.MenuError):
        supagit_menu.parse_integrate_line(inv, "old")

def test_integrate_ninguno(self) -> None:
    inv = _fake_inventory()
    self.assertEqual(supagit_menu.parse_integrate_line(inv, "ninguno"), ())

def test_pipeline_number_scoped_to_pipeline_block(self) -> None:
    inv = _fake_inventory()
    # 1 = first pipeline branch (dev), not feature/x
    self.assertEqual(
        supagit_menu.parse_pipeline_line(inv, "1,2", ("dev", "pre", "prod")),
        ("dev", "pre"),
    )
```

- [ ] **Step 1: Write/update failing tests** (above)
- [ ] **Step 2: Run MenuTests — expect FAIL on new behaviors**
- [ ] **Step 3: Implement parsers; fix `parse_menu_responses`**
- [ ] **Step 4: Run full MenuTests — PASS**
- [ ] **Step 5: Commit**

```bash
git add scripts/supagit_menu.py scripts/test_supagit_sweep.py
git commit -m "Parse integrate by name and pipeline numbers by block"
```

---

### Task 5: Execution plan renderer + wire `run_branch_menu`

**Files:**
- Modify: `scripts/supagit_menu.py` (`render_execution_plan`)
- Modify: `scripts/supagit.py` (`run_branch_menu`)
- Test: `scripts/test_supagit_sweep.py`

**Interfaces:**
- Produces: `render_execution_plan(selection: MenuSelection, *, first_branch: str | None = None) -> str`
  - Header `t("plan_header")`
  - One line per integrate: `t("plan_integrate_item", branch=..., base=selection.pipeline[0])`
  - If no integrate: `t("plan_none_integrate")`
  - Then high-level promote steps: for each adjacent pair `t("plan_promote_item", source=..., target=...)`; optional publish line for first branch
- `run_branch_menu`:
  1. `--yes` → `selection_from_flags` (unchanged)
  2. else: `self.explain(render_sweeper_menu(inventory))`
  3. `integrate_line = self.tutor_prompt(t("explain_integrate"), t("integrate_prompt"))`
  4. `pipeline_line = self.tutor_prompt(t("explain_pipeline_order"), t("pipeline_order_prompt", default=...))`
  5. parse with `parse_integrate_line` + `parse_pipeline_line` (or `parse_menu_responses`)
  6. `self.explain(render_execution_plan(selection))`
  7. `self.tutor_confirm("", t("confirm_plan"))` — if explanation empty, `tutor_confirm` should skip blank explain OR pass a short `t("explain_plan")` like “Confirm to start this plan.” Prefer non-empty `explain_plan`.

Add i18n `explain_plan` if not already in Task 2.

- [ ] **Step 1: Failing test for plan text**

```python
def test_render_execution_plan_lists_integrates(self) -> None:
    selection = MenuSelection(integrate=("feature/x",), pipeline=("dev", "pre", "prod"))
    text = supagit_menu.render_execution_plan(selection)
    self.assertIn("feature/x", text)
    self.assertIn("dev", text)
```

- [ ] **Step 2: Run — FAIL**
- [ ] **Step 3: Implement renderer + rewrite `run_branch_menu`**
- [ ] **Step 4: Run MenuTests + a quick dry orchestration if any — PASS**
- [ ] **Step 5: Commit**

```bash
git add scripts/supagit_menu.py scripts/supagit.py scripts/test_supagit_sweep.py scripts/supagit_i18n.py
git commit -m "Wire tutor sweeper menu with cyan plan confirmation"
```

---

### Task 6: Tutor-wrap remaining confirm/prompt call sites

**Files:**
- Modify: `scripts/supagit.py` (all interactive sites listed below)
- Test: `scripts/test_supagit.py` (spot-check one migrate/publish path uses print+input order if easy; otherwise rely on existing confirm tests + manual checklist)

Replace:

| Location | New call |
|----------|----------|
| `_auto_create_config` backend `prompt` | `tutor_prompt(t("explain_backend"), t("backend_prompt"))` |
| `_commit_message` | `tutor_prompt(t("explain_commit_message"), t("commit_message_prompt", ...))` |
| publish commit confirm | `tutor_confirm(t("explain_commit_publish", ...), t("confirm_commit_publish", ...))` |
| publish existing | `tutor_confirm(t("explain_publish_existing", ...), t("confirm_publish_existing", ...))` |
| migrate | `tutor_confirm(t("explain_migrate", ...), t("confirm_migrate", ...))` |
| promote | `tutor_confirm(t("explain_promote", ...), t("confirm_promote", ...))` |
| cleanup | `tutor_confirm(t("explain_cleanup"), t("confirm_cleanup"))` after cyan candidates list (candidates can stay plain or cyan via `explain`) |
| final pipeline confirm | `tutor_confirm(t("explain_pipeline", chain=...), t("confirm_pipeline", ...))` |

Also update `initialise_project` prompts if they use `init_prompt` without tutor — either add cyan there with `colour_text(..., CYAN)` before `init_prompt`, or route through a small shared helper. Same rule: cyan then green.

- [ ] **Step 1: Grep for remaining bare confirm/prompt**

Run: `rg "self\\.(confirm|prompt)\\(|init_prompt\\(" scripts/supagit.py`

Expected after this task: only implementations of `confirm`/`prompt` themselves, plus `tutor_*` wrappers calling them.

- [ ] **Step 2: Apply replacements + any missing i18n explain strings with format fields**
- [ ] **Step 3: Run both suites**

```bash
SUPAGIT_SKIP_UPDATE=1 python3 scripts/test_supagit.py -v
SUPAGIT_SKIP_UPDATE=1 python3 scripts/test_supagit_sweep.py -v
```

Expected: all PASS (sweep tests need full permissions if sandbox blocks `git init`)

- [ ] **Step 4: Commit**

```bash
git add scripts/supagit.py scripts/supagit_i18n.py scripts/test_supagit.py
git commit -m "Apply tutor explanations to all interactive prompts"
```

---

### Task 7: Docs + final verification

**Files:**
- Modify: `README.md`, `docs/supagit-agent-command.md`
- Optionally: one line in `docs/superpowers/specs/2026-08-10-supagit-tutor-menu-design.md` status “implemented” only if you track that — skip unless useful

Docs bullets:
- Cyan = explanation; green = your answer
- Sweeper: checks for independent work (Enter = all checked), numbers for pipeline order
- Plan printed in cyan, then confirm

- [ ] **Step 1: Update README + agent command**
- [ ] **Step 2: Run both unit suites again — PASS**
- [ ] **Step 3: Manual smoke (human)**

```bash
SUPAGIT_SKIP_UPDATE=1 scripts/supagit --dry-run --lang es
```

Expect: cyan menu with checks/numbers; integrate prompt then pipeline; cyan plan; green confirm. Enter through defaults should not crash in dry-run.

- [ ] **Step 4: Commit**

```bash
git add README.md docs/supagit-agent-command.md
git commit -m "Document tutor mode and redesigned sweeper menu"
```

---

## Self-review (plan vs spec)

| Spec requirement | Task |
|------------------|------|
| Cyan/green contract | 1, 6 |
| Tutor before every interactive prompt | 1, 6 |
| Menu sections + checks + numbers | 3 |
| Contained shown unchecked, not default | 3, 4 |
| Two prompts integrate then pipeline | 5 |
| Defaults Enter | 4 |
| Cyan plan + green confirm | 5 |
| `--yes` flags unchanged | 5 |
| i18n en/es | 2 |
| Tests both suites | 4, 6, 7 |
| Docs | 7 |
| No TUI / no new deps | Global constraints |

No TBD placeholders. Parser change: integrate no longer accepts unified-list index `4` — tests updated in Task 4.
