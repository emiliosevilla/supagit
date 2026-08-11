# scripts/supagit_situation.py
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from supagit_i18n import t


class SyncStatus(str, Enum):
    IN_SYNC = "in_sync"
    AHEAD_ONLY = "ahead_only"
    BEHIND_ONLY = "behind_only"
    DIVERGED = "diverged"
    NO_UPSTREAM = "no_upstream"


class PolicyClass(str, Enum):
    SAFE_CURE = "safe_cure"
    BLOCKED = "blocked"
    INFO = "info"


class SituationError(RuntimeError):
    pass


@dataclass(frozen=True)
class BranchSync:
    name: str
    upstream: str | None
    sync: SyncStatus
    ahead: int
    behind: int
    dirty: bool
    worktree_path: str | None


@dataclass(frozen=True)
class Finding:
    policy: PolicyClass
    cure_id: str
    sync: SyncStatus
    dirty: bool
    role: str


@dataclass(frozen=True)
class Situation:
    current_branch: str
    dirty: bool
    pipeline0: BranchSync | None
    features: tuple[BranchSync, ...]
    findings: tuple[Finding, ...]
    gh_ready: bool | None
    self_update: SyncStatus | None


_FINDING_I18N: dict[str, str] = {
    "ff_only": "situation_finding_ff_only",
    "publish_then_ff": "situation_finding_publish_then_ff",
    "stop_diverged": "situation_finding_stop_diverged",
    "stop_dirty_feature": "situation_finding_stop_dirty_feature",
    "none": "situation_finding_none",
}


def render_preflight(situation: Situation) -> str:
    lines = [t("situation_preflight_header")]
    for finding in situation.findings:
        key = _FINDING_I18N.get(finding.cure_id)
        if key is None:
            continue
        lines.append(t(key, role=finding.role))
    return "\n".join(lines)


def parse_ahead_behind(text: str) -> tuple[int, int]:
    parts = text.strip().split()
    if len(parts) != 2:
        raise SituationError(f"Malformed ahead/behind counts: {text!r}")
    try:
        return int(parts[0]), int(parts[1])
    except ValueError as exc:
        raise SituationError(f"Malformed ahead/behind counts: {text!r}") from exc


def classify_sync_counts(ahead: int, behind: int) -> SyncStatus:
    if ahead < 0 or behind < 0:
        raise ValueError(f"ahead/behind must be >= 0 (got {ahead}, {behind})")
    if ahead and behind:
        return SyncStatus.DIVERGED
    if ahead:
        return SyncStatus.AHEAD_ONLY
    if behind:
        return SyncStatus.BEHIND_ONLY
    return SyncStatus.IN_SYNC


def build_branch_sync(
    git,
    name: str,
    *,
    remote: str,
    role: str,
    worktree_path: str | None,
) -> tuple[BranchSync, Finding]:
    try:
        git("rev-parse", "--verify", f"refs/heads/{name}")
    except Exception as exc:
        raise SituationError(f"Branch not found: {name}") from exc

    status_kwargs: dict = {}
    if worktree_path is not None:
        status_kwargs["cwd"] = worktree_path
    dirty = bool(git("status", "--porcelain", **status_kwargs).strip())

    try:
        upstream = git("rev-parse", "--abbrev-ref", f"{name}@{{upstream}}").strip()
    except Exception:
        sync = BranchSync(
            name=name,
            upstream=None,
            sync=SyncStatus.NO_UPSTREAM,
            ahead=0,
            behind=0,
            dirty=dirty,
            worktree_path=worktree_path,
        )
        finding = classify_ref_finding(
            SyncStatus.NO_UPSTREAM, dirty=dirty, role=role
        )
        return sync, finding

    counts = git(
        "rev-list",
        "--left-right",
        "--count",
        f"{upstream}...{name}",
    )
    behind, ahead = parse_ahead_behind(counts)
    sync_status = classify_sync_counts(ahead=ahead, behind=behind)

    sync = BranchSync(
        name=name,
        upstream=upstream,
        sync=sync_status,
        ahead=ahead,
        behind=behind,
        dirty=dirty,
        worktree_path=worktree_path,
    )
    finding = classify_ref_finding(sync_status, dirty=dirty, role=role)
    return sync, finding


def classify_ref_finding(
    sync: SyncStatus, *, dirty: bool, role: str
) -> Finding:
    if sync is SyncStatus.DIVERGED:
        return Finding(PolicyClass.BLOCKED, "stop_diverged", sync, dirty, role)
    if sync is SyncStatus.BEHIND_ONLY and not dirty:
        return Finding(PolicyClass.SAFE_CURE, "ff_only", sync, dirty, role)
    if role == "pipeline0" and dirty and sync in {
        SyncStatus.BEHIND_ONLY,
        SyncStatus.AHEAD_ONLY,
        SyncStatus.IN_SYNC,
    }:
        if sync is SyncStatus.BEHIND_ONLY:
            return Finding(PolicyClass.SAFE_CURE, "publish_then_ff", sync, dirty, role)
        return Finding(PolicyClass.SAFE_CURE, "publish_only", sync, dirty, role)
    if role == "feature" and dirty and sync is SyncStatus.BEHIND_ONLY:
        return Finding(PolicyClass.BLOCKED, "stop_dirty_feature", sync, dirty, role)
    if sync is SyncStatus.BEHIND_ONLY:
        return Finding(PolicyClass.SAFE_CURE, "ff_only", sync, dirty, role)
    return Finding(PolicyClass.INFO, "none", sync, dirty, role)
