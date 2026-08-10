# Spec: supagit tutor mode + novice-friendly sweeper menu

## Objective

Make interactive `supagit` understandable to a Git novice:

1. **Cyan = context / tutor explanations**; **green = where the user types** (`prompt` / `confirm`).
2. **Before every green prompt**, print a cyan explanation of what will happen if the user proceeds (“tutor git mode”).
3. Redesign the sweeper menu: two labeled blocks (independent worktrees / main pipeline branches), checks vs numbers, two prompts, then a cyan execution plan + green confirm.

**User:** developers who may not know Git jargon (`feature`, `contained`, `pipeline` tags).

**Success:** a first-time user can answer the sweeper with Enter for sensible defaults, understand each confirmation, and never confuse instructional text with the answer field.

## ASSUMPTIONS (approved in brainstorming)

1. Color rule **A**: cyan = help/context; green = input.
2. Menu layout **B** with renamed sections and **two prompts** (not one combined order line).
3. Worktrees use **checks** `[✓]`/`[ ]` (order irrelevant); pipeline uses **numbers** (order matters).
4. Independent work list is **C**: linked worktrees first, then other non-pipeline locals without worktree; single screen, separate sub-headings.
5. Contained branches (**A**): shown with note, **not** in Enter-default integrate set.
6. Defaults: integrate all eligible `[✓]` work; pipeline = configured order (dev/pre/prod or detected variants).
7. After selection: cyan explanatory numbered plan, then green `[Y/n]` / `[S/n]` confirm (Enter = yes).
8. Tutor rule applies to **all** interactive `confirm`/`prompt` call sites in `supagit` (not only the menu).
9. `--yes` / flags path unchanged (`--integrate`, `--pipeline`); no menu, no tutor prompts under `--yes` (explanations may still print for dry-run plan if useful, but no blocking confirm).
10. Python 3 stdlib only; respect existing `--color` / `--no-color` / `NO_COLOR`.

## Color contract

| Role | ANSI | Usage |
|------|------|--------|
| Tutor / context | `\033[36m` (cyan) | Lists, section headers, “what will happen”, execution plan |
| Input | `\033[32m` (green) | `prompt()` and `confirm()` text including `[Y/n]` / `[S/n]` |
| Warning / error | red (existing) | `warning`, `ERROR`, `ABORTED` |

No cyan on green input lines. No green on tutor blocks.

## Tutor API

Add on `Pipeline` (or thin helpers used by `Pipeline`):

- `explain(message: str) -> None` — print cyan (color-gated).
- `tutor_prompt(explanation: str, prompt_message: str) -> str` — `explain` then green `prompt`.
- `tutor_confirm(explanation: str, confirm_message: str) -> None` — `explain` then green `confirm`.

Under `--yes`, `confirm` remains a no-op. Under `--dry-run`, explanations
still print and **blocking confirms still wait** (green prompt, Enter = yes)
so the user can review the plan before the dry-run walk continues.

Every interactive question gets an i18n pair: `explain_*` + existing/short confirm/prompt key.

### Required tutor pairs (minimum)

| Flow | explain key | input |
|------|-------------|--------|
| Auto-init backend | `explain_backend` | `backend_prompt` |
| Commit message | `explain_commit_message` | `commit_message_prompt` |
| Commit+publish | `explain_commit_publish` | `confirm_commit_publish` |
| Publish existing | `explain_publish_existing` | `confirm_publish_existing` |
| Migrate | `explain_migrate` | `confirm_migrate` |
| Promote | `explain_promote` | `confirm_promote` |
| Cleanup | `explain_cleanup` | `confirm_cleanup` |
| Start pipeline | `explain_pipeline` | `confirm_pipeline` |
| Integrate worktrees | `explain_integrate` | `integrate_prompt` (rewritten) |
| Pipeline order | `explain_pipeline_order` | `pipeline_order_prompt` (rewritten) |
| Confirm plan | `explain_plan` (or the plan body itself is cyan) | `confirm_plan` |

## Sweeper menu UX

### Screen (cyan), one print before prompts

```
── Independent worktrees ── / ── Worktrees independientes ──
  [✓] feature/login    worktree: ../wt-login   (uncommitted changes)
  [✓] feature/ui       worktree: ../wt-ui
  [ ] hotfix           already included in {first}   # contained; not default

── Other local work branches (no worktree) ── / ── Otras ramas de trabajo (sin worktree) ──
  [✓] experiment

── Main local and remote repository branches ── / ── Ramas principales del repositorio local y remoto ──
  1. main
  2. pre
  3. prod
```

