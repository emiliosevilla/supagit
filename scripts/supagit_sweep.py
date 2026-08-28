#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence
import os
import re
import shlex
import subprocess
import sys
import time

from supagit_inventory import RepoInventory
from supagit_i18n import t

# Patchable in tests (backoff between UNKNOWN mergeability polls).
sleep = time.sleep

GitRunner = Callable[..., str]
RejectSensitive = Callable[[Sequence[str], Path], Sequence[str]]
IsSensitive = Callable[[str], bool]
ExplainFn = Callable[[str], None]
ConfirmFn = Callable[[str], bool]
EditorFn = Callable[[Sequence[str], Path], None]

_CYAN = "\033[36m"
_GREEN = "\033[32m"
_RESET = "\033[0m"
_YES_ANSWERS = frozenset({"", "y", "yes", "s", "si", "sí"})

PR_BODY = "Integrated by supagit sweeper."
PROMOTE_PR_BODY = "Promoted by supagit."
_PR_URL_NUMBER = re.compile(r"/pull/(\d+)\b")


def status_entries(status: str) -> list[tuple[str, str]]:
    """Return porcelain status codes and paths, excluding ignored entries."""
    return [
        (line[:2], line[3:])
        for line in status.splitlines()
        if len(line) >= 4 and line[:2] != "!!"
    ]


def has_status_changes(status: str) -> bool:
    return bool(status_entries(status))


