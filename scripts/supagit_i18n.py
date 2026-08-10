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
            "Pipeline order (numbers/names, empty = default {default}): "
        ),
        "integrate_prompt": (
            "Integrate features (numbers/names, empty = default, 'none' = skip): "
        ),
        "confirm_plan": "Proceed with this plan?",
        "confirm_commit_publish": (
            "Commit all current changes on {branch} and publish them to {remote}?"
        ),
        "confirm_publish_existing": (
            "Publish the existing commits from {branch} to {remote}?"
        ),
        "confirm_pipeline": "Start the complete {chain} pipeline?",
        "confirm_migrate": "Apply pending migrations to {label} ({ref})?",
        "confirm_promote": "Merge {source} into {target} and publish {target}?",
        "confirm_cleanup": "Apply optional cleanup of merged features/worktrees?",
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
            "Orden del pipeline (números/nombres, vacío = por defecto {default}): "
        ),
        "integrate_prompt": (
            "Integrar features (números/nombres, vacío = por defecto, 'none' = omitir): "
        ),
        "confirm_plan": "¿Continuar con este plan?",
        "confirm_commit_publish": (
            "¿Hacer commit de todos los cambios en {branch} y publicarlos en {remote}?"
        ),
        "confirm_publish_existing": (
            "¿Publicar los commits existentes de {branch} en {remote}?"
        ),
        "confirm_pipeline": "¿Iniciar el pipeline completo {chain}?",
        "confirm_migrate": "¿Aplicar migraciones pendientes a {label} ({ref})?",
        "confirm_promote": "¿Fusionar {source} en {target} y publicar {target}?",
        "confirm_cleanup": "¿Aplicar la limpieza opcional de features/worktrees fusionados?",
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
