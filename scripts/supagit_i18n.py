#!/usr/bin/env python3
"""Language catalogs and helpers for supagit user-facing text."""

from __future__ import annotations

import os
import sys
from typing import Callable

SUPPORTED = ("en", "es")

_MESSAGES: dict[str, dict[str, str]] = {
    "en": {
        "lang_menu": "Language / Idioma:\n  (1) English\n  (2) Español\nChoice [1/2]: ",
        "lang_required_yes": "With --yes (or non-TTY), provide --lang en|es or set SUPAGIT_LANG.",
        "lang_invalid": "Language must be 'en' or 'es' (got {value!r}).",
        "aborted": "ABORTED: {detail}",
        "error": "ERROR: {detail}",
        "aborted_interrupt": "ABORTED: user interruption.",
        "user_aborted": "Operation cancelled by the user.",
        "confirm_suffix": " [Y/n] ",
        "confirm_continue": "Continue?",
        "warning": "WARNING: {detail}",
        "missing_config_creating": "Missing configuration file {path}; creating it now.",
        "missing_config_need_backend": (
            "Missing configuration file {path}. With --yes or non-TTY, pass --backend none|supabase."
        ),
        "backend_prompt": "Backend [none/supabase] (none): ",
        "backend_invalid": "Backend must be 'none' or 'supabase'.",
        "created_config": "Created project configuration: {path}",
        "commit_message_prompt": "Commit message for {branch} [{default}]: ",
        "commit_message_yes": "With --yes, provide --message/-m for the initial {branch} commit.",
        "pipeline_order_prompt": "Order? Enter = {default}: ",
        "integrate_prompt": (
            "Which features? Enter = pending [✓], or numbers / 0 to skip: "
        ),
        "confirm_merge_single": "Merge feature {branch} into {base}?",
        "confirm_plan": "Run these steps?",
        "explain_backend": (
            "Supagit needs a project configuration file. "
            "Choose whether this project uses Supabase for database migrations."
        ),
        "explain_commit_message": (
            "You have local changes to save. "
            "A commit message describes what changed; it stays in the Git history."
        ),
        "explain_commit_publish": (
            "This will save all current changes on {branch} as a commit "
            "and upload them to {remote}."
        ),
        "explain_publish_existing": (
            "Your local {branch} has commits that are not on {remote} yet. "
            "This will upload them without creating a new commit."
        ),
        "explain_migrate": (
            "This applies pending database schema changes to {label} (project {ref})."
        ),
        "error_migrate_no_target": (
            "No database migration target configured for branch {branch}; "
            "aborting before any code merge."
        ),
        "error_database_checkpoint": (
            "Database checkpoint for {label} failed; aborting before any code merge. "
            "Detail: {detail}"
        ),
        "error_database_checkpoint_stale": (
            "The post-migration check does not confirm that {label} is up to date; "
            "aborting before any code merge."
        ),
        "error_migration_state_mismatch": (
            "Remote migrations for {label} do not match local supabase/migrations; "
            "aborting before any code merge. Local-only: {local_only}. "
            "Remote-only: {remote_only}."
        ),
        "error_supabase_env_missing": (
            "Environment variable {env_name} for Supabase {role} is not set. Supagit reads "
            "the variable named in .supagit.json; VITE_SUPABASE_* is not a substitute "
            "unless configured explicitly. Set it before rerunning, for example: "
            "export {env_name}=your-project-ref, or add {env_name}=your-project-ref to .env.local."
        ),
        "explain_promote": (
            "This merges {source} into {target} on the remote and publishes {target}."
        ),
        "explain_promote_direct": (
            "This merges {source} into {target} locally and pushes {target} ({detail})."
        ),
        "explain_promote_pr": (
            "GitHub protects {target} ({visibility}): I will open or reuse a pull request "
            "from {source} into {target} and merge it with administrator merge so branch "
            "rules do not block the release."
        ),
        "promote_gate_summary": (
            "GitHub {owner}/{repo} is {visibility}; updating {branch} uses {mode}."
        ),
        "promote_gate_non_github": "remote is not GitHub",
        "promote_mode_pr": "a pull request (branch rules require it)",
        "promote_mode_direct": "a direct merge and push",
        "promote_pr_created": "Opened pull request #{number}: {source} → {target}.",
        "promote_pr_reused": "Reusing open pull request #{number}: {source} → {target}.",
        "error_promote_pr_needs_approval": (
            "Pull request #{number} ({source} → {target}) could not be merged automatically. "
            "Approve it as code owner (or satisfy the branch rules), then re-run supagit."
        ),
        "error_promote_pr_merge_failed": (
            "Could not merge pull request #{number} ({source} → {target}) after retrying "
            "authentication refresh and administrator/auto/plain merge fallbacks. Check "
            "`gh auth status` "
            "and repository permissions, then re-run supagit."
        ),
        "error_gh_missing": (
            "GitHub CLI (gh) is not installed or not on PATH. Install it: {command}"
        ),
        "error_gh_not_authenticated": (
            "GitHub CLI (gh) is not authenticated and the failure is not a stale token: {detail}"
        ),
        "error_gh_refresh_failed": (
            "Tried to refresh the expired GitHub token with `gh auth refresh -h github.com`, "
            "but it failed: {detail}. No interactive terminal is available to complete "
            "`gh auth login`, so supagit cannot recover automatically."
        ),
        "error_gh_login_failed": (
            "Tried to refresh the GitHub token (`gh auth refresh`) and then launch "
            "`gh auth login -h github.com`, but login failed: {detail} "
            "(refresh error was: {refresh_detail})."
        ),
        "error_gh_still_unauthenticated": (
            "GitHub CLI is still not authenticated after refresh/login recovery: {detail}."
        ),
        "error_supabase_missing": (
            "Supabase CLI is not installed or not on PATH. Install it: {command}"
        ),
        "error_supabase_not_authenticated": (
            "Supabase CLI is not ready and the failure does not look like a missing login: {detail}"
        ),
        "error_supabase_login_unavailable": (
            "Supabase CLI auth probe (`supabase projects list`) failed: {detail}. "
            "No interactive terminal is available to complete `supabase login`, "
            "so supagit cannot recover automatically."
        ),
        "error_supabase_login_failed": (
            "Tried `supabase login` after an auth probe failure, but login failed: {detail} "
            "(probe error was: {probe_detail})."
        ),
        "error_supabase_still_unauthenticated": (
            "Supabase CLI is still not authenticated after login recovery: {detail}."
        ),
        "explain_cleanup": (
            "Optional step: remove worktrees and branches that were already merged "
            "and are safe to delete."
        ),
        "explain_pipeline": (
            "This runs the full release pipeline through: {chain}."
        ),
        "explain_integrate": (
            "Merge feature branches into {base} with a pull request.\n"
            "[✓] = selected if you press Enter. Already-in-{base} stays [✓] but is skipped."
        ),
        "explain_integrate_single": (
            "Only one pending feature to merge into {base} with a pull request: {branch}."
        ),
        "explain_pipeline_order": (
            "Promotion path for this run (numbers from the pipeline list above)."
        ),
        "explain_integrate_none": "No feature branches to merge into {base}.",
        "explain_pipeline_single": "Pipeline for this run: {branch}.",
        "explain_plan": "Review the plan above.",
        "menu_section_worktrees": "── Feature branches (worktrees) ──",
        "menu_section_other_work": "── Feature branches (local only) ──",
        "menu_section_pipeline": "── Release pipeline ──",
        "menu_section_work_empty": "(none — nothing to merge into {base})",
        "menu_check_on": "[✓]",
        "menu_check_off": "[ ]",
        "menu_note_contained": "already in {base}",
        "menu_note_dirty": "(uncommitted changes)",
        "menu_note_worktree": "worktree: {path}",
        "plan_header": "This is what I will do:",
        "plan_integrate_item": "Integrate {branch} into {base} via a GitHub pull request",
        "plan_publish_item": "Publish {branch} to {remote}",
        "plan_ff_item": "Fast-forward {branch} to {upstream}",
        "plan_ff_feature_item": "Fast-forward {branch} to {upstream} before integrating",
        "plan_commit_feature_item": "Commit local changes on {branch}",
        "plan_migrate_item": "Apply pending migrations to {label} ({ref})",
        "plan_promote_item": "Merge {source} into {target} and publish {target}",
        "plan_none_integrate": "No feature branches to integrate.",
        "error_ff_dirty": (
            "Refusing fast-forward of {branch}: the worktree has uncommitted changes. "
            "Commit and publish them first (supagit publish phase), then re-run. "
            "supagit will not stash or reset --hard while dirty."
        ),
        "publish_defer_behind": (
            "Local {branch} is behind {remote}/{branch} with a clean worktree; "
            "fast-forward sync will bring it up to date next."
        ),
        "publish_skip_push_behind": (
            "Committed local changes on {branch}, but it is still behind "
            "{remote}/{branch} (or has diverged). Skipping push; sync comes next."
        ),
        "publish_rebase_behind": (
            "Committed local changes on {branch}; rebasing onto "
            "{remote}/{branch} before publishing."
        ),
        "error_contained_integrate": (
            "Branch {branch} is already included in {base}; it needs no new pull request. "
            "Omit it, press Enter for defaults, or type 0/none to skip all work branches."
        ),
        "error_nothing_to_integrate": (
            "Branch {branch} is already contained in {base}; nothing to integrate."
        ),
        "note_nothing_to_merge": (
            "Nothing to merge: {branch} is already contained in {base}."
        ),
        "already merged": "already merged",
        "error_empty_pr": (
            "No commits to put in a pull request from {head} into {base} "
            "({base_ref}..{head} is empty). Omit this branch or add commits first."
        ),
        "error_dirty_pipeline_with_integrate": (
            "{pipeline} has uncommitted changes while feature branch(es) "
            "({features}) will integrate via pull request. Commit on a feature "
            "branch first (run supagit from that branch), then integrate — "
            "committing on {pipeline} first causes merge conflicts."
        ),
        "error_rebase_conflict": (
            "Rebase of {branch} onto {base_ref} could not finish after conflict "
            "resolution. Re-run supagit to try again."
        ),
        "explain_rebase_conflict": (
            "Rebase of {branch} onto {base_ref} stopped with conflicts in:\n"
            "{files}\n"
            "I will open your editor on those files. Resolve the conflict markers, "
            "save, then confirm so I can stage them and continue the rebase."
        ),
        "confirm_rebase_continue": "Conflicts resolved? Continue the rebase?",
        "error_rebase_conflict_cancelled": (
            "Conflict resolution for the rebase of {branch} onto {base_ref} was "
            "cancelled. I aborted the rebase so the checkout is clean — re-run when ready."
        ),
        "error_rebase_conflict_needs_interactive": (
            "Rebase of {branch} onto {base_ref} hit conflicts that need an "
            "interactive editor. Re-run supagit in a terminal without --yes."
        ),
        "error_pr_merge_conflict": (
            "Pull request #{number} ({head} into {base}) still has merge conflicts "
            "after guided rebase recovery. Re-run supagit interactively to resolve "
            "them, or close the PR and reconcile the branches first."
        ),
        "note_pr_auto_merge_armed": (
            "Pull request #{number}: auto-merge is armed but the merge has not "
            "completed yet. Trying plain merge as a fallback."
        ),
        "error_pr_auto_merge_not_completed": (
            "Pull request #{number}: auto-merge was armed but the pull request "
            "never reached MERGED, and the plain merge fallback also failed. "
            "supagit will not continue as if the merge landed."
        ),
        "error_integrate_number": (
            "Invalid independent-work number: {token}. Use the numbers shown next to "
            "worktrees / other local work."
        ),        "confirm_commit_publish": (
            "Commit all current changes on {branch} and publish them to {remote}?"
        ),
        "confirm_publish_existing": (
            "Publish the existing commits from {branch} to {remote}?"
        ),
        "confirm_pipeline": "Start the complete {chain} pipeline?",
        "confirm_migrate": "Apply pending migrations to {label} ({ref})?",
        "confirm_promote": "Merge {source} into {target} and publish {target}?",
        "confirm_cleanup": "Apply optional cleanup of merged branches/worktrees?",
        "cleanup_nothing": "Cleanup: nothing safe to remove.",
        "cleanup_candidates": "Cleanup candidates:",
        "error_cleanup_not_merged": (
            "Refusing to delete local branch {branch}: it is not fully merged into {base}."
        ),
        "pipeline_completed": "\nPipeline completed: {chain}. Final checkout: {branch}.",
        "update_checking": "[supagit] Checking for updates from GitHub…",
        "update_current": "[supagit] Already on the latest supagit (origin/main).",
        "update_found": "[supagit] Update available; pulling and reinstalling…",
        "update_done_reexec": "[supagit] Update installed; restarting…",
        "update_failed": "Could not update supagit from GitHub: {detail}",
        "update_healing_source": (
            "[supagit] Source clone missing or unhealthy; refreshing into {path}…"
        ),
        "update_healing_reinstall": (
            "[supagit] Reinstalling global skill from the refreshed source (--lang {lang})…"
        ),
        "update_reinstalled": "[supagit] Reinstalled. [build: {build}]",
        "update_clone_failed": (
            "Could not clone https://github.com/emiliosevilla/supagit into the "
            "managed source directory: {detail}"
        ),
        "update_installer_missing": (
            "Managed source clone is missing the installer script: {path}"
        ),
        "error_self_update_diverged": (
            "The registered supagit source clone at {path} has diverged from "
            "{remote}/{branch}. Do not auto-update; reconcile manually, for example:\n"
            "  cd {path}\n"
            "  git fetch {remote}\n"
            "  git log --oneline --left-right {remote}/{branch}...HEAD\n"
            "Then re-run scripts/install-supagit-global.sh from a clean clone if needed."
        ),
        "update_no_source": (
            "Cannot locate the registered supagit source-root clone. "
            "Re-run scripts/install-supagit-global.sh from a clone of "
            "https://github.com/emiliosevilla/supagit.git"
        ),
        "yes_need_flags": (
            "With --yes, provide --integrate (or --integrate none) and --pipeline, "
            "or pass --no-sweep."
        ),
        "not_git_repo": "Not inside a Git repository.",
        "local_branches_header": "Local branches",
        "tag_pipeline": "[P]",
        "tag_feature": "[F]",
        "welcome_banner": (
            "supagit\n"
            "Fail-closed Git promotion sweeper: integrate work, publish, check, migrate, promote.\n"
            "Author: Emilio Sevilla\n"
            "\n"
            "Tips:\n"
            "  • Cyan text explains what will happen; green is where you answer.\n"
            "  • Press Enter to accept defaults; n / no cancels a confirmation.\n"
            "  • Press Ctrl+C anytime to abort."
        ),
        "busy_working": "supagit is working…",
        "busy_abort_hint": "(Ctrl+C to abort)",
        "explain_reposition": (
            "The plan starts on {target}, but this checkout is on {current}. "
            "I need to move the checkout to {target}. Nothing on {current} is lost — "
            "that branch stays exactly as it is."
        ),
        "confirm_reposition": "Move the checkout from {current} to {target}?",
        "detached_label": "detached HEAD at {sha}",
        "rescued_detached_head": (
            "HEAD was detached at {sha}; I rescued it as branch {branch}."
        ),
        "sequencer_kind_merge": "merge",
        "sequencer_kind_rebase": "rebase",
        "sequencer_kind_cherry-pick": "cherry-pick",
        "explain_sequencer_in_progress": (
            "This repository has an unfinished {kind}. "
            "I should abort it before changing anything else, so we start from a clean checkout."
        ),
        "confirm_sequencer_abort": "Abort the unfinished {kind} now?",
        "sequencer_aborted": "Aborted the unfinished {kind}.",
        "sequencer_left_in_progress": (
            "Left the unfinished {kind} as-is. Finish or abort it, then re-run supagit."
        ),
        "sequencer_stale_cleared": (
            "Removed stale sequencer marker(s): {markers}."
        ),
        "explain_secrets_gitignore": (
            "I found potential secrets in the working tree and will leave them unstaged: "
            "{paths}. I can add these ignore patterns so they stay out of future commits: "
            "{patterns}."
        ),
        "confirm_secrets_gitignore": "Add those patterns to .gitignore now?",
        "secrets_gitignore_updated": "Updated .gitignore to ignore detected secrets.",
        "error_only_secrets": (
            "Only potential secrets are left to commit ({paths}). "
            "Nothing safe remains to stage — remove or ignore them, then re-run."
        ),
        "error_only_secrets_remaining": (
            "Only potential secrets were left after exclusions; nothing safe to commit."
        ),
        "error_dirty_reposition": (
            "I cannot move the checkout to {target}: {current} has uncommitted changes:\n"
            "{files}\n"
            "Commit them on {current} first (interactive: re-run supagit; "
            "non-interactive: pass -m), or park them outside supagit with: "
            "git stash push -u -m supagit"
        ),
        "error_dirty_reposition_more": "  … and {count} more file(s)",
        "explain_commit_before_reposition": (
            "This checkout is on {branch} with uncommitted changes. "
            "I will commit them on {branch} before moving to {target}."
        ),
        "confirm_commit_before_reposition": (
            "Commit all current changes on {branch} so I can move to {target}?"
        ),
        "integrate_after_pre_commit": (
            "Committed new work on {branch} that is not yet in {base}; "
            "I will integrate {branch} via pull request in this run."
        ),
        "error_pre_commit_needs_integrate": (
            "Committed local changes on {branch}, but they are not in {base} and "
            "--no-sweep skipped feature integration. Re-run without --no-sweep "
            "(or pass --integrate {branch}) so those commits can be merged."
        ),
        "final_checkout_mismatch": (
            "the run finished on {actual}, not on the expected {expected}. "
            "Nothing is pending on the remote; stay here or run supagit again from {expected}."
        ),
        "startup_any_branch": (
            "You are on {branch}. Do not change branches yourself — after you confirm "
            "the plan, I will move the checkout to the first pipeline branch if needed."
        ),
        "explain_return": (
            "The release finished on {pipeline}. You started this run on {branch}."
        ),
        "confirm_return": "Return the checkout to {branch}?",
        "return_done": "Checkout is back on {branch}.",
        "return_skipped_dirty": (
            "Leaving you on {pipeline}: moving back to {branch} needs a clean tree. "
            "Your release is done; run supagit again when you want to continue on {branch}."
        ),
        "return_skipped_yes": (
            "Leaving the checkout on {pipeline} (--yes). Start again from {branch} "
            "whenever you want to continue there — no manual git switch is required."
        ),
        "error_diverged_head": (
            "Local {branch} has diverged from {remote}/{branch} ({counts}); "
            "reconcile it manually before running the pipeline. "
            "Fast-forward-only sync cannot proceed while both sides have unique commits."
        ),
        "head_behind_note": (
            "Local {branch} is behind {remote}/{branch} ({counts}); "
            "fast-forward sync will run before publish."
        ),
        "head_ahead_note": (
            "Local {branch} is ahead of {remote}/{branch} ({counts}); "
            "it will be published in the initial phase."
        ),
        "menu_current_branch": "You are on: {branch}",
        "menu_base_changed": (
            "The first pipeline branch is now {base}, so I re-checked the work "
            "branches against {base}:"
        ),
        "error_not_pipeline_branch": (
            "{branch} is not one of this project's main branches ({configured}); "
            "only those can be ordered here. To merge {branch} into the pipeline, "
            "answer it in the independent-work question instead; to make it a main "
            'branch, add it to "branches" in .supagit.json.'
        ),
        "error_unknown_branch": "There is no local branch named {branch}.",
        "error_integrate_in_pipeline": (
            "{branch} is a main pipeline branch; it cannot also be merged as independent work."
        ),
        "error_pipeline_empty": "The pipeline must include at least one branch.",
        "error_pipeline_number": (
            "Invalid pipeline number: {token}. Use the numbers shown in the main-branches list."
        ),
        "explain_branches_init": (
            "Supagit needs this project's main branches, in release order "
            "(for example: main, or dev,pre,prod)."
        ),
        "branches_prompt": "Main branches in order (comma-separated) [{default}]: ",
        "missing_config_need_branches": (
            "Missing configuration file {path}. With --yes or non-TTY, also pass "
            "--pipeline a,b,c to declare the main branches."
        ),
        "error_branch_detection": (
            'Could not detect the {role} branch. Remote branches: {available}. '
            'Set "branches" in {path} to an ordered list (for example "branches": ["main"]), '
            "or re-create the config with: supagit init --branches a,b,c"
        ),
        "error_branch_ambiguous": (
            "Ambiguous {role} branch detection: {candidates}. "
            'Set "branches" in {path} to an ordered list, or re-create the config with: '
            "supagit init --branches a,b,c"
        ),
        "error_first_branch_in_worktree": (
            "{branch} is already checked out in another worktree: {path}. "
            "Run supagit from there, or close that worktree with: git worktree remove {path}"
        ),
        "adopt_first_branch_worktree": (
            "{branch} is already checked out in {path}; continuing from that worktree."
        ),
        "error_detached_unreachable": (
            "HEAD is detached at {sha} and that commit is not on any branch; "
            "moving the checkout would lose it. Save it first by creating a branch, "
            "for example: git switch -c rescue-work"
        ),
        "layout_unsupported": "Unsupported repository layout: {detail}",
        "situation_preflight_header": "Before running the pipeline, here is the repository situation:",
        "situation_finding_ff_only": (
            "• {role}: behind upstream — a fast-forward sync will run."
        ),
        "situation_finding_publish_then_ff": (
            "• {role}: dirty and behind upstream — commit, rebase onto upstream, then publish."
        ),
        "situation_finding_publish_only": (
            "• {role}: dirty — publish local changes first."
        ),
        "situation_finding_commit_feature": (
            "• {role}: dirty — commit local changes on the feature branch first."
        ),
        "situation_finding_stop_diverged": (
            "• {role}: diverged from upstream — reconcile manually before continuing."
        ),
        "situation_finding_stop_dirty_feature": (
            "• {role}: dirty feature branch behind upstream — commit changes on the feature branch first."
        ),
        "situation_finding_none": "• {role}: no sync action needed.",
        "situation_error_diverged": (
            "Branch {branch} has diverged from {upstream}. Reconcile manually before continuing, "
            "for example:\n"
            "  git fetch\n"
            "  git log --oneline --left-right {upstream}...{branch}"
        ),
        "situation_error_dirty_feature": (
            "Feature branch {branch} is dirty and behind its upstream. Commit (or stash outside "
            "supagit) on that branch first, then re-run."
        ),
    },
    "es": {
        "lang_menu": "Language / Idioma:\n  (1) English\n  (2) Español\nOpción [1/2]: ",
        "lang_required_yes": "Con --yes (o sin TTY), indica --lang en|es o define SUPAGIT_LANG.",
        "lang_invalid": "El idioma debe ser 'en' o 'es' (recibido {value!r}).",
        "aborted": "ABORTADO: {detail}",
        "error": "ERROR: {detail}",
        "aborted_interrupt": "ABORTADO: interrupción del usuario.",
        "user_aborted": "Operación cancelada por el usuario.",
        "confirm_suffix": " [S/n] ",
        "confirm_continue": "¿Continuar?",
        "warning": "AVISO: {detail}",
        "missing_config_creating": "Falta el fichero de configuración {path}; creándolo ahora.",
        "missing_config_need_backend": (
            "Falta el fichero de configuración {path}. Con --yes o sin TTY, pasa --backend none|supabase."
        ),
        "backend_prompt": "Backend [none/supabase] (none): ",
        "backend_invalid": "El backend debe ser 'none' o 'supabase'.",
        "created_config": "Configuración del proyecto creada: {path}",
        "commit_message_prompt": "Mensaje de commit para {branch} [{default}]: ",
        "commit_message_yes": "Con --yes, indica --message/-m para el commit inicial de {branch}.",
        "pipeline_order_prompt": "¿Orden? Enter = {default}: ",
        "integrate_prompt": (
            "¿Qué features? Enter = pendientes [✓], o números / 0 para omitir: "
        ),
        "confirm_merge_single": "¿Fusionar feature {branch} en {base}?",
        "confirm_plan": "¿Ejecuto estos pasos?",
        "explain_backend": (
            "Supagit necesita un fichero de configuración del proyecto. "
            "Indica si este proyecto usa Supabase para migraciones de base de datos."
        ),
        "explain_commit_message": (
            "Tienes cambios locales que guardar. "
            "Un mensaje de commit describe qué cambió; queda en el historial de Git."
        ),
        "explain_commit_publish": (
            "Esto guardará todos los cambios actuales en {branch} como commit "
            "y los subirá a {remote}."
        ),
        "explain_publish_existing": (
            "Tu {branch} local tiene commits que aún no están en {remote}. "
            "Esto los subirá sin crear un commit nuevo."
        ),
        "explain_migrate": (
            "Esto aplicará cambios de esquema pendientes a {label} (proyecto {ref})."
        ),
        "error_migrate_no_target": (
            "No hay destino de migración de base de datos configurado para la rama "
            "{branch}; se aborta antes de fusionar código."
        ),
        "error_database_checkpoint": (
            "El checkpoint de base de datos para {label} falló; se aborta antes de "
            "fusionar código. Detalle: {detail}"
        ),
        "error_database_checkpoint_stale": (
            "La comprobación posterior a la migración no confirma que {label} esté "
            "al día; se aborta antes de fusionar código."
        ),
        "error_migration_state_mismatch": (
            "Las migraciones remotas de {label} no coinciden con supabase/migrations "
            "local; se aborta antes de fusionar código. Solo local: {local_only}. "
            "Solo remoto: {remote_only}."
        ),
        "error_supabase_env_missing": (
            "La variable {env_name} de Supabase ({role}) no está definida. Supagit lee "
            "la variable indicada en .supagit.json; VITE_SUPABASE_* no la sustituye "
            "salvo que la configures explícitamente. Defínela antes de repetir, por ejemplo: "
            "export {env_name}=tu-project-ref, o añade {env_name}=tu-project-ref a .env.local."
        ),
        "explain_promote": (
            "Esto fusionará {source} en {target} en el remoto y publicará {target}."
        ),
        "explain_promote_direct": (
            "Esto fusionará {source} en {target} en local y subirá {target} ({detail})."
        ),
        "explain_promote_pr": (
            "GitHub protege {target} ({visibility}): abriré o reutilizaré un pull request "
            "de {source} a {target} y lo fusionaré con permisos de administrador para que "
            "las reglas de rama no bloqueen el release."
        ),
        "promote_gate_summary": (
            "GitHub {owner}/{repo} es {visibility}; actualizar {branch} usa {mode}."
        ),
        "promote_gate_non_github": "el remoto no es GitHub",
        "promote_mode_pr": "un pull request (las reglas de rama lo exigen)",
        "promote_mode_direct": "una fusión y push directos",
        "promote_pr_created": "Pull request #{number} abierto: {source} → {target}.",
        "promote_pr_reused": "Reutilizando pull request abierto #{number}: {source} → {target}.",
        "error_promote_pr_needs_approval": (
            "El pull request #{number} ({source} → {target}) no se pudo fusionar automáticamente. "
            "Apruébalo como code owner (o cumple las reglas de la rama) y vuelve a ejecutar "
            "supagit."
        ),
        "error_promote_pr_merge_failed": (
            "No se pudo fusionar el pull request #{number} ({source} → {target}) tras "
            "reintentar refresco de autenticación y las alternativas de merge con "
            "administrador/auto/normal. "
            "Revisa `gh auth status` y los permisos del repositorio, y vuelve a ejecutar supagit."
        ),
        "error_gh_missing": (
            "GitHub CLI (gh) no está instalado o no está en PATH. Instálalo: {command}"
        ),
        "error_gh_not_authenticated": (
            "GitHub CLI (gh) no está autenticado y el fallo no es un token caducado: {detail}"
        ),
        "error_gh_refresh_failed": (
            "Intenté refrescar el token de GitHub con `gh auth refresh -h github.com`, "
            "pero falló: {detail}. No hay terminal interactiva para completar "
            "`gh auth login`, así que supagit no puede recuperarse automáticamente."
        ),
        "error_gh_login_failed": (
            "Intenté refrescar el token de GitHub (`gh auth refresh`) y luego lanzar "
            "`gh auth login -h github.com`, pero el login falló: {detail} "
            "(el error de refresh fue: {refresh_detail})."
        ),
        "error_gh_still_unauthenticated": (
            "GitHub CLI sigue sin autenticar tras el intento de refresh/login: {detail}."
        ),
        "error_supabase_missing": (
            "La CLI de Supabase no está instalada o no está en PATH. Instálala: {command}"
        ),
        "error_supabase_not_authenticated": (
            "La CLI de Supabase no está lista y el fallo no parece un login ausente: {detail}"
        ),
        "error_supabase_login_unavailable": (
            "La sonda de auth de Supabase (`supabase projects list`) falló: {detail}. "
            "No hay terminal interactiva para completar `supabase login`, "
            "así que supagit no puede recuperarse automáticamente."
        ),
        "error_supabase_login_failed": (
            "Intenté `supabase login` tras un fallo de la sonda de auth, pero el login falló: {detail} "
            "(el error de la sonda fue: {probe_detail})."
        ),
        "error_supabase_still_unauthenticated": (
            "La CLI de Supabase sigue sin autenticar tras el intento de login: {detail}."
        ),
        "explain_cleanup": (
            "Paso opcional: eliminar worktrees y ramas ya fusionadas que se pueden borrar con seguridad."
        ),
        "explain_pipeline": (
            "Esto ejecutará el pipeline completo de publicación: {chain}."
        ),
        "explain_integrate": (
            "Fusionar features en {base} con un pull request.\n"
            "[✓] = seleccionadas si pulsas Enter. Las ya en {base} quedan [✓] pero se omiten."
        ),
        "explain_integrate_single": (
            "Solo hay una feature pendiente para fusionar en {base} con un pull request: {branch}."
        ),
        "explain_pipeline_order": (
            "Camino de promoción de esta ejecución (números de la lista de pipeline arriba)."
        ),
        "explain_integrate_none": "No hay features que fusionar en {base}.",
        "explain_pipeline_single": "Pipeline de esta ejecución: {branch}.",
        "explain_plan": "Revisa el plan anterior.",
        "menu_section_worktrees": "── Features (worktrees) ──",
        "menu_section_other_work": "── Features (solo locales) ──",
        "menu_section_pipeline": "── Pipeline de release ──",
        "menu_section_work_empty": "(ninguna — nada que fusionar en {base})",
        "menu_check_on": "[✓]",
        "menu_check_off": "[ ]",
        "menu_note_contained": "ya en {base}",
        "menu_note_dirty": "(cambios sin commit)",
        "menu_note_worktree": "worktree: {path}",
        "plan_header": "Esto es lo que voy a hacer:",
        "plan_integrate_item": "Integrar {branch} en {base} mediante una pull request de GitHub",
        "plan_publish_item": "Publicar {branch} en {remote}",
        "plan_ff_item": "Avanzar {branch} hasta {upstream} (fast-forward)",
        "plan_ff_feature_item": "Avanzar {branch} hasta {upstream} (fast-forward) antes de integrar",
        "plan_commit_feature_item": "Confirmar cambios locales en {branch}",
        "plan_migrate_item": "Aplicar migraciones pendientes a {label} ({ref})",
        "plan_promote_item": "Fusionar {source} en {target} y publicar {target}",
        "plan_none_integrate": "No hay features que integrar.",
        "error_ff_dirty": (
            "Se rechaza el fast-forward de {branch}: el worktree tiene cambios sin confirmar. "
            "Confírmalos y publícalos primero (fase publish de supagit) y vuelve a ejecutar. "
            "supagit no hará stash ni reset --hard con el árbol sucio."
        ),
        "publish_defer_behind": (
            "La rama local {branch} está por detrás de {remote}/{branch} con el worktree limpio; "
            "el fast-forward la actualizará a continuación."
        ),
        "publish_skip_push_behind": (
            "Se confirmaron cambios locales en {branch}, pero sigue por detrás de "
            "{remote}/{branch} (o ha divergido). Se omite el push; la sincronización viene después."
        ),
        "publish_rebase_behind": (
            "Se confirmaron cambios locales en {branch}; haciendo rebase sobre "
            "{remote}/{branch} antes de publicar."
        ),
        "error_contained_integrate": (
            "La rama {branch} ya está incluida en {base}; no necesita una pull request nueva. "
            "Omítela, pulsa Enter para los valores por defecto, o escribe 0/ninguno para "
            "omitir todo el trabajo independiente."
        ),
        "error_nothing_to_integrate": (
            "La rama {branch} ya está contenida en {base}; no hay nada que integrar."
        ),
        "note_nothing_to_merge": (
            "Nada que fusionar: {branch} ya está contenida en {base}."
        ),
        "already merged": "ya fusionada",
        "error_empty_pr": (
            "No hay commits para una pull request de {head} hacia {base} "
            "({base_ref}..{head} está vacío). Omite esa rama o añade commits primero."
        ),
        "error_dirty_pipeline_with_integrate": (
            "{pipeline} tiene cambios sin confirmar mientras la(s) rama(s) feature "
            "({features}) se integrarán vía pull request. Confírmalos primero en una "
            "rama feature (ejecuta supagit desde esa rama) y luego integra — confirmar "
            "en {pipeline} antes provoca conflictos de merge."
        ),
        "error_rebase_conflict": (
            "El rebase de {branch} sobre {base_ref} no pudo terminarse tras "
            "resolver conflictos. Vuelve a ejecutar supagit para reintentar."
        ),
        "explain_rebase_conflict": (
            "El rebase de {branch} sobre {base_ref} se detuvo por conflictos en:\n"
            "{files}\n"
            "Abriré tu editor con esos ficheros. Resuelve los marcadores de "
            "conflicto, guarda y confirma para que los prepare y continúe el rebase."
        ),
        "confirm_rebase_continue": "¿Conflictos resueltos? ¿Continuar el rebase?",
        "error_rebase_conflict_cancelled": (
            "Se canceló la resolución de conflictos del rebase de {branch} sobre "
            "{base_ref}. Aborté el rebase para dejar el checkout limpio — vuelve a "
            "ejecutar cuando quieras."
        ),
        "error_rebase_conflict_needs_interactive": (
            "El rebase de {branch} sobre {base_ref} tiene conflictos que necesitan "
            "un editor interactivo. Vuelve a ejecutar supagit en una terminal sin --yes."
        ),
        "error_pr_merge_conflict": (
            "La pull request #{number} ({head} hacia {base}) sigue con conflictos "
            "de merge tras la recuperación con rebase guiado. Vuelve a ejecutar "
            "supagit de forma interactiva para resolverlos, o cierra la PR y "
            "reconcilia las ramas antes."
        ),
        "note_pr_auto_merge_armed": (
            "Pull request #{number}: auto-merge está armado pero la fusión aún no "
            "ha terminado. Probando fusión normal como alternativa."
        ),
        "error_pr_auto_merge_not_completed": (
            "Pull request #{number}: auto-merge quedó armado pero la pull request "
            "nunca llegó a MERGED, y la fusión normal alternativa también "
            "falló. supagit no continuará como si el merge hubiera aterrizado."
        ),
        "error_integrate_number": (
            "Número de trabajo independiente no válido: {token}. Usa los números junto a "
            "los worktrees / otro trabajo local."
        ),
        "confirm_commit_publish": (
            "¿Hacer commit de todos los cambios en {branch} y publicarlos en {remote}?"
        ),
        "confirm_publish_existing": (
            "¿Publicar los commits existentes de {branch} en {remote}?"
        ),
        "confirm_pipeline": "¿Iniciar el pipeline completo {chain}?",
        "confirm_migrate": "¿Aplicar migraciones pendientes a {label} ({ref})?",
        "confirm_promote": "¿Fusionar {source} en {target} y publicar {target}?",
        "confirm_cleanup": "¿Aplicar la limpieza opcional de ramas/worktrees fusionados?",
        "cleanup_nothing": "Limpieza: no hay nada seguro que eliminar.",
        "cleanup_candidates": "Candidatos a limpieza:",
        "error_cleanup_not_merged": (
            "Me niego a borrar la rama local {branch}: no está completamente fusionada en {base}."
        ),
        "pipeline_completed": "\nPipeline completado: {chain}. Checkout final: {branch}.",
        "update_checking": "[supagit] Comprobando actualizaciones en GitHub…",
        "update_current": "[supagit] Ya estás en la última versión de supagit (origin/main).",
        "update_found": "[supagit] Hay actualización; descargando y reinstalando…",
        "update_done_reexec": "[supagit] Actualización instalada; reiniciando…",
        "update_failed": "No se pudo actualizar supagit desde GitHub: {detail}",
        "update_healing_source": (
            "[supagit] Clon fuente ausente o dañado; refrescando en {path}…"
        ),
        "update_healing_reinstall": (
            "[supagit] Reinstalando la skill global desde la fuente refrescada (--lang {lang})…"
        ),
        "update_reinstalled": "[supagit] Reinstalado. [build: {build}]",
        "update_clone_failed": (
            "No se pudo clonar https://github.com/emiliosevilla/supagit en el "
            "directorio de fuente gestionado: {detail}"
        ),
        "update_installer_missing": (
            "Al clon de fuente gestionado le falta el script instalador: {path}"
        ),
        "error_self_update_diverged": (
            "El clon source-root de supagit en {path} ha divergido de "
            "{remote}/{branch}. No se actualiza automáticamente; reconcílialo a mano, "
            "por ejemplo:\n"
            "  cd {path}\n"
            "  git fetch {remote}\n"
            "  git log --oneline --left-right {remote}/{branch}...HEAD\n"
            "Luego vuelve a ejecutar scripts/install-supagit-global.sh desde un clon limpio si hace falta."
        ),
        "update_no_source": (
            "No se encuentra el source-root registrado de supagit. "
            "Vuelve a ejecutar scripts/install-supagit-global.sh desde un clon de "
            "https://github.com/emiliosevilla/supagit.git"
        ),
        "yes_need_flags": (
            "Con --yes, indica --integrate (o --integrate none) y --pipeline, "
            "o pasa --no-sweep."
        ),
        "not_git_repo": "No estás dentro de un repositorio Git.",
        "local_branches_header": "Ramas locales",
        "tag_pipeline": "[P]",
        "tag_feature": "[F]",
        "welcome_banner": (
            "supagit\n"
            "Coche escoba fail-closed de Git: integrar trabajo, publicar, comprobar, migrar, promover.\n"
            "Autor: Emilio Sevilla\n"
            "\n"
            "Consejos:\n"
            "  • El texto cyan explica qué va a pasar; el verde es donde respondes.\n"
            "  • Pulsa Enter para aceptar valores por defecto; n / no cancela una confirmación.\n"
            "  • Pulsa Ctrl+C en cualquier momento para abortar."
        ),
        "busy_working": "supagit está trabajando…",
        "busy_abort_hint": "(Ctrl+C para abortar)",
        "explain_reposition": (
            "El plan empieza en {target}, pero este checkout está en {current}. "
            "Necesito mover el checkout a {target}. No se pierde nada de {current}: "
            "esa rama se queda tal cual."
        ),
        "confirm_reposition": "¿Mover el checkout de {current} a {target}?",
        "detached_label": "HEAD desacoplado en {sha}",
        "rescued_detached_head": (
            "HEAD estaba desacoplado en {sha}; lo he rescatado como rama {branch}."
        ),
        "sequencer_kind_merge": "fusión (merge)",
        "sequencer_kind_rebase": "rebase",
        "sequencer_kind_cherry-pick": "cherry-pick",
        "explain_sequencer_in_progress": (
            "Este repositorio tiene un {kind} a medias. "
            "Debo abortarlo antes de cambiar nada más, para partir de un checkout limpio."
        ),
        "confirm_sequencer_abort": "¿Aborto el {kind} a medias ahora?",
        "sequencer_aborted": "He abortado el {kind} a medias.",
        "sequencer_left_in_progress": (
            "He dejado el {kind} a medias como estaba. Termínalo o abortalo y vuelve a ejecutar supagit."
        ),
        "sequencer_stale_cleared": (
            "He eliminado marcador(es) de sequencer obsoletos: {markers}."
        ),
        "explain_secrets_gitignore": (
            "He encontrado posibles secretos en el árbol de trabajo y los dejaré sin stage: "
            "{paths}. Puedo añadir estos patrones a .gitignore para que no entren en commits futuros: "
            "{patterns}."
        ),
        "confirm_secrets_gitignore": "¿Añado esos patrones a .gitignore ahora?",
        "secrets_gitignore_updated": "He actualizado .gitignore para ignorar los secretos detectados.",
        "error_only_secrets": (
            "Solo quedan posibles secretos por commitear ({paths}). "
            "No hay nada seguro que añadir — quítalos o ignóralos y vuelve a ejecutar."
        ),
        "error_only_secrets_remaining": (
            "Tras excluir secretos no queda nada seguro que commitear."
        ),
        "error_dirty_reposition": (
            "No puedo mover el checkout a {target}: {current} tiene cambios sin guardar:\n"
            "{files}\n"
            "Confírmalos primero en {current} (interactivo: vuelve a ejecutar supagit; "
            "no interactivo: pasa -m), o apártalos fuera de supagit con: "
            "git stash push -u -m supagit"
        ),
        "error_dirty_reposition_more": "  … y {count} fichero(s) más",
        "explain_commit_before_reposition": (
            "Este checkout está en {branch} con cambios sin commit. "
            "Los confirmaré en {branch} antes de mover a {target}."
        ),
        "confirm_commit_before_reposition": (
            "¿Confirmar todos los cambios actuales en {branch} para poder mover a {target}?"
        ),
        "integrate_after_pre_commit": (
            "He confirmado trabajo nuevo en {branch} que aún no está en {base}; "
            "integraré {branch} con una pull request en esta misma ejecución."
        ),
        "error_pre_commit_needs_integrate": (
            "He confirmado cambios locales en {branch}, pero no están en {base} y "
            "--no-sweep omitió la integración de features. Vuelve a ejecutar sin "
            "--no-sweep (o pasa --integrate {branch}) para fusionar esos commits."
        ),
        "final_checkout_mismatch": (
            "la ejecución terminó en {actual}, no en {expected} como se esperaba. "
            "En remoto no queda nada pendiente; quédate aquí o vuelve a ejecutar "
            "supagit desde {expected}."
        ),
        "startup_any_branch": (
            "Estás en {branch}. No cambies de rama tú — cuando confirmes el plan, "
            "yo moveré el checkout a la primera rama del pipeline si hace falta."
        ),
        "explain_return": (
            "La publicación terminó en {pipeline}. Empezaste esta ejecución en {branch}."
        ),
        "confirm_return": "¿Vuelvo el checkout a {branch}?",
        "return_done": "Checkout de vuelta en {branch}.",
        "return_skipped_dirty": (
            "Te dejo en {pipeline}: para volver a {branch} el árbol debe estar limpio. "
            "La publicación ya está hecha; vuelve a ejecutar supagit cuando quieras "
            "seguir en {branch}."
        ),
        "return_skipped_yes": (
            "Dejo el checkout en {pipeline} (--yes). Cuando quieras seguir en {branch}, "
            "vuelve a ejecutar supagit desde ahí — no hace falta un git switch manual."
        ),
        "error_diverged_head": (
            "El {branch} local ha divergido de {remote}/{branch} ({counts}); "
            "reconcílialo manualmente antes de ejecutar el pipeline. "
            "La sincronización solo-fast-forward no puede continuar si ambos lados tienen commits propios."
        ),
        "head_behind_note": (
            "El {branch} local está por detrás de {remote}/{branch} ({counts}); "
            "se hará fast-forward antes de publicar."
        ),
        "head_ahead_note": (
            "El {branch} local está por delante de {remote}/{branch} ({counts}); "
            "se publicará en la fase inicial."
        ),
        "menu_current_branch": "Estás en: {branch}",
        "menu_base_changed": (
            "La primera rama del pipeline ahora es {base}, así que he vuelto a comprobar "
            "las ramas de trabajo contra {base}:"
        ),
        "error_not_pipeline_branch": (
            "{branch} no es una de las ramas principales de este proyecto ({configured}); "
            "aquí solo se pueden ordenar esas. Para fusionar {branch} en el pipeline, "
            "respóndela en la pregunta de trabajo independiente; para convertirla en rama "
            'principal, añádela a "branches" en .supagit.json.'
        ),
        "error_unknown_branch": "No existe ninguna rama local llamada {branch}.",
        "error_integrate_in_pipeline": (
            "{branch} es una rama principal del pipeline; no puede fusionarse además "
            "como trabajo independiente."
        ),
        "error_pipeline_empty": "El pipeline debe incluir al menos una rama.",
        "error_pipeline_number": (
            "Número de pipeline no válido: {token}. Usa los números de la lista de ramas principales."
        ),
        "explain_branches_init": (
            "Supagit necesita las ramas principales de este proyecto, en orden de publicación "
            "(por ejemplo: main, o dev,pre,prod)."
        ),
        "branches_prompt": "Ramas principales en orden (separadas por comas) [{default}]: ",
        "missing_config_need_branches": (
            "Falta el fichero de configuración {path}. Con --yes o sin TTY, pasa también "
            "--pipeline a,b,c para declarar las ramas principales."
        ),
        "error_branch_detection": (
            "No se pudo detectar la rama {role}. Ramas remotas: {available}. "
            'Define "branches" en {path} como una lista ordenada (por ejemplo "branches": ["main"]), '
            "o recrea la configuración con: supagit init --branches a,b,c"
        ),
        "error_branch_ambiguous": (
            "Detección ambigua de la rama {role}: {candidates}. "
            'Define "branches" en {path} como una lista ordenada, o recrea la configuración con: '
            "supagit init --branches a,b,c"
        ),
        "error_first_branch_in_worktree": (
            "{branch} ya está abierta en otro worktree: {path}. "
            "Ejecuta supagit desde allí, o cierra ese worktree con: git worktree remove {path}"
        ),
        "adopt_first_branch_worktree": (
            "{branch} ya está abierta en {path}; continúo desde ese worktree."
        ),
        "error_detached_unreachable": (
            "HEAD está desacoplado en {sha} y ese commit no está en ninguna rama; "
            "mover el checkout lo perdería. Guárdalo primero creando una rama, "
            "por ejemplo: git switch -c rescue-work"
        ),
        "layout_unsupported": "Estructura de repositorio no soportada: {detail}",
        "situation_preflight_header": "Antes de ejecutar el pipeline, esta es la situación del repositorio:",
        "situation_finding_ff_only": (
            "• {role}: por detrás del upstream — se hará un fast-forward."
        ),
        "situation_finding_publish_then_ff": (
            "• {role}: sucia y por detrás del upstream — commit, rebase sobre el upstream y publicar."
        ),
        "situation_finding_publish_only": (
            "• {role}: sucia — publicar primero los cambios locales."
        ),
        "situation_finding_commit_feature": (
            "• {role}: sucia — confirmar cambios locales en la rama feature primero."
        ),
        "situation_finding_stop_diverged": (
            "• {role}: divergió del upstream — reconcíliala manualmente antes de continuar."
        ),
        "situation_finding_stop_dirty_feature": (
            "• {role}: rama de trabajo sucia y por detrás del upstream — confirma los cambios en la rama primero."
        ),
        "situation_finding_none": "• {role}: no hace falta ninguna acción de sincronización.",
        "situation_error_diverged": (
            "La rama {branch} ha divergido de {upstream}. Reconcíliala manualmente antes de continuar, "
            "por ejemplo:\n"
            "  git fetch\n"
            "  git log --oneline --left-right {upstream}...{branch}"
        ),
        "situation_error_dirty_feature": (
            "La rama de trabajo {branch} está sucia y por detrás de su upstream. Confirma "
            "(o haz stash fuera de supagit) en esa rama y vuelve a ejecutar."
        ),
    },
}

