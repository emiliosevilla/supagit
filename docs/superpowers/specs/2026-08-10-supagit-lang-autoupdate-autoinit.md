# Spec: supagit UX — language, auto-init, GitHub self-update

## Objective

Make `supagit` usable by non-experts without dead-ends:

1. **Confirmations default to Yes** (`[Y/n]`, Enter = proceed) — already present in code; keep and lock with tests.
2. **Language selection** at start: English or Español; every user-facing string for that run uses the chosen language.
3. **Missing `.supagit.json`** auto-recovers via interactive init (or flags), then continues the pipeline.
4. **Self-update from GitHub** before any pipeline work: if the registered source is behind `origin/main` of `emiliosevilla/supagit`, pull ff-only, reinstall globally, and re-exec.

**User:** developers (often non-Git-experts) running the sweeper from a project checkout or worktree.

**Success:** a first-time or stale install can choose language, create missing config without a hard stop, stay on the latest published sweeper, and confirm steps with Enter = Yes — all messages in the chosen language.

## ASSUMPTIONS (confirmed by user “ok así”)

1. Confirm default Yes is already correct; verify no remaining `[y/N]` and keep tests green.
2. Language: menu `(1) English / (2) Español` each run; no persistence in `.supagit.json`. Override with `--lang en|es` or `SUPAGIT_LANG`. Required under `--yes` / non-TTY via flag or env.
3. Missing config: run init-like prompts (backend none/supabase), write `.supagit.json`, continue (do not exit).
4. Update: `git fetch` + compare to `origin/main` on registered `source-root` (repo `https://github.com/emiliosevilla/supagit.git`); if behind → `git pull --ff-only` + `scripts/install-supagit-global.sh` + re-exec. If update needed but network/pull/install fails → **fail-closed** (do not silently continue on known-stale).
5. Child git/gh/supabase stderr from tools stays as emitted by those tools (not translated). All **supagit-authored** strings are translated.
6. Python 3 stdlib only; no new third-party deps.

→ Correct now or we proceed with these.

## Tech Stack

- Python 3 (`scripts/supagit.py` + `scripts/supagit_*.py`)
- Shell installer / global launcher: `scripts/install-supagit-global.sh`
- Git + GitHub remote `origin` on source-root
- unittest

## Commands

```bash
# Tests
python3 scripts/test_supagit.py -v
python3 scripts/test_supagit_sweep.py -v
# or
cd scripts && python3 -m unittest test_supagit test_supagit_sweep -v

# Manual / dry-run
scripts/supagit --dry-run --lang en
scripts/supagit --dry-run --lang es
SUPAGIT_LANG=es scripts/supagit --dry-run --no-sweep --yes --pipeline main

# Reinstall global
scripts/install-supagit-global.sh
```

## Project Structure

```
scripts/supagit.py              → CLI, Pipeline, confirm/prompt, main orchestration
scripts/supagit_i18n.py         → NEW: catalogs en/es + t(key, **kwargs) + language resolve
scripts/supagit_update.py       → NEW: GitHub/source-root freshness check + pull + reinstall + re-exec helpers
scripts/supagit_inventory.py    → unchanged behavior (errors mapped via Pipeline i18n)
scripts/supagit_layout.py
scripts/supagit_menu.py
scripts/supagit_sweep.py
scripts/install-supagit-global.sh → install new modules; optional pre-Python fetch may stay in Python
scripts/test_supagit.py
scripts/test_supagit_sweep.py
docs/supagit-agent-command.md
README.md
docs/superpowers/specs/…       → this spec
```

## Code Style

Match existing `Pipeline` / dataclass / `ShipError` patterns:

```python
# Good: keyed messages, not string soup in call sites
print(t("missing_config", path=str(path)))

# Good: confirm stays fail-closed on explicit no
# prompt ends with [Y/n]; "" / y / yes → proceed; n / no → UserAborted
```

- Prefer a flat message catalog `dict[str, dict[str, str]]` with `{name}` format fields.
- Keep fail-closed; never force-push; never invent Supabase refs.
- New modules installed next to `supagit.py` with installer `cmp` staleness checks.

