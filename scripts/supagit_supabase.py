#!/usr/bin/env python3
"""Supabase CLI readiness preflight (auth / install), mirroring GhClient."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from supagit_i18n import t

# Install hint shown when the CLI binary is missing from PATH (tutor recovery).
_INSTALL_HINT = "brew install supabase/tap/supabase   # macOS"

_AUTH_MARKERS = (
    "logged-in",
    "logged in",
    "login",
    "access token",
    "token",
    "unauthorized",
    "auth",
)

# Supabase migration versions are timestamp prefixes (commonly 14 digits).
_VERSION_RE = re.compile(r"^(\d+)")


class SupabaseError(RuntimeError):
    """Fail-closed Supabase CLI preflight error mapped to ShipError by callers."""


def local_migration_versions(migrations_dir: Path) -> set[str]:
    """Versions implied by filenames under ``supabase/migrations``."""
    if not migrations_dir.is_dir():
        return set()
    versions: set[str] = set()
    for path in migrations_dir.iterdir():
        if not path.is_file() or path.suffix != ".sql":
            continue
        match = _VERSION_RE.match(path.name)
        if match:
            versions.add(match.group(1))
    return versions


def parse_migration_list_remote(output: str) -> set[str]:
    """Parse remote versions from Supabase text, JSON, or stream-JSON output."""

    def version_from_cell(value: object) -> str | None:
        if not isinstance(value, str):
            return None
        cleaned = value.strip().strip("`'\"").strip()
        match = _VERSION_RE.match(cleaned)
        return match.group(1) if match else None

    def json_remote_versions(value: object, versions: set[str]) -> None:
        if isinstance(value, dict):
            version = version_from_cell(value.get("remote"))
            if version:
                versions.add(version)
            for child in value.values():
                json_remote_versions(child, versions)
        elif isinstance(value, list):
            for child in value:
                json_remote_versions(child, versions)

    json_documents: list[object] = []
    try:
        json_documents.append(json.loads(output))
    except json.JSONDecodeError:
        # stream-json emits one valid document per line.
        for line in output.splitlines():
            try:
                json_documents.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    if json_documents:
        remote: set[str] = set()
        for document in json_documents:
            json_remote_versions(document, remote)
        return remote

    remote: set[str] = set()
    for line in output.splitlines():
        delimiter = "│" if "│" in line else "|" if "|" in line else None
        if delimiter is None:
            continue
        parts = [part.strip() for part in line.split(delimiter)]
        if len(parts) < 2:
            continue
        local_cell, remote_cell = parts[0], parts[1]
        if local_cell.upper() == "LOCAL" or remote_cell.upper() == "REMOTE":
            continue
        if all(character in "─-" for character in local_cell + remote_cell):
            continue
        version = version_from_cell(remote_cell)
        if version:
            remote.add(version)
    return remote


def assert_migration_state_matches(
    *,
    local: set[str],
    remote: set[str],
    label: str,
) -> None:
    """Fail closed when local migration filenames and remote history disagree."""
    if local == remote:
        return
    local_only = ", ".join(sorted(local - remote)) or "—"
    remote_only = ", ".join(sorted(remote - local)) or "—"
    raise SupabaseError(
        t(
            "error_migration_state_mismatch",
            label=label,
            local_only=local_only,
            remote_only=remote_only,
        )
    )


def _is_auth_failure(detail: str) -> bool:
    lowered = detail.lower()
    return any(marker in lowered for marker in _AUTH_MARKERS)


def _default_run_raw(command: Sequence[str]) -> str:
    """Run a supabase CLI command; inherit stdio for interactive login."""
    cmd = [str(part) for part in command]
    interactive_login = len(cmd) >= 2 and cmd[1] == "login"
    completed = subprocess.run(
        cmd,
        text=True,
        stdout=None if interactive_login else subprocess.PIPE,
        stderr=None if interactive_login else subprocess.PIPE,
    )
    if completed.returncode != 0:
        if interactive_login:
            raise RuntimeError(
                f"{cmd[0]} login exited {completed.returncode}"
            )
        detail = (completed.stderr or completed.stdout or "no error output").strip()
        raise RuntimeError(detail)
    return (completed.stdout or "") if not interactive_login else ""


def ensure_supabase_ready(
    cli: str,
    *,
    dry_run: bool,
    run_raw: Callable[..., str] | None = None,
) -> None:
    """Ensure the Supabase CLI is installed and authenticated.

    Probe with ``{cli} projects list``. On auth failure with a TTY, launch
    ``{cli} login`` once, then re-verify. Without a TTY, fail closed — never
    hang, and never print “run this yourself” as the primary fix.
    """
    if dry_run:
        return

    if shutil.which(cli) is None:
        raise SupabaseError(
            t("error_supabase_missing", command=_INSTALL_HINT)
        )

    runner: Callable[..., str] = run_raw if run_raw is not None else _default_run_raw
    probe = [cli, "projects", "list"]

    try:
        runner(probe)
        return
    except FileNotFoundError as exc:
        raise SupabaseError(
            t("error_supabase_missing", command=_INSTALL_HINT)
        ) from exc
    except Exception as exc:
        detail = str(exc)
        if not _is_auth_failure(detail):
            raise SupabaseError(
                t("error_supabase_not_authenticated", detail=detail)
            ) from exc
        auth_detail = detail

    if not sys.stdin.isatty():
        raise SupabaseError(
            t("error_supabase_login_unavailable", detail=auth_detail)
        )

    try:
        runner([cli, "login"])
    except Exception as login_exc:
        raise SupabaseError(
            t(
                "error_supabase_login_failed",
                detail=str(login_exc),
                probe_detail=auth_detail,
            )
        ) from login_exc

    try:
        runner(probe)
    except Exception as status_exc:
        raise SupabaseError(
            t(
                "error_supabase_still_unauthenticated",
                detail=str(status_exc),
            )
        ) from status_exc
