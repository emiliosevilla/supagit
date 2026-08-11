#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence
import re

from supagit_inventory import RepoInventory
from supagit_i18n import t

GitRunner = Callable[..., str]
RejectSensitive = Callable[[Sequence[str]], None]

PR_BODY = "Integrated by supagit sweeper."
PROMOTE_PR_BODY = "Promoted by supagit."
_PR_URL_NUMBER = re.compile(r"/pull/(\d+)\b")


def pr_number_from_create_output(output: str) -> int | None:
    """Parse the PR number from `gh pr create` stdout (PR URL)."""
    match = _PR_URL_NUMBER.search(output or "")
    if not match:
        return None
    return int(match.group(1))


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


@dataclass(frozen=True)
class PromoteGate:
    """How a pipeline destination branch must be updated on GitHub."""

    owner: str
    repo: str
    branch: str
    visibility: str
    requires_pull_request: bool
    rule_types: tuple[str, ...]

    @property
    def mode(self) -> str:
        return "pull_request" if self.requires_pull_request else "direct"


def parse_github_owner_repo(remote_url: str) -> tuple[str, str] | None:
    """Return (owner, repo) for GitHub remotes, else None."""
    raw = remote_url.strip()
    if not raw:
        return None
    normalized = raw.replace("\\", "/")
    lower = normalized.lower()
    if "github.com" not in lower:
        return None
    # git@github.com:owner/repo.git
    if lower.startswith("git@github.com:"):
        path = normalized.split(":", 1)[1]
    elif "github.com/" in lower:
        path = normalized.split("github.com/", 1)[1]
    else:
        return None
    path = path.removeprefix("/").removesuffix(".git")
    parts = [p for p in path.split("/") if p]
    if len(parts) < 2:
        return None
    return parts[0], parts[1]


def _gh_api_json(run_raw: Callable[..., str], endpoint: str) -> object:
    import json

    output = run_raw(["gh", "api", endpoint]).strip()
    if not output:
        return None
    return json.loads(output)


def inspect_promote_gate(
    run_raw: Callable[..., str],
    remote_url: str,
    branch: str,
) -> PromoteGate | None:
    """Inspect GitHub visibility + branch rules for *branch*.

    Returns None when the remote is not GitHub (caller keeps the direct
    merge+push path). Raises SweepError when GitHub cannot be queried.
    """
    from urllib.parse import quote

    slug = parse_github_owner_repo(remote_url)
    if slug is None:
        return None
    owner, repo = slug
    try:
        meta = _gh_api_json(run_raw, f"repos/{owner}/{repo}")
    except Exception as exc:
        raise SweepError(
            f"Could not read GitHub repository metadata for {owner}/{repo}."
        ) from exc
    visibility = "unknown"
    if isinstance(meta, dict):
        raw_vis = meta.get("visibility")
        if raw_vis:
            visibility = str(raw_vis)
        elif meta.get("private") is True:
            visibility = "private"
        elif meta.get("private") is False:
            visibility = "public"

    rule_types: list[str] = []
    requires_pr = False
    encoded_branch = quote(branch, safe="")
    try:
        rules = _gh_api_json(
            run_raw, f"repos/{owner}/{repo}/rules/branches/{encoded_branch}"
        )
        if isinstance(rules, list):
            for rule in rules:
                if not isinstance(rule, dict):
                    continue
                rtype = str(rule.get("type") or "")
                if rtype:
                    rule_types.append(rtype)
                if rtype == "pull_request":
                    requires_pr = True
    except Exception:
        # Rulesets API may be unavailable (older plans / permissions); fall back.
        rules = None

    if not requires_pr:
        try:
            protection = _gh_api_json(
                run_raw,
                f"repos/{owner}/{repo}/branches/{encoded_branch}/protection",
            )
            if isinstance(protection, dict):
                rule_types.append("classic_protection")
                reviews = protection.get("required_pull_request_reviews")
                if reviews:
                    requires_pr = True
                    rule_types.append("required_pull_request_reviews")
        except Exception:
            pass

    return PromoteGate(
        owner=owner,
        repo=repo,
        branch=branch,
        visibility=visibility,
        requires_pull_request=requires_pr,
        rule_types=tuple(dict.fromkeys(rule_types)),
    )


def ahead_behind(
    run_git: GitRunner,
    local: str,
    remote_ref: str,
    *,
    cwd: Path | None = None,
) -> tuple[int, int]:
    kw: dict = {}
    if cwd is not None:
        kw["cwd"] = cwd
    counts = run_git(
        "rev-list",
        "--left-right",
        "--count",
        f"{remote_ref}...{local}",
        **kw,
    ).strip()
    parts = counts.split()
    if len(parts) != 2:
        raise SweepError(
            f"Could not compute ahead/behind for {local} versus {remote_ref} "
            f"(got {counts!r})."
        )
    remote_only, local_only = (int(part) for part in parts)
    return remote_only, local_only


def _abort_merge_if_needed(run_git: GitRunner, *, cwd: Path | None = None) -> None:
    kw: dict = {}
    if cwd is not None:
        kw["cwd"] = cwd
    try:
        run_git("rev-parse", "--verify", "MERGE_HEAD", **kw)
    except Exception:
        return
    try:
        run_git("merge", "--abort", **kw)
    except Exception:
        pass


