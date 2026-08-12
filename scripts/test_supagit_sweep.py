#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Callable, Sequence
from unittest.mock import patch

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
            if args[:2] == ("branch", "--show-current"):
                return "dev\n"
            if args[:2] == ("status", "--porcelain"):
                return ""
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
        self.assertEqual(calls[0][:2], ("branch", "--show-current"))
        self.assertIn(("fetch", "origin", "refs/heads/dev:refs/remotes/origin/dev"), calls)
        self.assertIn(("remote", "get-url", "origin"), calls)

    def test_ff_refuses_dirty_worktree(self) -> None:
        import supagit_i18n

        supagit_i18n.set_lang("en")
        calls: list[tuple[str, ...]] = []

        def run_git(*args: str, cwd=None, capture: bool = True) -> str:
            calls.append(tuple(args))
            if args[:2] == ("branch", "--show-current"):
                return "dev\n"
            if args[:2] == ("status", "--porcelain"):
                return " M README.md\n"
            raise AssertionError(f"unexpected git call: {args}")

        with self.assertRaises(supagit_sweep.SweepError) as ctx:
            supagit_sweep.ff_sync_branch(run_git, "dev", "origin", dry_run=False)
        text = str(ctx.exception).lower()
        self.assertIn("dirty", text)
        self.assertIn("dev", str(ctx.exception))
        self.assertFalse(any(c[0] == "fetch" for c in calls))
        self.assertFalse(any(c[0] == "merge" for c in calls))
        self.assertFalse(any(c[:2] == ("reset", "--hard") for c in calls))

    def test_ff_update_ref_when_not_checked_out(self) -> None:
        calls: list[tuple[str, ...]] = []
        tips = {"feature/x": "aaa", "origin/feature/x": "bbb"}

        def run_git(*args: str, cwd=None, capture: bool = True) -> str:
            calls.append(tuple(args))
            if cwd != Path("/repo"):
                raise AssertionError(f"expected cwd=/repo got {cwd!r}")
            if args[:2] == ("branch", "--show-current"):
                return "main\n"
            if args[:2] == ("fetch", "origin"):
                return ""
            if args[0] == "rev-parse" and args[-1] in tips:
                return tips[args[-1]]
            if args[:3] == ("rev-list", "--left-right", "--count"):
                return "1\t0"
            if args[:2] == ("merge-base", "--is-ancestor"):
                return ""
            if args[0] == "update-ref":
                tips["feature/x"] = tips[args[2]]
                return ""
            raise AssertionError(f"unexpected git call: {args}")

        result = supagit_sweep.ff_sync_branch(
            run_git, "feature/x", "origin", dry_run=False, cwd=Path("/repo")
        )
        self.assertTrue(result.changed)
        self.assertEqual(tips["feature/x"], "bbb")
        self.assertFalse(any(c[0] == "checkout" for c in calls))
        self.assertFalse(any(c[0] == "merge" for c in calls))
        self.assertTrue(
            any(c[:2] == ("update-ref", "refs/heads/feature/x") for c in calls)
        )

    def test_ahead_behind_rejects_empty_output(self) -> None:
        def run_git(*args: str, cwd=None, capture: bool = True) -> str:
            return ""

        with self.assertRaises(supagit_sweep.SweepError) as ctx:
            supagit_sweep.ahead_behind(run_git, "dev", "origin/dev")
        self.assertIn("ahead/behind", str(ctx.exception))


