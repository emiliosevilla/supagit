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
    "publish_only": "situation_finding_publish_only",
    "commit_feature": "situation_finding_commit_feature",
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


def format_blocked_error(
    finding: Finding, *, branch: str, upstream: str | None
) -> str:
    if finding.cure_id == "stop_diverged":
        up = upstream or f"(no upstream for {branch})"
        return t("situation_error_diverged", branch=branch, upstream=up)
    if finding.cure_id == "stop_dirty_feature":
        return t("situation_error_dirty_feature", branch=branch)
    return t("situation_error_diverged", branch=branch, upstream=upstream or branch)


def _upstream_label(sync: BranchSync | None, *, remote: str, name: str) -> str:
    if sync is not None and sync.upstream:
        return sync.upstream
    return f"{remote}/{name}"


def plan_cure_lines(situation: Situation, *, remote: str) -> tuple[str, ...]:
    """Ordered extra plan lines for SAFE_CURE findings (ff only; publish stays in menu)."""
    lines: list[str] = []
    for finding, sync in zip(
        [f for f in situation.findings if f.role == "feature"],
        situation.features,
    ):
        if finding.policy != PolicyClass.SAFE_CURE:
            continue
        if finding.cure_id == "commit_feature":
            lines.append(t("plan_commit_feature_item", branch=sync.name))
            continue
        if finding.cure_id != "ff_only":
            continue
        lines.append(
            t(
                "plan_ff_feature_item",
                branch=sync.name,
                upstream=_upstream_label(sync, remote=remote, name=sync.name),
            )
        )

    pipeline_ff = pipeline0_ff_line(situation, remote=remote)
    if pipeline_ff is not None:
        lines.append(pipeline_ff)
    return tuple(lines)


def feature_ff_line(
    situation: Situation, branch: str, *, remote: str
) -> str | None:
    for finding, sync in zip(
        [f for f in situation.findings if f.role == "feature"],
        situation.features,
    ):
        if sync.name != branch:
            continue
        if (
            finding.policy == PolicyClass.SAFE_CURE
            and finding.cure_id == "ff_only"
        ):
            return t(
                "plan_ff_feature_item",
                branch=sync.name,
                upstream=_upstream_label(sync, remote=remote, name=sync.name),
            )
        return None
    return None


def feature_commit_line(situation: Situation, branch: str) -> str | None:
    for finding, sync in zip(
        [f for f in situation.findings if f.role == "feature"],
        situation.features,
    ):
        if sync.name != branch:
            continue
        if (
            finding.policy == PolicyClass.SAFE_CURE
            and finding.cure_id == "commit_feature"
        ):
            return t("plan_commit_feature_item", branch=sync.name)
        return None
    return None


def pipeline0_ff_line(situation: Situation, *, remote: str) -> str | None:
    if situation.pipeline0 is None:
        return None
    p0 = situation.pipeline0
    for finding in situation.findings:
        if finding.role != "pipeline0":
            continue
        if finding.cure_id in {"ff_only", "publish_then_ff"}:
            return t(
                "plan_ff_item",
                branch=p0.name,
                upstream=_upstream_label(p0, remote=remote, name=p0.name),
            )
        return None
    return None


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


def worktree_dirty_for_branch(
    git, name: str, worktree_path: str | None
) -> bool:
    """Dirty only counts when this branch is the worktree HEAD.

    Measuring ``status --porcelain`` in a shared main checkout while another
    branch is checked out must not attribute that dirtiness to pipeline[0].
    A branch with no worktree cannot own working-tree dirtiness.
    """
    if worktree_path is None:
        return False
    status_kwargs: dict = {"cwd": worktree_path}
    try:
        current = git("branch", "--show-current", **status_kwargs).strip()
    except Exception:
        return False
    if current != name:
        return False
    return bool(git("status", "--porcelain", **status_kwargs).strip())


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

    dirty = worktree_dirty_for_branch(git, name, worktree_path)

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
    if sync == SyncStatus.DIVERGED:
        return Finding(PolicyClass.BLOCKED, "stop_diverged", sync, dirty, role)
    if sync == SyncStatus.BEHIND_ONLY and not dirty:
        return Finding(PolicyClass.SAFE_CURE, "ff_only", sync, dirty, role)
    if role == "pipeline0" and dirty and sync in {
        SyncStatus.BEHIND_ONLY,
        SyncStatus.AHEAD_ONLY,
        SyncStatus.IN_SYNC,
    }:
        if sync == SyncStatus.BEHIND_ONLY:
            return Finding(PolicyClass.SAFE_CURE, "publish_then_ff", sync, dirty, role)
        return Finding(PolicyClass.SAFE_CURE, "publish_only", sync, dirty, role)
    if role == "feature" and dirty and sync == SyncStatus.BEHIND_ONLY:
        return Finding(PolicyClass.BLOCKED, "stop_dirty_feature", sync, dirty, role)
    if role == "feature" and dirty:
        return Finding(PolicyClass.SAFE_CURE, "commit_feature", sync, dirty, role)
    if sync == SyncStatus.BEHIND_ONLY:
        return Finding(PolicyClass.SAFE_CURE, "ff_only", sync, dirty, role)
    return Finding(PolicyClass.INFO, "none", sync, dirty, role)