English / Spanish section titles via i18n. Prefer plain language over tags like `[pipeline, contained]`.

### Classification

- **Pipeline block:** `branch.is_pipeline`.
- **Independent worktrees block:** not pipeline, `has_worktree`, not main checkout-only noise if branch is pipeline (already excluded).
- **Other work block:** not pipeline, not `has_worktree`.
- **Default integrate (`[✓]`):** `default_integrate_names` — not pipeline and not `contained_in_first`.
- **Shown unchecked (`[ ]`):** not pipeline and `contained_in_first` (with plain note).

### Prompt 1 — integrate (green)

- Enter → all `[✓]` names (`default_integrate_names`).
- `none` / `ninguno` → empty integrate.
- Comma-separated **names** (not pipeline numbers) → those branches.
- Explicitly selecting a contained branch → `MenuError` with clear message (already included in first pipeline branch).
- Order of names irrelevant.

### Prompt 2 — pipeline order (green)

- Enter → configured / detected pipeline order (`default_pipeline`).
- Comma-separated numbers (1..N of pipeline block only) or names → reorder.
- Invalid number / unknown name → `MenuError`.

### Cyan plan + green confirm

After parsing, print a numbered cyan list of what will happen (integrate each selected → first pipeline branch via PR; then publish / migrate / promote steps at a high level for the chosen pipeline). Then green confirm “Continue?” / “¿Continuar?” with Enter = yes.

Remove the old English instructional lines from `render_branch_menu` that duplicated the green prompts (`Pipeline order (comma-separated…)` printed as static text).

## Parser / API changes

`supagit_menu.py`:

- Keep `MenuSelection(integrate, pipeline)`.
- Replace or extend `render_branch_menu` → `render_sweeper_menu(inventory, *, lang messages via caller or t())`.
- Prefer: menu module returns plain strings; colour applied by `Pipeline.explain`.
- Split parsing:
  - `parse_integrate_line(inventory, line) -> tuple[str, ...]`
  - `parse_pipeline_line(inventory, line, default_pipeline) -> tuple[str, ...]`
  - Or keep `parse_menu_responses` but **swap call order** in `run_branch_menu` to integrate first, then pipeline (today pipeline is prompted first — must change).
- `render_execution_plan(selection, inventory, branches_for_promotion) -> str` for cyan plan body.
- `selection_from_flags` unchanged for `--yes`.

`run_branch_menu` in `supagit.py`: print menu via `explain`/`print` cyan; `tutor_prompt` integrate; `tutor_prompt` pipeline; cyan plan; `tutor_confirm` plan.

## Non-goals

- Full TUI with arrow-key checkbox toggles.
- Persisting menu choices.
- Translating git/gh/supabase child stderr.
- Changing PR merge semantics.

## Testing

- Unit: menu classification, default checks exclude contained, integrate parse (`none`/`ninguno`/names), pipeline numbers scoped to pipeline block, contained explicit → error.
- Unit: `explain`/`tutor_confirm` use cyan then green when color forced.
- Regression: `test_supagit.py` + `test_supagit_sweep.py` green; `--yes` path still requires flags.
- Snapshot-style assert on rendered menu containing `[✓]`, section headers, and numbered pipeline only.

## Docs

- Update `README.md` and `docs/supagit-agent-command.md` briefly: cyan tutor, green answers, sweeper two-step, Enter defaults.

## Success criteria

1. No instructional sweeper lines printed in green; no answer prompts in cyan.
2. Every interactive confirm/prompt preceded by cyan explanation (except when skipped by `--yes`/`dry_run` confirm short-circuit).
3. Menu shows checks for work, numbers for pipeline; defaults match approved rules.
4. Plan cyan + confirm green after menu.
5. Both unit suites pass; installer unchanged unless new module file is added (prefer no new module; extend menu + i18n + Pipeline).

## Amendment (2026-08-10 — flexible checkout)

Prompt order remains **integrate first, then pipeline** (as above). After the
pipeline line is parsed, if `pipeline[0]` differs from the inventory's
`first_branch`, the inventory is rebuilt with that new base (configured
pipeline membership unchanged) and the integrate answer is re-validated
against it before the execution plan is rendered. This keeps `[✓]` defaults,
"already included in …" notes, and `error_contained_integrate` aligned with
the base the run will actually use.