## Testing Strategy

- Framework: unittest (existing).
- Locations: `scripts/test_supagit.py`, `scripts/test_supagit_sweep.py` (or `test_supagit_i18n.py` if catalogs grow).
- Levels:
  - Unit: `t()` language selection; confirm empty = yes / `n` = abort; missing-config auto-init creates file (temp dir); update helpers: behind → needs_update True; up-to-date → False; fetch fail → SweepError/ShipError.
  - Regression: existing suites stay green.
- Do not require live GitHub in CI: mock `run_git` / subprocess for update tests.

## Boundaries

**Always:**
- Run both unit suites before considering done.
- Install new `supagit_*.py` modules via `install-supagit-global.sh` + cmp.
- Update README + `docs/supagit-agent-command.md` for `--lang`, auto-init, self-update.
- Fail-closed when self-update is required but cannot complete.

**Ask first:**
- Changing remote URL / default branch name away from `origin`/`main`.
- Persisting language into `.supagit.json`.
- Soft-warn-and-continue on failed updates.

**Never:**
- Force-push or `git reset --hard` of the user's project repo for updates (only ff-only pull of **source-root**).
- Overwrite an existing `.supagit.json`.
- Translate third-party tool stderr.
- Add non-stdlib dependencies.

## Success Criteria

1. **Confirm:** Every `confirm()` prompt shows `[Y/n]`; Enter proceeds; `n`/`no` aborts with exit 2. No `[y/N]` remains.
2. **Language:** Interactive start shows bilingual language menu; choosing 1 or 2 sets language for all subsequent **supagit** messages that run (including errors/aborts authored by us). `--lang` / `SUPAGIT_LANG` skip the menu. Under `--yes` without lang → clear `ShipError`.
3. **Catalog coverage:** User-facing strings in `Pipeline` / `main` / init / menu prompts / status / warnings / ABORTED / ERROR wrappers use `t(...)`. Dry-run and confirm summaries included.
4. **Auto-init:** Missing `.supagit.json` no longer hard-fails immediately; TTY prompts for backend (default none), writes config (refuses overwrite), continues. Non-TTY / `--yes`: requires `--backend none|supabase` (or existing `--backend` on init path) — if missing, fail closed with message telling how to pass it.
5. **Self-update:** Before pipeline (and before language? — see Open Questions resolution below): check source-root vs `origin/main`; if behind, ff-pull + install + `os.execv` re-run with same argv. If already current, continue. If check/update fails → ERROR exit 1.
6. **Installer:** New modules listed in install + launcher cmp/existence checks.
7. **Tests:** Both suites pass; new tests cover confirm default, i18n resolve, auto-init, update decision helpers.
8. **Docs:** README + agent skill mention language, auto-init, self-update.

## Ordered startup (target)

```
1. Parse argv (including --lang)
2. Self-update check (+ possible re-exec)   # English bootstrap messages OK for this phase OR bilingual fixed strings
3. Resolve language (flag/env/menu)
4. init command OR Pipeline.run
5. If missing config → auto-init in chosen language → continue
6. Rest of sweeper/pipeline
```

## Open Questions (resolved defaults)

| Question | Resolution |
|---|---|
| Self-update before or after language menu? | **Before**, so a stale binary updates first. Bootstrap strings for update may be bilingual fixed lines (`[supagit] Updating… / Actualizando…`) until language is chosen. |
| Non-TTY missing config | Require `--backend`; do not guess. |
| Source-root not a git clone of GitHub | Fail closed with message to re-run installer from a clone of `emiliosevilla/supagit`. |
| `supagit init` alone | Still supported; language menu applies; does not run self-update loop into pipeline. Self-update still runs at main() entry for all invocations. |

## Out of scope

- Full translation of git/gh/supabase output
- Language persistence
- Soft-continue on failed updates
- GUI / TUI beyond numbered menu
- Versioning via semver tags (use git tip of `main`)
