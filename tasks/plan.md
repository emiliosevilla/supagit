# Plan: supagit lang / auto-init / self-update

Spec: `docs/superpowers/specs/2026-08-10-supagit-lang-autoupdate-autoinit.md`

## Approach

1. Add `supagit_i18n.py` (catalogs + resolve + `t`).
2. Add `supagit_update.py` (source-root freshness vs `origin/main`, ff-pull, install, re-exec).
3. Wire `main()`: update → language → command/pipeline.
4. Replace missing-config hard-fail with auto-init continuation.
5. Route user-facing strings through `t(...)`.
6. Installer + docs.

Confirm `[Y/n]` is already correct — verify only.

## Dependency order

```
i18n module
  → language resolve in main
    → translate confirm/prompt/errors
      → auto-init (uses i18n)
update module → main entry (before language; bilingual bootstrap)
installer + docs (last)
```

## Risks

| Risk | Mitigation |
|---|---|
| Incomplete catalog leaves English orphans | Grep for hard-coded user strings; tests for key paths |
| Update re-exec loop | Env `SUPAGIT_SKIP_UPDATE=1` after successful reinstall once |
| Auto-init races | Refuse overwrite; `open(..., "x")` |
| Git write policy for agent | Human commits; agent leaves exact commands |

## Verification checkpoints

- After Tasks 1–2: i18n + confirm tests green
- After Tasks 3–4: auto-init + translated errors green
- After Tasks 5–6: update helpers + installer + full suites + docs
