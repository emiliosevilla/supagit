#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from supagit_inventory import RepoInventory

GitRunner = Callable[..., str]
RejectSensitive = Callable[[Sequence[str]], None]

PR_BODY = "Integrated by supagit sweeper."


class SweepError(RuntimeError):
    """Fail-closed sweep/sync error mapped to ShipError by Pipeline."""


@dataclass(frozen=True)
class SyncResult:
    changed: bool
    before: str
    after: str


@dataclass(frozen=True)
class CleanupItem:
    kind: str
    name: str
    path: Path | None


@dataclass(frozen=True)
class CleanupPlan:
    items: tuple[CleanupItem, ...]


def ahead_behind(run_git: GitRunner, local: str, remote_ref: str) -> tuple[int, int]:
    counts = run_git(
        "rev-list",
        "--left-right",
        "--count",
        f"{remote_ref}...{local}",
    )
    remote_only, local_only = (int(part) for part in counts.split())
    return remote_only, local_only


def _abort_merge_if_needed(run_git: GitRunner) -> None:
    try:
        run_git("rev-parse", "--verify", "MERGE_HEAD")
    except Exception:
        return
    try:
        run_git("merge", "--abort")
    except Exception:
        pass


def _fetch_remote_branch(
    run_git: GitRunner, remote: str, branch: str, remote_ref: str
) -> None:
    try:
        run_git(
            "fetch",
            remote,
            f"refs/heads/{branch}:refs/remotes/{remote}/{branch}",
        )
    except Exception as exc:
        try:
            run_git("remote", "get-url", remote)
            raise SweepError(f"Could not fetch {remote}/{branch}.") from exc
        except SweepError:
            raise
        except Exception:
            try:
                run_git("rev-parse", "--verify", remote_ref)
            except Exception:
                raise SweepError(
                    f"Could not fetch {remote}/{branch} and no local remote-tracking ref exists."
                ) from exc


def ff_sync_branch(
    run_git: GitRunner,
    branch: str,
    remote: str,
    *,
    dry_run: bool,
) -> SyncResult:
    remote_ref = f"{remote}/{branch}"
    _fetch_remote_branch(run_git, remote, branch, remote_ref)
    before = run_git("rev-parse", branch)
    remote_only, local_only = ahead_behind(run_git, branch, remote_ref)

    if remote_only == 0:
        return SyncResult(False, before, before)
    if local_only > 0:
        raise SweepError(
            f"Local branch {branch} has diverged from {remote_ref} "
            f"({remote_only}\t{local_only}). Synchronize with fast-forward only."
        )

    if dry_run:
        return SyncResult(True, before, run_git("rev-parse", remote_ref))

    current = run_git("branch", "--show-current")
    if current != branch:
        run_git("checkout", branch)

    try:
        run_git("merge", "--ff-only", remote_ref)
    except Exception as exc:
        _abort_merge_if_needed(run_git)
        run_git("reset", "--hard", before)
        raise SweepError(
            f"Fast-forward merge of {remote_ref} into {branch} failed."
        ) from exc

    after = run_git("rev-parse", branch)
    remote_tip = run_git("rev-parse", remote_ref)
    if after != remote_tip:
        run_git("reset", "--hard", before)
        raise SweepError(
            f"Fast-forward sync verification failed for {branch}: "
            f"tip {after} does not match {remote_ref} ({remote_tip})."
        )
    return SyncResult(True, before, after)


class GhClient:
    def __init__(self, run_raw: Callable[..., str], *, dry_run: bool) -> None:
        self._run_raw = run_raw
        self._dry_run = dry_run

    def ensure_ready(self) -> None:
        if self._dry_run:
            return
        try:
            self._run_raw(["gh", "auth", "status"])
        except FileNotFoundError as exc:
            raise SweepError("GitHub CLI (gh) is not installed or not on PATH.") from exc
        except Exception as exc:
            raise SweepError("GitHub CLI (gh) is not authenticated.") from exc

    def ensure_github_remote(self, remote_url: str) -> None:
        normalized = remote_url.lower()
        if "github.com" not in normalized:
            raise SweepError(f"Remote is not GitHub: {remote_url}")

    def find_open_pr(self, head: str, base: str) -> int | None:
        if self._dry_run:
            return None
        output = self._run_raw(
            [
                "gh",
                "pr",
                "list",
                "--head",
                head,
                "--base",
                base,
                "--state",
                "open",
                "--json",
                "number",
                "--jq",
                ".[0].number",
            ]
        ).strip()
        if not output or output == "null":
            return None
        return int(output)

    def create_pr(self, head: str, base: str, title: str) -> int:
        if self._dry_run:
            return 0
        output = self._run_raw(
            [
                "gh",
                "pr",
                "create",
                "--base",
                base,
                "--head",
                head,
                "--title",
                title,
                "--body",
                PR_BODY,
                "--json",
                "number",
                "--jq",
                ".number",
            ]
        ).strip()
        if not output:
            raise SweepError(f"Could not create pull request for {head} into {base}.")
        return int(output)

    def merge_pr(self, number: int) -> None:
        if self._dry_run:
            return
        self._run_raw(
            ["gh", "pr", "merge", str(number), "--merge", "--delete-branch"]
        )