def stage_safe_paths(
    run_git: GitRunner,
    *,
    status: str,
    safe_paths: Sequence[str],
    cwd: Path,
) -> None:
    """Stage tracked changes with ``-u`` so ignored parents cannot reject them."""
    safe = {path for path in safe_paths if path}
    tracked: list[str] = []
    untracked: list[str] = []
    status_paths = {path for _, path in status_entries(status)}

    for code, path in status_entries(status):
        if path not in safe:
            continue
        if code == "??":
            untracked.append(path)
        else:
            tracked.append(path)

    # The sensitive-path guard may add a new .gitignore path not present in status.
    untracked.extend(path for path in safe_paths if path not in status_paths)
    if tracked:
        run_git("add", "-u", "--", *tracked, cwd=cwd)
    if untracked:
        run_git("add", "--", *untracked, cwd=cwd)


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
class SweepResult:
    """Outcome of a sweep action that may skip instead of fail-closed."""

    skipped: bool = False
    reason: str = ""


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

    def _run(self, command: list[str]) -> str:
        return self._run_raw(command)

    def _run_status(self, command: list[str]) -> tuple[int, str, str]:
        """Run without raising; return (returncode, stdout, stderr)."""
        try:
            out = self._run_raw(command)
            return 0, out, ""
        except Exception as exc:
            # run_raw in supagit collapses stdout/stderr into the exception text.
            return 1, "", str(exc)

    def ensure_ready(self) -> None:
        """Ensure gh works; refresh expired tokens, then interactive login.

        When the keyring token is stale, `gh auth status` fails even though the
        user previously logged in. Try `gh auth refresh -h github.com` once.
        On refresh failure with a TTY, launch `gh auth login -h github.com`
        once (web/device), then re-verify. Without a TTY, fail closed — never
        hang, and never print “run this yourself” as the primary fix.
        """
        if self._dry_run:
            return
        try:
            self._run(["gh", "auth", "status"])
            return
        except FileNotFoundError as exc:
            raise SweepError(
                t(
                    "error_gh_missing",
                    command="brew install gh   # macOS",
                )
            ) from exc
        except Exception as exc:
            detail = str(exc)
            lowered = detail.lower()
            if not any(
                marker in lowered
                for marker in ("token", "auth", "logged in", "keyring")
            ):
                raise SweepError(
                    t("error_gh_not_authenticated", detail=detail)
                ) from exc
        # Stale/expired token — attempt silent refresh, then verify.
        try:
            self._run(["gh", "auth", "refresh", "-h", "github.com"])
        except Exception as refresh_exc:
            if not sys.stdin.isatty():
                raise SweepError(
                    t(
                        "error_gh_refresh_failed",
                        detail=str(refresh_exc),
                    )
                ) from refresh_exc
            # TTY: launch interactive login once (web/device), then re-verify.
            try:
                self._run(["gh", "auth", "login", "-h", "github.com"])
            except Exception as login_exc:
                raise SweepError(
                    t(
                        "error_gh_login_failed",
                        refresh_detail=str(refresh_exc),
                        detail=str(login_exc),
                    )
                ) from login_exc
            try:
                self._run(["gh", "auth", "status"])
                return
            except Exception as status_exc:
                raise SweepError(
                    t(
                        "error_gh_still_unauthenticated",
                        detail=str(status_exc),
                    )
                ) from status_exc
        try:
            self._run(["gh", "auth", "status"])
        except Exception as exc:
            raise SweepError(
                t(
                    "error_gh_still_unauthenticated",
                    detail=str(exc),
                )
            ) from exc

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

    def pr_mergeable(self, number: int) -> str:
        """Return GitHub mergeable: MERGEABLE, CONFLICTING, or UNKNOWN."""
        if self._dry_run:
            return "MERGEABLE"
        import json

        output = self._run_raw(
            [
                "gh",
                "pr",
                "view",
                str(number),
                "--json",
                "mergeable",
            ]
        ).strip()
        try:
            data = json.loads(output)
        except json.JSONDecodeError as exc:
            raise SweepError(
                f"Could not parse mergeability for pull request #{number}."
            ) from exc
        return str(data.get("mergeable") or "UNKNOWN")

    def pr_state(self, number: int) -> str:
        """Return GitHub PR state: OPEN, MERGED, or CLOSED."""
        if self._dry_run:
            return "MERGED"
        import json

        output = self._run_raw(
            [
                "gh",
                "pr",
                "view",
                str(number),
                "--json",
                "state",
            ]
        ).strip()
        try:
            data = json.loads(output)
        except json.JSONDecodeError as exc:
            raise SweepError(
                f"Could not parse state for pull request #{number}."
            ) from exc
        return str(data.get("state") or "OPEN").upper()

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

    def merge_pr(
        self, number: int, *, delete_branch: bool = True, admin: bool = False
    ) -> None:
        """Merge via ladder: plain merge → --auto → --admin.

        ``admin`` is kept for call-site compatibility but is ignored: the ladder
        always ends with ``--admin`` after policy blocks, and never starts there.
        """
        del admin  # ladder owns admin escalation
        if self._dry_run:
            return

        def _cmd(*, auto: bool = False, use_admin: bool = False) -> list[str]:
            command = ["gh", "pr", "merge", str(number), "--merge"]
            if auto:
                command.append("--auto")
            if use_admin:
                command.append("--admin")
            if delete_branch:
                command.append("--delete-branch")
            return command

        first = _cmd()
        first_exc: Exception
        try:
            self._run(first)
            return
        except Exception as exc:
            first_exc = exc

        detail = str(first_exc).lower()
        authish = any(
            marker in detail
            for marker in ("token", "auth", "permission", "forbidden", "403")
        )
        policyish = "policy" in detail or "not mergeable" in detail

        # Auth/permission failure: refresh token once, then retry the same merge.
        if authish:
            try:
                self._run(["gh", "auth", "refresh", "-h", "github.com"])
            except Exception:
                pass
            try:
                self._run(first)
                return
            except Exception:
                raise first_exc

        # Branch-policy / not-mergeable: climb merge → --auto → --admin.
        # `--auto` exit 0 only arms auto-merge; wait for MERGED before success.
        if policyish:
            auto_armed = False
            try:
                self._run(_cmd(auto=True))
                auto_armed = True
            except Exception:
                pass

            if auto_armed:
                if wait_until_pr_merged(self, number):
                    return
                print(t("note_pr_auto_merge_armed", number=number))

            try:
                self._run(_cmd(use_admin=True))
                return
            except Exception as admin_exc:
                if auto_armed:
                    raise SweepError(
                        t("error_pr_auto_merge_not_completed", number=number)
                    ) from admin_exc
                raise first_exc

        raise first_exc

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


def poll_pr_mergeable(
    gh: GhClient,
    number: int,
    *,
    attempts: int = 3,
    delays: Sequence[float] = (1.0, 2.0),
    sleeper: Callable[[float], None] | None = None,
) -> str:
    """Poll GitHub mergeability up to ``attempts`` times when status is UNKNOWN."""
    wait = sleeper or sleep
    last = "UNKNOWN"
    for index in range(attempts):
        last = gh.pr_mergeable(number)
        if last != "UNKNOWN":
            return last
        if index >= attempts - 1:
            break
        delay = delays[index] if index < len(delays) else delays[-1]
        wait(delay)
    return last