def _fetch_remote_branch(
    run_git: GitRunner,
    remote: str,
    branch: str,
    remote_ref: str,
    *,
    cwd: Path | None = None,
) -> None:
    kw: dict = {}
    if cwd is not None:
        kw["cwd"] = cwd
    try:
        run_git(
            "fetch",
            remote,
            f"refs/heads/{branch}:refs/remotes/{remote}/{branch}",
            **kw,
        )
    except Exception as exc:
        try:
            run_git("remote", "get-url", remote, **kw)
            raise SweepError(f"Could not fetch {remote}/{branch}.") from exc
        except SweepError:
            raise
        except Exception:
            try:
                run_git("rev-parse", "--verify", remote_ref, **kw)
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
    cwd: Path | None = None,
) -> SyncResult:
    kw: dict = {}
    if cwd is not None:
        kw["cwd"] = cwd

    try:
        current = run_git("branch", "--show-current", **kw).strip()
    except Exception:
        current = ""

    if current == branch:
        dirty = run_git("status", "--porcelain", **kw).strip()
        if dirty:
            raise SweepError(t("error_ff_dirty", branch=branch))

    remote_ref = f"{remote}/{branch}"
    _fetch_remote_branch(run_git, remote, branch, remote_ref, cwd=cwd)
    before = run_git("rev-parse", branch, **kw)
    remote_only, local_only = ahead_behind(run_git, branch, remote_ref, cwd=cwd)

    if remote_only == 0:
        return SyncResult(False, before, before)
    if local_only > 0:
        raise SweepError(
            f"Local branch {branch} has diverged from {remote_ref} "
            f"({remote_only}\t{local_only}). Synchronize with fast-forward only."
        )

    if dry_run:
        return SyncResult(True, before, run_git("rev-parse", remote_ref, **kw))

    if current != branch:
        try:
            run_git("merge-base", "--is-ancestor", branch, remote_ref, **kw)
        except Exception as exc:
            raise SweepError(
                f"Cannot fast-forward {branch} to {remote_ref} without checkout; "
                f"{branch} is not an ancestor of {remote_ref}."
            ) from exc
        run_git("update-ref", f"refs/heads/{branch}", remote_ref, **kw)
        after = run_git("rev-parse", branch, **kw)
        remote_tip = run_git("rev-parse", remote_ref, **kw)
        if after != remote_tip:
            run_git("update-ref", f"refs/heads/{branch}", before, **kw)
            raise SweepError(
                f"Fast-forward sync verification failed for {branch}: "
                f"tip {after} does not match {remote_ref} ({remote_tip})."
            )
        return SyncResult(True, before, after)

    try:
        run_git("merge", "--ff-only", remote_ref, **kw)
    except Exception as exc:
        _abort_merge_if_needed(run_git, cwd=cwd)
        run_git("reset", "--hard", before, **kw)
        raise SweepError(
            f"Fast-forward merge of {remote_ref} into {branch} failed."
        ) from exc

    after = run_git("rev-parse", branch, **kw)
    remote_tip = run_git("rev-parse", remote_ref, **kw)
    if after != remote_tip:
        run_git("reset", "--hard", before, **kw)
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
        # `gh pr create` prints the PR URL; it does not support --json/--jq.
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
            ]
        ).strip()
        number = pr_number_from_create_output(output)
        if number is None:
            number = self.find_open_pr(head, base)
        if number is None:
            raise SweepError(f"Could not create pull request for {head} into {base}.")
        return number

    def merge_pr(self, number: int, *, delete_branch: bool = True) -> None:
        if self._dry_run:
            return
        command = ["gh", "pr", "merge", str(number), "--merge"]
        if delete_branch:
            command.append("--delete-branch")
        self._run_raw(command)

    def create_promote_pr(self, head: str, base: str, title: str) -> int:
        if self._dry_run:
            return 0
        # Same as create_pr: stdout is the PR URL, not JSON.
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
                PROMOTE_PR_BODY,
            ]
        ).strip()
        number = pr_number_from_create_output(output)
        if number is None:
            number = self.find_open_pr(head, base)
        if number is None:
            raise SweepError(f"Could not create pull request for {head} into {base}.")
        return number


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


def assert_commits_for_pr(
    run_git: GitRunner,
    *,
    head: str,
    base: str,
    remote: str,
    cwd: Path,
) -> int:
    """Return how many commits head is ahead of base; raise if the PR would be empty."""
    remote_base = f"{remote}/{base}"
    try:
        run_git(
            "fetch",
            remote,
            f"refs/heads/{base}:refs/remotes/{remote}/{base}",
            cwd=cwd,
        )
    except Exception:
        pass

    base_ref = base
    try:
        run_git("rev-parse", "--verify", remote_base, cwd=cwd)
        base_ref = remote_base
    except Exception:
        try:
            run_git("rev-parse", "--verify", base, cwd=cwd)
        except Exception as exc:
            raise SweepError(
                f"Cannot resolve base branch {base!r} (or {remote_base}) to check for an empty PR."
            ) from exc

    try:
        run_git("rev-parse", "--verify", head, cwd=cwd)
    except Exception as exc:
        raise SweepError(
            f"Cannot resolve head branch {head!r} to check for an empty PR."
        ) from exc

    raw = run_git("rev-list", "--count", f"{base_ref}..{head}", cwd=cwd).strip()
    try:
        count = int(raw)
    except ValueError as exc:
        raise SweepError(
            f"Could not count commits for {base_ref}..{head} (got {raw!r})."
        ) from exc

    if count == 0:
        raise SweepError(
            t(
                "error_empty_pr",
                head=head,
                base=base,
                base_ref=base_ref,
            )
        )
    return count


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
        raise SweepError(
            t("error_nothing_to_integrate", branch=branch, base=base)
        )

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
    else:
        ff_sync_branch(
            run_git,
            branch,
            remote,
            dry_run=dry_run,
            cwd=cwd,
        )

    push_branch(run_git, remote, branch, cwd=cwd, dry_run=dry_run)

    pr_number = gh.find_open_pr(branch, base)
    if pr_number is None:
        assert_commits_for_pr(
            run_git,
            head=branch,
            base=base,
            remote=remote,
            cwd=cwd,
        )
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
