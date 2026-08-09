#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

GitRunner = Callable[..., str]


class SweepError(RuntimeError):
    """Fail-closed sweep/sync error mapped to ShipError by Pipeline."""


@dataclass(frozen=True)
class SyncResult:
    changed: bool
    before: str
    after: str


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