def wait_until_pr_merged(
    gh: GhClient,
    number: int,
    *,
    attempts: int = 5,
    delays: Sequence[float] = (1.0, 2.0, 3.0, 5.0),
    sleeper: Callable[[float], None] | None = None,
) -> bool:
    """Poll until the PR state is MERGED. Returns False on timeout."""
    wait = sleeper or sleep
    for index in range(attempts):
        if gh.pr_state(number) == "MERGED":
            return True
        if index >= attempts - 1:
            break
        delay = delays[index] if index < len(delays) else delays[-1]
        wait(delay)
    return gh.pr_state(number) == "MERGED"


def commit_dirty_tree(
    run_git: GitRunner,
    *,
    cwd: Path,
    message: str,
    reject_sensitive: RejectSensitive,
    dry_run: bool,
    is_sensitive: IsSensitive | None = None,
) -> bool:
    status = run_git("status", "--porcelain", cwd=cwd)
    status_paths = [path for _, path in status_entries(status)]
    if not status_paths:
        return False

    safe_paths = [path for path in reject_sensitive(status_paths, cwd) if path]
    if not safe_paths:
        raise SweepError(t("error_only_secrets_remaining"))

    if dry_run:
        return True

    safe_set = set(safe_paths)
    sense = is_sensitive or (lambda path: path not in safe_set)

    stage_safe_paths(
        run_git,
        status=status,
        safe_paths=safe_paths,
        cwd=cwd,
    )
    staged = run_git("diff", "--cached", "--name-only", cwd=cwd)
    staged_paths = [path for path in staged.splitlines() if path]
    leaked = [path for path in staged_paths if sense(path)]
    if leaked:
        # Novice chaos: secrets may already be in the index (e.g. prior `git add -A`).
        run_git("restore", "--staged", "--", *leaked, cwd=cwd)
        staged = run_git("diff", "--cached", "--name-only", cwd=cwd)
        staged_paths = [path for path in staged.splitlines() if path]
    if not staged_paths:
        raise SweepError(t("error_only_secrets_remaining"))
    still_sensitive = [path for path in staged_paths if sense(path)]
    if still_sensitive:
        raise SweepError(
            t("error_only_secrets", paths=", ".join(sorted(still_sensitive)))
        )
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
    """Return how many commits head is ahead of base (0 when the range is empty)."""
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

    return count


def remote_heads_exist(
    run_git: GitRunner,
    remote: str,
    branch: str,
    *,
    cwd: Path | None = None,
) -> bool:
    """True when ``remote`` currently has ``refs/heads/branch`` (live ls-remote)."""
    kw: dict = {}
    if cwd is not None:
        kw["cwd"] = cwd
    try:
        out = run_git(
            "ls-remote",
            "--heads",
            remote,
            f"refs/heads/{branch}",
            **kw,
        )
    except Exception:
        return False
    return bool(out.strip())


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


def conflicted_paths(run_git: GitRunner, *, cwd: Path) -> list[str]:
    """Return unmerged paths left by a conflicted rebase/merge."""
    try:
        out = run_git("diff", "--name-only", "--diff-filter=U", cwd=cwd)
    except Exception:
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


def _colour_tty_enabled() -> bool:
    return bool(sys.stdout.isatty() and os.environ.get("TERM") != "dumb")


def default_explain_rebase(message: str) -> None:
    if _colour_tty_enabled():
        print(f"{_CYAN}{message}{_RESET}")
    else:
        print(message)


def default_confirm_rebase_continue(prompt: str) -> bool:
    """Green [Y/n] gate; Enter = yes. Non-TTY returns False (cannot guide)."""
    if not sys.stdin.isatty():
        return False
    rendered = f"{prompt}{t('confirm_suffix')}"
    if _colour_tty_enabled():
        rendered = f"{_GREEN}{rendered}{_RESET}"
    answer = input(rendered).strip().lower()
    if answer in _YES_ANSWERS:
        return True
    if answer in {"n", "no"}:
        return False
    return True


def open_conflict_editor(paths: Sequence[str], *, cwd: Path) -> None:
    """Open conflicted files in $VISUAL / $EDITOR (default nano)."""
    if not paths:
        return
    raw = os.environ.get("VISUAL") or os.environ.get("EDITOR") or "nano"
    cmd = shlex.split(raw) + list(paths)
    subprocess.run(cmd, cwd=str(cwd), check=False)


def _abort_rebase_quietly(run_git: GitRunner, *, cwd: Path) -> None:
    try:
        run_git("rebase", "--abort", cwd=cwd)
    except Exception:
        pass


