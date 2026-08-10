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
            "Independent work to merge (names, Enter = all checked, none = skip): "
        ),
        "confirm_plan": "Continue?",
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
        "explain_cleanup": (
            "Optional step: remove worktrees and branches that were already merged "
            "and are safe to delete."
        ),
        "explain_pipeline": (
            "This runs the full release pipeline through: {chain}."
        ),
        "explain_integrate": (
            "Optional: merge independent work into the first pipeline branch before publishing.\n"
            "Checked items [✓] are selected if you press Enter. Type none to skip."
        ),
        "explain_pipeline_order": (
            "Choose which main branches to include and their order. "
            "Numbers refer to the pipeline list above."
        ),
        "explain_plan": "Review the plan above. Continue to run these steps.",
        "menu_section_worktrees": "── Independent worktrees ──",
        "menu_section_other_work": "── Other local work branches (no worktree) ──",
        "menu_section_pipeline": "── Main local and remote repository branches ──",
        "menu_check_on": "[✓]",
        "menu_check_off": "[ ]",
        "menu_note_contained": "already included in {base}",
        "menu_note_dirty": "(uncommitted changes)",
        "menu_note_worktree": "worktree: {path}",
        "plan_header": "This is what I will do:",
        "plan_integrate_item": "Integrate {branch} into {base} via a GitHub pull request",
        "plan_publish_item": "Publish {branch} to {remote}",
        "plan_migrate_item": "Apply pending migrations to {label} ({ref})",
        "plan_promote_item": "Merge {source} into {target} and publish {target}",
        "plan_none_integrate": "No independent work branches to integrate.",
        "error_contained_integrate": (
            "Branch {branch} is already included in {base}; omit it or press Enter for defaults."
        ),
        "confirm_commit_publish": (
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
            "Trabajo independiente a fusionar (nombres, Enter = todos marcados, ninguno = omitir): "
        ),
        "confirm_plan": "¿Continuar?",
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
        "explain_cleanup": (
            "Paso opcional: eliminar worktrees y ramas ya fusionadas que se pueden borrar con seguridad."
        ),
        "explain_pipeline": (
            "Esto ejecutará el pipeline completo de publicación: {chain}."
        ),
        "explain_integrate": (
            "Opcional: fusionar trabajo independiente en la primera rama del pipeline antes de publicar.\n"
            "Los elementos marcados [✓] se seleccionan si pulsas Enter. Escribe ninguno para omitir."
        ),
        "explain_pipeline_order": (
            "Elige qué ramas principales incluir y su orden. "
            "Los números se refieren a la lista del pipeline arriba."
        ),
        "explain_plan": "Revisa el plan anterior. Continúa para ejecutar estos pasos.",
        "menu_section_worktrees": "── Worktrees independientes ──",
        "menu_section_other_work": "── Otras ramas de trabajo locales (sin worktree) ──",
        "menu_section_pipeline": "── Ramas principales del repositorio local y remoto ──",
        "menu_check_on": "[✓]",
        "menu_check_off": "[ ]",
        "menu_note_contained": "ya incluida en {base}",
        "menu_note_dirty": "(cambios sin commit)",
        "menu_note_worktree": "worktree: {path}",
        "plan_header": "Esto es lo que voy a hacer:",
        "plan_integrate_item": "Integrar {branch} en {base} mediante una pull request de GitHub",
        "plan_publish_item": "Publicar {branch} en {remote}",
        "plan_migrate_item": "Aplicar migraciones pendientes a {label} ({ref})",
        "plan_promote_item": "Fusionar {source} en {target} y publicar {target}",
        "plan_none_integrate": "No hay ramas de trabajo independientes que integrar.",
        "error_contained_integrate": (
            "La rama {branch} ya está incluida en {base}; omítela o pulsa Enter para los valores por defecto."
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
