# Tasks: supagit lang / auto-init / self-update

- [x] Task 1: Lock confirm default Yes
  - Acceptance: `[Y/n]`; Enter proceeds; `n` aborts; no `[y/N]`
  - Verify: `python3 scripts/test_supagit.py -v`
  - Files: `scripts/supagit.py`, `scripts/test_supagit.py`

- [x] Task 2: i18n module + language resolve
  - Acceptance: `t(key)`, `--lang` / `SUPAGIT_LANG` / menu; `--yes` without lang fails
  - Verify: new unittest cases
  - Files: `scripts/supagit_i18n.py`, `scripts/supagit.py`, `scripts/test_supagit.py`, installer

- [x] Task 3: Wire catalogs into Pipeline/main user strings
  - Acceptance: confirm/prompt/status/ERROR/ABORTED/menu/init use `t`
  - Verify: suites green; spot-check Spanish keys exist for critical paths
  - Files: `scripts/supagit.py`, `scripts/supagit_menu.py`, `scripts/supagit_i18n.py`

- [x] Task 4: Auto-init missing `.supagit.json`
  - Acceptance: missing config → create via prompt/flags → continue; never overwrite
  - Verify: temp-dir unittest
  - Files: `scripts/supagit.py`, `scripts/test_supagit.py`

- [x] Task 5: Self-update from GitHub source-root
  - Acceptance: behind → pull+install+re-exec; current → noop; failure → ShipError
  - Verify: mocked unit tests; `SUPAGIT_SKIP_UPDATE` prevents loop
  - Files: `scripts/supagit_update.py`, `scripts/supagit.py`, tests, installer

- [x] Task 6: Docs + installer audit
  - Acceptance: README + agent skill document lang/auto-init/update; installer copies new modules
  - Verify: both suites pass; grep installer for new files
  - Files: `README.md`, `docs/supagit-agent-command.md`, `scripts/install-supagit-global.sh`
