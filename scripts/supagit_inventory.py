#!/usr/bin/env python3
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from supagit_layout import RepoLayout

GitRunner = Callable[..., str]


@dataclass(frozen=True)
class WorktreeInfo:
    path: Path
    branch: str | None
    is_main: bool
    dirty_paths: tuple[str, ...]


@dataclass(frozen=True)
class BranchInfo:
    name: str
    is_pipeline: bool
    has_worktree: bool
    worktree_path: Path | None
    ahead: int
    behind: int
    contained_in_first: bool
    upstream: str | None
    dirty: bool


@dataclass(frozen=True)
class RepoInventory:
    layout: RepoLayout
    worktrees: tuple[WorktreeInfo, ...]
    branches: tuple[BranchInfo, ...]
    first_branch: str


def parse_worktree_porcelain(text: str) -> list[dict[str, str | None]]:
    entries: list[dict[str, str | None]] = []
    current: dict[str, str | None] | None = None
    for line in text.splitlines():
        if not line:
            continue
        key, _, value = line.partition(" ")
        if key == "worktree":
            if current is not None:
                entries.append(current)
            current = {"path": value, "branch": None}
        elif current is not None and key == "branch":
            ref = value
            prefix = "refs/heads/"
            current["branch"] = ref[len(prefix):] if ref.startswith(prefix) else ref
    if current is not None:
        entries.append(current)
    return entries


def branch_contained(needle: str, haystack: str, git_runner: GitRunner) -> bool:
    try:
        git_runner("merge-base", "--is-ancestor", needle, haystack, capture=True)
        return True
    except subprocess.CalledProcessError:
        return False


def _ref_exists(ref: str, git_runner: GitRunner, cwd: Path) -> bool:
    try:
        git_runner("rev-parse", "--verify", ref, cwd=cwd, capture=True)
        return True
    except subprocess.CalledProcessError:
        return False


def _upstream_name(branch: str, git_runner: GitRunner, cwd: Path) -> str | None:
    try:
        upstream = git_runner(
            "rev-parse",
            "--abbrev-ref",
            f"{branch}@{{upstream}}",
            cwd=cwd,
            capture=True,
        ).strip()
        if upstream and upstream != f"{branch}@{{upstream}}":
            return upstream
    except subprocess.CalledProcessError:
        pass
    return None


def _ahead_behind(
    branch: str, compare_ref: str, git_runner: GitRunner, cwd: Path
) -> tuple[int, int]:
    counts = git_runner(
        "rev-list",
        "--left-right",
        "--count",
        f"{compare_ref}...{branch}",
        cwd=cwd,
        capture=True,
    ).strip()
    behind, ahead = (int(part) for part in counts.split())
    return ahead, behind


def _status_paths(git_runner: GitRunner, cwd: Path) -> tuple[str, ...]:
    status = git_runner("status", "--porcelain", cwd=cwd, capture=True)
    paths = [line[3:] for line in status.splitlines() if len(line) >= 4]
    return tuple(paths)


def build_inventory(
    layout: RepoLayout,
    pipeline_branches: Sequence[str],
    remote: str,
    *,
    git_runner: GitRunner,
) -> RepoInventory:
    cwd = layout.main_root
    first_branch = pipeline_branches[0]
    pipeline_set = set(pipeline_branches)

    porcelain = git_runner("worktree", "list", "--porcelain", cwd=cwd, capture=True)
    parsed_worktrees = parse_worktree_porcelain(porcelain)

    branch_to_worktree: dict[str, Path] = {}
    worktrees: list[WorktreeInfo] = []
    for entry in parsed_worktrees:
        path = Path(entry["path"]).resolve()
        branch = entry["branch"]
        is_main = path == layout.main_root.resolve()
        dirty_paths = _status_paths(git_runner, path)
        worktrees.append(
            WorktreeInfo(
                path=path,
                branch=branch,
                is_main=is_main,
                dirty_paths=dirty_paths,
            )
        )
        if branch is not None:
            branch_to_worktree[branch] = path

    branch_names = [
        line.strip()
        for line in git_runner(
            "for-each-ref",
            "refs/heads",
            "--format=%(refname:short)",
            cwd=cwd,
            capture=True,
        ).splitlines()
        if line.strip()
    ]

    remote_first = f"{remote}/{first_branch}"
    remote_first_exists = _ref_exists(remote_first, git_runner, cwd)

    branches: list[BranchInfo] = []
    for name in branch_names:
        worktree_path = branch_to_worktree.get(name)
        has_worktree = worktree_path is not None
        dirty = bool(worktree_path and _status_paths(git_runner, worktree_path))

        upstream = _upstream_name(name, git_runner, cwd)
        if upstream is not None:
            ahead, behind = _ahead_behind(name, upstream, git_runner, cwd)
        elif remote_first_exists:
            upstream = remote_first
            ahead, behind = _ahead_behind(name, remote_first, git_runner, cwd)
        else:
            upstream = None
            ahead, behind = 0, 0

        contained = branch_contained(name, first_branch, git_runner)

        branches.append(
            BranchInfo(
                name=name,
                is_pipeline=name in pipeline_set,
                has_worktree=has_worktree,
                worktree_path=worktree_path,
                ahead=ahead,
                behind=behind,
                contained_in_first=contained,
                upstream=upstream,
                dirty=dirty,
            )
        )

    return RepoInventory(
        layout=layout,
        worktrees=tuple(worktrees),
        branches=tuple(branches),
        first_branch=first_branch,
    )


def default_integrate_names(inventory: RepoInventory) -> tuple[str, ...]:
    return tuple(
        b.name
        for b in inventory.branches
        if not b.is_pipeline and not b.contained_in_first
    )
