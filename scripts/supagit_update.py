#!/usr/bin/env python3
"""Keep the installed supagit skill on the latest GitHub main tip."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import TextIO

from supagit_i18n import t
from supagit_situation import SyncStatus, classify_sync_counts


class UpdateError(RuntimeError):
    pass


SKIP_ENV = "SUPAGIT_SKIP_UPDATE"
DEFAULT_REMOTE = "origin"
DEFAULT_BRANCH = "main"
GITHUB_MARKER = "github.com/emiliosevilla/supagit"
GITHUB_CLONE_URL = "https://github.com/emiliosevilla/supagit.git"
# Visible on every reinstall so users can confirm freshness.
BUILD_STAMP = "2026-08-12"


def source_root_from_marker(home: Path | None = None) -> Path | None:
    base = home or Path.home()
    marker = base / ".agents" / "skills" / "supagit" / "source-root"
    if not marker.is_file():
        return None
    try:
        text = marker.read_text(encoding="utf-8").strip().splitlines()
    except (OSError, UnicodeError):
        # Unreadable/corrupt marker → treat as missing so ensure can self-heal.
        return None
    if not text or not text[0].strip():
        return None
    path = Path(text[0].strip()).expanduser()
    if not path.is_dir():
        return None
    return path.resolve()


def managed_source_root(home: Path | None = None) -> Path:
    """Canonical self-owned clone path (~/.supagit/source)."""
    return ((home or Path.home()) / ".supagit" / "source").resolve()


def write_source_root_marker(source_root: Path, home: Path | None = None) -> None:
    base = home or Path.home()
    marker = base / ".agents" / "skills" / "supagit" / "source-root"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(f"{source_root.resolve()}\n", encoding="utf-8")


def _run(cwd: Path, *args: str) -> str:
    completed = subprocess.run(
        list(args),
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "command failed").strip()
        raise UpdateError(f"{' '.join(args)}: {detail}")
    return completed.stdout.strip()


def resolve_update_lang(argv: list[str] | None = None) -> str:
    """Pick install language before argparse runs (non-interactive self-update)."""
    if argv:
        index = 0
        while index < len(argv):
            arg = argv[index]
            if arg in ("--lang", "-l") and index + 1 < len(argv):
                value = argv[index + 1].strip().lower()
                if value in ("en", "es"):
                    return value
                index += 2
                continue
            if arg.startswith("--lang="):
                value = arg.split("=", 1)[1].strip().lower()
                if value in ("en", "es"):
                    return value
            index += 1
    env = os.environ.get("SUPAGIT_LANG", "").strip().lower()
    if env in ("en", "es"):
        return env
    return "en"


def _run_installer(cwd: Path, installer: Path, lang: str) -> None:
    """Run the global installer without blocking on an interactive language menu."""
    if lang not in ("en", "es"):
        lang = "en"
    completed = subprocess.run(
        ["sh", str(installer), "--lang", lang],
        cwd=str(cwd),
        stdin=subprocess.DEVNULL,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "command failed").strip()
        raise UpdateError(f"sh {installer} --lang {lang}: {detail}")


def assert_github_source(source_root: Path) -> None:
    url = _run(source_root, "git", "remote", "get-url", DEFAULT_REMOTE)
    normalised = url.replace(":", "/").lower()
    if GITHUB_MARKER not in normalised and "emiliosevilla/supagit" not in normalised:
        raise UpdateError(
            f"source-root remote is not the expected GitHub repo (got {url!r})"
        )


def sync_counts(
    source_root: Path,
    remote: str = DEFAULT_REMOTE,
    branch: str = DEFAULT_BRANCH,
) -> tuple[int, int]:
    """Return (remote_only, local_only) for {remote}/{branch}...HEAD after fetch."""
    _run(source_root, "git", "fetch", remote, branch)
    ahead_behind = _run(
        source_root,
        "git",
        "rev-list",
        "--left-right",
        "--count",
        f"{remote}/{branch}...HEAD",
    )
    parts = ahead_behind.split()
    if len(parts) != 2:
        raise UpdateError(
            f"Could not compute ahead/behind for {remote}/{branch}...HEAD "
            f"(got {ahead_behind!r})."
        )
    remote_only, local_only = (int(part) for part in parts)
    return remote_only, local_only


def commits_behind(
    source_root: Path, remote: str = DEFAULT_REMOTE, branch: str = DEFAULT_BRANCH
) -> int:
    remote_only, _local_only = sync_counts(source_root, remote=remote, branch=branch)
    return remote_only


def self_update_sync_status(
    source_root: Path,
    remote: str = DEFAULT_REMOTE,
    branch: str = DEFAULT_BRANCH,
) -> SyncStatus:
    remote_only, local_only = sync_counts(source_root, remote=remote, branch=branch)
    return classify_sync_counts(ahead=local_only, behind=remote_only)


def ensure_self_update_allowed(
    source_root: Path,
    remote: str = DEFAULT_REMOTE,
    branch: str = DEFAULT_BRANCH,
) -> SyncStatus:
    """Raise UpdateError when the source clone has diverged from upstream."""
    status = self_update_sync_status(source_root, remote=remote, branch=branch)
    if status == SyncStatus.DIVERGED:
        raise UpdateError(
            t(
                "error_self_update_diverged",
                path=str(source_root),
                remote=remote,
                branch=branch,
            )
        )
    return status


def needs_update(source_root: Path) -> bool:
    assert_github_source(source_root)
    status = ensure_self_update_allowed(source_root)
    return status == SyncStatus.BEHIND_ONLY


def pull_and_reinstall(
    source_root: Path, *, lang: str = "en", progress: TextIO | None = None
) -> None:
    def _progress(message: str) -> None:
        if progress is not None:
            print(message, file=progress, flush=True)

    assert_github_source(source_root)
    status = ensure_self_update_allowed(source_root)
    if status != SyncStatus.BEHIND_ONLY:
        return
    _progress("[supagit] git pull --ff-only origin main…")
    _run(source_root, "git", "pull", "--ff-only", DEFAULT_REMOTE, DEFAULT_BRANCH)
    installer = source_root / "scripts" / "install-supagit-global.sh"
    if not installer.is_file():
        raise UpdateError(t("update_installer_missing", path=str(installer)))
    _progress(f"[supagit] install-supagit-global.sh --lang {lang}…")
    _run_installer(source_root, installer, lang)
    _progress(t("update_reinstalled", build=BUILD_STAMP))


def _shallow_clone_github(dest: Path) -> None:
    """Shallow-clone the canonical public repo into dest (replacing dest if present)."""
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [
            "git",
            "clone",
            "--depth",
            "1",
            "--branch",
            DEFAULT_BRANCH,
            GITHUB_CLONE_URL,
            str(dest),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "git clone failed").strip()
        raise UpdateError(t("update_clone_failed", detail=detail))


def _source_is_usable(source_root: Path) -> bool:
    """True when the clone can be used for ff-only self-update (or is already current)."""
    installer = source_root / "scripts" / "install-supagit-global.sh"
    if not installer.is_file():
        return False
    try:
        assert_github_source(source_root)
        status = self_update_sync_status(source_root)
    except UpdateError:
        return False
    if status in (
        SyncStatus.DIVERGED,
        SyncStatus.AHEAD_ONLY,
        SyncStatus.NO_UPSTREAM,
    ):
        return False
    if status not in (SyncStatus.IN_SYNC, SyncStatus.BEHIND_ONLY):
        return False
    try:
        dirty = _run(source_root, "git", "status", "--porcelain")
    except UpdateError:
        return False
    return not dirty.strip()


def ensure_healthy_source_root(
    home: Path | None = None,
    *,
    lang: str = "en",
    progress: TextIO | None = None,
    run_installer: bool = True,
) -> Path:
    """Return a healthy GitHub source root, re-cloning into ~/.supagit/source when needed.

    Sets ``ensure_healthy_source_root.repaired`` to True when the managed clone was
    adopted (marker rewrite / installer) or shallow-cloned.
    """
    ensure_healthy_source_root.repaired = False
    base = home or Path.home()

    def _progress(message: str) -> None:
        if progress is not None:
            print(message, file=progress, flush=True)

    existing = source_root_from_marker(home=base)
    if existing is not None and _source_is_usable(existing):
        return existing

    managed = managed_source_root(home=base)
    # Prefer an already-healthy managed tree over destroying it with rmtree+clone.
    if managed.is_dir() and _source_is_usable(managed):
        _progress(t("update_healing_source", path=str(managed)))
        write_source_root_marker(managed, home=base)
        if run_installer:
            installer = managed / "scripts" / "install-supagit-global.sh"
            if not installer.is_file():
                raise UpdateError(t("update_installer_missing", path=str(installer)))
            _progress(t("update_healing_reinstall", lang=lang))
            _run_installer(managed, installer, lang)
            _progress(t("update_reinstalled", build=BUILD_STAMP))
        ensure_healthy_source_root.repaired = True
        return managed

    _progress(t("update_healing_source", path=str(managed)))
    try:
        _shallow_clone_github(managed)
    except UpdateError:
        raise
    except OSError as exc:
        raise UpdateError(t("update_clone_failed", detail=str(exc))) from exc

    write_source_root_marker(managed, home=base)
    if run_installer:
        installer = managed / "scripts" / "install-supagit-global.sh"
        if not installer.is_file():
            raise UpdateError(t("update_installer_missing", path=str(installer)))
        _progress(t("update_healing_reinstall", lang=lang))
        _run_installer(managed, installer, lang)
        _progress(t("update_reinstalled", build=BUILD_STAMP))
    ensure_healthy_source_root.repaired = True
    return managed


ensure_healthy_source_root.repaired = False


def maybe_self_update_and_reexec(argv: list[str]) -> None:
    """If source is behind origin/main, update, reinstall, and re-exec once."""
    if os.environ.get(SKIP_ENV) == "1":
        return
    lang = resolve_update_lang(argv)
    source = ensure_healthy_source_root(lang=lang)
    repaired = bool(getattr(ensure_healthy_source_root, "repaired", False))
    if not repaired and not needs_update(source):
        return
    if needs_update(source):
        pull_and_reinstall(source, lang=lang)
    env = os.environ.copy()
    env[SKIP_ENV] = "1"
    script = Path(__file__).resolve().parent / "supagit.py"
    if not script.is_file():
        script = Path(sys.argv[0]).resolve()
    os.execve(sys.executable, [sys.executable, str(script), *argv], env)
