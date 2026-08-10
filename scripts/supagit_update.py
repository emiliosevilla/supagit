#!/usr/bin/env python3
"""Keep the installed supagit skill on the latest GitHub main tip."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


class UpdateError(RuntimeError):
    pass


SKIP_ENV = "SUPAGIT_SKIP_UPDATE"
DEFAULT_REMOTE = "origin"
DEFAULT_BRANCH = "main"
GITHUB_MARKER = "github.com/emiliosevilla/supagit"


def source_root_from_marker(home: Path | None = None) -> Path | None:
    base = home or Path.home()
    marker = base / ".agents" / "skills" / "supagit" / "source-root"
    if not marker.is_file():
        return None
    text = marker.read_text(encoding="utf-8").strip().splitlines()
    if not text or not text[0].strip():
        return None
    path = Path(text[0].strip()).expanduser()
    if not path.is_dir():
        return None
    return path.resolve()


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


def assert_github_source(source_root: Path) -> None:
    url = _run(source_root, "git", "remote", "get-url", DEFAULT_REMOTE)
    normalised = url.replace(":", "/").lower()
    if GITHUB_MARKER not in normalised and "emiliosevilla/supagit" not in normalised:
        raise UpdateError(
            f"source-root remote is not the expected GitHub repo (got {url!r})"
        )


def commits_behind(source_root: Path, remote: str = DEFAULT_REMOTE, branch: str = DEFAULT_BRANCH) -> int:
    _run(source_root, "git", "fetch", remote, branch)
    ahead_behind = _run(
        source_root,
        "git",
        "rev-list",
        "--left-right",
        "--count",
        f"{remote}/{branch}...HEAD",
    )
    remote_only, _local_only = (int(part) for part in ahead_behind.split())
    return remote_only


def needs_update(source_root: Path) -> bool:
    assert_github_source(source_root)
    return commits_behind(source_root) > 0


def pull_and_reinstall(source_root: Path) -> None:
    _run(source_root, "git", "pull", "--ff-only", DEFAULT_REMOTE, DEFAULT_BRANCH)
    installer = source_root / "scripts" / "install-supagit-global.sh"
    if not installer.is_file():
        raise UpdateError(f"installer missing: {installer}")
    _run(source_root, "sh", str(installer))


def maybe_self_update_and_reexec(argv: list[str]) -> None:
    """If source is behind origin/main, update, reinstall, and re-exec once."""
    if os.environ.get(SKIP_ENV) == "1":
        return
    source = source_root_from_marker()
    if source is None:
        # Running from a checkout that is itself the source: allow local scripts path.
        candidate = Path(__file__).resolve().parent.parent
        if (candidate / "scripts" / "install-supagit-global.sh").is_file():
            source = candidate
        else:
            raise UpdateError("no_source")
    if not needs_update(source):
        return
    pull_and_reinstall(source)
    env = os.environ.copy()
    env[SKIP_ENV] = "1"
    script = Path(__file__).resolve().parent / "supagit.py"
    if not script.is_file():
        script = Path(sys.argv[0]).resolve()
    os.execve(sys.executable, [sys.executable, str(script), *argv], env)