class MenuTests(unittest.TestCase):
    def setUp(self) -> None:
        import supagit_i18n

        supagit_i18n.set_lang("en")

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
        with self.assertRaises(supagit_menu.MenuError) as ctx:
            supagit_menu.parse_integrate_line(inv, "99")
        self.assertIn("99", str(ctx.exception))

    def test_integrate_accepts_work_number(self) -> None:
        inv = _fake_inventory()
        # work order: feature/x (worktree), then old (other)
        self.assertEqual(supagit_menu.parse_integrate_line(inv, "1"), ("feature/x",))

    def test_integrate_zero_skips(self) -> None:
        inv = _fake_inventory()
        self.assertEqual(supagit_menu.parse_integrate_line(inv, "0"), ())

    def test_integrate_rejects_contained_explicit(self) -> None:
        inv = _fake_inventory()
        with self.assertRaises(supagit_menu.MenuError):
            supagit_menu.parse_integrate_line(inv, "old")
        with self.assertRaises(supagit_menu.MenuError):
            # "old" is work item 2 when feature/x is 1
            supagit_menu.parse_integrate_line(inv, "2")

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
        self.assertRegex(text, r"(?m)^1\. \[✓\] feature/x")
        self.assertRegex(text, r"(?m)^2\. \[✓\] old")  # contained still checked
        self.assertIn("already included", text)
        self.assertNotIn("[ ]", text)
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

    def test_render_execution_plan_weaves_ff_after_integrate_before_promote(self) -> None:
        import supagit_i18n
        import supagit_situation as sit

        supagit_i18n.set_lang("en")
        selection = supagit_menu.MenuSelection(
            integrate=("feature/x",), pipeline=("dev", "pre")
        )
        pipeline0 = sit.BranchSync(
            "dev", "origin/dev", sit.SyncStatus.BEHIND_ONLY, 0, 1, False, "/repo"
        )
        feature = sit.BranchSync(
            "feature/x",
            "origin/feature/x",
            sit.SyncStatus.BEHIND_ONLY,
            0,
            1,
            False,
            "/wt",
        )
        situation = sit.Situation(
            current_branch="dev",
            dirty=False,
            pipeline0=pipeline0,
            features=(feature,),
            findings=(
                sit.Finding(
                    sit.PolicyClass.SAFE_CURE,
                    "ff_only",
                    sit.SyncStatus.BEHIND_ONLY,
                    False,
                    "pipeline0",
                ),
                sit.Finding(
                    sit.PolicyClass.SAFE_CURE,
                    "ff_only",
                    sit.SyncStatus.BEHIND_ONLY,
                    False,
                    "feature",
                ),
            ),
            gh_ready=None,
            self_update=None,
        )
        text = supagit_menu.render_execution_plan(
            selection, first_branch="dev", remote="origin", situation=situation
        )
        feature_ff = sit.feature_ff_line(situation, "feature/x", remote="origin")
        pipeline_ff = sit.pipeline0_ff_line(situation, remote="origin")
        assert feature_ff is not None and pipeline_ff is not None
        publish_i = text.index("Publish dev")
        feature_ff_i = text.index(feature_ff)
        integrate_i = text.index("Integrate feature/x")
        pipeline_ff_i = text.index(pipeline_ff)
        promote_i = text.index("Merge dev into pre")
        self.assertLess(publish_i, feature_ff_i)
        self.assertLess(feature_ff_i, integrate_i)
        self.assertLess(integrate_i, pipeline_ff_i)
        self.assertLess(pipeline_ff_i, promote_i)


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

    def test_merge_pr_can_keep_head_branch(self) -> None:
        calls: list[list[str]] = []

        def run_raw(cmd, **kwargs):
            calls.append(list(cmd))
            return ""

        client = supagit_sweep.GhClient(run_raw, dry_run=False)
        client.merge_pr(7, delete_branch=False)
        self.assertEqual(calls[0], ["gh", "pr", "merge", "7", "--merge"])

    def test_pr_number_from_create_output(self) -> None:
        self.assertEqual(
            supagit_sweep.pr_number_from_create_output(
                "https://github.com/acme/demo/pull/42\n"
            ),
            42,
        )
        self.assertIsNone(supagit_sweep.pr_number_from_create_output("no url here"))

    def test_create_pr_parses_url_and_omits_json_flags(self) -> None:
        calls: list[list[str]] = []

        def run_raw(cmd, **kwargs):
            calls.append(list(cmd))
            return "https://github.com/acme/demo/pull/99\n"

        client = supagit_sweep.GhClient(run_raw, dry_run=False)
        number = client.create_pr("work", "main", "title")
        self.assertEqual(number, 99)
        self.assertEqual(calls[0][:3], ["gh", "pr", "create"])
        self.assertNotIn("--json", calls[0])
        self.assertNotIn("--jq", calls[0])

    def test_create_promote_pr_parses_url_and_omits_json_flags(self) -> None:
        calls: list[list[str]] = []

        def run_raw(cmd, **kwargs):
            calls.append(list(cmd))
            return "https://github.com/acme/demo/pull/7\n"

        client = supagit_sweep.GhClient(run_raw, dry_run=False)
        number = client.create_promote_pr("dev", "main", "promote")
        self.assertEqual(number, 7)
        self.assertNotIn("--json", calls[0])

    def test_create_pr_falls_back_to_find_open_pr(self) -> None:
        calls: list[list[str]] = []

        def run_raw(cmd, **kwargs):
            calls.append(list(cmd))
            if cmd[:3] == ["gh", "pr", "create"]:
                return "created without url"
            if cmd[:3] == ["gh", "pr", "list"]:
                return "15"
            raise AssertionError(cmd)

        client = supagit_sweep.GhClient(run_raw, dry_run=False)
        self.assertEqual(client.create_pr("work", "main", "title"), 15)

    def test_parse_github_owner_repo(self) -> None:
        self.assertEqual(
            supagit_sweep.parse_github_owner_repo("git@github.com:acme/demo.git"),
            ("acme", "demo"),
        )
        self.assertEqual(
            supagit_sweep.parse_github_owner_repo("https://github.com/acme/demo"),
            ("acme", "demo"),
        )
        self.assertIsNone(
            supagit_sweep.parse_github_owner_repo("git@gitlab.com:acme/demo.git")
        )

    def test_inspect_promote_gate_detects_pull_request_rule(self) -> None:
        import json

        def run_raw(cmd, **kwargs):
            endpoint = cmd[2]
            if endpoint.endswith("/demo") or endpoint == "repos/acme/demo":
                return json.dumps({"visibility": "public", "private": False})
            if "rules/branches" in endpoint:
                return json.dumps([{"type": "pull_request"}, {"type": "deletion"}])
            raise AssertionError(endpoint)

        gate = supagit_sweep.inspect_promote_gate(
            run_raw, "git@github.com:acme/demo.git", "main"
        )
        assert gate is not None
        self.assertTrue(gate.requires_pull_request)
        self.assertEqual(gate.mode, "pull_request")
        self.assertEqual(gate.visibility, "public")
        self.assertIn("pull_request", gate.rule_types)

    def test_inspect_promote_gate_unprotected_is_direct(self) -> None:
        import json

        def run_raw(cmd, **kwargs):
            endpoint = cmd[2]
            if endpoint == "repos/acme/demo":
                return json.dumps({"visibility": "private", "private": True})
            if "rules/branches" in endpoint:
                return json.dumps([])
            if "protection" in endpoint:
                raise RuntimeError("HTTP 404")
            raise AssertionError(endpoint)

        gate = supagit_sweep.inspect_promote_gate(
            run_raw, "https://github.com/acme/demo.git", "main"
        )
        assert gate is not None
        self.assertFalse(gate.requires_pull_request)
        self.assertEqual(gate.mode, "direct")
        self.assertEqual(gate.visibility, "private")

    def test_inspect_promote_gate_non_github_returns_none(self) -> None:
        gate = supagit_sweep.inspect_promote_gate(
            lambda *a, **k: "", "git@gitlab.com:acme/demo.git", "main"
        )
        self.assertIsNone(gate)


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
            if args[:2] == ("branch", "--show-current"):
                return "feature/x\n"
            if args[:3] == ("rev-list", "--left-right", "--count"):
                return "0\t0"
            if args[0] == "rev-parse":
                return "abc"
            if args[0] == "push":
                return ""
            if args[0] == "fetch":
                return ""
            if args[:2] == ("rev-parse", "--abbrev-ref"):
                return "origin/feature/x\n"
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
            if args[:2] == ("branch", "--show-current"):
                return "feature/x\n"
            if args[:3] == ("rev-list", "--left-right", "--count"):
                return "0\t0"
            if args[:2] == ("rev-list", "--count"):
                return "2"
            if args[0] == "rev-parse":
                return "abc"
            if args[0] == "push":
                return ""
            if args[0] == "fetch":
                return ""
            if args[:2] == ("rev-parse", "--abbrev-ref"):
                return "origin/feature/x\n"
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

    def test_integrate_skips_ff_when_remote_feature_missing(self) -> None:
        actions: list[str] = []

        class FakeGh:
            def ensure_ready(self) -> None:
                return None

            def ensure_github_remote(self, remote_url: str) -> None:
                return None

            def find_open_pr(self, head: str, base: str) -> int | None:
                return None

            def create_pr(self, head: str, base: str, title: str) -> int:
                actions.append(f"create:{head}")
                return 11

            def merge_pr(self, number: int) -> None:
                actions.append(f"merge:{number}")

        def run_git(*args, cwd=None, capture=True):
            actions.append("git:" + " ".join(args))
            if args[:2] == ("status", "--porcelain"):
                return ""
            if args[:3] == ("ls-remote", "--heads", "origin"):
                return ""
            if args[:2] == ("branch", "--show-current"):
                return "main\n"
            if args[:2] == ("rev-parse", "--abbrev-ref"):
                raise RuntimeError("no upstream")
            if args[0] == "push":
                return ""
            if args[:2] == ("rev-list", "--count"):
                return "2"
            if args[0] == "rev-parse":
                return "abc"
            if args[0] == "fetch":
                if "refs/heads/work" in args:
                    raise AssertionError("must not fetch missing feature ref")
                return ""
            return "ok"

        supagit_sweep.integrate_branch(
            run_git,
            gh=FakeGh(),
            remote="origin",
            remote_url="git@github.com:acme/demo.git",
            branch="work",
            base="main",
            cwd=Path("/repo"),
            message_provider=lambda: "unused",
            reject_sensitive=lambda paths: None,
            dry_run=False,
            contained_in_first=False,
        )
        self.assertTrue(any(a.startswith("git:ls-remote") for a in actions))
        self.assertFalse(
            any("refs/heads/work:refs/remotes/origin/work" in a for a in actions)
        )
        self.assertIn("create:work", actions)
        self.assertIn("merge:11", actions)

    def test_integrate_refuses_empty_pr_before_create(self) -> None:
        import supagit_i18n

        supagit_i18n.set_lang("en")
        created = False

        class FakeGh:
            def ensure_ready(self) -> None:
                return None

            def ensure_github_remote(self, remote_url: str) -> None:
                return None

            def find_open_pr(self, head: str, base: str) -> int | None:
                return None

            def create_pr(self, head: str, base: str, title: str) -> int:
                nonlocal created
                created = True
                raise AssertionError("must not create empty PR")

            def merge_pr(self, number: int) -> None:
                raise AssertionError("must not merge")

        def run_git(*args, cwd=None, capture=True):
            if args[:2] == ("status", "--porcelain"):
                return ""
            if args[:2] == ("branch", "--show-current"):
                return "feature/x\n"
            if args[:3] == ("rev-list", "--left-right", "--count"):
                return "0\t0"
            if args[:2] == ("rev-list", "--count"):
                return "0"
            if args[0] == "rev-parse":
                return "abc"
            if args[0] == "push":
                return ""
            if args[0] == "fetch":
                return ""
            if args[:2] == ("rev-parse", "--abbrev-ref"):
                return "origin/feature/x\n"
            return "ok"

        with self.assertRaises(supagit_sweep.SweepError) as ctx:
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
        self.assertFalse(created)
        self.assertIn("empty", str(ctx.exception).lower())
        self.assertIn("feature/x", str(ctx.exception))

    def test_assert_commits_for_pr_ok(self) -> None:
        def run_git(*args, cwd=None, capture=True):
            if args[0] == "fetch":
                return ""
            if args[:2] == ("rev-parse", "--verify"):
                return "ok"
            if args[:2] == ("rev-list", "--count"):
                self.assertEqual(args[2], "origin/dev..feature/x")
                return "3"
            raise AssertionError(args)

        count = supagit_sweep.assert_commits_for_pr(
            run_git,
            head="feature/x",
            base="dev",
            remote="origin",
            cwd=Path("/wt"),
        )
        self.assertEqual(count, 3)

    def test_integrate_ffs_clean_behind_feature_before_push(self) -> None:
        actions: list[str] = []
        tips = {"feature/x": "old", "origin/feature/x": "new"}

        class FakeGh:
            def ensure_ready(self) -> None:
                return None

            def ensure_github_remote(self, remote_url: str) -> None:
                return None

            def find_open_pr(self, head: str, base: str) -> int | None:
                return 1

            def create_pr(self, head: str, base: str, title: str) -> int:
                raise AssertionError("reuse")

            def merge_pr(self, number: int) -> None:
                actions.append(f"merge:{number}")

        def run_git(*args, cwd=None, capture=True):
            actions.append("git:" + " ".join(args))
            if args[:2] == ("status", "--porcelain"):
                return ""
            if args[:2] == ("branch", "--show-current"):
                return "feature/x\n"
            if args[:3] == ("rev-list", "--left-right", "--count"):
                return "1\t0"
            if args[0] == "rev-parse" and args[-1] in tips:
                return tips[args[-1]]
            if args[0] == "fetch":
                return ""
            if args[:2] == ("merge", "--ff-only"):
                tips["feature/x"] = tips["origin/feature/x"]
                return ""
            if args[0] == "push":
                actions.append("pushed")
                return ""
            if args[:2] == ("rev-parse", "--abbrev-ref"):
                return "origin/feature/x\n"
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
        merge_ff = next(i for i, a in enumerate(actions) if "merge --ff-only" in a)
        push_i = next(i for i, a in enumerate(actions) if a == "pushed")
        self.assertLess(merge_ff, push_i)
        self.assertEqual(tips["feature/x"], "new")

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
    def setUp(self) -> None:
        import supagit_i18n

        supagit_i18n.set_lang("en")

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

    def test_run_yes_without_flags_fails_before_preflight_repo(self) -> None:
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
        git_calls: list[tuple] = []

        def fail_if_called() -> None:
            raise AssertionError("preflight_repo should not be called")

        def fail_git(*args, **kwargs):
            git_calls.append(args)
            raise AssertionError(f"git should not be called: {args}")

        pipeline.preflight_repo = fail_if_called  # type: ignore[method-assign]
        pipeline.git = fail_git  # type: ignore[method-assign]
        with self.assertRaisesRegex(ENGINE.ShipError, "--integrate"):
            pipeline.run()
        self.assertEqual(git_calls, [])

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

        def build_inventory(**kwargs) -> RepoInventory:
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
        pipeline.original_branch = "dev"
        pipeline.backend = ENGINE.BackendConfig(provider="none", cli=None, targets={})
        call_branches: list[tuple[str, ...]] = []
        sweep_inventory: list[RepoInventory] = []

        def build_inventory(*, first_branch: str | None = None) -> RepoInventory:
            call_branches.append(tuple(pipeline.branches))
            base = _fake_inventory()
            return RepoInventory(
                base.layout,
                base.worktrees,
                base.branches,
                first_branch or pipeline.branches[0],
            )

        def sweep_features(selection: supagit_menu.MenuSelection, inventory: RepoInventory) -> None:
            sweep_inventory.append(inventory)

        pipeline.build_inventory = build_inventory  # type: ignore[method-assign]
        pipeline.preflight_repo = lambda: None  # type: ignore[method-assign]
        pipeline._require_noninteractive_selection = lambda: None  # type: ignore[method-assign]
        pipeline.run_branch_menu = lambda inv: supagit_menu.MenuSelection(  # type: ignore[method-assign]
            integrate=("feature/x",), pipeline=("pre", "dev", "prod")
        )
        pipeline.ensure_checkout_on_first_branch = lambda: None  # type: ignore[method-assign]
        pipeline.validate_pipeline_head = lambda: None  # type: ignore[method-assign]
        pipeline.verify_final_checkout = lambda: None  # type: ignore[method-assign]
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

    def _pipeline_for_reposition(
        self,
        *,
        dry_run: bool = False,
        yes: bool = False,
        linked: bool = False,
        current: str = "feature/x",
        dirty: str = "",
        worktree_porcelain: str | None = None,
        verify_refs: set[str] | None = None,
        contains: str = "feature/x\n",
        short_sha: str = "abc1234",
        message: str | None = "save work",
    ) -> tuple[ENGINE.Pipeline, list[tuple], list[str]]:
        pipeline = ENGINE.Pipeline.__new__(ENGINE.Pipeline)
        pipeline.options = ENGINE.Options(
            dry_run=dry_run,
            yes=yes,
            config_path=None,
            message=message,
            color="never",
            no_sweep=True,
            integrate=None,
            pipeline_order=None,
            cleanup=False,
        )
        root = Path("/repo")
        pipeline.layout = RepoLayout(
            launch_root=Path("/wt") if linked else root,
            main_root=root,
            common_dir=Path("/repo/.git"),
            is_linked_launch=linked,
        )
        pipeline.launch_root = pipeline.layout.launch_root
        pipeline.root = root
        pipeline.dev = "main"
        pipeline.branches = ("main",)
        pipeline.remote = "origin"
        pipeline.original_branch = current
        pipeline.project_name = "demo"
        calls: list[tuple] = []
        explained: list[str] = []
        refs = verify_refs if verify_refs is not None else {
            "refs/heads/main",
            "refs/remotes/origin/main",
        }
        porcelain = worktree_porcelain or (
            "worktree /repo\nbranch refs/heads/feature/x\n"
        )
        dirty_state = {"value": dirty}

        def git(*args: str, capture: bool = False, check: bool = True, mutating: bool = False, cwd: Path | None = None) -> str:
            calls.append(args)
            if args[:2] == ("branch", "--show-current"):
                return f"{current}\n"
            if args[:2] == ("status", "--porcelain"):
                return dirty_state["value"]
            if args[:2] == ("worktree", "list"):
                return porcelain
            if args[:2] == ("rev-parse", "--verify"):
                ref = args[2]
                if ref in refs:
                    return "ok\n"
                raise ENGINE.ShipError(f"missing {ref}")
            if args[:2] == ("rev-parse", "--short"):
                return f"{short_sha}\n"
            if args[:2] == ("branch", "--contains"):
                return contains
            if args[0] == "fetch":
                return ""
            if args[0] == "checkout":
                return ""
            if args[0] == "add":
                return ""
            if args[0] == "commit":
                dirty_state["value"] = ""
                return ""
            if args[:2] == ("diff", "--cached"):
                return "a.txt\n" if args[-1] == "--name-only" else ""
            if args[:2] == ("remote", "get-url"):
                return "git@github.com:acme/demo.git\n"
            raise AssertionError(f"unexpected git call: {args}")

        pipeline.git = git  # type: ignore[method-assign]
        pipeline._sweep_git = (  # type: ignore[method-assign]
            lambda *a, cwd=None, capture=True: git(*a, capture=capture, cwd=cwd)
        )
        pipeline._reject_sensitive_paths = lambda paths: None  # type: ignore[method-assign]

        def capture_explain(
            message: str, *, ask_continue: bool = True, force_confirm: bool = False
        ) -> None:
            explained.append(message)

        pipeline.explain = capture_explain  # type: ignore[method-assign]
        pipeline.confirm = lambda message, force=False: None  # type: ignore[method-assign]
        return pipeline, calls, explained

    def test_preflight_non_linked_wrong_branch_ok(self) -> None:
        pipeline, calls, _ = self._pipeline_for_reposition(current="feature/x", linked=False)
        pipeline.preflight_repo()
        self.assertFalse(any(c[0] == "checkout" for c in calls))
        self.assertFalse(any(c[0] == "ls-remote" for c in calls))

    def test_preflight_linked_launch_defers_clean_wrong_branch(self) -> None:
        pipeline, calls, _ = self._pipeline_for_reposition(
            current="feature/x", linked=True, dry_run=True
        )
        pipeline.preflight_repo()
        self.assertFalse(any(c[0] == "checkout" for c in calls))

    def test_ensure_checkout_clean_wrong_branch_tutors(self) -> None:
        pipeline, calls, explained = self._pipeline_for_reposition(
            current="feature/x", dirty=""
        )
        import builtins

        def fake_input(prompt: str = "") -> str:
            return "y"

        original = builtins.input
        builtins.input = fake_input  # type: ignore[assignment]
        try:
            pipeline.ensure_checkout_on_first_branch()
        finally:
            builtins.input = original  # type: ignore[assignment]
        self.assertTrue(any("main" in e and "feature/x" in e for e in explained))
        self.assertIn(("checkout", "main"), calls)

    def test_ensure_checkout_dirty_wrong_branch_commits_then_moves(self) -> None:
        pipeline, calls, _ = self._pipeline_for_reposition(
            current="feature/x",
            dirty=" M a.txt\n?? b.txt\n",
        )
        pipeline.ensure_checkout_on_first_branch()
        self.assertTrue(any(c[0] == "add" for c in calls))
        self.assertTrue(any(c[0] == "commit" for c in calls))
        self.assertIn(("checkout", "main"), calls)

    def test_ensure_checkout_dirty_on_first_branch_ok(self) -> None:
        pipeline, calls, _ = self._pipeline_for_reposition(
            current="main", dirty=" M a.txt\n"
        )
        pipeline.ensure_checkout_on_first_branch()
        self.assertFalse(any(c[0] == "checkout" for c in calls))
        self.assertFalse(any(c[:2] == ("status", "--porcelain") for c in calls))

    def test_ensure_checkout_yes_clean_no_input(self) -> None:
        pipeline, calls, _ = self._pipeline_for_reposition(
            current="feature/x", yes=True, dirty=""
        )
        import builtins

        def boom(prompt: str = "") -> str:
            raise AssertionError("input should not be called")

        original = builtins.input
        builtins.input = boom  # type: ignore[assignment]
        try:
            pipeline.ensure_checkout_on_first_branch()
        finally:
            builtins.input = original  # type: ignore[assignment]
        self.assertIn(("checkout", "main"), calls)

    def test_ensure_checkout_yes_dirty_commits_with_message(self) -> None:
        pipeline, calls, _ = self._pipeline_for_reposition(
            current="feature/x",
            yes=True,
            dirty=" M a.txt\n?? b.txt\n",
            message="save work",
        )
        pipeline.ensure_checkout_on_first_branch()
        self.assertTrue(any(c[0] == "commit" for c in calls))
        self.assertIn(("checkout", "main"), calls)

    def test_ensure_checkout_yes_dirty_requires_message(self) -> None:
        pipeline, calls, _ = self._pipeline_for_reposition(
            current="feature/x",
            yes=True,
            dirty=" M a.txt\n?? b.txt\n",
            message=None,
        )
        with self.assertRaises(ENGINE.ShipError) as ctx:
            pipeline.ensure_checkout_on_first_branch()
        self.assertIn("--message", str(ctx.exception))
        self.assertFalse(any(c[0] == "checkout" for c in calls))

    def test_ensure_checkout_dry_run_clean(self) -> None:
        pipeline, calls, explained = self._pipeline_for_reposition(
            current="feature/x", dry_run=True, dirty=""
        )
        import builtins

        def boom(prompt: str = "") -> str:
            raise AssertionError("input should not be called")

        original = builtins.input
        builtins.input = boom  # type: ignore[assignment]
        try:
            pipeline.ensure_checkout_on_first_branch()
        finally:
            builtins.input = original  # type: ignore[assignment]
        self.assertTrue(any("main" in e and "feature/x" in e for e in explained))
        self.assertIn(("checkout", "main"), calls)

    def test_ensure_checkout_dry_run_dirty_ok(self) -> None:
        pipeline, calls, _ = self._pipeline_for_reposition(
            current="feature/x", dry_run=True, dirty=" M a.txt\n"
        )
        pipeline.ensure_checkout_on_first_branch()
        self.assertIn(("checkout", "main"), calls)

    def test_ensure_checkout_fetches_missing_ref(self) -> None:
        pipeline, calls, _ = self._pipeline_for_reposition(
            current="feature/x", yes=True, dirty="", verify_refs=set()
        )
        pipeline.ensure_checkout_on_first_branch()
        self.assertTrue(
            any(
                c[0] == "fetch"
                and "refs/heads/main:refs/remotes/origin/main" in c
                for c in calls
            )
        )
        self.assertIn(("checkout", "main"), calls)

    def test_assert_dev_checkout_dry_run_noop(self) -> None:
        pipeline = ENGINE.Pipeline.__new__(ENGINE.Pipeline)
        pipeline.options = ENGINE.Options(
            dry_run=True,
            yes=False,
            config_path=None,
            message=None,
            color="never",
        )
        pipeline.dev = "main"
        calls: list[tuple] = []

        def git(*args, **kwargs):
            calls.append(args)
            return "feature/x\n"

        pipeline.git = git  # type: ignore[method-assign]
        pipeline._assert_dev_checkout()
        self.assertEqual(calls, [])

    def test_validate_pipeline_head_diverged(self) -> None:
        pipeline = ENGINE.Pipeline.__new__(ENGINE.Pipeline)
        pipeline.options = ENGINE.Options(
            dry_run=False,
            yes=True,
            config_path=None,
            message=None,
            color="never",
        )
        pipeline.dev = "main"
        pipeline.remote = "origin"

        def git(*args, **kwargs):
            if args[0] == "fetch":
                return ""
            if args[:2] == ("rev-list", "--left-right"):
                return "2\t3"
            raise AssertionError(args)

        pipeline.git = git  # type: ignore[method-assign]
        with self.assertRaises(ENGINE.ShipError) as ctx:
            pipeline.validate_pipeline_head()
        self.assertIn("diverged", str(ctx.exception).lower())

    def test_verify_final_checkout_warns_on_mismatch(self) -> None:
        pipeline = ENGINE.Pipeline.__new__(ENGINE.Pipeline)
        pipeline.options = ENGINE.Options(
            dry_run=False,
            yes=True,
            config_path=None,
            message=None,
            color="never",
        )
        pipeline.root = Path("/repo")
        pipeline.dev = "main"
        pipeline.original_branch = "feature/x"
        warnings: list[str] = []

        def git(*args, **kwargs):
            return "feature/x\n"

        pipeline.git = git  # type: ignore[method-assign]
        pipeline.warning = warnings.append  # type: ignore[method-assign]
        pipeline.verify_final_checkout()
        self.assertEqual(len(warnings), 1)
        self.assertIn("feature/x", warnings[0])
        self.assertIn("main", warnings[0])

    def test_verify_final_checkout_reads_live_state(self) -> None:
        pipeline = ENGINE.Pipeline.__new__(ENGINE.Pipeline)
        pipeline.options = ENGINE.Options(
            dry_run=False,
            yes=True,
            config_path=None,
            message=None,
            color="never",
        )
        pipeline.root = Path("/repo")
        pipeline.dev = "main"
        pipeline.original_branch = "feature/x"
        warnings: list[str] = []

        def git(*args, **kwargs):
            return "main\n"

        pipeline.git = git  # type: ignore[method-assign]
        pipeline.warning = warnings.append  # type: ignore[method-assign]
        pipeline.verify_final_checkout()
        self.assertEqual(warnings, [])

    def test_verify_final_checkout_dry_run_skips(self) -> None:
        pipeline = ENGINE.Pipeline.__new__(ENGINE.Pipeline)
        pipeline.options = ENGINE.Options(
            dry_run=True,
            yes=True,
            config_path=None,
            message=None,
            color="never",
        )
        pipeline.root = Path("/repo")
        pipeline.dev = "dev"
        pipeline.original_branch = "feature/x"
        warnings: list[str] = []
        git_calls: list[tuple] = []

        def git(*args, **kwargs):
            git_calls.append(args)
            return "feature/x\n"

        pipeline.git = git  # type: ignore[method-assign]
        pipeline.warning = warnings.append  # type: ignore[method-assign]
        pipeline.verify_final_checkout()
        self.assertEqual(warnings, [])
        self.assertEqual(git_calls, [])

    def test_run_dry_run_from_feature_records_order(self) -> None:
        pipeline = ENGINE.Pipeline.__new__(ENGINE.Pipeline)
        pipeline.options = ENGINE.Options(
            dry_run=True,
            yes=True,
            config_path=None,
            message="test",
            color="never",
            no_sweep=False,
            integrate="none",
            pipeline_order="main",
            cleanup=False,
        )
        pipeline.branches = ("main",)
        pipeline.dev = "main"
        pipeline.pre = None
        pipeline.prod = "main"
        pipeline.remote = "origin"
        pipeline.original_branch = "feature/x"
        pipeline.backend = ENGINE.BackendConfig(provider="none", cli=None, targets={})
        order: list[str] = []

        def mark(name: str):
            def _inner(*args, **kwargs):
                order.append(name)
                if name == "build_inventory":
                    return _fake_inventory()
                if name == "run_branch_menu":
                    return supagit_menu.MenuSelection(integrate=(), pipeline=("main",))
                return None

            return _inner

        for name in (
            "preflight_repo",
            "build_inventory",
            "run_branch_menu",
            "ensure_checkout_on_first_branch",
            "validate_pipeline_head",
            "commit_and_publish_dev",
            "ff_sync_first_branch",
            "_assert_dev_synced",
            "run_checks",
            "validate_clean_after_checks",
            "return_to_dev",
            "verify_final_checkout",
        ):
            setattr(pipeline, name, mark(name))
        pipeline.optional_cleanup = mark("optional_cleanup")  # type: ignore[method-assign]
        pipeline.status = lambda *a, **k: None  # type: ignore[method-assign]
        pipeline.tutor_confirm = lambda *a, **k: None  # type: ignore[method-assign]
        pipeline._require_noninteractive_selection = lambda: None  # type: ignore[method-assign]
        pipeline.run()
        self.assertEqual(order[0], "preflight_repo")
        self.assertIn("ensure_checkout_on_first_branch", order)
        self.assertIn("validate_pipeline_head", order)
        self.assertLess(
            order.index("ensure_checkout_on_first_branch"),
            order.index("validate_pipeline_head"),
        )
        self.assertLess(
            order.index("commit_and_publish_dev"),
            order.index("ff_sync_first_branch"),
        )
        self.assertEqual(order[-1], "verify_final_checkout")

    def test_first_branch_in_other_worktree_refused(self) -> None:
        porcelain = (
            "worktree /repo\nbranch refs/heads/feature/x\n\n"
            "worktree /wt-main\nbranch refs/heads/main\n"
        )
        pipeline, calls, _ = self._pipeline_for_reposition(
            current="feature/x",
            worktree_porcelain=porcelain,
            yes=True,
        )
        with self.assertRaises(ENGINE.ShipError) as ctx:
            pipeline.ensure_checkout_on_first_branch()
        self.assertIn("/wt-main", str(ctx.exception))
        self.assertFalse(any(c[0] == "checkout" for c in calls))

    def test_first_branch_worktree_at_root_ok(self) -> None:
        porcelain = "worktree /repo\nbranch refs/heads/main\n"
        pipeline, calls, _ = self._pipeline_for_reposition(
            current="feature/x",
            worktree_porcelain=porcelain,
            yes=True,
        )
        pipeline.ensure_checkout_on_first_branch()
        self.assertIn(("checkout", "main"), calls)

    def test_detached_reachable_repositions(self) -> None:
        pipeline, calls, explained = self._pipeline_for_reposition(
            current="",
            dry_run=True,
            contains="feature/x\n",
            short_sha="deadbee",
        )
        pipeline.ensure_checkout_on_first_branch()
        self.assertIn(("checkout", "main"), calls)
        self.assertTrue(any("detached HEAD at deadbee" in e for e in explained))

    def test_detached_unreachable_refused(self) -> None:
        pipeline, calls, _ = self._pipeline_for_reposition(
            current="",
            yes=True,
            contains="",
            short_sha="deadbee",
        )
        with self.assertRaises(ENGINE.ShipError) as ctx:
            pipeline.ensure_checkout_on_first_branch()
        text = str(ctx.exception)
        self.assertIn("deadbee", text)
        self.assertIn("git switch -c", text)
        self.assertNotIn("<", text)
        self.assertFalse(any(c[0] == "checkout" for c in calls))

    def test_announce_launch_checkout_explains_no_manual_switch(self) -> None:
        pipeline = ENGINE.Pipeline.__new__(ENGINE.Pipeline)
        pipeline.options = ENGINE.Options(
            dry_run=True,
            yes=True,
            config_path=None,
            message=None,
            color="never",
        )
        pipeline.root = Path("/repo")
        explained: list[str] = []

        def git(*args, **kwargs):
            if args[:2] == ("branch", "--show-current"):
                return "feature/x\n"
            raise AssertionError(args)

        pipeline.git = git  # type: ignore[method-assign]
        pipeline.explain = lambda message, **_kwargs: explained.append(message)  # type: ignore[method-assign]
        pipeline.announce_launch_checkout()
        self.assertEqual(len(explained), 1)
        self.assertIn("feature/x", explained[0])
        self.assertIn("Do not change branches yourself", explained[0])

    def test_maybe_return_to_start_branch_checkouts_when_clean(self) -> None:
        pipeline = ENGINE.Pipeline.__new__(ENGINE.Pipeline)
        pipeline.options = ENGINE.Options(
            dry_run=False,
            yes=False,
            config_path=None,
            message=None,
            color="never",
        )
        pipeline.root = Path("/repo")
        pipeline.dev = "dev"
        pipeline.original_branch = "feature/x"
        pipeline.GREEN = ""
        calls: list[tuple] = []
        statuses: list[str] = []

        def git(*args, **kwargs):
            calls.append(args)
            if args[:2] == ("status", "--porcelain"):
                return ""
            if args[0] == "checkout":
                return ""
            raise AssertionError(args)

        pipeline.git = git  # type: ignore[method-assign]
        pipeline.explain = lambda *_a, **_k: None  # type: ignore[method-assign]
        pipeline.ask_yes_no = lambda *_a, **_k: True  # type: ignore[method-assign]
        pipeline.status = lambda msg, _c: statuses.append(msg)  # type: ignore[method-assign]
        pipeline.maybe_return_to_start_branch()
        self.assertIn(("checkout", "feature/x"), calls)
        self.assertTrue(any("feature/x" in s for s in statuses))

    def test_maybe_return_to_start_branch_yes_does_not_switch(self) -> None:
        pipeline = ENGINE.Pipeline.__new__(ENGINE.Pipeline)
        pipeline.options = ENGINE.Options(
            dry_run=False,
            yes=True,
            config_path=None,
            message=None,
            color="never",
        )
        pipeline.root = Path("/repo")
        pipeline.dev = "dev"
        pipeline.original_branch = "feature/x"
        explained: list[str] = []
        calls: list[tuple] = []

        def git(*args, **kwargs):
            calls.append(args)
            return ""

        pipeline.git = git  # type: ignore[method-assign]
        pipeline.explain = lambda message, **_kwargs: explained.append(message)  # type: ignore[method-assign]
        pipeline.maybe_return_to_start_branch()
        self.assertEqual(calls, [])
        self.assertTrue(any("--yes" in e for e in explained))
        self.assertTrue(any("feature/x" in e for e in explained))

    def test_no_sweep_reposition_explanation_self_contained(self) -> None:
        pipeline, _, explained = self._pipeline_for_reposition(
            current="feature/x", dry_run=True, dirty=""
        )
        pipeline.ensure_checkout_on_first_branch()
        joined = "\n".join(explained)
        self.assertIn("feature/x", joined)
        self.assertIn("main", joined)

    def test_resolve_selection_rebuilds_when_base_changes(self) -> None:
        pipeline = ENGINE.Pipeline.__new__(ENGINE.Pipeline)
        pipeline.options = ENGINE.Options(
            dry_run=True,
            yes=True,
            config_path=None,
            message=None,
            color="never",
        )
        pipeline.branches = ("dev", "pre", "prod")
        pipeline.remote = "origin"
        pipeline.original_branch = "dev"
        pipeline.layout = _fake_inventory().layout
        rebuilds: list[str] = []
        printed: list[str] = []

        def build_inventory(*, first_branch: str | None = None) -> RepoInventory:
            rebuilds.append(first_branch or "")
            inv = _fake_inventory()
            # mark "old" contained in pre only when first_branch is pre
            branches = []
            for b in inv.branches:
                contained = b.contained_in_first
                if b.name == "old":
                    contained = first_branch == "pre" or (
                        first_branch is None and inv.first_branch == "dev" and b.contained_in_first
                    )
                    if first_branch == "pre":
                        contained = True
                    elif first_branch == "dev":
                        contained = False
                branches.append(
                    BranchInfo(
                        b.name,
                        b.is_pipeline,
                        b.has_worktree,
                        b.worktree_path,
                        b.ahead,
                        b.behind,
                        contained if b.name == "old" and first_branch is not None else b.contained_in_first,
                        b.upstream,
                        b.dirty,
                    )
                )
            return RepoInventory(
                inv.layout, inv.worktrees, tuple(branches), first_branch or "dev"
            )

        pipeline.build_inventory = build_inventory  # type: ignore[method-assign]
        pipeline.explain = lambda message, **_kwargs: printed.append(message)  # type: ignore[method-assign]
        import builtins

        original_print = builtins.print
        builtins.print = printed.append  # type: ignore[assignment]
        try:
            selection = pipeline._resolve_selection(
                _fake_inventory(),
                "2,1,3",
                "",
                ("dev", "pre", "prod"),
                interactive=True,
            )
        finally:
            builtins.print = original_print  # type: ignore[assignment]
        self.assertEqual(rebuilds, ["pre"])
        self.assertEqual(selection.pipeline, ("pre", "dev", "prod"))
        self.assertTrue(any("pre" in str(p) for p in printed))

    def test_resolve_selection_no_rebuild_on_default(self) -> None:
        pipeline = ENGINE.Pipeline.__new__(ENGINE.Pipeline)
        pipeline.options = ENGINE.Options(
            dry_run=True,
            yes=True,
            config_path=None,
            message=None,
            color="never",
        )
        pipeline.branches = ("dev", "pre", "prod")
        rebuilds: list[str] = []

        def build_inventory(*, first_branch: str | None = None) -> RepoInventory:
            rebuilds.append(first_branch or "")
            return _fake_inventory()

        pipeline.build_inventory = build_inventory  # type: ignore[method-assign]
        selection = pipeline._resolve_selection(
            _fake_inventory(), "", "none", ("dev", "pre", "prod")
        )
        self.assertEqual(rebuilds, [])
        self.assertEqual(selection.pipeline, ("dev", "pre", "prod"))

    def test_resolve_selection_drops_contained_on_new_base(self) -> None:
        pipeline = ENGINE.Pipeline.__new__(ENGINE.Pipeline)
        pipeline.options = ENGINE.Options(
            dry_run=True,
            yes=True,
            config_path=None,
            message=None,
            color="never",
        )
        pipeline.branches = ("dev", "pre", "prod")
        pipeline.original_branch = "dev"
        pipeline.layout = _fake_inventory().layout

        def build_inventory(*, first_branch: str | None = None) -> RepoInventory:
            inv = _fake_inventory()
            branches = []
            for b in inv.branches:
                contained = b.contained_in_first
                if b.name == "feature/x":
                    contained = first_branch == "pre"
                branches.append(
                    BranchInfo(
                        b.name,
                        b.is_pipeline,
                        b.has_worktree,
                        b.worktree_path,
                        b.ahead,
                        b.behind,
                        contained,
                        b.upstream,
                        b.dirty,
                    )
                )
            return RepoInventory(
                inv.layout, inv.worktrees, tuple(branches), first_branch or "dev"
            )

        pipeline.build_inventory = build_inventory  # type: ignore[method-assign]
        with patch("builtins.print"):
            selection = pipeline._resolve_selection(
                _fake_inventory(),
                "pre,dev,prod",
                "",
                ("dev", "pre", "prod"),
            )
        self.assertNotIn("feature/x", selection.integrate)

    def test_yes_flags_path_rederives_base(self) -> None:
        pipeline = ENGINE.Pipeline.__new__(ENGINE.Pipeline)
        pipeline.options = ENGINE.Options(
            dry_run=True,
            yes=True,
            config_path=None,
            message=None,
            color="never",
            integrate="none",
            pipeline_order="pre,dev,prod",
        )
        pipeline.branches = ("dev", "pre", "prod")
        pipeline.original_branch = "dev"
        pipeline.layout = _fake_inventory().layout
        rebuilds: list[str | None] = []

        def build_inventory(*, first_branch: str | None = None) -> RepoInventory:
            rebuilds.append(first_branch)
            inv = _fake_inventory()
            return RepoInventory(
                inv.layout, inv.worktrees, inv.branches, first_branch or "dev"
            )

        pipeline.build_inventory = build_inventory  # type: ignore[method-assign]
        with patch("builtins.print"):
            selection = pipeline._resolve_selection(
                _fake_inventory(),
                "pre,dev,prod",
                "none",
                (),
            )
        self.assertEqual(rebuilds, ["pre"])
        self.assertEqual(selection.pipeline[0], "pre")

    def test_menu_rejects_non_pipeline_branch(self) -> None:
        with self.assertRaises(supagit_menu.MenuError) as ctx:
            supagit_menu.parse_pipeline_line(
                _fake_inventory(), "feature/x", ("dev", "pre", "prod")
            )
        text = str(ctx.exception)
        self.assertIn("feature/x", text)
        self.assertIn("dev, pre, prod", text)
        self.assertIn(".supagit.json", text)
        self.assertIn("independent", text.lower())

    def test_run_branch_menu_forces_plan_confirm_under_dry_run(self) -> None:
        pipeline = ENGINE.Pipeline.__new__(ENGINE.Pipeline)
        pipeline.options = ENGINE.Options(
            dry_run=True,
            yes=False,
            config_path=None,
            message=None,
            color="never",
        )
        pipeline.branches = ("dev", "pre", "prod")
        pipeline.remote = "origin"
        pipeline.original_branch = "dev"
        explain_kwargs: list[dict] = []

        def capture_explain(
            message: str, *, ask_continue: bool = True, force_confirm: bool = False
        ) -> None:
            explain_kwargs.append(
                {"ask_continue": ask_continue, "force_confirm": force_confirm}
            )

        pipeline.explain = capture_explain  # type: ignore[method-assign]
        pipeline.tutor_prompt = lambda explanation, prompt: ""  # type: ignore[method-assign]
        pipeline._require_noninteractive_selection = lambda: None  # type: ignore[method-assign]
        pipeline._explain_situation_preflight = lambda *_a, **_k: None  # type: ignore[method-assign]

        selection = pipeline.run_branch_menu(_fake_inventory())
        self.assertEqual(selection.pipeline, ("dev", "pre", "prod"))
        self.assertGreaterEqual(len(explain_kwargs), 2)
        # Menu list: no Continue?; execution plan: force_confirm for dry-run gate.
        self.assertEqual(explain_kwargs[0]["ask_continue"], False)
        self.assertFalse(explain_kwargs[0]["force_confirm"])
        plan_call = explain_kwargs[-1]
        self.assertTrue(plan_call["force_confirm"])

    def test_no_sweep_run_calls_situation_preflight(self) -> None:
        pipeline = ENGINE.Pipeline.__new__(ENGINE.Pipeline)
        pipeline.options = ENGINE.Options(
            dry_run=True,
            yes=True,
            config_path=None,
            message=None,
            color="never",
            no_sweep=True,
            integrate=None,
            pipeline_order=None,
            cleanup=False,
        )
        pipeline.branches = ("main",)
        pipeline.dev = "main"
        pipeline.remote = "origin"
        pipeline.backend = ENGINE.BackendConfig(provider="none", cli=None, targets={})
        called: list[str] = []

        def mark_preflight(selection, inventory):
            called.append("situation_preflight")
            return None

        pipeline.preflight_repo = lambda: None  # type: ignore[method-assign]
        pipeline.build_inventory = lambda **_k: _fake_inventory()  # type: ignore[method-assign]
        pipeline._explain_situation_preflight = mark_preflight  # type: ignore[method-assign]
        pipeline.ensure_checkout_on_first_branch = lambda: None  # type: ignore[method-assign]
        pipeline.validate_pipeline_head = lambda: None  # type: ignore[method-assign]
        pipeline.ff_sync_first_branch = lambda: None  # type: ignore[method-assign]
        pipeline.commit_and_publish_dev = lambda: None  # type: ignore[method-assign]
        pipeline._assert_dev_synced = lambda: None  # type: ignore[method-assign]
        pipeline.run_checks = lambda: None  # type: ignore[method-assign]
        pipeline.validate_clean_after_checks = lambda: None  # type: ignore[method-assign]
        pipeline.tutor_confirm = lambda *a, **k: None  # type: ignore[method-assign]
        pipeline.return_to_dev = lambda: None  # type: ignore[method-assign]
        pipeline.optional_cleanup = lambda *a, **k: None  # type: ignore[method-assign]
        pipeline.verify_final_checkout = lambda: None  # type: ignore[method-assign]
        pipeline.status = lambda *a, **k: None  # type: ignore[method-assign]
        pipeline.maybe_return_to_start_branch = lambda: None  # type: ignore[method-assign]
        pipeline.run()
        self.assertEqual(called, ["situation_preflight"])

    def test_menu_rejects_unknown_branch(self) -> None:
        with self.assertRaises(supagit_menu.MenuError) as ctx:
            supagit_menu.parse_pipeline_line(
                _fake_inventory(), "no-such", ("dev", "pre", "prod")
            )
        self.assertIn("no-such", str(ctx.exception))

    def test_menu_rejects_bad_pipeline_number(self) -> None:
        with self.assertRaises(supagit_menu.MenuError) as ctx:
            supagit_menu.parse_pipeline_line(
                _fake_inventory(), "9", ("dev", "pre", "prod")
            )
        self.assertIn("9", str(ctx.exception))

    def test_render_menu_current_branch_header(self) -> None:
        text = supagit_menu.render_sweeper_menu(
            _fake_inventory(), current_branch="feature/x"
        )
        self.assertTrue(text.startswith("You are on: feature/x"))

    def test_promote_uses_pr_when_gate_requires_it(self) -> None:
        pipeline = ENGINE.Pipeline.__new__(ENGINE.Pipeline)
        pipeline.options = ENGINE.Options(
            dry_run=False,
            yes=True,
            config_path=None,
            message=None,
            color="never",
        )
        pipeline.root = Path("/repo")
        pipeline.remote = "origin"
        explained: list[str] = []
        calls: list[str] = []

        def git(*args, **kwargs):
            if args[:2] == ("remote", "get-url"):
                return "git@github.com:acme/demo.git\n"
            return ""

        def promote_via_pr(source, target, remote_url):
            calls.append(f"pr:{source}->{target}")

        def promote_direct(source, target):
            calls.append(f"direct:{source}->{target}")

        pipeline.git = git  # type: ignore[method-assign]
        pipeline.explain = lambda message, **_kwargs: explained.append(message)  # type: ignore[method-assign]
        pipeline.tutor_confirm = lambda *a, **k: None  # type: ignore[method-assign]
        pipeline._promote_via_pr = promote_via_pr  # type: ignore[method-assign]
        pipeline._promote_direct = promote_direct  # type: ignore[method-assign]

        with patch.object(
            ENGINE.supagit_sweep,
            "inspect_promote_gate",
            return_value=ENGINE.supagit_sweep.PromoteGate(
                owner="acme",
                repo="demo",
                branch="main",
                visibility="public",
                requires_pull_request=True,
                rule_types=("pull_request",),
            ),
        ):
            pipeline.promote("dev", "main")
        self.assertEqual(calls, ["pr:dev->main"])
        self.assertTrue(any("pull request" in e.lower() or "pr" in e.lower() for e in explained))

    def test_promote_uses_direct_when_unprotected(self) -> None:
        pipeline = ENGINE.Pipeline.__new__(ENGINE.Pipeline)
        pipeline.options = ENGINE.Options(
            dry_run=False,
            yes=True,
            config_path=None,
            message=None,
            color="never",
        )
        pipeline.root = Path("/repo")
        pipeline.remote = "origin"
        calls: list[str] = []

        def git(*args, **kwargs):
            if args[:2] == ("remote", "get-url"):
                return "git@github.com:acme/demo.git\n"
            return ""

        pipeline.git = git  # type: ignore[method-assign]
        pipeline.explain = lambda *_a, **_k: None  # type: ignore[method-assign]
        pipeline.tutor_confirm = lambda *a, **k: None  # type: ignore[method-assign]
        pipeline._promote_via_pr = lambda *a, **k: calls.append("pr")  # type: ignore[method-assign]
        pipeline._promote_direct = lambda *a, **k: calls.append("direct")  # type: ignore[method-assign]

        with patch.object(
            ENGINE.supagit_sweep,
            "inspect_promote_gate",
            return_value=ENGINE.supagit_sweep.PromoteGate(
                owner="acme",
                repo="demo",
                branch="main",
                visibility="private",
                requires_pull_request=False,
                rule_types=(),
            ),
        ):
            pipeline.promote("dev", "main")
        self.assertEqual(calls, ["direct"])


if __name__ == "__main__":
    unittest.main()