def commit_dirty_tree(
    run_git: GitRunner,
    *,
    cwd: Path,
    message: str,
    reject_sensitive: RejectSensitive,
    dry_run: bool,
) -> bool:
    status = run_git("status", "--porcelain", cwd=cwd)
    if not status.strip():
        return False

    status_paths = [line[3:] for line in status.splitlines() if len(line) >= 4]
    reject_sensitive(status_paths)

    if dry_run:
        return True

    run_git("add", "-A", cwd=cwd)
    staged = run_git("diff", "--cached", "--name-only", cwd=cwd)
    reject_sensitive(staged.splitlines())
    run_git("diff", "--cached", "--check", cwd=cwd)
    run_git("commit", "-m", message, cwd=cwd)
    return True


def _branch_checked_out(run_git: GitRunner, branch: str, *, cwd: Path) -> bool:
    try:
        current = run_git("branch", "--show-current", cwd=cwd).strip()
    except Exception:
        return False
    return current == branch


def _branch_has_upstream(run_git: GitRunner, branch: str, *, cwd: Path) -> bool:
    try:
        run_git("rev-parse", "--abbrev-ref", f"{branch}@{{upstream}}", cwd=cwd)
        return True
    except Exception:
        return False


def push_branch(
    run_git: GitRunner,
    remote: str,
    branch: str,
    *,
    cwd: Path,
    dry_run: bool,
) -> None:
    if dry_run:
        return

    if _branch_checked_out(run_git, branch, cwd=cwd):
        if _branch_has_upstream(run_git, branch, cwd=cwd):
            run_git("push", remote, branch, cwd=cwd)
        else:
            run_git("push", "-u", remote, branch, cwd=cwd)
        return

    run_git("push", remote, f"{branch}:{branch}", cwd=cwd)


def integrate_branch(
    run_git: GitRunner,
    *,
    gh: GhClient,
    remote: str,
    remote_url: str,
    branch: str,
    base: str,
    cwd: Path,
    message_provider: Callable[[], str],
    reject_sensitive: RejectSensitive,
    dry_run: bool,
    contained_in_first: bool,
) -> None:
    if contained_in_first:
        raise SweepError("nothing to integrate")

    gh.ensure_ready()
    gh.ensure_github_remote(remote_url)

    status = run_git("status", "--porcelain", cwd=cwd)
    if status.strip():
        message = message_provider()
        commit_dirty_tree(
            run_git,
            cwd=cwd,
            message=message,
            reject_sensitive=reject_sensitive,
            dry_run=dry_run,
        )

    push_branch(run_git, remote, branch, cwd=cwd, dry_run=dry_run)

    pr_number = gh.find_open_pr(branch, base)
    if pr_number is None:
        title = f"supagit: integrate {branch} into {base}"
        pr_number = gh.create_pr(branch, base, title)

    gh.merge_pr(pr_number)

    if dry_run:
        return

    try:
        run_git(
            "fetch",
            remote,
            f"refs/heads/{base}:refs/remotes/{remote}/{base}",
            cwd=cwd,
        )
    except Exception as exc:
        raise SweepError(f"Could not fetch {remote}/{base} after merge.") from exc


def plan_cleanup(
    inventory: RepoInventory,
    pipeline: Sequence[str],
    merged_features: Sequence[str],
) -> CleanupPlan:
    pipeline_set = set(pipeline)
    merged_set = set(merged_features)

    eligible: set[str] = set()
    for branch in inventory.branches:
        if branch.is_pipeline or branch.name in pipeline_set:
            continue
        if branch.contained_in_first or branch.name in merged_set:
            eligible.add(branch.name)

    items: list[CleanupItem] = []

    for worktree in inventory.worktrees:
        branch_name = worktree.branch
        if branch_name is None or branch_name in pipeline_set:
            continue
        if branch_name not in eligible or worktree.dirty_paths:
            continue
        items.append(CleanupItem(kind="worktree", name=branch_name, path=worktree.path))

    for branch in inventory.branches:
        if branch.is_pipeline or branch.name in pipeline_set:
            continue
        if branch.name not in eligible or branch.dirty:
            continue
        items.append(CleanupItem(kind="local-branch", name=branch.name, path=None))

    return CleanupPlan(items=tuple(items))


def apply_cleanup(
    run_git: GitRunner,
    plan: CleanupPlan,
    *,
    dry_run: bool,
) -> None:
    worktrees = [item for item in plan.items if item.kind == "worktree"]
    branches = [item for item in plan.items if item.kind == "local-branch"]

    for item in worktrees:
        if dry_run:
            continue
        if item.path is None:
            continue
        run_git("worktree", "remove", str(item.path))

    for item in branches:
        if dry_run:
            continue
        run_git("branch", "-d", item.name)