def _guide_rebase_conflicts(
    run_git: GitRunner,
    *,
    branch: str,
    onto_ref: str,
    cwd: Path,
    explain: ExplainFn,
    confirm_continue: ConfirmFn,
    open_editor: EditorFn,
) -> None:
    """Tutor loop: list files → editor → confirm → add + rebase --continue."""
    while True:
        paths = conflicted_paths(run_git, cwd=cwd)
        files = "\n".join(f"  • {path}" for path in paths) or "  • (unlisted)"
        explain(
            t(
                "explain_rebase_conflict",
                branch=branch,
                base_ref=onto_ref,
                files=files,
            )
        )
        open_editor(paths, cwd=cwd)
        if not confirm_continue(t("confirm_rebase_continue")):
            raise SweepError(
                t("error_rebase_conflict_cancelled", branch=branch, base_ref=onto_ref)
            )
        if paths:
            run_git("add", *paths, cwd=cwd)
        else:
            run_git("add", "-u", cwd=cwd)
        try:
            # Avoid a second EDITOR popup for the rebase commit message.
            run_git("-c", "core.editor=true", "rebase", "--continue", cwd=cwd)
            return
        except Exception as cont_exc:
            if conflicted_paths(run_git, cwd=cwd):
                continue
            raise SweepError(
                t("error_rebase_conflict", branch=branch, base_ref=onto_ref)
            ) from cont_exc


