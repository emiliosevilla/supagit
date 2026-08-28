#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from supagit_busy import BusySpinner


class LayoutError(RuntimeError):
    pass


@dataclass(frozen=True)
class RepoLayout:
    launch_root: Path
    main_root: Path
    common_dir: Path
    is_linked_launch: bool


def _git(cwd: Path, *args: str, spinner_enabled: bool | None = None) -> str:
    if spinner_enabled is None:
        spinner_enabled = bool(
            sys.stdin.isatty()
            and sys.stderr.isatty()
            and "NO_COLOR" not in os.environ
            and os.environ.get("TERM") != "dumb"
        )
    with BusySpinner(enabled=spinner_enabled):
        completed = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    if completed.returncode != 0:
        details = completed.stderr.strip() or "git failed"
        raise LayoutError(details)
    return completed.stdout.strip()


def resolve_repo_layout(
    cwd: Path | None = None, *, spinner_enabled: bool | None = None
) -> RepoLayout:
    start = (cwd or Path.cwd()).resolve()
    launch_root = Path(
        _git(
            start,
            "rev-parse",
            "--show-toplevel",
            spinner_enabled=spinner_enabled,
        )
    ).resolve()
    git_dir = Path(
        _git(launch_root, "rev-parse", "--git-dir", spinner_enabled=spinner_enabled)
    )
    if not git_dir.is_absolute():
        git_dir = (launch_root / git_dir).resolve()
    else:
        git_dir = git_dir.resolve()
    common_dir = Path(
        _git(
            launch_root,
            "rev-parse",
            "--git-common-dir",
            spinner_enabled=spinner_enabled,
        )
    )
    if not common_dir.is_absolute():
        common_dir = (launch_root / common_dir).resolve()
    else:
        common_dir = common_dir.resolve()
    is_linked = git_dir != common_dir
    # main worktree root: parent of common_dir when common_dir ends with .git
    if common_dir.name == ".git":
        main_root = common_dir.parent
    else:
        # bare or unusual layouts — fail closed
        raise LayoutError(
            f"Unsupported git common dir layout: {common_dir}. "
            "supagit requires a normal non-bare repository."
        )
    return RepoLayout(
        launch_root=launch_root,
        main_root=main_root.resolve(),
        common_dir=common_dir,
        is_linked_launch=is_linked,
    )
