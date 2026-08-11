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
        "commit_message_prompt": "Commit message for {branch}: ",
        "commit_message_empty": "The commit message cannot be empty.",
        "commit_message_yes": "With --yes, provide --message/-m for the initial {branch} commit.",
        "pipeline_order_prompt": (
            "Pipeline order (numbers/names, Enter = {default}): "
        ),
        "integrate_prompt": (
            "Independent work to merge (numbers or names; Enter = all [✓] still needed; "
            "0/none = skip): "
        ),
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
        "explain_promote": (
            "This merges {source} into {target} on the remote and publishes {target}."
        ),
        "explain_promote_direct": (
            "This merges {source} into {target} locally and pushes {target} ({detail})."
        ),
        "explain_promote_pr": (
            "GitHub protects {target} ({visibility}): I will open or reuse a pull request "
            "from {source} into {target} and merge it. I will not use admin bypass."
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
            "Approve it as code owner (or satisfy the branch rules), then re-run supagit. "
            "supagit never uses admin bypass."
        ),
        "explain_cleanup": (
            "Optional step: remove worktrees and branches that were already merged "
            "and are safe to delete."
        ),
        "explain_pipeline": (
            "This runs the full release pipeline through: {chain}."
        ),
        "explain_integrate": (
            "Optional: merge independent work into the first pipeline branch before publishing.\n"
            "Each work branch is numbered. [✓] means selected by default for Enter.\n"
            "Branches already included in the first pipeline branch stay [✓] with a note, "
            "but Enter skips opening a new pull request for them.\n"
            "Type numbers (for example 1,3), names, or 0/none to skip all."
        ),
        "explain_pipeline_order": (
            "Choose which main branches to include and their order. "
            "Numbers refer to the main-branches list above (not the work list)."
        ),
        "explain_plan": "Review the plan above.",
        "menu_section_worktrees": "── Independent worktrees ──",
        "menu_section_other_work": "── Other local work branches (no worktree) ──",
        "menu_section_pipeline": "── Main local and remote repository branches ──",
        "menu_check_on": "[✓]",
        "menu_check_off": "[ ]",
        "menu_note_contained": "already included in {base} (no new PR on Enter)",
        "menu_note_dirty": "(uncommitted changes)",
        "menu_note_worktree": "worktree: {path}",
        "plan_header": "This is what I will do:",
        "plan_integrate_item": "Integrate {branch} into {base} via a GitHub pull request",
        "plan_publish_item": "Publish {branch} to {remote}",
        "plan_ff_item": "Fast-forward {branch} to {upstream}",
        "plan_ff_feature_item": "Fast-forward {branch} to {upstream} before integrating",
        "plan_migrate_item": "Apply pending migrations to {label} ({ref})",
        "plan_promote_item": "Merge {source} into {target} and publish {target}",
        "plan_none_integrate": "No independent work branches to integrate.",
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
        "error_contained_integrate": (
            "Branch {branch} is already included in {base}; it needs no new pull request. "
            "Omit it, press Enter for defaults, or type 0/none to skip all work branches."
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
        "pipeline_completed": "\nPipeline completed: {chain}. Final checkout: {branch}.",
        "update_checking": "[supagit] Checking for updates from GitHub…",
        "update_current": "[supagit] Already on the latest supagit (origin/main).",
        "update_found": "[supagit] Update available; pulling and reinstalling…",
        "update_done_reexec": "[supagit] Update installed; restarting…",
        "update_failed": "Could not update supagit from GitHub: {detail}",
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
        "error_dirty_reposition": (
            "I cannot move the checkout to {target}: {current} has uncommitted changes:\n"
            "{files}\n"
            "Save them first (run supagit again and let it commit them on {current}), "
            "or park them with: git stash push -u -m supagit"
        ),
        "error_dirty_reposition_more": "  … and {count} more file(s)",
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
            "• {role}: dirty and behind upstream — publish first, then fast-forward."
        ),
        "situation_finding_publish_only": (
            "• {role}: dirty — publish local changes first."
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
        "commit_message_prompt": "Mensaje de commit para {branch}: ",
        "commit_message_empty": "El mensaje de commit no puede estar vacío.",
        "commit_message_yes": "Con --yes, indica --message/-m para el commit inicial de {branch}.",
        "pipeline_order_prompt": (
            "Orden del pipeline (números/nombres, Enter = {default}): "
        ),
        "integrate_prompt": (
            "Trabajo independiente a fusionar (números o nombres; Enter = todos los [✓] "
            "que aún hacen falta; 0/ninguno = omitir): "
        ),
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
        "explain_promote": (
            "Esto fusionará {source} en {target} en el remoto y publicará {target}."
        ),
        "explain_promote_direct": (
            "Esto fusionará {source} en {target} en local y subirá {target} ({detail})."
        ),
        "explain_promote_pr": (
            "GitHub protege {target} ({visibility}): abriré o reutilizaré un pull request "
            "de {source} a {target} y lo fusionaré. No usaré bypass de administrador."
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
            "supagit. supagit nunca usa bypass de administrador."
        ),
        "explain_cleanup": (
            "Paso opcional: eliminar worktrees y ramas ya fusionadas que se pueden borrar con seguridad."
        ),
        "explain_pipeline": (
            "Esto ejecutará el pipeline completo de publicación: {chain}."
        ),
        "explain_integrate": (
            "Opcional: fusionar trabajo independiente en la primera rama del pipeline antes de publicar.\n"
            "Cada rama de trabajo tiene un número. [✓] = seleccionada por defecto con Enter.\n"
            "Las ya incluidas en la primera rama del pipeline siguen con [✓] y una nota, "
            "pero Enter no abre una pull request nueva para ellas.\n"
            "Escribe números (por ejemplo 1,3), nombres, o 0/ninguno para omitir todo."
        ),
        "explain_pipeline_order": (
            "Elige qué ramas principales incluir y su orden. "
            "Los números se refieren a la lista de ramas principales (no a la de trabajo)."
        ),
        "explain_plan": "Revisa el plan anterior.",
        "menu_section_worktrees": "── Worktrees independientes ──",
        "menu_section_other_work": "── Otras ramas de trabajo locales (sin worktree) ──",
        "menu_section_pipeline": "── Ramas principales del repositorio local y remoto ──",
        "menu_check_on": "[✓]",
        "menu_check_off": "[ ]",
        "menu_note_contained": "ya incluida en {base} (Enter no abre PR nueva)",
        "menu_note_dirty": "(cambios sin commit)",
        "menu_note_worktree": "worktree: {path}",
        "plan_header": "Esto es lo que voy a hacer:",
        "plan_integrate_item": "Integrar {branch} en {base} mediante una pull request de GitHub",
        "plan_publish_item": "Publicar {branch} en {remote}",
        "plan_ff_item": "Avanzar {branch} hasta {upstream} (fast-forward)",
        "plan_ff_feature_item": "Avanzar {branch} hasta {upstream} (fast-forward) antes de integrar",
        "plan_migrate_item": "Aplicar migraciones pendientes a {label} ({ref})",
        "plan_promote_item": "Fusionar {source} en {target} y publicar {target}",
        "plan_none_integrate": "No hay ramas de trabajo independientes que integrar.",
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
        "error_contained_integrate": (
            "La rama {branch} ya está incluida en {base}; no necesita una pull request nueva. "
            "Omítela, pulsa Enter para los valores por defecto, o escribe 0/ninguno para "
            "omitir todo el trabajo independiente."
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
        "pipeline_completed": "\nPipeline completado: {chain}. Checkout final: {branch}.",
        "update_checking": "[supagit] Comprobando actualizaciones en GitHub…",
        "update_current": "[supagit] Ya estás en la última versión de supagit (origin/main).",
        "update_found": "[supagit] Hay actualización; descargando y reinstalando…",
        "update_done_reexec": "[supagit] Actualización instalada; reiniciando…",
        "update_failed": "No se pudo actualizar supagit desde GitHub: {detail}",
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
        "error_dirty_reposition": (
            "No puedo mover el checkout a {target}: {current} tiene cambios sin guardar:\n"
            "{files}\n"
            "Guárdalos primero (vuelve a ejecutar supagit y deja que los confirme en {current}), "
            "o apártalos con: git stash push -u -m supagit"
        ),
        "error_dirty_reposition_more": "  … y {count} fichero(s) más",
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
            "• {role}: sucia y por detrás del upstream — publicar primero y luego fast-forward."
        ),
        "situation_finding_publish_only": (
            "• {role}: sucia — publicar primero los cambios locales."
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
    if kwargs:
        return template.format(**kwargs)
    return template


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