def rebase_branch_onto(
    run_git: GitRunner,
    branch: str,
    onto_ref: str,
    *,
    cwd: Path,
    dry_run: bool,
    force: bool = False,
    explain: ExplainFn | None = None,
    confirm_continue: ConfirmFn | None = None,
    open_editor: EditorFn | None = None,
    interactive: bool | None = None,
) -> bool:
    """Rebase ``branch`` onto ``onto_ref`` when the base moved ahead. Returns True if rebased.

    When ``force`` is True (CONFLICTING PR recovery), skip the ancestor/behind
    short-circuits and always attempt the rebase.

    On conflicts: keep rebase state, list files, open $EDITOR / tutor loop,
    then ``git add`` + ``rebase --continue`` on confirm. Abort only on explicit
    cancel (or when interactive guidance is impossible).
    """
    if not force:
        try:
            run_git("merge-base", "--is-ancestor", onto_ref, branch, cwd=cwd)
            return False
        except Exception:
            pass

        try:
            behind = int(
                run_git("rev-list", "--count", f"{branch}..{onto_ref}", cwd=cwd).strip()
            )
        except ValueError as exc:
            raise SweepError(
                f"Could not count commits between {branch} and {onto_ref} before rebase."
            ) from exc
        if behind <= 0:
            return False

    if dry_run:
        return True

    current = ""
    try:
        current = run_git("branch", "--show-current", cwd=cwd).strip()
    except Exception:
        pass

    switched = False
    if current != branch:
        run_git("checkout", branch, cwd=cwd)
        switched = True

    explain_fn = explain or default_explain_rebase
    confirm_fn = confirm_continue or default_confirm_rebase_continue
    editor_fn = open_editor or open_conflict_editor
    can_guide = sys.stdin.isatty() if interactive is None else interactive

    try:
        run_git("rebase", onto_ref, cwd=cwd)
    except Exception as exc:
        paths = conflicted_paths(run_git, cwd=cwd)
        if not paths and not can_guide:
            _abort_rebase_quietly(run_git, cwd=cwd)
            if switched and current:
                try:
                    run_git("checkout", current, cwd=cwd)
                except Exception:
                    pass
            raise SweepError(
                t("error_rebase_conflict", branch=branch, base_ref=onto_ref)
            ) from exc

        if not can_guide and confirm_continue is None:
            # Keep state only when we can guide; otherwise clean abort.
            _abort_rebase_quietly(run_git, cwd=cwd)
            if switched and current:
                try:
                    run_git("checkout", current, cwd=cwd)
                except Exception:
                    pass
            raise SweepError(
                t(
                    "error_rebase_conflict_needs_interactive",
                    branch=branch,
                    base_ref=onto_ref,
                )
            ) from exc

        try:
            _guide_rebase_conflicts(
                run_git,
                branch=branch,
                onto_ref=onto_ref,
                cwd=cwd,
                explain=explain_fn,
                confirm_continue=confirm_fn,
                open_editor=editor_fn,
            )
        except SweepError:
            _abort_rebase_quietly(run_git, cwd=cwd)
            if switched and current:
                try:
                    run_git("checkout", current, cwd=cwd)
                except Exception:
                    pass
            raise

    if switched and current:
        run_git("checkout", current, cwd=cwd)
    return True


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
    is_sensitive: IsSensitive | None = None,
    explain: ExplainFn | None = None,
    confirm_continue: ConfirmFn | None = None,
    open_editor: EditorFn | None = None,
    interactive: bool | None = None,
) -> SweepResult:
    if contained_in_first:
        print(t("note_nothing_to_merge", branch=branch, base=base))
        return SweepResult(skipped=True, reason="already merged")

    gh.ensure_ready()
    gh.ensure_github_remote(remote_url)

    status = run_git("status", "--porcelain", cwd=cwd)
    if has_status_changes(status):
        message = message_provider()
        commit_dirty_tree(
            run_git,
            cwd=cwd,
            message=message,
            reject_sensitive=reject_sensitive,
            dry_run=dry_run,
            is_sensitive=is_sensitive,
        )
    elif remote_heads_exist(run_git, remote, branch, cwd=cwd):
        # Fast-forward only when the remote feature still exists. After a merged
        # PR GitHub often deletes the head branch; a stale origin/<feature> must
        # not block republishing via push + new PR.
        ff_sync_branch(
            run_git,
            branch,
            remote,
            dry_run=dry_run,
            cwd=cwd,
        )

    push_branch(run_git, remote, branch, cwd=cwd, dry_run=dry_run)

    remote_base = f"{remote}/{base}"
    try:
        run_git(
            "fetch",
            remote,
            f"refs/heads/{base}:refs/remotes/{remote}/{base}",
            cwd=cwd,
        )
    except Exception as exc:
        raise SweepError(f"Could not fetch {remote_base} before integrating.") from exc

    rebased = rebase_branch_onto(
        run_git,
        branch,
        remote_base,
        cwd=cwd,
        dry_run=dry_run,
        explain=explain,
        confirm_continue=confirm_continue,
        open_editor=open_editor,
        interactive=interactive,
    )
    if rebased and not dry_run:
        run_git("push", "--force-with-lease", remote, branch, cwd=cwd)

    pr_number = gh.find_open_pr(branch, base)
    if pr_number is None:
        count = assert_commits_for_pr(
            run_git,
            head=branch,
            base=base,
            remote=remote,
            cwd=cwd,
        )
        if count == 0:
            print(t("note_nothing_to_merge", branch=branch, base=base))
            return SweepResult(skipped=True, reason="already merged")
        title = f"supagit: integrate {branch} into {base}"
        pr_number = gh.create_pr(branch, base, title)

    mergeable = poll_pr_mergeable(gh, pr_number)
    if mergeable == "CONFLICTING":
        # Rebase onto current base and push, then re-poll before failing closed.
        recovered = rebase_branch_onto(
            run_git,
            branch,
            remote_base,
            cwd=cwd,
            dry_run=dry_run,
            force=True,
            explain=explain,
            confirm_continue=confirm_continue,
            open_editor=open_editor,
            interactive=interactive,
        )
        if recovered and not dry_run:
            run_git("push", "--force-with-lease", remote, branch, cwd=cwd)
        mergeable = poll_pr_mergeable(gh, pr_number)
        if mergeable == "CONFLICTING":
            raise SweepError(
                t(
                    "error_pr_merge_conflict",
                    head=branch,
                    base=base,
                    number=pr_number,
                )
            )

    gh.merge_pr(pr_number)

    if dry_run:
        return SweepResult(skipped=False)

    try:
        run_git(
            "fetch",
            remote,
            f"refs/heads/{base}:refs/remotes/{remote}/{base}",
            cwd=cwd,
        )
    except Exception as exc:
        raise SweepError(f"Could not fetch {remote}/{base} after merge.") from exc

    return SweepResult(skipped=False)


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


def delete_merged_local_branch(
    run_git: GitRunner,
    name: str,
    *,
    into: str,
    dry_run: bool,
) -> None:
    """Delete a local branch only after verifying it is merged into ``into``.

    After a GitHub PR merge, local ``work`` often matches ``main`` while still
    being ahead of a stale ``origin/work``. Plain ``git branch -d`` then refuses
    even though the branch is safely contained in HEAD. Force-delete (``-D``) is
    only used after the ancestor check.
    """
    try:
        run_git("merge-base", "--is-ancestor", name, into)
    except Exception as exc:
        raise SweepError(
            t("error_cleanup_not_merged", branch=name, base=into)
        ) from exc
    if dry_run:
        return
    try:
        run_git("branch", "-d", name)
    except Exception:
        run_git("branch", "-D", name)


def apply_cleanup(
    run_git: GitRunner,
    plan: CleanupPlan,
    *,
    dry_run: bool,
    into: str = "HEAD",
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
        delete_merged_local_branch(
            run_git, item.name, into=into, dry_run=dry_run
        )
