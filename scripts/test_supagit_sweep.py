#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Callable, Sequence

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import supagit_inventory
import supagit_layout
import supagit_menu
import supagit_sweep
from supagit_inventory import BranchInfo, RepoInventory, WorktreeInfo
from supagit_layout import RepoLayout


def _run(cwd: Path, *args: str) -> str:
    completed = subprocess.run(
        args, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True
    )
    return completed.stdout.strip()


class RepoLayoutTests(unittest.TestCase):
    def test_main_checkout_is_not_linked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _run(root, "git", "init", "-b", "dev")
            _run(root, "git", "config", "user.email", "t@example.com")
            _run(root, "git", "config", "user.name", "t")
            (root / "README").write_text("x\n", encoding="utf-8")
            _run(root, "git", "add", "README")
            _run(root, "git", "commit", "-m", "init")
            layout = supagit_layout.resolve_repo_layout(root)
            self.assertEqual(layout.launch_root, root.resolve())
            self.assertEqual(layout.main_root, root.resolve())
            self.assertFalse(layout.is_linked_launch)

    def test_linked_worktree_resolves_main_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "main"
            wt = Path(directory) / "wt"
            root.mkdir()
            _run(root, "git", "init", "-b", "dev")
            _run(root, "git", "config", "user.email", "t@example.com")
            _run(root, "git", "config", "user.name", "t")
            (root / "README").write_text("x\n", encoding="utf-8")
            _run(root, "git", "add", "README")
            _run(root, "git", "commit", "-m", "init")
            _run(root, "git", "branch", "feature/x")
            _run(root, "git", "worktree", "add", str(wt), "feature/x")
            layout = supagit_layout.resolve_repo_layout(wt)
            self.assertTrue(layout.is_linked_launch)
            self.assertEqual(layout.launch_root, wt.resolve())
            self.assertEqual(layout.main_root, root.resolve())