_lang: str = "en"


def get_lang() -> str:
    return _lang


def set_lang(lang: str) -> None:
    global _lang
    normalised = (lang or "").strip().lower()
    if normalised not in SUPPORTED:
        raise ValueError(normalised)
    _lang = normalised


def t(key: str, **kwargs: object) -> str:
    catalog = _MESSAGES.get(_lang) or _MESSAGES["en"]
    template = catalog.get(key) or _MESSAGES["en"].get(key) or key
    if not kwargs:
        return template
    try:
        return template.format(**kwargs)
    except (KeyError, ValueError) as exc:
        raise ValueError(f"i18n key {key!r} failed to format: {exc}") from exc


def resolve_lang_from_env_and_args(lang_arg: str | None, *, yes: bool, stdin_isatty: bool) -> str | None:
    """Return language if already decided, else None (caller should prompt)."""
    if lang_arg and lang_arg.strip():
        value = lang_arg.strip().lower()
        if value not in SUPPORTED:
            raise ValueError(value)
        return value
    env = os.environ.get("SUPAGIT_LANG", "").strip().lower()
    if env:
        if env not in SUPPORTED:
            raise ValueError(env)
        return env
    if yes or not stdin_isatty:
        return None  # missing → caller raises
    return None


def prompt_language(input_fn: Callable[[str], str] = input) -> str:
    while True:
        raw = input_fn(_MESSAGES["en"]["lang_menu"]).strip()
        if raw in {"1", ""}:
            return "en"
        if raw == "2":
            return "es"
        # allow typing en/es
        low = raw.lower()
        if low in SUPPORTED:
            return low


def ensure_language(lang_arg: str | None, *, yes: bool) -> str:
    try:
        decided = resolve_lang_from_env_and_args(
            lang_arg, yes=yes, stdin_isatty=sys.stdin.isatty()
        )
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc
    if decided:
        set_lang(decided)
        return decided
    if yes or not sys.stdin.isatty():
        set_lang("en")
        raise RuntimeError("lang_required_yes")
    chosen = prompt_language()
    set_lang(chosen)
    return chosen