class InventoryTests(unittest.TestCase):
    def test_parse_worktree_porcelain_lists_main_and_linked(self) -> None:
        text = """worktree /repo
HEAD abc
branch refs/heads/dev

worktree /repo-feature
HEAD def
branch refs/heads/feature/x
"""
        parsed = supagit_inventory.parse_worktree_porcelain(text)
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0]["path"], "/repo")
        self.assertEqual(parsed[0]["branch"], "dev")
        self.assertEqual(parsed[1]["branch"], "feature/x")

    def test_feature_not_contained_is_integrable_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _run(root, "git", "init", "-b", "dev")
            _run(root, "git", "config", "user.email", "t@example.com")
            _run(root, "git", "config", "user.name", "t")
            (root / "README").write_text("x\n", encoding="utf-8")
            _run(root, "git", "add", "README")
            _run(root, "git", "commit", "-m", "init")
            _run(root, "git", "checkout", "-b", "feature/x")
            (root / "README").write_text("y\n", encoding="utf-8")
            _run(root, "git", "add", "README")
            _run(root, "git", "commit", "-m", "feat")
            _run(root, "git", "checkout", "dev")

            layout = supagit_layout.resolve_repo_layout(root)

            def run_git(*args: str, cwd: Path | None = None, capture: bool = True) -> str:
                completed = subprocess.run(
                    ["git", *args],
                    cwd=str(cwd or root),
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=True,
                )
                return completed.stdout if capture else ""

            inv = supagit_inventory.build_inventory(
                layout, ("dev", "pre", "prod"), "origin", git_runner=run_git
            )
            names = {b.name: b for b in inv.branches}
            self.assertIn("feature/x", names)
            self.assertFalse(names["feature/x"].is_pipeline)
            self.assertFalse(names["feature/x"].contained_in_first)

    def test_branch_contained_treats_runner_exception_as_false(self) -> None:
        class FakeShipError(RuntimeError):
            pass

        def failing_git(*args: str, **kwargs) -> str:
            if len(args) >= 2 and args[0] == "merge-base" and args[1] == "--is-ancestor":
                raise FakeShipError("Command failed: git merge-base --is-ancestor feature/x dev")
            raise AssertionError(f"unexpected git call: {args}")

        self.assertFalse(
            supagit_inventory.branch_contained("feature/x", "dev", failing_git)
        )

    def test_build_inventory_survives_ship_error_merge_base(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _run(root, "git", "init", "-b", "dev")
            _run(root, "git", "config", "user.email", "t@example.com")
            _run(root, "git", "config", "user.name", "t")
            (root / "README").write_text("x\n", encoding="utf-8")
            _run(root, "git", "add", "README")
            _run(root, "git", "commit", "-m", "init")
            _run(root, "git", "checkout", "-b", "feature/x")
            (root / "README").write_text("y\n", encoding="utf-8")
            _run(root, "git", "add", "README")
            _run(root, "git", "commit", "-m", "feat")
            _run(root, "git", "checkout", "dev")

            layout = supagit_layout.resolve_repo_layout(root)

            def run_git(*args: str, cwd: Path | None = None, capture: bool = True) -> str:
                completed = subprocess.run(
                    ["git", *args],
                    cwd=str(cwd or root),
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=True,
                )
                return completed.stdout if capture else ""

            def ship_error_git(*args: str, cwd: Path | None = None, capture: bool = True) -> str:
                if len(args) >= 2 and args[0] == "merge-base" and args[1] == "--is-ancestor":
                    raise RuntimeError(
                        "Command failed: git merge-base --is-ancestor feature/x dev: not an ancestor"
                    )
                return run_git(*args, cwd=cwd, capture=capture)

            inv = supagit_inventory.build_inventory(
                layout, ("dev", "pre", "prod"), "origin", git_runner=ship_error_git
            )
            names = {b.name: b for b in inv.branches}
            self.assertIn("feature/x", names)
            self.assertFalse(names["feature/x"].contained_in_first)


def _fake_inventory() -> RepoInventory:
    layout = RepoLayout(
        launch_root=Path("/repo"),
        main_root=Path("/repo"),
        common_dir=Path("/repo/.git"),
        is_linked_launch=False,
    )
    branches = (
        BranchInfo("dev", True, True, Path("/repo"), 0, 0, True, "origin/dev", False),
        BranchInfo("pre", True, False, None, 0, 0, False, "origin/pre", False),
        BranchInfo("prod", True, False, None, 0, 0, False, "origin/prod", False),
        BranchInfo("feature/x", False, True, Path("/wt"), 1, 0, False, None, True),
        BranchInfo("old", False, False, None, 0, 0, True, None, False),
    )
    return RepoInventory(layout, (), branches, "dev")


class FfSyncTests(unittest.TestCase):
    def test_ff_when_remote_ahead(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            remote = Path(directory) / "remote.git"
            local = Path(directory) / "local"
            _run(Path(directory), "git", "init", "--bare", str(remote))
            _run(Path(directory), "git", "clone", str(remote), str(local))
            _run(local, "git", "checkout", "-b", "dev")
            _run(local, "git", "config", "user.email", "t@example.com")
            _run(local, "git", "config", "user.name", "t")
            (local / "a").write_text("1\n", encoding="utf-8")
            _run(local, "git", "add", "a")
            _run(local, "git", "commit", "-m", "one")
            _run(local, "git", "push", "-u", "origin", "dev")

            other = Path(directory) / "other"
            _run(Path(directory), "git", "clone", str(remote), str(other))
            _run(other, "git", "checkout", "dev")
            _run(other, "git", "config", "user.email", "t@example.com")
            _run(other, "git", "config", "user.name", "t")
            (other / "a").write_text("2\n", encoding="utf-8")
            _run(other, "git", "add", "a")
            _run(other, "git", "commit", "-m", "two")
            _run(other, "git", "push", "origin", "dev")

            def run_git(*args: str, cwd: Path | None = None, capture: bool = True) -> str:
                completed = subprocess.run(
                    ["git", *args],
                    cwd=str(cwd or local),
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                if completed.returncode != 0:
                    raise RuntimeError(completed.stderr)
                return completed.stdout.strip()

            result = supagit_sweep.ff_sync_branch(run_git, "dev", "origin", dry_run=False)
            self.assertTrue(result.changed)
            self.assertEqual(run_git("rev-parse", "dev"), run_git("rev-parse", "origin/dev"))

    def test_diverge_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _run(root, "git", "init", "-b", "dev")
            _run(root, "git", "config", "user.email", "t@example.com")
            _run(root, "git", "config", "user.name", "t")
            (root / "a").write_text("1\n", encoding="utf-8")
            _run(root, "git", "add", "a")
            _run(root, "git", "commit", "-m", "base")
            _run(root, "git", "branch", "remote-dev")
            (root / "a").write_text("local\n", encoding="utf-8")
            _run(root, "git", "add", "a")
            _run(root, "git", "commit", "-m", "local")
            _run(root, "git", "checkout", "remote-dev")
            (root / "a").write_text("remote\n", encoding="utf-8")
            _run(root, "git", "add", "a")
            _run(root, "git", "commit", "-m", "remote")
            _run(root, "git", "update-ref", "refs/remotes/origin/dev", "remote-dev")
            _run(root, "git", "checkout", "dev")

            def run_git(*args: str, cwd: Path | None = None, capture: bool = True) -> str:
                completed = subprocess.run(
                    ["git", *args],
                    cwd=str(root),
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                if completed.returncode != 0:
                    raise RuntimeError(completed.stderr)
                return completed.stdout.strip()

            with self.assertRaises(supagit_sweep.SweepError):
                supagit_sweep.ff_sync_branch(run_git, "dev", "origin", dry_run=False)

    def test_fetch_failure_with_configured_remote_raises(self) -> None:
        calls: list[tuple[str, ...]] = []

        def run_git(*args: str, cwd=None, capture: bool = True) -> str:
            calls.append(tuple(args))
            if args[:2] == ("fetch", "origin"):
                raise RuntimeError("network down")
            if args == ("remote", "get-url", "origin"):
                return "https://example.com/repo.git"
            if args == ("rev-parse", "dev"):
                return "abc123"
            if args == ("rev-list", "--left-right", "--count", "origin/dev...dev"):
                return "1\t0"
            raise AssertionError(f"unexpected git call: {args}")

        with self.assertRaises(supagit_sweep.SweepError) as ctx:
            supagit_sweep.ff_sync_branch(run_git, "dev", "origin", dry_run=False)
        self.assertIn("Could not fetch origin/dev", str(ctx.exception))
        self.assertEqual(calls[0][:2], ("fetch", "origin"))
        self.assertIn(("remote", "get-url", "origin"), calls)


class MenuTests(unittest.TestCase):
    def test_defaults_skip_contained_features(self) -> None:
        inv = _fake_inventory()
        selection = supagit_menu.parse_menu_responses(
            inv, pipeline_line="", integrate_line="", default_pipeline=("dev", "pre", "prod")
        )
        self.assertEqual(selection.pipeline, ("dev", "pre", "prod"))
        self.assertEqual(selection.integrate, ("feature/x",))

    def test_numbers_reorder_pipeline_and_pick_features(self) -> None:
        inv = _fake_inventory()
        selection = supagit_menu.parse_menu_responses(
            inv,
            pipeline_line="1,3,2",
            integrate_line="feature/x",
            default_pipeline=("dev", "pre", "prod"),
        )
        self.assertEqual(selection.pipeline, ("dev", "prod", "pre"))
        self.assertEqual(selection.integrate, ("feature/x",))

    def test_integrate_rejects_digit_token(self) -> None:
        inv = _fake_inventory()
        with self.assertRaises(supagit_menu.MenuError):
            supagit_menu.parse_integrate_line(inv, "4")

    def test_integrate_rejects_contained_explicit(self) -> None:
        inv = _fake_inventory()
        with self.assertRaises(supagit_menu.MenuError):
            supagit_menu.parse_integrate_line(inv, "old")

    def test_integrate_ninguno(self) -> None:
        inv = _fake_inventory()
        self.assertEqual(supagit_menu.parse_integrate_line(inv, "ninguno"), ())

    def test_pipeline_number_scoped_to_pipeline_block(self) -> None:
        inv = _fake_inventory()
        self.assertEqual(
            supagit_menu.parse_pipeline_line(inv, "1,2", ("dev", "pre", "prod")),
            ("dev", "pre"),
        )

    def test_yes_mode_flags_parser(self) -> None:
        inv = _fake_inventory()
        selection = supagit_menu.selection_from_flags(inv, "dev,pre,prod", "feature/x")
        self.assertEqual(selection.integrate, ("feature/x",))

    def test_integrate_none(self) -> None:
        inv = _fake_inventory()
        selection = supagit_menu.parse_menu_responses(
            inv, "", "none", default_pipeline=("dev", "pre", "prod")
        )
        self.assertEqual(selection.integrate, ())

    def test_render_sweeper_menu_uses_checks_and_pipeline_numbers(self) -> None:
        inv = _fake_inventory()
        text = supagit_menu.render_sweeper_menu(inv)
        self.assertIn("[✓]", text)
        self.assertIn("feature/x", text)
        self.assertIn("[ ]", text)  # contained "old"
        self.assertIn("old", text)
        self.assertRegex(text, r"(?m)^1\. dev")
        self.assertRegex(text, r"(?m)^2\. pre")
        self.assertRegex(text, r"(?m)^3\. prod")
        self.assertNotIn("Pipeline order (comma-separated", text)
        self.assertNotIn("[pipeline", text)

    def test_classify_puts_worktree_before_other_work(self) -> None:
        inv = _fake_inventory()
        worktrees, other, pipeline = supagit_menu.classify_menu_branches(inv)
        self.assertEqual([b.name for b in worktrees], ["feature/x"])
        self.assertEqual([b.name for b in other], ["old"])
        self.assertEqual([b.name for b in pipeline], ["dev", "pre", "prod"])

    def test_render_execution_plan_lists_integrates(self) -> None:
        selection = supagit_menu.MenuSelection(
            integrate=("feature/x",), pipeline=("dev", "pre", "prod")
        )
        text = supagit_menu.render_execution_plan(selection)
        self.assertIn("feature/x", text)
        self.assertIn("dev", text)


class GhClientTests(unittest.TestCase):
    def test_ensure_ready_fails_when_gh_missing(self) -> None:
        def run_raw(cmd, **kwargs):
            raise FileNotFoundError("gh")

        client = supagit_sweep.GhClient(run_raw, dry_run=False)
        with self.assertRaises(supagit_sweep.SweepError):
            client.ensure_ready()

    def test_ensure_ready_fails_when_gh_unauthenticated(self) -> None:
        def run_raw(cmd, **kwargs):
            raise RuntimeError("not logged in")

        client = supagit_sweep.GhClient(run_raw, dry_run=False)
        with self.assertRaises(supagit_sweep.SweepError):
            client.ensure_ready()

    def test_ensure_github_remote_rejects_non_github(self) -> None:
        client = supagit_sweep.GhClient(lambda *a, **k: "", dry_run=False)
        with self.assertRaises(supagit_sweep.SweepError):
            client.ensure_github_remote("git@gitlab.com:acme/demo.git")

    def test_ensure_github_remote_accepts_github_ssh(self) -> None:
        client = supagit_sweep.GhClient(lambda *a, **k: "", dry_run=False)
        client.ensure_github_remote("git@github.com:acme/demo.git")

    def test_ensure_github_remote_accepts_github_https(self) -> None:
        client = supagit_sweep.GhClient(lambda *a, **k: "", dry_run=False)
        client.ensure_github_remote("https://github.com/acme/demo.git")

    def test_merge_pr_uses_merge_and_delete_branch(self) -> None:
        calls: list[list[str]] = []

        def run_raw(cmd, **kwargs):
            calls.append(list(cmd))
            return ""

        client = supagit_sweep.GhClient(run_raw, dry_run=False)
        client.merge_pr(42)
        self.assertEqual(
            calls[0],
            ["gh", "pr", "merge", "42", "--merge", "--delete-branch"],
        )


class CommitDirtyTreeTests(unittest.TestCase):
    def test_secret_rejection_short_circuits_before_commit(self) -> None:
        calls: list[list[str]] = []

        def reject_sensitive(paths: Sequence[str]) -> None:
            calls.append(list(paths))
            raise ValueError("secrets")

        def run_git(*args, cwd=None, capture=True):
            if args[:2] == ("status", "--porcelain"):
                return " M .env\n"
            raise AssertionError(f"should not proceed past secret check: {args}")

        with self.assertRaises(ValueError):
            supagit_sweep.commit_dirty_tree(
                run_git,
                cwd=Path("/wt"),
                message="x",
                reject_sensitive=reject_sensitive,
                dry_run=False,
            )
        self.assertEqual(len(calls), 1)
        self.assertIn(".env", calls[0])

    def test_clean_tree_returns_false(self) -> None:
        def run_git(*args, cwd=None, capture=True):
            if args[:2] == ("status", "--porcelain"):
                return ""
            raise AssertionError(f"unexpected git call: {args}")

        created = supagit_sweep.commit_dirty_tree(
            run_git,
            cwd=Path("/wt"),
            message="x",
            reject_sensitive=lambda paths: None,
            dry_run=False,
        )
        self.assertFalse(created)


class IntegrateBranchTests(unittest.TestCase):
    def test_reuses_existing_pr_and_merges(self) -> None:
        actions: list[str] = []

        class FakeGh:
            def ensure_ready(self) -> None:
                actions.append("auth")

            def ensure_github_remote(self, remote_url: str) -> None:
                actions.append(f"remote:{remote_url}")

            def find_open_pr(self, head: str, base: str) -> int | None:
                actions.append(f"find:{head}->{base}")
                return 7

            def create_pr(self, head: str, base: str, title: str) -> int:
                raise AssertionError("should reuse")

            def merge_pr(self, number: int) -> None:
                actions.append(f"merge:{number}")

        def run_git(*args, cwd=None, capture=True):
            actions.append("git:" + " ".join(args))
            if args[:2] == ("status", "--porcelain"):
                return ""
            if args[0] == "push":
                return ""
            if args[:1] == ("fetch",):
                return ""
            return "ok"

        supagit_sweep.integrate_branch(
            run_git,
            gh=FakeGh(),
            remote="origin",
            remote_url="git@github.com:acme/demo.git",
            branch="feature/x",
            base="dev",
            cwd=Path("/wt"),
            message_provider=lambda: "should not be called",
            reject_sensitive=lambda paths: None,
            dry_run=False,
            contained_in_first=False,
        )
        self.assertEqual(actions[0], "auth")
        self.assertIn("merge:7", actions)
        self.assertIn("find:feature/x->dev", actions)

    def test_creates_pr_when_none_open(self) -> None:
        actions: list[str] = []

        class FakeGh:
            def ensure_ready(self) -> None:
                actions.append("auth")

            def ensure_github_remote(self, remote_url: str) -> None:
                pass

            def find_open_pr(self, head: str, base: str) -> int | None:
                return None

            def create_pr(self, head: str, base: str, title: str) -> int:
                actions.append(f"create:{head}->{base}:{title}")
                return 9

            def merge_pr(self, number: int) -> None:
                actions.append(f"merge:{number}")

        def run_git(*args, cwd=None, capture=True):
            if args[:2] == ("status", "--porcelain"):
                return ""
            if args[0] == "push":
                return ""
            if args[:1] == ("fetch",):
                return ""
            return "ok"

        supagit_sweep.integrate_branch(
            run_git,
            gh=FakeGh(),
            remote="origin",
            remote_url="git@github.com:acme/demo.git",
            branch="feature/x",
            base="dev",
            cwd=Path("/wt"),
            message_provider=lambda: "unused",
            reject_sensitive=lambda paths: None,
            dry_run=False,
            contained_in_first=False,
        )
        self.assertIn("create:feature/x->dev:supagit: integrate feature/x into dev", actions)
        self.assertIn("merge:9", actions)

    def test_contained_branch_fails_closed(self) -> None:
        class FakeGh:
            def ensure_ready(self) -> None:
                return None

            def ensure_github_remote(self, remote_url: str) -> None:
                return None

            def find_open_pr(self, head: str, base: str) -> int | None:
                return None

            def create_pr(self, head: str, base: str, title: str) -> int:
                raise AssertionError("should not create")

            def merge_pr(self, number: int) -> None:
                raise AssertionError("should not merge")

        with self.assertRaises(supagit_sweep.SweepError):
            supagit_sweep.integrate_branch(
                lambda *a, **k: "",
                gh=FakeGh(),
                remote="origin",
                remote_url="git@github.com:acme/demo.git",
                branch="old",
                base="dev",
                cwd=Path("/repo"),
                message_provider=lambda: "x",
                reject_sensitive=lambda paths: None,
                dry_run=False,
                contained_in_first=True,
            )


class CleanupTests(unittest.TestCase):
    def test_plan_skips_pipeline_and_dirty_worktrees(self) -> None:
        layout = RepoLayout(
            launch_root=Path("/repo"),
            main_root=Path("/repo"),
            common_dir=Path("/repo/.git"),
            is_linked_launch=False,
        )
        worktrees = (
            WorktreeInfo(Path("/repo"), "dev", True, ()),
            WorktreeInfo(Path("/wt-dirty"), "feature/x", False, ("a.txt",)),
            WorktreeInfo(Path("/wt-clean"), "feature/y", False, ()),
        )
        branches = (
            BranchInfo("dev", True, True, Path("/repo"), 0, 0, True, "origin/dev", False),
            BranchInfo("pre", True, False, None, 0, 0, False, "origin/pre", False),
            BranchInfo("prod", True, False, None, 0, 0, False, "origin/prod", False),
            BranchInfo("feature/x", False, True, Path("/wt-dirty"), 0, 0, True, None, True),
            BranchInfo("feature/y", False, True, Path("/wt-clean"), 0, 0, True, None, False),
        )
        inv = RepoInventory(layout, worktrees, branches, "dev")
        plan = supagit_sweep.plan_cleanup(inv, ("dev", "pre", "prod"), ("feature/x", "feature/y"))
        kinds = {(i.kind, i.name) for i in plan.items}
        self.assertNotIn(("local-branch", "dev"), kinds)
        self.assertNotIn(("worktree", "feature/x"), kinds)
        self.assertIn(("worktree", "feature/y"), kinds)
        self.assertIn(("local-branch", "feature/y"), kinds)


SPEC = importlib.util.spec_from_file_location("supagit_engine", SCRIPTS / "supagit.py")
assert SPEC and SPEC.loader
ENGINE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ENGINE
SPEC.loader.exec_module(ENGINE)


class OrchestrationTests(unittest.TestCase):
    def test_yes_without_flags_fails(self) -> None:
        pipeline = ENGINE.Pipeline.__new__(ENGINE.Pipeline)
        pipeline.options = ENGINE.Options(
            dry_run=False,
            yes=True,
            config_path=None,
            message=None,
            color="never",
            no_sweep=False,
            integrate=None,
            pipeline_order=None,
            cleanup=None,
        )
        with self.assertRaisesRegex(ENGINE.ShipError, "--integrate"):
            pipeline._require_noninteractive_selection()

    def test_yes_with_no_sweep_ok(self) -> None:
        pipeline = ENGINE.Pipeline.__new__(ENGINE.Pipeline)
        pipeline.options = ENGINE.Options(
            dry_run=False,
            yes=True,
            config_path=None,
            message=None,
            color="never",
            no_sweep=True,
            integrate=None,
            pipeline_order=None,
            cleanup=False,
        )
        pipeline._require_noninteractive_selection()

    def test_run_yes_without_flags_fails_before_validate_workspace(self) -> None:
        pipeline = ENGINE.Pipeline.__new__(ENGINE.Pipeline)
        pipeline.options = ENGINE.Options(
            dry_run=False,
            yes=True,
            config_path=None,
            message=None,
            color="never",
            no_sweep=False,
            integrate=None,
            pipeline_order=None,
            cleanup=None,
        )

        def fail_if_called() -> None:
            raise AssertionError("validate_workspace should not be called")

        pipeline.validate_workspace = fail_if_called  # type: ignore[method-assign]
        with self.assertRaisesRegex(ENGINE.ShipError, "--integrate"):
            pipeline.run()

    def test_optional_cleanup_rebuilds_inventory(self) -> None:
        pipeline = ENGINE.Pipeline.__new__(ENGINE.Pipeline)
        pipeline.options = ENGINE.Options(
            dry_run=True,
            yes=True,
            config_path=None,
            message=None,
            color="never",
            no_sweep=False,
            integrate=None,
            pipeline_order=None,
            cleanup=True,
        )
        stale_inventory = object()
        fresh_layout = RepoLayout(
            launch_root=Path("/repo"),
            main_root=Path("/repo"),
            common_dir=Path("/repo/.git"),
            is_linked_launch=False,
        )
        fresh_inventory = RepoInventory(fresh_layout, (), (), "dev")
        rebuilt = False

        def build_inventory() -> RepoInventory:
            nonlocal rebuilt
            rebuilt = True
            return fresh_inventory

        pipeline.build_inventory = build_inventory  # type: ignore[method-assign]
        pipeline._sweep_git = lambda *a, **k: ""  # type: ignore[method-assign]
        selection = supagit_menu.MenuSelection(
            integrate=("feature/y",), pipeline=("dev", "pre", "prod")
        )
        pipeline.optional_cleanup(stale_inventory, selection)  # type: ignore[arg-type]
        self.assertTrue(rebuilt)

    def test_run_rebuilds_inventory_after_menu_selection(self) -> None:
        pipeline = ENGINE.Pipeline.__new__(ENGINE.Pipeline)
        pipeline.options = ENGINE.Options(
            dry_run=True,
            yes=True,
            config_path=None,
            message="test",
            color="never",
            no_sweep=False,
            integrate=("feature/x",),
            pipeline_order="pre,dev,prod",
            cleanup=False,
        )
        pipeline.branches = ("dev", "pre", "prod")
        pipeline.dev = "dev"
        pipeline.pre = "pre"
        pipeline.prod = "prod"
        pipeline.remote = "origin"
        pipeline.backend = ENGINE.BackendConfig(provider="none", cli=None, targets={})
        call_branches: list[tuple[str, ...]] = []
        sweep_inventory: list[RepoInventory] = []

        def build_inventory() -> RepoInventory:
            call_branches.append(tuple(pipeline.branches))
            base = _fake_inventory()
            return RepoInventory(
                base.layout, base.worktrees, base.branches, pipeline.branches[0]
            )

        def sweep_features(selection: supagit_menu.MenuSelection, inventory: RepoInventory) -> None:
            sweep_inventory.append(inventory)

        pipeline.build_inventory = build_inventory  # type: ignore[method-assign]
        pipeline.validate_workspace = lambda: None  # type: ignore[method-assign]
        pipeline._require_noninteractive_selection = lambda: None  # type: ignore[method-assign]
        pipeline.run_branch_menu = lambda inv: supagit_menu.MenuSelection(  # type: ignore[method-assign]
            integrate=("feature/x",), pipeline=("pre", "dev", "prod")
        )
        pipeline.ensure_main_checkout_for_promotion = lambda: None  # type: ignore[method-assign]
        pipeline.sweep_features = sweep_features  # type: ignore[method-assign]
        pipeline.ff_sync_first_branch = lambda: None  # type: ignore[method-assign]
        pipeline.commit_and_publish_dev = lambda: None  # type: ignore[method-assign]
        pipeline._assert_dev_synced = lambda: None  # type: ignore[method-assign]
        pipeline.run_checks = lambda: None  # type: ignore[method-assign]
        pipeline.validate_clean_after_checks = lambda: None  # type: ignore[method-assign]
        pipeline.confirm = lambda message: None  # type: ignore[method-assign]
        pipeline.promote = lambda source, target: None  # type: ignore[method-assign]
        pipeline.return_to_dev = lambda: None  # type: ignore[method-assign]
        pipeline.optional_cleanup = lambda inv, sel: None  # type: ignore[method-assign]
        pipeline.status = lambda message, color: None  # type: ignore[method-assign]

        pipeline.run()

        self.assertGreaterEqual(len(call_branches), 2)
        self.assertEqual(call_branches[0], ("dev", "pre", "prod"))
        self.assertEqual(call_branches[1], ("pre", "dev", "prod"))
        self.assertEqual(len(sweep_inventory), 1)
        self.assertEqual(sweep_inventory[0].first_branch, "pre")

    def test_validate_linked_launch_defers_clean_wrong_branch(self) -> None:
        pipeline = ENGINE.Pipeline.__new__(ENGINE.Pipeline)
        pipeline.options = ENGINE.Options(
            dry_run=True,
            yes=False,
            config_path=None,
            message=None,
            color="never",
            no_sweep=True,
            integrate=None,
            pipeline_order=None,
            cleanup=False,
        )
        pipeline.layout = RepoLayout(
            launch_root=Path("/wt"),
            main_root=Path("/repo"),
            common_dir=Path("/repo/.git"),
            is_linked_launch=True,
        )
        pipeline.launch_root = Path("/wt")
        pipeline.root = Path("/repo")
        pipeline.dev = "dev"
        pipeline.branches = ("dev", "pre", "prod")
        pipeline.remote = "origin"
        pipeline.original_branch = "feature/x"
        pipeline.project_name = "demo"
        checkout_calls: list[tuple[str, ...]] = []

        def git(*args: str, capture: bool = False, check: bool = True, mutating: bool = False, cwd: Path | None = None) -> str:
            if args[:2] == ("branch", "--show-current"):
                target = cwd or pipeline.root
                return "feature/x\n" if target == pipeline.root else "feature/x\n"
            if args[:2] == ("status", "--porcelain"):
                return ""
            if args[0] == "checkout":
                checkout_calls.append(args)
                return ""
            if args[:2] == ("remote", "get-url"):
                return "git@github.com:acme/demo.git\n"
            if args[:2] == ("worktree", "list"):
                return "worktree /repo\nbranch refs/heads/feature/x\n\nworktree /wt\nbranch refs/heads/feature/x\n"
            if args[0] == "ls-remote":
                return ""
            if args[0] == "fetch":
                return ""
            if args[:2] == ("rev-list", "--left-right"):
                return "0\t0\n"
            raise AssertionError(f"unexpected git call: {args}")

        pipeline.git = git  # type: ignore[method-assign]
        pipeline.validate_workspace()
        self.assertEqual(checkout_calls, [])

    def test_validate_linked_launch_fails_dirty_wrong_branch(self) -> None:
        pipeline = ENGINE.Pipeline.__new__(ENGINE.Pipeline)
        pipeline.options = ENGINE.Options(
            dry_run=True,
            yes=False,
            config_path=None,
            message=None,
            color="never",
            no_sweep=True,
            integrate=None,
            pipeline_order=None,
            cleanup=False,
        )
        pipeline.layout = RepoLayout(
            launch_root=Path("/wt"),
            main_root=Path("/repo"),
            common_dir=Path("/repo/.git"),
            is_linked_launch=True,
        )
        pipeline.launch_root = Path("/wt")
        pipeline.root = Path("/repo")
        pipeline.dev = "dev"
        pipeline.branches = ("dev", "pre", "prod")
        pipeline.remote = "origin"

        def git(*args: str, capture: bool = False, check: bool = True, mutating: bool = False, cwd: Path | None = None) -> str:
            if args[:2] == ("branch", "--show-current"):
                return "feature/x\n"
            if args[:2] == ("status", "--porcelain"):
                return " M dirty.txt\n"
            raise AssertionError(f"unexpected git call: {args}")

        pipeline.git = git  # type: ignore[method-assign]
        with self.assertRaisesRegex(ENGINE.ShipError, "uncommitted changes"):
            pipeline.validate_workspace()


if __name__ == "__main__":
    unittest.main()
