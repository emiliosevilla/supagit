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

    def test_stale_upstream_after_remote_delete_not_used(self) -> None:
        """Deleted remote branch must not leave a phantom origin/* sync target."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _run(root, "git", "init", "-b", "dev")
            _run(root, "git", "config", "user.email", "t@example.com")
            _run(root, "git", "config", "user.name", "t")
            (root / "a").write_text("1\n", encoding="utf-8")
            _run(root, "git", "add", "a")
            _run(root, "git", "commit", "-m", "init")
            _run(root, "git", "checkout", "-b", "work")
            (root / "a").write_text("work\n", encoding="utf-8")
            _run(root, "git", "add", "a")
            _run(root, "git", "commit", "-m", "work")
            _run(root, "git", "checkout", "dev")
            # Fake remote + upstream config as after push -u, then prune deleted work.
            _run(root, "git", "remote", "add", "origin", "https://example.com/repo.git")
            _run(root, "git", "update-ref", "refs/remotes/origin/dev", "dev")
            _run(root, "git", "update-ref", "refs/remotes/origin/work", "work")
            _run(root, "git", "branch", "--set-upstream-to=origin/dev", "dev")
            _run(root, "git", "branch", "--set-upstream-to=origin/work", "work")
            # Post-prune: configured upstream remains, remote-tracking ref is gone.
            _run(root, "git", "update-ref", "-d", "refs/remotes/origin/work")
            self.assertEqual(
                _run(root, "git", "config", "--get", "branch.work.merge"),
                "refs/heads/work",
            )
            with self.assertRaises(subprocess.CalledProcessError):
                _run(root, "git", "rev-parse", "--verify", "refs/remotes/origin/work")

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
                layout, ("dev",), "origin", git_runner=run_git
            )
            work = next(b for b in inv.branches if b.name == "work")
            self.assertNotEqual(work.upstream, "origin/work")
            self.assertIsNone(work.upstream)
            self.assertEqual(work.ahead, 0)
            self.assertEqual(work.behind, 0)


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
        self.assertIn("already in", text)
        self.assertNotIn("[ ]", text)
        self.assertIn("old", text)
        self.assertRegex(text, r"(?m)^1\. dev")
        self.assertRegex(text, r"(?m)^2\. pre")
        self.assertRegex(text, r"(?m)^3\. prod")
        self.assertNotIn("Pipeline order (comma-separated", text)
        self.assertNotIn("[pipeline", text)

    def test_render_sweeper_menu_empty_work_shows_none(self) -> None:
        layout = RepoLayout(
            launch_root=Path("/repo"),
            main_root=Path("/repo"),
            common_dir=Path("/repo/.git"),
            is_linked_launch=False,
        )
        inv = RepoInventory(
            layout,
            (),
            (
                BranchInfo(
                    "main", True, True, Path("/repo"), 0, 0, True, "origin/main", False
                ),
            ),
            "main",
        )
        text = supagit_menu.render_sweeper_menu(inv)
        self.assertIn("nothing to merge", text)
        self.assertIn("main", text)
        self.assertIn("Release pipeline", text)

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

    def test_render_execution_plan_surfaces_migrate_items(self) -> None:
        import supagit_i18n

        supagit_i18n.set_lang("en")
        selection = supagit_menu.MenuSelection(
            integrate=("feature/x",), pipeline=("dev", "pre", "prod")
        )
        text = supagit_menu.render_execution_plan(
            selection,
            first_branch="dev",
            remote="origin",
            migrate_targets={
                "dev": "dev-ref",
                "pre": "pre-ref",
                "prod": "prod-ref",
            },
        )
        migrate_dev = supagit_i18n.t(
            "plan_migrate_item", label="dev", ref="dev-ref"
        )
        migrate_pre = supagit_i18n.t(
            "plan_migrate_item", label="pre", ref="pre-ref"
        )
        migrate_prod = supagit_i18n.t(
            "plan_migrate_item", label="prod", ref="prod-ref"
        )
        self.assertIn(migrate_dev, text)
        self.assertIn(migrate_pre, text)
        self.assertIn(migrate_prod, text)
        self.assertLess(text.index(migrate_dev), text.index("Publish dev"))
        self.assertLess(text.index("Integrate feature/x"), text.index(migrate_pre))
        self.assertLess(text.index(migrate_pre), text.index("Merge dev into pre"))
        self.assertLess(text.index(migrate_prod), text.index("Merge pre into prod"))

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
    def test_ensure_ready_refreshes_stale_token(self) -> None:
        calls: list[list[str]] = []
        attempts = {"status": 0}

        def run_raw(cmd, **kwargs):
            calls.append(list(cmd))
            if cmd[:3] == ["gh", "auth", "status"]:
                attempts["status"] += 1
                if attempts["status"] == 1:
                    raise RuntimeError("token in keyring is invalid")
                return ""
            if cmd[:3] == ["gh", "auth", "refresh"]:
                return ""
            raise AssertionError(cmd)

        client = supagit_sweep.GhClient(run_raw, dry_run=False)
        client.ensure_ready()
        self.assertEqual(calls[0], ["gh", "auth", "status"])
        self.assertEqual(calls[1], ["gh", "auth", "refresh", "-h", "github.com"])
        self.assertEqual(calls[2], ["gh", "auth", "status"])

    def test_ensure_ready_login_fallback_on_refresh_failure_tty(self) -> None:
        """Refresh fails on TTY → launch gh auth login once, then re-verify."""
        calls: list[list[str]] = []
        attempts = {"status": 0}

        def run_raw(cmd, **kwargs):
            calls.append(list(cmd))
            if cmd[:3] == ["gh", "auth", "status"]:
                attempts["status"] += 1
                if attempts["status"] == 1:
                    raise RuntimeError("token in keyring is invalid")
                return ""
            if cmd[:3] == ["gh", "auth", "refresh"]:
                raise RuntimeError("refresh denied")
            if cmd[:3] == ["gh", "auth", "login"]:
                return ""
            raise AssertionError(cmd)

        client = supagit_sweep.GhClient(run_raw, dry_run=False)
        with patch.object(sys.stdin, "isatty", return_value=True):
            client.ensure_ready()
        self.assertEqual(calls[0], ["gh", "auth", "status"])
        self.assertEqual(calls[1], ["gh", "auth", "refresh", "-h", "github.com"])
        self.assertEqual(calls[2], ["gh", "auth", "login", "-h", "github.com"])
        self.assertEqual(calls[3], ["gh", "auth", "status"])
        self.assertEqual(attempts["status"], 2)

    def test_ensure_ready_refresh_failure_non_tty_fails_closed(self) -> None:
        """No TTY → do not hang on login; fail closed without 'run login yourself'."""
        calls: list[list[str]] = []

        def run_raw(cmd, **kwargs):
            calls.append(list(cmd))
            if cmd[:3] == ["gh", "auth", "status"]:
                raise RuntimeError("token in keyring is invalid")
            if cmd[:3] == ["gh", "auth", "refresh"]:
                raise RuntimeError("refresh denied")
            raise AssertionError(f"unexpected command (no login without TTY): {cmd}")

        client = supagit_sweep.GhClient(run_raw, dry_run=False)
        with patch.object(sys.stdin, "isatty", return_value=False):
            with self.assertRaises(supagit_sweep.SweepError) as ctx:
                client.ensure_ready()
        message = str(ctx.exception).lower()
        self.assertIn("refresh", message)
        self.assertNotIn("run `gh auth login`", message)
        self.assertNotIn("ejecuta `gh auth login`", message)
        self.assertEqual(
            calls,
            [
                ["gh", "auth", "status"],
                ["gh", "auth", "refresh", "-h", "github.com"],
            ],
        )

    def test_ensure_ready_login_failure_on_tty_fails_closed(self) -> None:
        """TTY login attempted once; if it fails, fail closed without manual primary fix."""
        calls: list[list[str]] = []

        def run_raw(cmd, **kwargs):
            calls.append(list(cmd))
            if cmd[:3] == ["gh", "auth", "status"]:
                raise RuntimeError("token in keyring is invalid")
            if cmd[:3] == ["gh", "auth", "refresh"]:
                raise RuntimeError("refresh denied")
            if cmd[:3] == ["gh", "auth", "login"]:
                raise RuntimeError("login cancelled")
            raise AssertionError(cmd)

        client = supagit_sweep.GhClient(run_raw, dry_run=False)
        with patch.object(sys.stdin, "isatty", return_value=True):
            with self.assertRaises(supagit_sweep.SweepError) as ctx:
                client.ensure_ready()
        message = str(ctx.exception).lower()
        self.assertIn("login", message)
        self.assertNotIn("run `gh auth login`", message)
        self.assertEqual(calls[2], ["gh", "auth", "login", "-h", "github.com"])
        self.assertEqual(len(calls), 3)

    def test_ensure_ready_fails_when_gh_missing(self) -> None:
        def run_raw(cmd, **kwargs):
            raise FileNotFoundError("gh")

        client = supagit_sweep.GhClient(run_raw, dry_run=False)
        with self.assertRaises(supagit_sweep.SweepError) as ctx:
            client.ensure_ready()
        self.assertIn("not installed", str(ctx.exception).lower())

    def test_ensure_ready_fails_when_gh_unauthenticated(self) -> None:
        def run_raw(cmd, **kwargs):
            raise RuntimeError("network unreachable")

        client = supagit_sweep.GhClient(run_raw, dry_run=False)
        with self.assertRaises(supagit_sweep.SweepError) as ctx:
            client.ensure_ready()
        self.assertIn("network unreachable", str(ctx.exception))

    def test_merge_pr_policy_ladder_merge_then_auto_then_admin(self) -> None:
        """Policy blocks climb merge → --auto → --admin (never admin first)."""
        calls: list[list[str]] = []
        outcomes = [
            RuntimeError("base branch policy prohibits the merge"),
            RuntimeError("base branch policy prohibits the merge"),
            "",
        ]

        def run_raw(cmd, **kwargs):
            calls.append(list(cmd))
            outcome = outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return ""

        client = supagit_sweep.GhClient(run_raw, dry_run=False)
        client.merge_pr(9, delete_branch=False)
        self.assertEqual(calls[0], ["gh", "pr", "merge", "9", "--merge"])
        self.assertEqual(
            calls[1], ["gh", "pr", "merge", "9", "--merge", "--auto"]
        )
        self.assertEqual(
            calls[2], ["gh", "pr", "merge", "9", "--merge", "--admin"]
        )
        self.assertNotIn("--admin", calls[0])
        self.assertNotIn("--admin", calls[1])

    def test_merge_pr_policy_auto_succeeds_without_admin(self) -> None:
        calls: list[list[str]] = []
        outcomes = [
            RuntimeError("not mergeable by policy"),
            "",
        ]

        def run_raw(cmd, **kwargs):
            calls.append(list(cmd))
            if list(cmd)[:3] == ["gh", "pr", "view"]:
                return '{"state":"MERGED"}'
            outcome = outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return ""

        client = supagit_sweep.GhClient(run_raw, dry_run=False)
        with patch.object(supagit_sweep, "sleep", lambda _s: None):
            client.merge_pr(11, delete_branch=True)
        self.assertEqual(
            calls[0], ["gh", "pr", "merge", "11", "--merge", "--delete-branch"]
        )
        self.assertEqual(
            calls[1],
            ["gh", "pr", "merge", "11", "--merge", "--auto", "--delete-branch"],
        )
        self.assertTrue(any(c[:3] == ["gh", "pr", "view"] for c in calls))
        self.assertFalse(any("--admin" in c for c in calls))

    def test_merge_pr_auto_exit_zero_waits_for_merged_before_success(self) -> None:
        """`--auto` exit 0 only arms auto-merge; success requires MERGED state."""
        calls: list[list[str]] = []
        states = ["OPEN", "OPEN", "MERGED"]

        def run_raw(cmd, **kwargs):
            calls.append(list(cmd))
            if list(cmd)[:3] == ["gh", "pr", "view"]:
                return f'{{"state":"{states.pop(0)}"}}'
            if list(cmd)[:4] == ["gh", "pr", "merge", "15"]:
                if "--auto" in cmd:
                    return ""
                if "--admin" in cmd:
                    raise AssertionError("must not escalate to admin once MERGED")
                raise RuntimeError("base branch policy prohibits the merge")
            raise AssertionError(cmd)

        sleeps: list[float] = []

        def fake_sleep(seconds: float) -> None:
            sleeps.append(seconds)

        client = supagit_sweep.GhClient(run_raw, dry_run=False)
        with patch.object(supagit_sweep, "sleep", fake_sleep):
            client.merge_pr(15, delete_branch=False)

        self.assertIn(
            ["gh", "pr", "merge", "15", "--merge", "--auto"], calls
        )
        self.assertEqual(sum(1 for c in calls if c[:3] == ["gh", "pr", "view"]), 3)
        self.assertEqual(len(sleeps), 2)
        self.assertFalse(any("--admin" in c for c in calls))

    def test_merge_pr_auto_armed_not_merged_escalates_to_admin(self) -> None:
        """Auto exit 0 without MERGED must not return success; try --admin next."""
        calls: list[list[str]] = []

        def run_raw(cmd, **kwargs):
            calls.append(list(cmd))
            if list(cmd)[:3] == ["gh", "pr", "view"]:
                return '{"state":"OPEN"}'
            if list(cmd)[:4] == ["gh", "pr", "merge", "16"]:
                if "--admin" in cmd:
                    return ""
                if "--auto" in cmd:
                    return ""
                raise RuntimeError("not mergeable by policy")
            raise AssertionError(cmd)

        client = supagit_sweep.GhClient(run_raw, dry_run=False)
        with patch.object(supagit_sweep, "sleep", lambda _s: None):
            client.merge_pr(16, delete_branch=False)

        self.assertTrue(any("--auto" in c for c in calls))
        self.assertTrue(any("--admin" in c for c in calls))
        view_before_admin = True
        seen_admin = False
        for c in calls:
            if "--admin" in c:
                seen_admin = True
                break
            if c[:3] == ["gh", "pr", "view"]:
                view_before_admin = True
        self.assertTrue(seen_admin)
        self.assertTrue(view_before_admin)

    def test_merge_pr_auto_armed_admin_fails_fail_closed(self) -> None:
        import supagit_i18n

        supagit_i18n.set_lang("en")
        calls: list[list[str]] = []

        def run_raw(cmd, **kwargs):
            calls.append(list(cmd))
            if list(cmd)[:3] == ["gh", "pr", "view"]:
                return '{"state":"OPEN"}'
            if list(cmd)[:4] == ["gh", "pr", "merge", "17"]:
                if "--admin" in cmd:
                    raise RuntimeError("admin merge blocked")
                if "--auto" in cmd:
                    return ""
                raise RuntimeError("not mergeable by policy")
            raise AssertionError(cmd)

        client = supagit_sweep.GhClient(run_raw, dry_run=False)
        with patch.object(supagit_sweep, "sleep", lambda _s: None):
            with self.assertRaises(supagit_sweep.SweepError) as ctx:
                client.merge_pr(17, delete_branch=False)
        detail = str(ctx.exception).lower()
        self.assertIn("17", detail)
        self.assertTrue("auto" in detail or "armed" in detail or "pending" in detail)
        self.assertTrue(any("--auto" in c for c in calls))
        self.assertTrue(any("--admin" in c for c in calls))

    def test_merge_pr_refreshes_token_then_retries(self) -> None:
        calls: list[list[str]] = []
        outcomes = [
            RuntimeError("token expired"),
            "",
            "",
        ]

        def run_raw(cmd, **kwargs):
            calls.append(list(cmd))
            outcome = outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return ""

        client = supagit_sweep.GhClient(run_raw, dry_run=False)
        client.merge_pr(10, admin=True, delete_branch=True)
        self.assertEqual(calls[0][:4], ["gh", "pr", "merge", "10"])
        self.assertEqual(calls[1], ["gh", "auth", "refresh", "-h", "github.com"])
        self.assertEqual(calls[2][:4], ["gh", "pr", "merge", "10"])

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

    def test_promote_via_pr_uses_merge_ladder_not_admin_first(self) -> None:
        merges: list[tuple] = []
        pipeline = ENGINE.Pipeline.__new__(ENGINE.Pipeline)
        pipeline.options = ENGINE.Options(
            dry_run=False,
            yes=True,
            config_path=None,
            message=None,
            color="never",
        )
        pipeline.root = Path("/repo")
        pipeline.launch_root = Path("/repo")
        pipeline.main_root = Path("/repo")
        pipeline.remote = "origin"
        explained: list[str] = []

        def git(*args, **kwargs):
            if args[:2] == ("worktree", "list"):
                return "worktree /repo\nbranch refs/heads/main\n"
            return ""

        pipeline.git = git  # type: ignore[method-assign]
        pipeline._sweep_git = lambda *a, cwd=None, capture=True: ""  # type: ignore[method-assign]
        pipeline.explain = lambda message, **_kwargs: explained.append(message)  # type: ignore[method-assign]
        pipeline.tutor_confirm = lambda *a, **k: None  # type: ignore[method-assign]

        class FakeGh:
            def ensure_ready(self) -> None: ...
            def ensure_github_remote(self, url: str) -> None: ...
            def find_open_pr(self, head, base): return 5
            def create_promote_pr(self, head, base, title): return 5
            def merge_pr(self, number: int, **kwargs):
                merges.append((number, kwargs))

        with patch.object(ENGINE.supagit_sweep, "GhClient", return_value=FakeGh()):
            with patch.object(ENGINE.supagit_sweep, "push_branch", return_value=None):
                pipeline._promote_via_pr("dev", "main", "git@github.com:acme/demo.git")

        self.assertEqual(len(merges), 1)
        self.assertEqual(merges[0][0], 5)
        self.assertEqual(merges[0][1].get("delete_branch"), False)
        self.assertNotEqual(merges[0][1].get("admin"), True)

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
    def test_all_sensitive_paths_abort_before_commit(self) -> None:
        calls: list[tuple[list[str], Path]] = []

        def reject_sensitive(paths: Sequence[str], cwd: Path) -> Sequence[str]:
            calls.append((list(paths), cwd))
            raise ValueError("only secrets")

        def run_git(*args, cwd=None, capture=True):
            if args[:2] == ("status", "--porcelain"):
                return " M .env\n?? .env.local\n"
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
        self.assertEqual(calls[0][1], Path("/wt"))
        self.assertIn(".env", calls[0][0])
        self.assertIn(".env.local", calls[0][0])

    def test_mixed_tree_excludes_secrets_and_commits_rest(self) -> None:
        git_calls: list[tuple] = []
        guard_calls: list[list[str]] = []

        def reject_sensitive(paths: Sequence[str], cwd: Path) -> Sequence[str]:
            guard_calls.append(list(paths))
            self.assertEqual(cwd, Path("/wt"))
            # Mimic Pipeline guard: drop secrets, keep safe (+ .gitignore).
            safe = [p for p in paths if not str(p).startswith(".env")]
            return [*safe, ".gitignore"]

        def run_git(*args, cwd=None, capture=True):
            git_calls.append(args)
            if args[:2] == ("status", "--porcelain"):
                return " M app.py\n?? .env.local\n"
            if args[0] == "add":
                return ""
            if args[:3] == ("diff", "--cached", "--name-only"):
                return "app.py\n.gitignore\n"
            if args[:3] == ("diff", "--cached", "--check"):
                return ""
            if args[0] == "commit":
                return ""
            raise AssertionError(f"unexpected git call: {args}")

        created = supagit_sweep.commit_dirty_tree(
            run_git,
            cwd=Path("/wt"),
            message="save work",
            reject_sensitive=reject_sensitive,
            dry_run=False,
        )
        self.assertTrue(created)
        self.assertEqual(len(guard_calls), 1)
        self.assertIn(".env.local", guard_calls[0])
        self.assertIn("app.py", guard_calls[0])

        add_calls = [c for c in git_calls if c and c[0] == "add"]
        self.assertEqual(len(add_calls), 1)
        add_args = add_calls[0]
        self.assertNotIn("-A", add_args)
        self.assertIn("app.py", add_args)
        self.assertIn(".gitignore", add_args)
        self.assertNotIn(".env.local", add_args)

        commit_calls = [c for c in git_calls if c and c[0] == "commit"]
        self.assertEqual(len(commit_calls), 1)

    def test_clean_tree_returns_false(self) -> None:
        def run_git(*args, cwd=None, capture=True):
            if args[:2] == ("status", "--porcelain"):
                return ""
            raise AssertionError(f"unexpected git call: {args}")

        created = supagit_sweep.commit_dirty_tree(
            run_git,
            cwd=Path("/wt"),
            message="x",
            reject_sensitive=lambda paths, cwd: list(paths),
            dry_run=False,
        )
        self.assertFalse(created)

    def test_prestaged_secret_unstaged_before_commit(self) -> None:
        """Porcelain + pre-staged .env must not land in the commit (novice `git add -A`)."""
        git_calls: list[tuple] = []
        cached_reads = {"n": 0}

        def reject_sensitive(paths: Sequence[str], cwd: Path) -> Sequence[str]:
            return [path for path in paths if path == "app.py"]

        def is_sensitive(path: str) -> bool:
            return path == ".env" or path.startswith(".env.")

        def run_git(*args, cwd=None, capture=True):
            git_calls.append(args)
            if args[:2] == ("status", "--porcelain"):
                return "A  .env\n M app.py\n"
            if args[0] == "add":
                self.assertNotIn(".env", args)
                return ""
            if args[:3] == ("diff", "--cached", "--name-only"):
                cached_reads["n"] += 1
                if cached_reads["n"] == 1:
                    return ".env\napp.py\n"
                return "app.py\n"
            if args[:2] == ("restore", "--staged"):
                self.assertIn(".env", args)
                return ""
            if args[:3] == ("diff", "--cached", "--check"):
                return ""
            if args[0] == "commit":
                return ""
            raise AssertionError(f"unexpected git call: {args}")

        created = supagit_sweep.commit_dirty_tree(
            run_git,
            cwd=Path("/wt"),
            message="save work",
            reject_sensitive=reject_sensitive,
            dry_run=False,
            is_sensitive=is_sensitive,
        )
        self.assertTrue(created)
        restore_calls = [c for c in git_calls if c[:2] == ("restore", "--staged")]
        self.assertEqual(len(restore_calls), 1)
        self.assertIn(".env", restore_calls[0])
        commit_idx = next(i for i, c in enumerate(git_calls) if c and c[0] == "commit")
        restore_idx = git_calls.index(restore_calls[0])
        self.assertLess(restore_idx, commit_idx)


class IntegrateBranchTests(unittest.TestCase):
    @staticmethod
    def _mergeable_gh(**extra: object):
        """Minimal GhClient stand-in with mergeability check."""

        class FakeGh:
            def pr_mergeable(self, number: int) -> str:
                return "MERGEABLE"

        for name, value in extra.items():
            setattr(FakeGh, name, value)
        return FakeGh

    def test_reuses_existing_pr_and_merges(self) -> None:
        actions: list[str] = []

        class FakeGh(self._mergeable_gh()):
            def ensure_ready(self) -> None:
                actions.append("auth")

            def ensure_github_remote(self, remote_url: str) -> None:
                actions.append(f"remote:{remote_url}")

            def find_open_pr(self, head: str, base: str) -> int | None:
                actions.append(f"find:{head}->{base}")
                return 7

            def create_pr(self, head: str, base: str, title: str) -> int:
                raise AssertionError("should reuse")

            def merge_pr(self, number: int, **kwargs) -> None:
                actions.append(f"merge:{number}")

        def run_git(*args, cwd=None, capture=True):
            actions.append("git:" + " ".join(args))
            if args[:2] == ("status", "--porcelain"):
                return ""
            if args[:3] == ("ls-remote", "--heads", "origin"):
                return "abc refs/heads/feature/x\n"
            if args[:2] == ("branch", "--show-current"):
                return "feature/x\n"
            if args[:3] == ("rev-list", "--left-right", "--count"):
                return "0\t0"
            if args[:2] == ("merge-base", "--is-ancestor"):
                return ""
            if args[0] == "rev-parse":
                return "abc"
            if args[0] == "push":
                return ""
            if args[0] == "fetch":
                return ""
            if args[:2] == ("rev-parse", "--abbrev-ref"):
                return "origin/feature/x\n"
            raise AssertionError(f"unexpected git call: {args}")

        supagit_sweep.integrate_branch(
            run_git,
            gh=FakeGh(),
            remote="origin",
            remote_url="git@github.com:acme/demo.git",
            branch="feature/x",
            base="dev",
            cwd=Path("/wt"),
            message_provider=lambda: "should not be called",
            reject_sensitive=lambda paths, cwd: list(paths),
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

            def pr_mergeable(self, number: int) -> str:
                return "MERGEABLE"

            def create_pr(self, head: str, base: str, title: str) -> int:
                actions.append(f"create:{head}->{base}:{title}")
                return 9

            def merge_pr(self, number: int, **kwargs) -> None:
                actions.append(f"merge:{number}")

        def run_git(*args, cwd=None, capture=True):
            if args[:2] == ("status", "--porcelain"):
                return ""
            if args[:3] == ("ls-remote", "--heads", "origin"):
                return "abc refs/heads/feature/x\n"
            if args[:2] == ("branch", "--show-current"):
                return "feature/x\n"
            if args[:3] == ("rev-list", "--left-right", "--count"):
                return "0\t0"
            if args[:2] == ("rev-list", "--count"):
                return "2"
            if args[:2] == ("merge-base", "--is-ancestor"):
                return ""
            if args[0] == "rev-parse":
                return "abc"
            if args[0] == "push":
                return ""
            if args[0] == "fetch":
                return ""
            if args[:2] == ("rev-parse", "--abbrev-ref"):
                return "origin/feature/x\n"
            raise AssertionError(f"unexpected git call: {args}")

        supagit_sweep.integrate_branch(
            run_git,
            gh=FakeGh(),
            remote="origin",
            remote_url="git@github.com:acme/demo.git",
            branch="feature/x",
            base="dev",
            cwd=Path("/wt"),
            message_provider=lambda: "unused",
            reject_sensitive=lambda paths, cwd: list(paths),
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

            def pr_mergeable(self, number: int) -> str:
                return "MERGEABLE"

            def create_pr(self, head: str, base: str, title: str) -> int:
                actions.append(f"create:{head}")
                return 11

            def merge_pr(self, number: int, **kwargs) -> None:
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
            if args[:2] == ("merge-base", "--is-ancestor"):
                return ""
            if args[0] == "rev-parse":
                return "abc"
            if args[0] == "fetch":
                if "refs/heads/work" in args:
                    raise AssertionError("must not fetch missing feature ref")
                return ""
            if args[:2] == ("merge-base", "--is-ancestor"):
                return ""
            raise AssertionError(f"unexpected git call: {args}")

        supagit_sweep.integrate_branch(
            run_git,
            gh=FakeGh(),
            remote="origin",
            remote_url="git@github.com:acme/demo.git",
            branch="work",
            base="main",
            cwd=Path("/repo"),
            message_provider=lambda: "unused",
            reject_sensitive=lambda paths, cwd: list(paths),
            dry_run=False,
            contained_in_first=False,
        )
        self.assertTrue(any(a.startswith("git:ls-remote") for a in actions))
        self.assertFalse(
            any("refs/heads/work:refs/remotes/origin/work" in a for a in actions)
        )
        self.assertIn("create:work", actions)
        self.assertIn("merge:11", actions)

    def test_integrate_rebases_when_base_moved_ahead(self) -> None:
        actions: list[str] = []

        class FakeGh:
            def ensure_ready(self) -> None:
                return None

            def ensure_github_remote(self, remote_url: str) -> None:
                return None

            def find_open_pr(self, head: str, base: str) -> int | None:
                return None

            def pr_mergeable(self, number: int) -> str:
                return "MERGEABLE"

            def create_pr(self, head: str, base: str, title: str) -> int:
                return 12

            def merge_pr(self, number: int, **kwargs) -> None:
                actions.append(f"merge:{number}")

        def run_git(*args, cwd=None, capture=True):
            actions.append(args)
            if args[:2] == ("status", "--porcelain"):
                return ""
            if args[:3] == ("ls-remote", "--heads", "origin"):
                return ""
            if args[:2] == ("branch", "--show-current"):
                return "main\n"
            if args[:2] == ("merge-base", "--is-ancestor"):
                raise RuntimeError("not ancestor")
            if args[:2] == ("rev-list", "--count"):
                if args[2] == "work..origin/main":
                    return "1"
                if args[2] == "origin/main..work":
                    return "2"
                return "0"
            if args[0] == "checkout":
                return ""
            if args[0] == "rebase":
                return ""
            if args[0] == "push":
                return ""
            if args[0] == "fetch":
                return ""
            if args[0] == "rev-parse":
                return "abc"
            raise AssertionError(f"unexpected git call: {args}")

        supagit_sweep.integrate_branch(
            run_git,
            gh=FakeGh(),
            remote="origin",
            remote_url="git@github.com:acme/demo.git",
            branch="work",
            base="main",
            cwd=Path("/repo"),
            message_provider=lambda: "unused",
            reject_sensitive=lambda paths, cwd: list(paths),
            dry_run=False,
            contained_in_first=False,
        )
        self.assertIn(("rebase", "origin/main"), actions)
        self.assertTrue(
            any(a[:3] == ("push", "--force-with-lease", "origin") for a in actions)
        )
        self.assertIn("merge:12", actions)

    def test_integrate_polls_unknown_mergeability_before_merge(self) -> None:
        mergeable_reads: list[str] = []
        sleeps: list[float] = []
        states = ["UNKNOWN", "UNKNOWN", "MERGEABLE"]

        class FakeGh:
            def ensure_ready(self) -> None:
                return None

            def ensure_github_remote(self, remote_url: str) -> None:
                return None

            def find_open_pr(self, head: str, base: str) -> int | None:
                return 31

            def pr_mergeable(self, number: int) -> str:
                state = states.pop(0)
                mergeable_reads.append(state)
                return state

            def create_pr(self, head: str, base: str, title: str) -> int:
                raise AssertionError("should not create")

            def merge_pr(self, number: int, **kwargs) -> None:
                mergeable_reads.append(f"merge:{number}")

        def run_git(*args, cwd=None, capture=True):
            if args[:2] == ("status", "--porcelain"):
                return ""
            if args[:3] == ("ls-remote", "--heads", "origin"):
                return ""
            if args[:2] == ("branch", "--show-current"):
                return "main\n"
            if args[:2] == ("merge-base", "--is-ancestor"):
                return ""
            if args[:2] == ("rev-list", "--count"):
                return "0"
            if args[0] == "push":
                return ""
            if args[0] == "fetch":
                return ""
            if args[0] == "rev-parse":
                return "abc"
            raise AssertionError(args)

        def fake_sleep(seconds: float) -> None:
            sleeps.append(seconds)

        with patch.object(supagit_sweep, "sleep", fake_sleep, create=True):
            supagit_sweep.integrate_branch(
                run_git,
                gh=FakeGh(),
                remote="origin",
                remote_url="git@github.com:acme/demo.git",
                branch="work",
                base="main",
                cwd=Path("/repo"),
                message_provider=lambda: "unused",
                reject_sensitive=lambda paths, cwd: list(paths),
                dry_run=False,
                contained_in_first=False,
            )

        self.assertEqual(mergeable_reads[:3], ["UNKNOWN", "UNKNOWN", "MERGEABLE"])
        self.assertIn("merge:31", mergeable_reads)
        self.assertEqual(len(sleeps), 2)
        self.assertLess(sleeps[0], sleeps[1])

    def test_poll_pr_mergeable_stops_early_when_known(self) -> None:
        reads: list[str] = []
        sleeps: list[float] = []

        class FakeGh:
            def pr_mergeable(self, number: int) -> str:
                reads.append("UNKNOWN" if len(reads) == 0 else "MERGEABLE")
                return reads[-1]

        result = supagit_sweep.poll_pr_mergeable(
            FakeGh(),
            4,
            sleeper=lambda s: sleeps.append(s),
        )
        self.assertEqual(result, "MERGEABLE")
        self.assertEqual(reads, ["UNKNOWN", "MERGEABLE"])
        self.assertEqual(len(sleeps), 1)

    def test_integrate_conflicting_rebases_then_merges(self) -> None:
        actions: list[str] = []
        merge_states = ["CONFLICTING", "MERGEABLE"]

        class FakeGh:
            def ensure_ready(self) -> None:
                return None

            def ensure_github_remote(self, remote_url: str) -> None:
                return None

            def find_open_pr(self, head: str, base: str) -> int | None:
                return 21

            def pr_mergeable(self, number: int) -> str:
                state = merge_states.pop(0)
                actions.append(f"mergeable:{state}")
                return state

            def create_pr(self, head: str, base: str, title: str) -> int:
                raise AssertionError("should not create")

            def merge_pr(self, number: int, **kwargs) -> None:
                actions.append(f"merge:{number}")
                actions.append(f"merge_kwargs:{sorted(kwargs.items())}")

        ancestor_checks = {"n": 0}

        def run_git(*args, cwd=None, capture=True):
            actions.append("git:" + " ".join(args))
            if args[:2] == ("status", "--porcelain"):
                return ""
            if args[:3] == ("ls-remote", "--heads", "origin"):
                return ""
            if args[:2] == ("branch", "--show-current"):
                return "main\n"
            if args[:2] == ("merge-base", "--is-ancestor"):
                ancestor_checks["n"] += 1
                # Pre-PR check: already based. Conflict recovery forces rebase (skips check).
                return ""
            if args[:2] == ("rev-list", "--count"):
                if len(args) > 2 and args[2] == "work..origin/main":
                    return "1"
                return "0"
            if args[0] in ("checkout", "rebase", "push", "fetch"):
                return ""
            if args[0] == "rev-parse":
                return "abc"
            raise AssertionError(args)

        with patch.object(supagit_sweep, "sleep", lambda _s: None, create=True):
            supagit_sweep.integrate_branch(
                run_git,
                gh=FakeGh(),
                remote="origin",
                remote_url="git@github.com:acme/demo.git",
                branch="work",
                base="main",
                cwd=Path("/repo"),
                message_provider=lambda: "unused",
                reject_sensitive=lambda paths, cwd: list(paths),
                dry_run=False,
                contained_in_first=False,
            )

        self.assertIn("mergeable:CONFLICTING", actions)
        self.assertTrue(any(a.startswith("git:rebase") for a in actions))
        self.assertTrue(any("push --force-with-lease" in a for a in actions))
        self.assertIn("mergeable:MERGEABLE", actions)
        self.assertIn("merge:21", actions)
        self.assertTrue(
            all(
                not a.startswith("merge_kwargs:") or "('admin', True)" not in a
                for a in actions
            )
        )

    def test_integrate_refuses_conflicting_pr_after_rebase_retry(self) -> None:
        class FakeGh:
            def ensure_ready(self) -> None:
                return None

            def ensure_github_remote(self, remote_url: str) -> None:
                return None

            def find_open_pr(self, head: str, base: str) -> int | None:
                return 21

            def pr_mergeable(self, number: int) -> str:
                return "CONFLICTING"

            def create_pr(self, head: str, base: str, title: str) -> int:
                raise AssertionError("should not create")

            def merge_pr(self, number: int, **kwargs) -> None:
                raise AssertionError("must not merge")

        def run_git(*args, cwd=None, capture=True):
            if args[:2] == ("status", "--porcelain"):
                return ""
            if args[:3] == ("ls-remote", "--heads", "origin"):
                return ""
            if args[:2] == ("branch", "--show-current"):
                return "main\n"
            if args[:2] == ("merge-base", "--is-ancestor"):
                raise RuntimeError("not ancestor")
            if args[:2] == ("rev-list", "--count"):
                if len(args) > 2 and args[2] == "work..origin/main":
                    return "1"
                return "0"
            if args[0] in ("checkout", "rebase", "push", "fetch"):
                return ""
            if args[0] == "rev-parse":
                return "abc"
            raise AssertionError(args)

        with patch.object(supagit_sweep, "sleep", lambda _s: None, create=True):
            with self.assertRaises(supagit_sweep.SweepError) as ctx:
                supagit_sweep.integrate_branch(
                    run_git,
                    gh=FakeGh(),
                    remote="origin",
                    remote_url="git@github.com:acme/demo.git",
                    branch="work",
                    base="main",
                    cwd=Path("/repo"),
                    message_provider=lambda: "unused",
                    reject_sensitive=lambda paths, cwd: list(paths),
                    dry_run=False,
                    contained_in_first=False,
                )
        self.assertIn("21", str(ctx.exception))
        self.assertIn("conflict", str(ctx.exception).lower())

    def test_rebase_conflict_guides_then_continues_on_confirm(self) -> None:
        """Conflict keeps rebase state, lists files, opens editor, then continues."""
        import supagit_i18n

        supagit_i18n.set_lang("en")
        actions: list[str] = []
        editor_calls: list[tuple[str, ...]] = []
        confirms: list[str] = []
        explains: list[str] = []
        rebase_attempts = {"n": 0}

        def run_git(*args, cwd=None, capture=True, env=None):
            actions.append("git:" + " ".join(args))
            if args[:2] == ("merge-base", "--is-ancestor"):
                raise RuntimeError("not ancestor")
            if args[:2] == ("rev-list", "--count"):
                return "1"
            if args[:2] == ("branch", "--show-current"):
                return "main\n"
            if args[0] == "checkout":
                return ""
            if "rebase" in args and "--continue" in args:
                return ""
            if "rebase" in args and "--abort" in args:
                raise AssertionError("must not abort when user confirms")
            if args[0] == "rebase":
                rebase_attempts["n"] += 1
                raise RuntimeError("conflict")
            if args[:2] == ("diff", "--name-only"):
                return "a.txt\nb.txt\n"
            if args[0] == "add":
                return ""
            raise AssertionError(args)

        def fake_explain(message: str) -> None:
            explains.append(message)

        def fake_confirm(prompt: str) -> bool:
            confirms.append(prompt)
            return True

        def fake_editor(paths, *, cwd):
            editor_calls.append(tuple(paths))

        result = supagit_sweep.rebase_branch_onto(
            run_git,
            "work",
            "origin/main",
            cwd=Path("/repo"),
            dry_run=False,
            explain=fake_explain,
            confirm_continue=fake_confirm,
            open_editor=fake_editor,
        )
        self.assertTrue(result)
        self.assertTrue(any("a.txt" in e and "b.txt" in e for e in explains))
        self.assertEqual(editor_calls, [("a.txt", "b.txt")])
        self.assertEqual(len(confirms), 1)
        self.assertIn("git:add a.txt b.txt", actions)
        self.assertTrue(
            any("rebase --continue" in a or a.endswith("rebase --continue") for a in actions)
        )
        self.assertFalse(any("rebase --abort" in a for a in actions))

    def test_rebase_conflict_aborts_only_on_explicit_cancel(self) -> None:
        import supagit_i18n

        supagit_i18n.set_lang("en")
        actions: list[str] = []

        def run_git(*args, cwd=None, capture=True, env=None):
            actions.append("git:" + " ".join(args))
            if args[:2] == ("merge-base", "--is-ancestor"):
                raise RuntimeError("not ancestor")
            if args[:2] == ("rev-list", "--count"):
                return "1"
            if args[:2] == ("branch", "--show-current"):
                return "main\n"
            if args[0] == "checkout":
                return ""
            if args[0] == "rebase" and len(args) == 2:
                raise RuntimeError("conflict")
            if args[:2] == ("diff", "--name-only"):
                return "conflict.txt\n"
            if args[:2] == ("rebase", "--abort"):
                return ""
            raise AssertionError(args)

        with self.assertRaises(supagit_sweep.SweepError) as ctx:
            supagit_sweep.rebase_branch_onto(
                run_git,
                "work",
                "origin/main",
                cwd=Path("/repo"),
                dry_run=False,
                explain=lambda _m: None,
                confirm_continue=lambda _p: False,
                open_editor=lambda _paths, *, cwd: None,
            )
        self.assertIn("git:rebase --abort", actions)
        message = str(ctx.exception).lower()
        self.assertIn("conflict", message)
        # Must not push the user to run raw git as the primary fix.
        self.assertNotIn("git rebase", message)

    def test_integrate_skips_empty_pr_before_create(self) -> None:
        import io
        import contextlib
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

            def merge_pr(self, number: int, **kwargs) -> None:
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

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            result = supagit_sweep.integrate_branch(
                run_git,
                gh=FakeGh(),
                remote="origin",
                remote_url="git@github.com:acme/demo.git",
                branch="feature/x",
                base="dev",
                cwd=Path("/wt"),
                message_provider=lambda: "unused",
                reject_sensitive=lambda paths, cwd: list(paths),
                dry_run=False,
                contained_in_first=False,
            )
        self.assertFalse(created)
        self.assertTrue(result.skipped)
        self.assertEqual(result.reason, "already merged")
        self.assertIn("nothing to merge", buf.getvalue().lower())

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

    def test_assert_commits_for_pr_empty_returns_zero(self) -> None:
        def run_git(*args, cwd=None, capture=True):
            if args[0] == "fetch":
                return ""
            if args[:2] == ("rev-parse", "--verify"):
                return "ok"
            if args[:2] == ("rev-list", "--count"):
                return "0"
            raise AssertionError(args)

        count = supagit_sweep.assert_commits_for_pr(
            run_git,
            head="feature/x",
            base="dev",
            remote="origin",
            cwd=Path("/wt"),
        )
        self.assertEqual(count, 0)

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

            def pr_mergeable(self, number: int) -> str:
                return "MERGEABLE"

            def create_pr(self, head: str, base: str, title: str) -> int:
                raise AssertionError("reuse")

            def merge_pr(self, number: int, **kwargs) -> None:
                actions.append(f"merge:{number}")

        def run_git(*args, cwd=None, capture=True):
            actions.append("git:" + " ".join(args))
            if args[:2] == ("status", "--porcelain"):
                return ""
            if args[:3] == ("ls-remote", "--heads", "origin"):
                return "abc refs/heads/feature/x\n"
            if args[:2] == ("branch", "--show-current"):
                return "feature/x\n"
            if args[:3] == ("rev-list", "--left-right", "--count"):
                return "1\t0"
            if args[:2] == ("merge-base", "--is-ancestor"):
                return ""
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
            raise AssertionError(f"unexpected git call: {args}")

        supagit_sweep.integrate_branch(
            run_git,
            gh=FakeGh(),
            remote="origin",
            remote_url="git@github.com:acme/demo.git",
            branch="feature/x",
            base="dev",
            cwd=Path("/wt"),
            message_provider=lambda: "unused",
            reject_sensitive=lambda paths, cwd: list(paths),
            dry_run=False,
            contained_in_first=False,
        )
        merge_ff = next(i for i, a in enumerate(actions) if "merge --ff-only" in a)
        push_i = next(i for i, a in enumerate(actions) if a == "pushed")
        self.assertLess(merge_ff, push_i)
        self.assertEqual(tips["feature/x"], "new")

    def test_contained_branch_skips_instead_of_error(self) -> None:
        import io
        import contextlib
        import supagit_i18n

        supagit_i18n.set_lang("en")

        class FakeGh:
            def ensure_ready(self) -> None:
                raise AssertionError("should not touch gh")

            def ensure_github_remote(self, remote_url: str) -> None:
                raise AssertionError("should not touch gh")

            def find_open_pr(self, head: str, base: str) -> int | None:
                raise AssertionError("should not create")

            def create_pr(self, head: str, base: str, title: str) -> int:
                raise AssertionError("should not create")

            def merge_pr(self, number: int, **kwargs) -> None:
                raise AssertionError("should not merge")

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            result = supagit_sweep.integrate_branch(
                lambda *a, **k: "",
                gh=FakeGh(),
                remote="origin",
                remote_url="git@github.com:acme/demo.git",
                branch="old",
                base="dev",
                cwd=Path("/repo"),
                message_provider=lambda: "x",
                reject_sensitive=lambda paths, cwd: list(paths),
                dry_run=False,
                contained_in_first=True,
            )
        self.assertTrue(result.skipped)
        self.assertEqual(result.reason, "already merged")
        self.assertIn("nothing to merge", buf.getvalue().lower())


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

    def test_apply_cleanup_force_deletes_when_d_refuses_stale_upstream(self) -> None:
        calls: list[tuple[str, ...]] = []

        def run_git(*args: str, **kwargs):
            calls.append(args)
            if args[:2] == ("merge-base", "--is-ancestor"):
                return ""
            if args[:2] == ("branch", "-d"):
                raise RuntimeError(
                    "not deleting branch 'work' that is not yet merged to "
                    "'refs/remotes/origin/work', even though it is merged to HEAD"
                )
            if args[:2] == ("branch", "-D"):
                return ""
            raise AssertionError(args)

        plan = supagit_sweep.CleanupPlan(
            items=(
                supagit_sweep.CleanupItem(
                    kind="local-branch", name="work", path=None
                ),
            )
        )
        supagit_sweep.apply_cleanup(run_git, plan, dry_run=False, into="main")
        self.assertIn(("branch", "-d", "work"), calls)
        self.assertIn(("branch", "-D", "work"), calls)
        self.assertIn(("merge-base", "--is-ancestor", "work", "main"), calls)

    def test_apply_cleanup_refuses_unmerged(self) -> None:
        def run_git(*args: str, **kwargs):
            if args[:2] == ("merge-base", "--is-ancestor"):
                raise RuntimeError("not an ancestor")
            raise AssertionError(args)

        plan = supagit_sweep.CleanupPlan(
            items=(
                supagit_sweep.CleanupItem(
                    kind="local-branch", name="work", path=None
                ),
            )
        )
        with self.assertRaises(supagit_sweep.SweepError) as ctx:
            supagit_sweep.apply_cleanup(run_git, plan, dry_run=False, into="main")
        self.assertIn("work", str(ctx.exception))
        self.assertIn("main", str(ctx.exception))


SPEC = importlib.util.spec_from_file_location("supagit_engine", SCRIPTS / "supagit.py")
assert SPEC and SPEC.loader
ENGINE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ENGINE
SPEC.loader.exec_module(ENGINE)


class SensitivePathGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        import supagit_i18n

        supagit_i18n.set_lang("en")

    def _pipeline(self, *, yes: bool = True, dry_run: bool = False):
        pipeline = ENGINE.Pipeline.__new__(ENGINE.Pipeline)
        pipeline.root = Path("/tmp/unused")
        pipeline.options = ENGINE.Options(
            dry_run=dry_run,
            yes=yes,
            config_path=None,
            message=None,
            color="never",
            no_sweep=True,
            integrate=None,
            pipeline_order=None,
            cleanup=False,
        )
        return pipeline

    def test_all_sensitive_raises(self) -> None:
        pipeline = self._pipeline()
        with self.assertRaises(ENGINE.ShipError) as ctx:
            pipeline._reject_sensitive_paths([".env.local", "secret.pem"], cwd=Path("/wt"))
        self.assertIn(".env.local", str(ctx.exception))
        self.assertIn("secret.pem", str(ctx.exception))

    def test_mixed_paths_exclude_and_append_gitignore(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "app.py").write_text("print(1)\n", encoding="utf-8")
            (root / ".env.local").write_text("SECRET=1\n", encoding="utf-8")
            pipeline = self._pipeline(yes=True)
            pipeline.root = root

            safe = list(
                pipeline._reject_sensitive_paths(
                    ["app.py", ".env.local"],
                    cwd=root,
                )
            )
            self.assertIn("app.py", safe)
            self.assertNotIn(".env.local", safe)
            self.assertIn(".gitignore", safe)
            gitignore = (root / ".gitignore").read_text(encoding="utf-8")
            self.assertIn(".env*", gitignore)

    def test_gitignore_confirm_declined_still_excludes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pipeline = self._pipeline(yes=False)
            pipeline.root = root
            pipeline.ask_yes_no = lambda message, default_yes=True: False  # type: ignore[method-assign]
            pipeline.explain = lambda *a, **k: None  # type: ignore[method-assign]

            safe = list(
                pipeline._reject_sensitive_paths(
                    ["app.py", ".env"],
                    cwd=root,
                )
            )
            self.assertEqual(safe, ["app.py"])
            self.assertFalse((root / ".gitignore").exists())

    def test_no_sensitive_returns_paths_unchanged(self) -> None:
        pipeline = self._pipeline()
        paths = ["app.py", "README.md"]
        self.assertEqual(
            list(pipeline._reject_sensitive_paths(paths, cwd=Path("/wt"))),
            paths,
        )


class OrchestrationTests(unittest.TestCase):
    def setUp(self) -> None:
        import supagit_i18n

        supagit_i18n.set_lang("en")

    def test_yes_without_flags_fails_when_ambiguous(self) -> None:
        """Multiple pending features without --integrate → still need flags."""
        layout = RepoLayout(
            launch_root=Path("/repo"),
            main_root=Path("/repo"),
            common_dir=Path("/repo/.git"),
            is_linked_launch=False,
        )
        inv = RepoInventory(
            layout,
            (),
            (
                BranchInfo(
                    "dev", True, True, Path("/repo"), 0, 0, True, "origin/dev", False
                ),
                BranchInfo(
                    "feature/a",
                    False,
                    True,
                    Path("/wt-a"),
                    1,
                    0,
                    False,
                    None,
                    True,
                ),
                BranchInfo(
                    "feature/b",
                    False,
                    True,
                    Path("/wt-b"),
                    1,
                    0,
                    False,
                    None,
                    True,
                ),
            ),
            "dev",
        )
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
        pipeline.branches = ("dev",)
        with self.assertRaisesRegex(ENGINE.ShipError, "--integrate"):
            pipeline._require_noninteractive_selection(inv)

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
        pipeline._require_noninteractive_selection(_fake_inventory())

    def test_yes_infers_defaults_when_unambiguous(self) -> None:
        """--yes without --integrate/--pipeline uses default_integrate_names + config."""
        inv = _fake_inventory()  # one pending: feature/x; pipeline branches configured
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
            cleanup=False,
        )
        pipeline.branches = ("dev", "pre", "prod")
        pipeline.remote = "origin"
        pipeline.original_branch = "dev"
        pipeline._explain_situation_preflight = lambda *_a, **_k: None  # type: ignore[method-assign]

        pipeline._require_noninteractive_selection(inv)
        selection = pipeline.run_branch_menu(inv)
        self.assertEqual(selection.integrate, ("feature/x",))
        self.assertEqual(selection.pipeline, ("dev", "pre", "prod"))

    def test_run_yes_ambiguous_fails_after_inventory(self) -> None:
        """Ambiguous --yes still fails closed, but only after inventory exists."""
        layout = RepoLayout(
            launch_root=Path("/repo"),
            main_root=Path("/repo"),
            common_dir=Path("/repo/.git"),
            is_linked_launch=False,
        )
        inv = RepoInventory(
            layout,
            (),
            (
                BranchInfo(
                    "dev", True, True, Path("/repo"), 0, 0, True, "origin/dev", False
                ),
                BranchInfo(
                    "feature/a", False, False, None, 1, 0, False, None, False
                ),
                BranchInfo(
                    "feature/b", False, False, None, 1, 0, False, None, False
                ),
            ),
            "dev",
        )
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
        pipeline.branches = ("dev",)
        preflight_called = False

        def mark_preflight() -> None:
            nonlocal preflight_called
            preflight_called = True

        pipeline.preflight_repo = mark_preflight  # type: ignore[method-assign]
        pipeline.build_inventory = lambda **_k: inv  # type: ignore[method-assign]
        with self.assertRaisesRegex(ENGINE.ShipError, "--integrate"):
            pipeline.run()
        self.assertTrue(preflight_called)

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
        pipeline._require_noninteractive_selection = lambda *_a, **_k: None  # type: ignore[method-assign]
        pipeline.run_branch_menu = lambda inv: supagit_menu.MenuSelection(  # type: ignore[method-assign]
            integrate=("feature/x",), pipeline=("pre", "dev", "prod")
        )
        pipeline.ensure_checkout_on_first_branch = lambda: None  # type: ignore[method-assign]
        pipeline.validate_pipeline_head = lambda: None  # type: ignore[method-assign]
        pipeline.verify_final_checkout = lambda: None  # type: ignore[method-assign]
        pipeline.sweep_features = sweep_features  # type: ignore[method-assign]
        pipeline.ff_sync_first_branch = lambda: None  # type: ignore[method-assign]
        pipeline.commit_and_publish_dev = lambda **_k: None  # type: ignore[method-assign]
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
        pipeline.main_root = root
        pipeline.root = root
        pipeline.dev = "main"
        pipeline.branches = ("main",)
        pipeline.remote = "origin"
        pipeline.original_branch = current
        pipeline.project_name = "demo"
        pipeline.backend = ENGINE.BackendConfig(provider="none", cli=None, targets={})
        pipeline.cli = None
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
            if args[0] == "switch":
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
        pipeline._reject_sensitive_paths = lambda paths, cwd=None: list(paths)  # type: ignore[method-assign]

        def capture_explain(
            message: str, *, ask_continue: bool = True, force_confirm: bool = False
        ) -> None:
            explained.append(message)

        pipeline.explain = capture_explain  # type: ignore[method-assign]
        pipeline.confirm = lambda message, force=False: None  # type: ignore[method-assign]
        return pipeline, calls, explained

    def _pipeline_for_launch_worktree(
        self,
        *,
        dry_run: bool = False,
        yes: bool = True,
        main_branch: str = "main",
        launch_branch: str = "feat-x",
        launch_dirty: str = "",
        message: str | None = "save work",
    ) -> tuple[ENGINE.Pipeline, list[tuple]]:
        pipeline = ENGINE.Pipeline.__new__(ENGINE.Pipeline)
        pipeline.options = ENGINE.Options(
            dry_run=dry_run,
            yes=yes,
            config_path=None,
            message=message,
            color="never",
            no_sweep=False,
            integrate=None,
            pipeline_order=None,
            cleanup=False,
        )
        main_root = Path("/repo")
        launch_root = Path("/wt")
        pipeline.layout = RepoLayout(
            launch_root=launch_root,
            main_root=main_root,
            common_dir=Path("/repo/.git"),
            is_linked_launch=True,
        )
        pipeline.launch_root = launch_root
        pipeline.main_root = main_root
        pipeline.root = main_root
        pipeline.dev = "main"
        pipeline.branches = ("main", "prod")
        pipeline.remote = "origin"
        pipeline.original_branch = launch_branch
        pipeline.project_name = "demo"
        git_calls: list[tuple] = []
        dirty_state = {"value": launch_dirty}

        def git(*args: str, capture: bool = False, check: bool = True, mutating: bool = False, cwd: Path | None = None) -> str:
            git_calls.append((args, cwd))
            if args[:2] == ("branch", "--show-current"):
                if cwd == launch_root:
                    return f"{launch_branch}\n"
                return f"{main_branch}\n"
            if args[:2] == ("status", "--porcelain"):
                if cwd == launch_root:
                    return dirty_state["value"]
                return ""
            if args[0] == "add":
                return ""
            if args[0] == "commit":
                dirty_state["value"] = ""
                return ""
            if args[:2] == ("diff", "--cached"):
                return "a.txt\n" if args[-1] == "--name-only" else ""
            raise AssertionError(f"unexpected git call: {args} cwd={cwd}")

        pipeline.git = git  # type: ignore[method-assign]
        pipeline._sweep_git = (  # type: ignore[method-assign]
            lambda *a, cwd=None, capture=True: git(*a, capture=capture, cwd=cwd)
        )
        pipeline.explain = lambda *_a, **_k: None  # type: ignore[method-assign]
        pipeline.confirm = lambda *_a, **_k: None  # type: ignore[method-assign]
        return pipeline, git_calls

    def test_preflight_non_linked_wrong_branch_ok(self) -> None:
        pipeline, calls, _ = self._pipeline_for_reposition(current="feature/x", linked=False)
        pipeline.run_raw = lambda *a, **k: ""  # type: ignore[method-assign]
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
        committed = pipeline.ensure_checkout_on_first_branch()
        self.assertEqual(committed, "feature/x")
        self.assertTrue(any(c[0] == "add" for c in calls))
        self.assertTrue(any(c[0] == "commit" for c in calls))
        self.assertIn(("checkout", "main"), calls)

    def test_extend_integrate_after_pre_commit_when_not_contained(self) -> None:
        pipeline, _, _ = self._pipeline_for_reposition(
            current="work", yes=True
        )
        pipeline.dev = "main"
        pipeline.options.no_sweep = False
        selection = supagit_menu.MenuSelection(integrate=(), pipeline=("main",))

        def contained(needle: str, haystack: str, git_runner) -> bool:
            self.assertEqual(needle, "work")
            self.assertEqual(haystack, "main")
            return False

        with patch.object(supagit_inventory, "branch_contained", side_effect=contained):
            updated = pipeline._extend_integrate_after_pre_commit(selection, "work")
        self.assertEqual(updated.integrate, ("work",))

    def test_extend_integrate_skips_when_still_contained(self) -> None:
        pipeline, _, _ = self._pipeline_for_reposition(current="work", yes=True)
        pipeline.dev = "main"
        pipeline.options.no_sweep = False
        selection = supagit_menu.MenuSelection(integrate=(), pipeline=("main",))
        with patch.object(supagit_inventory, "branch_contained", return_value=True):
            updated = pipeline._extend_integrate_after_pre_commit(selection, "work")
        self.assertEqual(updated.integrate, ())

    def test_extend_integrate_no_sweep_fails_closed(self) -> None:
        pipeline, _, _ = self._pipeline_for_reposition(current="work", yes=True)
        pipeline.dev = "main"
        pipeline.options = ENGINE.Options(
            dry_run=False,
            yes=True,
            config_path=None,
            message="x",
            color="never",
            no_sweep=True,
            integrate=None,
            pipeline_order=None,
            cleanup=False,
        )
        selection = supagit_menu.MenuSelection(integrate=(), pipeline=("main",))
        with self.assertRaises(ENGINE.ShipError) as ctx:
            pipeline._extend_integrate_after_pre_commit(selection, "work")
        self.assertIn("--no-sweep", str(ctx.exception))
        self.assertIn("work", str(ctx.exception))

    def test_ensure_checkout_dirty_on_first_branch_ok(self) -> None:
        pipeline, calls, _ = self._pipeline_for_reposition(
            current="main", dirty=" M a.txt\n"
        )
        pipeline.ensure_checkout_on_first_branch()
        self.assertFalse(any(c[0] == "checkout" for c in calls))
        self.assertFalse(any(c[:2] == ("status", "--porcelain") for c in calls))

    def test_main_on_pipeline0_dirty_launch_feature_is_committed_and_integrated(self) -> None:
        pipeline, git_calls = self._pipeline_for_launch_worktree(
            launch_branch="feat-x", launch_dirty=" M a.txt\n?? b.txt\n"
        )
        committed = pipeline.ensure_checkout_on_first_branch()
        self.assertEqual(committed, "feat-x")
        launch_root = pipeline.launch_root
        self.assertTrue(
            any(
                args[:2] == ("add", "--") and cwd == launch_root
                for args, cwd in git_calls
            ),
            f"expected selective git add in {launch_root}, got {git_calls}",
        )
        self.assertFalse(
            any(args[:2] == ("add", "-A") for args, _ in git_calls),
            "secrets guard must not use git add -A",
        )
        self.assertTrue(
            any(args[0] == "commit" and cwd == launch_root for args, cwd in git_calls)
        )
        self.assertFalse(any(args[0] == "checkout" for args, _ in git_calls))
        selection = supagit_menu.MenuSelection(integrate=(), pipeline=("main", "prod"))
        with patch.object(supagit_inventory, "branch_contained", return_value=False):
            updated = pipeline._extend_integrate_after_pre_commit(selection, committed)
        self.assertEqual(updated.integrate, ("feat-x",))

    def test_main_on_pipeline0_clean_launch_worktree_returns_early(self) -> None:
        pipeline, git_calls = self._pipeline_for_launch_worktree(
            launch_branch="feat-x", launch_dirty=""
        )
        committed = pipeline.ensure_checkout_on_first_branch()
        self.assertIsNone(committed)
        self.assertFalse(any(args[0] == "commit" for args, _ in git_calls))
        self.assertFalse(any(args[0] == "add" for args, _ in git_calls))
        self.assertFalse(any(args[0] == "checkout" for args, _ in git_calls))

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
        pipeline._require_noninteractive_selection = lambda *_a, **_k: None  # type: ignore[method-assign]
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

    def test_pipeline0_db_checkpoint_runs_before_feature_merges(self) -> None:
        # with backend=supabase, migrate of pipeline[0] must precede sweep_features
        pipeline = ENGINE.Pipeline.__new__(ENGINE.Pipeline)
        pipeline.options = ENGINE.Options(
            dry_run=True,
            yes=True,
            config_path=None,
            message="test",
            color="never",
            no_sweep=False,
            integrate="feature/x",
            pipeline_order="dev,pre,prod",
            cleanup=False,
        )
        pipeline.branches = ("dev", "pre", "prod")
        pipeline.dev = "dev"
        pipeline.pre = "pre"
        pipeline.prod = "prod"
        pipeline.remote = "origin"
        pipeline.original_branch = "dev"
        pipeline.backend = ENGINE.BackendConfig(
            provider="supabase",
            cli="supabase",
            targets={"dev": "dev-ref", "pre": "pre-ref", "prod": "prod-ref"},
        )
        order: list[str] = []

        def mark(name: str):
            def _inner(*args, **kwargs):
                order.append(name)
                if name == "build_inventory":
                    return _fake_inventory()
                if name == "run_branch_menu":
                    return supagit_menu.MenuSelection(
                        integrate=("feature/x",), pipeline=("dev", "pre", "prod")
                    )
                return None

            return _inner

        def database_checkpoint(label: str, project_ref: str) -> None:
            order.append(f"database_checkpoint:{label}:{project_ref}")

        def promote(source: str, target: str) -> None:
            order.append(f"promote:{source}:{target}")

        for name in (
            "preflight_repo",
            "build_inventory",
            "run_branch_menu",
            "ensure_checkout_on_first_branch",
            "validate_pipeline_head",
            "commit_and_publish_dev",
            "sweep_features",
            "ff_sync_first_branch",
            "_assert_dev_synced",
            "run_checks",
            "validate_clean_after_checks",
            "return_to_dev",
            "verify_final_checkout",
        ):
            setattr(pipeline, name, mark(name))
        pipeline.database_checkpoint = database_checkpoint  # type: ignore[method-assign]
        pipeline.promote = promote  # type: ignore[method-assign]
        pipeline.optional_cleanup = mark("optional_cleanup")  # type: ignore[method-assign]
        pipeline.status = lambda *a, **k: None  # type: ignore[method-assign]
        pipeline.tutor_confirm = lambda *a, **k: None  # type: ignore[method-assign]
        pipeline._require_noninteractive_selection = lambda *_a, **_k: None  # type: ignore[method-assign]

        pipeline.run()

        self.assertIn("database_checkpoint:dev:dev-ref", order)
        self.assertIn("sweep_features", order)
        self.assertLess(
            order.index("database_checkpoint:dev:dev-ref"),
            order.index("sweep_features"),
        )
        self.assertLess(
            order.index("database_checkpoint:dev:dev-ref"),
            order.index("commit_and_publish_dev"),
        )
        self.assertLess(
            order.index("database_checkpoint:pre:pre-ref"),
            order.index("promote:dev:pre"),
        )
        self.assertLess(
            order.index("database_checkpoint:prod:prod-ref"),
            order.index("promote:pre:prod"),
        )

    def test_init_keys_environments_by_pipeline_branch_names(self) -> None:
        """Custom pipeline branches become environment keys (not legacy pre/prod)."""
        config = ENGINE.init_project_config(
            "supabase",
            "SUPABASE_PRE_PROJECT_REF",
            "SUPABASE_PROD_PROJECT_REF",
            ["main", "production"],
        )
        self.assertEqual(config["branches"], ["main", "production"])
        envs = config["backend"]["environments"]
        self.assertIn("main", envs)
        self.assertIn("production", envs)
        self.assertNotIn("pre", envs)
        self.assertNotIn("prod", envs)
        self.assertEqual(
            envs["main"]["project_ref_env"], "SUPABASE_PRE_PROJECT_REF"
        )
        self.assertEqual(
            envs["production"]["project_ref_env"], "SUPABASE_PROD_PROJECT_REF"
        )

    def test_custom_pipeline_main_production_migrates_production(self) -> None:
        """Branch-keyed targets: production must be migrated before promote (no soft skip)."""
        pipeline = ENGINE.Pipeline.__new__(ENGINE.Pipeline)
        pipeline.options = ENGINE.Options(
            dry_run=True,
            yes=True,
            config_path=None,
            message="test",
            color="never",
            no_sweep=True,
            integrate=None,
            pipeline_order=None,
            cleanup=False,
        )
        pipeline.branches = ("main", "production")
        pipeline.dev = "main"
        pipeline.pre = "production"
        pipeline.prod = "production"
        pipeline.remote = "origin"
        pipeline.original_branch = "main"
        pipeline.backend = ENGINE.BackendConfig(
            provider="supabase",
            cli="supabase",
            targets={"main": "main-ref", "production": "prod-ref"},
        )
        order: list[str] = []

        def mark(name: str):
            def _inner(*args, **kwargs):
                order.append(name)
                if name == "build_inventory":
                    return _fake_inventory()
                return None

            return _inner

        def database_checkpoint(label: str, project_ref: str) -> None:
            order.append(f"database_checkpoint:{label}:{project_ref}")

        def promote(source: str, target: str) -> None:
            order.append(f"promote:{source}:{target}")

        for name in (
            "preflight_repo",
            "build_inventory",
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
        pipeline._explain_situation_preflight = lambda *_a, **_k: None  # type: ignore[method-assign]
        pipeline.database_checkpoint = database_checkpoint  # type: ignore[method-assign]
        pipeline.promote = promote  # type: ignore[method-assign]
        pipeline.optional_cleanup = mark("optional_cleanup")  # type: ignore[method-assign]
        pipeline.status = lambda *a, **k: None  # type: ignore[method-assign]
        pipeline.tutor_confirm = lambda *a, **k: None  # type: ignore[method-assign]
        pipeline.maybe_return_to_start_branch = lambda: None  # type: ignore[method-assign]

        pipeline.run()

        self.assertIn("database_checkpoint:main:main-ref", order)
        self.assertIn("database_checkpoint:production:prod-ref", order)
        self.assertLess(
            order.index("database_checkpoint:production:prod-ref"),
            order.index("promote:main:production"),
        )

    def test_backend_target_exact_branch_never_legacy_index_guess(self) -> None:
        """Legacy pre/prod keys must not match by pipeline index when branch names differ."""
        pipeline = ENGINE.Pipeline.__new__(ENGINE.Pipeline)
        pipeline.branches = ("main", "production")
        pipeline.backend = ENGINE.BackendConfig(
            provider="supabase",
            cli="supabase",
            targets={"pre": "pre-ref", "prod": "prod-ref"},
        )
        self.assertIsNone(pipeline._backend_target_for_branch("main", 0))
        self.assertIsNone(pipeline._backend_target_for_branch("production", 1))
        # Even with a 3-branch pipeline, index must not map to pre/prod roles.
        pipeline.branches = ("main", "staging", "production")
        self.assertIsNone(pipeline._backend_target_for_branch("staging", 1))
        self.assertIsNone(pipeline._backend_target_for_branch("production", 2))

    def test_supabase_missing_destination_ref_fails_closed(self) -> None:
        """provider=supabase + missing destination ref → ShipError (no soft skip)."""
        import supagit_i18n

        en_tmpl = (
            "No database migration target configured for branch {branch}; "
            "aborting before any code merge."
        )
        es_tmpl = (
            "No hay destino de migración de base de datos configurado para la rama "
            "{branch}; se aborta antes de fusionar código."
        )
        self.assertEqual(
            set(supagit_i18n._MESSAGES["en"]), set(supagit_i18n._MESSAGES["es"])
        )
        self.assertEqual(
            supagit_i18n._MESSAGES["en"]["error_migrate_no_target"], en_tmpl
        )
        self.assertEqual(
            supagit_i18n._MESSAGES["es"]["error_migrate_no_target"], es_tmpl
        )

        pipeline = ENGINE.Pipeline.__new__(ENGINE.Pipeline)
        pipeline.options = ENGINE.Options(
            dry_run=True,
            yes=True,
            config_path=None,
            message="test",
            color="never",
            no_sweep=True,
            integrate=None,
            pipeline_order=None,
            cleanup=False,
        )
        pipeline.branches = ("main", "production")
        pipeline.dev = "main"
        pipeline.pre = "production"
        pipeline.prod = "production"
        pipeline.remote = "origin"
        pipeline.original_branch = "main"
        # Legacy-keyed targets: exact branch lookup misses → must fail closed, not soft skip.
        pipeline.backend = ENGINE.BackendConfig(
            provider="supabase",
            cli="supabase",
            targets={"pre": "pre-ref", "prod": "prod-ref"},
        )
        pipeline.preflight_repo = lambda: None  # type: ignore[method-assign]
        pipeline.build_inventory = lambda **_k: _fake_inventory()  # type: ignore[method-assign]
        pipeline._explain_situation_preflight = lambda *_a, **_k: None  # type: ignore[method-assign]
        pipeline.ensure_checkout_on_first_branch = lambda: None  # type: ignore[method-assign]
        pipeline.validate_pipeline_head = lambda: None  # type: ignore[method-assign]
        pipeline.commit_and_publish_dev = lambda **_k: None  # type: ignore[method-assign]
        pipeline.ff_sync_first_branch = lambda: None  # type: ignore[method-assign]
        pipeline._assert_dev_synced = lambda: None  # type: ignore[method-assign]
        pipeline.run_checks = lambda: None  # type: ignore[method-assign]
        pipeline.validate_clean_after_checks = lambda: None  # type: ignore[method-assign]
        pipeline.tutor_confirm = lambda *a, **k: None  # type: ignore[method-assign]

        def refuse_checkpoint(*_a, **_k) -> None:
            raise AssertionError("checkpoint should not run when destination lacks ref")

        pipeline.database_checkpoint = refuse_checkpoint  # type: ignore[method-assign]
        pipeline.promote = lambda *a, **k: None  # type: ignore[method-assign]
        pipeline.return_to_dev = lambda: None  # type: ignore[method-assign]
        pipeline.optional_cleanup = lambda *a, **k: None  # type: ignore[method-assign]
        pipeline.verify_final_checkout = lambda: None  # type: ignore[method-assign]
        pipeline.status = lambda *a, **k: None  # type: ignore[method-assign]
        pipeline.maybe_return_to_start_branch = lambda: None  # type: ignore[method-assign]

        for lang in ("en", "es"):
            with self.subTest(lang=lang):
                supagit_i18n.set_lang(lang)
                with self.assertRaises(ENGINE.ShipError) as ctx:
                    pipeline.run()
                msg = str(ctx.exception)
                self.assertIn("main", msg)
                self.assertNotIn("skipping checkpoint", msg.lower())
                self.assertNotIn("se omite el checkpoint", msg.lower())

    def test_database_checkpoint_failure_aborts_before_merge(self) -> None:
        """Failed pipeline[0] checkpoint must abort — never merge/promote."""
        pipeline = ENGINE.Pipeline.__new__(ENGINE.Pipeline)
        pipeline.options = ENGINE.Options(
            dry_run=False,
            yes=True,
            config_path=None,
            message="test",
            color="never",
            no_sweep=False,
            integrate="feature/x",
            pipeline_order="dev,pre,prod",
            cleanup=False,
        )
        pipeline.branches = ("dev", "pre", "prod")
        pipeline.dev = "dev"
        pipeline.pre = "pre"
        pipeline.prod = "prod"
        pipeline.remote = "origin"
        pipeline.original_branch = "dev"
        pipeline.backend = ENGINE.BackendConfig(
            provider="supabase",
            cli="supabase",
            targets={"dev": "dev-ref", "pre": "pre-ref", "prod": "prod-ref"},
        )
        order: list[str] = []

        def mark(name: str):
            def _inner(*args, **kwargs):
                order.append(name)
                if name == "build_inventory":
                    return _fake_inventory()
                if name == "run_branch_menu":
                    return supagit_menu.MenuSelection(
                        integrate=("feature/x",), pipeline=("dev", "pre", "prod")
                    )
                return None

            return _inner

        def fail_checkpoint(label: str, project_ref: str) -> None:
            order.append(f"database_checkpoint:{label}:{project_ref}")
            raise ENGINE.ShipError(
                f"Command failed: supabase db push --linked: auth expired ({label})"
            )

        def promote(source: str, target: str) -> None:
            order.append(f"promote:{source}:{target}")

        for name in (
            "preflight_repo",
            "build_inventory",
            "run_branch_menu",
            "ensure_checkout_on_first_branch",
            "validate_pipeline_head",
            "commit_and_publish_dev",
            "sweep_features",
            "ff_sync_first_branch",
            "_assert_dev_synced",
            "run_checks",
            "validate_clean_after_checks",
            "return_to_dev",
            "verify_final_checkout",
        ):
            setattr(pipeline, name, mark(name))
        pipeline.database_checkpoint = fail_checkpoint  # type: ignore[method-assign]
        pipeline.promote = promote  # type: ignore[method-assign]
        pipeline.optional_cleanup = mark("optional_cleanup")  # type: ignore[method-assign]
        pipeline.status = lambda *a, **k: None  # type: ignore[method-assign]
        pipeline.tutor_confirm = lambda *a, **k: None  # type: ignore[method-assign]
        pipeline._require_noninteractive_selection = lambda *_a, **_k: None  # type: ignore[method-assign]

        with self.assertRaises(ENGINE.ShipError) as ctx:
            pipeline.run()
        self.assertIn("auth expired", str(ctx.exception))
        self.assertEqual(order.count("database_checkpoint:dev:dev-ref"), 1)
        self.assertNotIn("commit_and_publish_dev", order)
        self.assertNotIn("sweep_features", order)
        self.assertFalse(any(item.startswith("promote:") for item in order))

    def test_promotion_checkpoint_failure_aborts_before_promote(self) -> None:
        """Failed target checkpoint in the promotion loop must not call promote."""
        pipeline = ENGINE.Pipeline.__new__(ENGINE.Pipeline)
        pipeline.options = ENGINE.Options(
            dry_run=False,
            yes=True,
            config_path=None,
            message="test",
            color="never",
            no_sweep=True,
            integrate=None,
            pipeline_order=None,
            cleanup=False,
        )
        pipeline.branches = ("dev", "pre", "prod")
        pipeline.dev = "dev"
        pipeline.pre = "pre"
        pipeline.prod = "prod"
        pipeline.remote = "origin"
        pipeline.original_branch = "dev"
        pipeline.backend = ENGINE.BackendConfig(
            provider="supabase",
            cli="supabase",
            targets={"dev": "dev-ref", "pre": "pre-ref", "prod": "prod-ref"},
        )
        order: list[str] = []

        def mark(name: str):
            def _inner(*args, **kwargs):
                order.append(name)
                if name == "build_inventory":
                    return _fake_inventory()
                return None

            return _inner

        def checkpoint(label: str, project_ref: str) -> None:
            order.append(f"database_checkpoint:{label}:{project_ref}")
            if label == "pre":
                raise ENGINE.ShipError("Command failed: supabase db push: refused")

        def promote(source: str, target: str) -> None:
            order.append(f"promote:{source}:{target}")

        for name in (
            "preflight_repo",
            "build_inventory",
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
        pipeline._explain_situation_preflight = lambda *_a, **_k: None  # type: ignore[method-assign]
        pipeline.database_checkpoint = checkpoint  # type: ignore[method-assign]
        pipeline.promote = promote  # type: ignore[method-assign]
        pipeline.optional_cleanup = mark("optional_cleanup")  # type: ignore[method-assign]
        pipeline.status = lambda *a, **k: None  # type: ignore[method-assign]
        pipeline.tutor_confirm = lambda *a, **k: None  # type: ignore[method-assign]
        pipeline.maybe_return_to_start_branch = lambda: None  # type: ignore[method-assign]

        with self.assertRaises(ENGINE.ShipError) as ctx:
            pipeline.run()
        self.assertIn("refused", str(ctx.exception))
        self.assertIn("database_checkpoint:dev:dev-ref", order)
        self.assertIn("database_checkpoint:pre:pre-ref", order)
        self.assertNotIn("promote:dev:pre", order)
        self.assertNotIn("promote:pre:prod", order)
        self.assertNotIn("database_checkpoint:prod:prod-ref", order)

    def test_database_checkpoint_wraps_run_raw_failure_as_ship_error(self) -> None:
        """Non-ShipError from db push must become ShipError (fail-closed)."""
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
        pipeline.cli = "supabase"
        pipeline.linked_ref = None
        pipeline.root = Path("/repo")
        unlinked: list[bool] = []

        def link_supabase(project_ref: str) -> None:
            pipeline.linked_ref = project_ref

        def unlink_supabase() -> None:
            unlinked.append(True)
            pipeline.linked_ref = None

        def run_raw(command: Sequence[str], **kwargs):
            parts = [str(p) for p in command]
            if "db" in parts and "push" in parts and "--dry-run" in parts:
                return "Pending migrations would be applied.\n"
            if "db" in parts and "push" in parts:
                raise OSError("supabase CLI crashed during db push")
            raise AssertionError(f"unexpected command: {parts}")

        pipeline.link_supabase = link_supabase  # type: ignore[method-assign]
        pipeline.unlink_supabase = unlink_supabase  # type: ignore[method-assign]
        pipeline.run_raw = run_raw  # type: ignore[method-assign]
        pipeline.tutor_confirm = lambda *a, **k: None  # type: ignore[method-assign]

        with self.assertRaises(ENGINE.ShipError) as ctx:
            pipeline.database_checkpoint("dev", "dev-ref")
        text = str(ctx.exception)
        self.assertIn("dev", text)
        self.assertIn("crashed", text)
        self.assertTrue(unlinked, "unlink must still run after checkpoint failure")

    def test_database_checkpoint_blocks_on_remote_migration_drift(self) -> None:
        """After push looks clean, remote history must still match local filenames."""
        import tempfile

        import supagit_i18n

        supagit_i18n.set_lang("en")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            migrations = root / "supabase" / "migrations"
            migrations.mkdir(parents=True)
            (migrations / "20240101000000_init.sql").write_text("-- local\n", encoding="utf-8")

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
            pipeline.cli = "supabase"
            pipeline.linked_ref = None
            pipeline.root = root
            commands: list[list[str]] = []
            unlinked: list[bool] = []

            def link_supabase(project_ref: str) -> None:
                pipeline.linked_ref = project_ref

            def unlink_supabase() -> None:
                unlinked.append(True)
                pipeline.linked_ref = None

            def run_raw(command: Sequence[str], **kwargs):
                parts = [str(p) for p in command]
                commands.append(parts)
                if "db" in parts and "push" in parts and "--dry-run" in parts:
                    return "Remote database is up to date.\n"
                if "db" in parts and "push" in parts:
                    return "Finished supabase db push.\n"
                if "migration" in parts and "list" in parts:
                    # Remote has an extra version not present as a local filename.
                    return (
                        "        LOCAL      │     REMOTE     │     TIME (UTC)\n"
                        "  ─────────────────┼────────────────┼──────────────────────\n"
                        "   20240101000000  │ 20240101000000 │ 2024-01-01 00:00:00\n"
                        "                   │ 20240202000000 │ 2024-02-02 00:00:00\n"
                    )
                raise AssertionError(f"unexpected command: {parts}")

            pipeline.link_supabase = link_supabase  # type: ignore[method-assign]
            pipeline.unlink_supabase = unlink_supabase  # type: ignore[method-assign]
            pipeline.run_raw = run_raw  # type: ignore[method-assign]
            pipeline.tutor_confirm = lambda *a, **k: None  # type: ignore[method-assign]

            with self.assertRaises(ENGINE.ShipError) as ctx:
                pipeline.database_checkpoint("pre", "pre-ref")
            message = str(ctx.exception)
            self.assertIn("pre", message)
            self.assertTrue(
                any("migration" in c and "list" in c for c in commands),
                f"expected migration list after push; got {commands}",
            )
            self.assertTrue(unlinked)

    def test_migration_drift_aborts_before_promote(self) -> None:
        """Invariant: never promote code when remote migrations drifted vs local files."""
        pipeline = ENGINE.Pipeline.__new__(ENGINE.Pipeline)
        pipeline.options = ENGINE.Options(
            dry_run=False,
            yes=True,
            config_path=None,
            message="test",
            color="never",
            no_sweep=True,
            integrate=None,
            pipeline_order=None,
            cleanup=False,
        )
        pipeline.branches = ("dev", "pre")
        pipeline.dev = "dev"
        pipeline.pre = "pre"
        pipeline.prod = "prod"
        pipeline.remote = "origin"
        pipeline.original_branch = "dev"
        pipeline.backend = ENGINE.BackendConfig(
            provider="supabase",
            cli="supabase",
            targets={"dev": "dev-ref", "pre": "pre-ref"},
        )
        order: list[str] = []

        def mark(name: str):
            def _inner(*args, **kwargs):
                order.append(name)
                if name == "build_inventory":
                    return _fake_inventory()
                return None

            return _inner

        def database_checkpoint(label: str, project_ref: str) -> None:
            order.append(f"database_checkpoint:{label}:{project_ref}")
            if label == "pre":
                raise ENGINE.ShipError(
                    "migration drift for pre (remote-only 20240202000000)"
                )

        def promote(source: str, target: str) -> None:
            order.append(f"promote:{source}:{target}")

        for name in (
            "preflight_repo",
            "build_inventory",
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
        pipeline.apply_menu_selection = lambda selection: None  # type: ignore[method-assign]
        pipeline._extend_integrate_after_pre_commit = (  # type: ignore[method-assign]
            lambda selection, committed: selection
        )
        pipeline._explain_situation_preflight = lambda *a, **k: None  # type: ignore[method-assign]
        pipeline.database_checkpoint = database_checkpoint  # type: ignore[method-assign]
        pipeline.promote = promote  # type: ignore[method-assign]
        pipeline.optional_cleanup = mark("optional_cleanup")  # type: ignore[method-assign]
        pipeline.status = lambda *a, **k: None  # type: ignore[method-assign]
        pipeline.tutor_confirm = lambda *a, **k: None  # type: ignore[method-assign]
        pipeline.maybe_return_to_start_branch = lambda: None  # type: ignore[method-assign]
        pipeline._require_noninteractive_selection = lambda *_a, **_k: None  # type: ignore[method-assign]

        with self.assertRaises(ENGINE.ShipError) as ctx:
            pipeline.run()
        self.assertIn("migration drift", str(ctx.exception))
        self.assertIn("database_checkpoint:dev:dev-ref", order)
        self.assertIn("database_checkpoint:pre:pre-ref", order)
        self.assertNotIn("promote:dev:pre", order)

    def test_first_branch_in_other_worktree_adopts(self) -> None:
        porcelain = (
            "worktree /repo\nbranch refs/heads/feature/x\n\n"
            "worktree /wt-main\nbranch refs/heads/main\n"
        )
        pipeline, calls, explained = self._pipeline_for_reposition(
            current="feature/x",
            worktree_porcelain=porcelain,
            yes=True,
        )
        pipeline.main_root = Path("/repo")
        committed = pipeline.ensure_checkout_on_first_branch()
        self.assertIsNone(committed)
        self.assertEqual(pipeline.root, Path("/wt-main").resolve())
        self.assertFalse(any(c[0] == "checkout" for c in calls))
        self.assertTrue(any("wt-main" in e for e in explained))

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
        self.assertFalse(any(c[0] == "switch" for c in calls))

    def test_detached_unreachable_auto_rescues(self) -> None:
        pipeline, calls, explained = self._pipeline_for_reposition(
            current="",
            yes=True,
            contains="",
            short_sha="deadbee",
        )
        committed = pipeline.ensure_checkout_on_first_branch()
        self.assertEqual(committed, "supagit-rescue-deadbee")
        self.assertIn(("switch", "-c", "supagit-rescue-deadbee"), calls)
        self.assertIn(("checkout", "main"), calls)
        self.assertTrue(
            any("rescued" in e.lower() and "supagit-rescue-deadbee" in e for e in explained)
        )
        self.assertFalse(any("git switch -c" in e for e in explained))

    def test_detached_dirty_auto_rescues_commits_and_repositions(self) -> None:
        pipeline, calls, explained = self._pipeline_for_reposition(
            current="",
            yes=True,
            contains="feature/x\n",
            short_sha="deadbee",
            dirty=" M a.txt\n?? b.txt\n",
            message="save work",
        )
        committed = pipeline.ensure_checkout_on_first_branch()
        self.assertEqual(committed, "supagit-rescue-deadbee")
        self.assertIn(("switch", "-c", "supagit-rescue-deadbee"), calls)
        self.assertTrue(any(c[0] == "add" for c in calls))
        self.assertTrue(any(c[0] == "commit" for c in calls))
        self.assertIn(("checkout", "main"), calls)
        self.assertTrue(
            any("rescued" in e.lower() and "supagit-rescue-deadbee" in e for e in explained)
        )
        joined = "\n".join(explained) + "\n".join(str(c) for c in calls)
        self.assertNotIn("git stash", joined.lower())

    def test_preflight_fetch_prune_then_announce(self) -> None:
        pipeline, calls, _ = self._pipeline_for_reposition(
            current="main", linked=False, dry_run=True
        )
        pipeline.run_raw = lambda *a, **k: ""  # type: ignore[method-assign]
        pipeline.preflight_repo()
        self.assertTrue(
            any(c[:3] == ("fetch", "--prune", "origin") for c in calls),
            f"expected fetch --prune origin in {calls}",
        )

    def test_preflight_supabase_missing_cli_fails_before_checkpoint(self) -> None:
        """provider=supabase + missing CLI must fail in preflight, not at checkpoint."""
        import supagit_supabase

        pipeline, _, _ = self._pipeline_for_reposition(
            current="main", linked=False, dry_run=False, yes=True
        )
        pipeline.backend = ENGINE.BackendConfig(
            provider="supabase", cli="supabase", targets={"dev": "dev-ref"}
        )
        pipeline.cli = "supabase"
        pipeline.run_raw = lambda *a, **k: ""  # type: ignore[method-assign]
        with patch.object(supagit_supabase.shutil, "which", return_value=None):
            with self.assertRaises(ENGINE.ShipError) as ctx:
                pipeline.preflight_repo()
        self.assertIn("not installed", str(ctx.exception).lower())

    def test_preflight_supabase_ready_ok(self) -> None:
        pipeline, _, _ = self._pipeline_for_reposition(
            current="main", linked=False, dry_run=False, yes=True
        )
        pipeline.backend = ENGINE.BackendConfig(
            provider="supabase", cli="supabase", targets={"dev": "dev-ref"}
        )
        pipeline.cli = "supabase"
        pipeline.run_raw = lambda *a, **k: ""  # type: ignore[method-assign]
        calls: list[tuple] = []

        def fake_ready(cli, *, dry_run, run_raw=None):
            calls.append((cli, dry_run, run_raw))

        with patch.object(
            ENGINE.supagit_supabase, "ensure_supabase_ready", side_effect=fake_ready
        ):
            pipeline.preflight_repo()
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "supabase")
        self.assertFalse(calls[0][1])
        self.assertEqual(calls[0][2].__func__, pipeline._supabase_run_raw.__func__)

    def test_preflight_merge_head_aborts_before_mutation(self) -> None:
        pipeline, calls, explained = self._pipeline_for_reposition(
            current="main", linked=False, yes=True
        )
        pipeline.run_raw = lambda *a, **k: ""  # type: ignore[method-assign]
        heads = {"MERGE_HEAD"}

        original_git = pipeline.git

        def git(*args: str, capture: bool = False, check: bool = True, mutating: bool = False, cwd: Path | None = None) -> str:
            if args[:2] == ("rev-parse", "--verify") and args[2] in {
                "MERGE_HEAD",
                "REBASE_HEAD",
                "CHERRY_PICK_HEAD",
            }:
                if args[2] in heads:
                    return "deadbeef\n"
                raise ENGINE.ShipError(f"missing {args[2]}")
            if args[:2] == ("merge", "--abort"):
                calls.append(args)
                heads.clear()
                return ""
            return original_git(*args, capture=capture, check=check, mutating=mutating, cwd=cwd)

        pipeline.git = git  # type: ignore[method-assign]
        pipeline.preflight_repo()
        self.assertTrue(
            any("merge" in e.lower() for e in explained),
            f"expected merge explanation in {explained}",
        )
        self.assertIn(("merge", "--abort"), calls)
        # Sequencer abort must run before fetch --prune so an unreachable
        # remote cannot skip the mid-merge tutor.
        abort_idx = calls.index(("merge", "--abort"))
        fetch_idx = next(
            i for i, c in enumerate(calls) if c[:3] == ("fetch", "--prune", "origin")
        )
        self.assertLess(
            abort_idx,
            fetch_idx,
            f"sequencer abort must precede fetch --prune in {calls}",
        )

    def test_preflight_sequencer_tutor_runs_when_fetch_unreachable(self) -> None:
        pipeline, calls, explained = self._pipeline_for_reposition(
            current="main", linked=False, yes=True
        )
        pipeline.run_raw = lambda *a, **k: ""  # type: ignore[method-assign]
        heads = {"MERGE_HEAD"}
        original_git = pipeline.git

        def git(*args: str, capture: bool = False, check: bool = True, mutating: bool = False, cwd: Path | None = None) -> str:
            if args[:2] == ("rev-parse", "--verify") and args[2] in {
                "MERGE_HEAD",
                "REBASE_HEAD",
                "CHERRY_PICK_HEAD",
            }:
                if args[2] in heads:
                    return "deadbeef\n"
                raise ENGINE.ShipError(f"missing {args[2]}")
            if args[:2] == ("merge", "--abort"):
                calls.append(args)
                heads.clear()
                return ""
            if args[:3] == ("fetch", "--prune", "origin"):
                calls.append(args)
                raise ENGINE.ShipError("Could not fetch: network unreachable")
            return original_git(*args, capture=capture, check=check, mutating=mutating, cwd=cwd)

        pipeline.git = git  # type: ignore[method-assign]
        with self.assertRaisesRegex(ENGINE.ShipError, "network unreachable"):
            pipeline.preflight_repo()
        self.assertTrue(
            any("merge" in e.lower() for e in explained),
            f"expected merge tutor before fetch failure; explained={explained}",
        )
        self.assertIn(("merge", "--abort"), calls)
        abort_idx = calls.index(("merge", "--abort"))
        fetch_idx = calls.index(("fetch", "--prune", "origin"))
        self.assertLess(abort_idx, fetch_idx)

    def test_preflight_rebase_head_abort_declined_raises(self) -> None:
        import tempfile

        pipeline, calls, _ = self._pipeline_for_reposition(
            current="main", linked=False, yes=False
        )
        pipeline.run_raw = lambda *a, **k: ""  # type: ignore[method-assign]
        pipeline.ask_yes_no = lambda *_a, **_k: False  # type: ignore[method-assign]

        original_git = pipeline.git

        with tempfile.TemporaryDirectory() as td:
            rebase_merge = Path(td) / "rebase-merge"
            rebase_merge.mkdir()

            def git(*args: str, capture: bool = False, check: bool = True, mutating: bool = False, cwd: Path | None = None) -> str:
                if args[:2] == ("rev-parse", "--git-path") and args[2] == "rebase-merge":
                    return f"{rebase_merge}\n"
                if args[:2] == ("rev-parse", "--git-path") and args[2] == "rebase-apply":
                    return f"{Path(td) / 'rebase-apply'}\n"
                if args[:2] == ("rev-parse", "--verify") and args[2] in {
                    "MERGE_HEAD",
                    "CHERRY_PICK_HEAD",
                }:
                    raise ENGINE.ShipError(f"missing {args[2]}")
                return original_git(
                    *args, capture=capture, check=check, mutating=mutating, cwd=cwd
                )

            pipeline.git = git  # type: ignore[method-assign]
            with self.assertRaises(ENGINE.UserAborted):
                pipeline.preflight_repo()
        self.assertFalse(any(c[:2] == ("rebase", "--abort") for c in calls))

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
        pipeline.launch_root = Path("/repo")
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
        pipeline.main_root = Path("/repo")
        pipeline.dev = "dev"
        pipeline.original_branch = "feature/x"
        pipeline.GREEN = ""
        calls: list[tuple] = []
        statuses: list[str] = []

        def git(*args, **kwargs):
            calls.append(args)
            if args[:2] == ("worktree", "list"):
                return "worktree /repo\nbranch refs/heads/dev\n"
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
        pipeline._require_noninteractive_selection = lambda *_a, **_k: None  # type: ignore[method-assign]
        pipeline._explain_situation_preflight = lambda *_a, **_k: None  # type: ignore[method-assign]

        selection = pipeline.run_branch_menu(_fake_inventory())
        self.assertEqual(selection.pipeline, ("dev", "pre", "prod"))
        self.assertGreaterEqual(len(explain_kwargs), 2)
        # Menu list: no Continue?; execution plan: force_confirm for dry-run gate.
        self.assertEqual(explain_kwargs[0]["ask_continue"], False)
        self.assertFalse(explain_kwargs[0]["force_confirm"])
        plan_call = explain_kwargs[-1]
        self.assertTrue(plan_call["force_confirm"])

    def test_run_branch_menu_skips_prompts_when_no_work_and_single_pipeline(self) -> None:
        layout = RepoLayout(
            launch_root=Path("/repo"),
            main_root=Path("/repo"),
            common_dir=Path("/repo/.git"),
            is_linked_launch=False,
        )
        inv = RepoInventory(
            layout,
            (),
            (
                BranchInfo(
                    "main", True, True, Path("/repo"), 0, 0, True, "origin/main", False
                ),
            ),
            "main",
        )
        pipeline = ENGINE.Pipeline.__new__(ENGINE.Pipeline)
        pipeline.options = ENGINE.Options(
            dry_run=True,
            yes=False,
            config_path=None,
            message=None,
            color="never",
        )
        pipeline.branches = ("main",)
        pipeline.remote = "origin"
        pipeline.original_branch = "main"
        tutor_calls: list[tuple[str, str]] = []
        explained: list[str] = []

        def capture_explain(
            message: str, *, ask_continue: bool = True, force_confirm: bool = False
        ) -> None:
            explained.append(message)

        def capture_tutor(explanation: str, prompt: str) -> str:
            tutor_calls.append((explanation, prompt))
            raise AssertionError("should not prompt when nothing to choose")

        pipeline.explain = capture_explain  # type: ignore[method-assign]
        pipeline.tutor_prompt = capture_tutor  # type: ignore[method-assign]
        pipeline._require_noninteractive_selection = lambda *_a, **_k: None  # type: ignore[method-assign]
        pipeline._explain_situation_preflight = lambda *_a, **_k: None  # type: ignore[method-assign]

        selection = pipeline.run_branch_menu(inv)
        self.assertEqual(selection.integrate, ())
        self.assertEqual(selection.pipeline, ("main",))
        self.assertEqual(tutor_calls, [])
        self.assertTrue(any("nothing to merge" in msg.lower() or "no feature" in msg.lower() for msg in explained))
        self.assertTrue(any("pipeline for this run: main" in msg.lower() for msg in explained))

    def test_run_branch_menu_single_pending_uses_confirm_skips_pipeline_order(self) -> None:
        """One pending [✓] + one pipeline branch → one Enter confirm; no order prompt."""
        layout = RepoLayout(
            launch_root=Path("/repo"),
            main_root=Path("/repo"),
            common_dir=Path("/repo/.git"),
            is_linked_launch=False,
        )
        inv = RepoInventory(
            layout,
            (),
            (
                BranchInfo(
                    "dev", True, True, Path("/repo"), 0, 0, True, "origin/dev", False
                ),
                BranchInfo(
                    "feature/x",
                    False,
                    True,
                    Path("/wt"),
                    1,
                    0,
                    False,
                    None,
                    True,
                ),
                BranchInfo(
                    "old", False, False, None, 0, 0, True, None, False
                ),
            ),
            "dev",
        )
        pipeline = ENGINE.Pipeline.__new__(ENGINE.Pipeline)
        pipeline.options = ENGINE.Options(
            dry_run=False,
            yes=False,
            config_path=None,
            message=None,
            color="never",
        )
        pipeline.branches = ("dev",)
        pipeline.remote = "origin"
        pipeline.original_branch = "dev"
        tutor_calls: list[tuple[str, str]] = []
        yes_no_calls: list[str] = []

        def capture_tutor(explanation: str, prompt: str) -> str:
            tutor_calls.append((explanation, prompt))
            raise AssertionError(
                f"should not use multi-choice prompt; got: {prompt!r}"
            )

        def capture_yes_no(message: str, *, default_yes: bool = True) -> bool:
            yes_no_calls.append(message)
            self.assertTrue(default_yes)
            return True

        pipeline.explain = lambda *a, **k: None  # type: ignore[method-assign]
        pipeline.tutor_prompt = capture_tutor  # type: ignore[method-assign]
        pipeline.ask_yes_no = capture_yes_no  # type: ignore[method-assign]
        pipeline._require_noninteractive_selection = lambda *_a, **_k: None  # type: ignore[method-assign]
        pipeline._explain_situation_preflight = lambda *_a, **_k: None  # type: ignore[method-assign]

        selection = pipeline.run_branch_menu(inv)
        self.assertEqual(selection.integrate, ("feature/x",))
        self.assertEqual(selection.pipeline, ("dev",))
        self.assertEqual(tutor_calls, [])
        self.assertEqual(len(yes_no_calls), 1)
        self.assertIn("Merge feature feature/x into dev?", yes_no_calls[0])

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
        pipeline.commit_and_publish_dev = lambda **_k: None  # type: ignore[method-assign]
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

    def test_promote_direct_adopts_worktree_holding_target(self) -> None:
        """Promote into a branch locked in another worktree must adopt, not error."""
        pipeline = ENGINE.Pipeline.__new__(ENGINE.Pipeline)
        pipeline.options = ENGINE.Options(
            dry_run=False,
            yes=True,
            config_path=None,
            message=None,
            color="never",
        )
        pipeline.root = Path("/repo")
        pipeline.main_root = Path("/repo")
        pipeline.remote = "origin"
        porcelain = (
            "worktree /repo\nbranch refs/heads/dev\n\n"
            "worktree /wt-main\nbranch refs/heads/main\n"
        )
        git_calls: list[tuple[tuple, Path | None]] = []
        explained: list[str] = []

        def git(
            *args: str,
            capture: bool = False,
            check: bool = True,
            mutating: bool = False,
            cwd: Path | None = None,
        ) -> str:
            git_calls.append((args, cwd))
            if args[:2] == ("worktree", "list"):
                return porcelain
            if args[:2] == ("branch", "--show-current"):
                resolved = Path(cwd).resolve() if cwd is not None else Path("/repo").resolve()
                if resolved == Path("/wt-main").resolve():
                    return "main\n"
                return "dev\n"
            if args[0] in {"fetch", "merge", "push", "checkout"}:
                return ""
            raise AssertionError(args)

        pipeline.git = git  # type: ignore[method-assign]
        pipeline.explain = lambda message, **_kwargs: explained.append(message)  # type: ignore[method-assign]

        # Must not raise error_first_branch_in_worktree / "worktree remove".
        pipeline._promote_direct("dev", "main")

        fetch_specs = [
            args
            for args, _cwd in git_calls
            if args[:1] == ("fetch",)
        ]
        self.assertEqual(
            fetch_specs,
            [("fetch", "origin", "refs/heads/main:refs/remotes/origin/main")],
            "promote-adopt must fetch into remote-tracking only, never refs/heads/{target}",
        )
        self.assertFalse(
            any(
                len(args) >= 3 and args[2].endswith(":refs/heads/main")
                for args, _cwd in git_calls
                if args[:1] == ("fetch",)
            ),
            "must not fetch into checked-out refs/heads/main",
        )
        merge_calls = [
            (args, Path(cwd).resolve() if cwd is not None else None)
            for args, cwd in git_calls
            if args[:1] == ("merge",)
        ]
        self.assertEqual(
            merge_calls,
            [
                (("merge", "--ff-only", "origin/main"), Path("/wt-main").resolve()),
                (("merge", "dev", "--no-edit"), Path("/wt-main").resolve()),
            ],
        )
        push_cwds = [
            Path(cwd).resolve()
            for args, cwd in git_calls
            if args[:1] == ("push",) and cwd is not None
        ]
        self.assertEqual(push_cwds, [Path("/wt-main").resolve()])
        self.assertFalse(
            any(args[:1] == ("checkout",) for args, _cwd in git_calls),
            "target already checked out in adopted worktree — no checkout",
        )
        self.assertTrue(
            any("wt-main" in msg for msg in explained),
            f"expected adopt explanation mentioning wt-main; got {explained!r}",
        )

    def test_commit_and_publish_rebases_when_dirty_and_behind(self) -> None:
        """Dirty pipeline[0] behind upstream must rebase then push (not skip-push)."""
        pipeline = ENGINE.Pipeline.__new__(ENGINE.Pipeline)
        pipeline.options = ENGINE.Options(
            dry_run=False,
            yes=True,
            config_path=None,
            message="local work",
            color="never",
        )
        pipeline.root = Path("/repo")
        pipeline.dev = "dev"
        pipeline.remote = "origin"
        calls: list[tuple] = []
        rev_list_phase = {"n": 0}

        def git(*args, capture: bool = False, check: bool = True, mutating: bool = False, cwd=None):
            calls.append(args)
            if args[:2] == ("status", "--porcelain"):
                return " M app.py\n"
            if args[:2] == ("diff", "--cached") and args[2:3] == ("--name-only",):
                return "app.py\n"
            if args[:2] == ("diff", "--cached") and args[2:3] == ("--check",):
                return ""
            if args[:1] == ("add",):
                return ""
            if args[:1] == ("commit",):
                return ""
            if args[:3] == ("rev-list", "--left-right", "--count"):
                rev_list_phase["n"] += 1
                # After commit: behind+ahead (would diverge if push skipped).
                # After rebase+push assert: 0/0.
                if rev_list_phase["n"] == 1:
                    return "2\t1\n"
                return "0\t0\n"
            if args[:1] == ("pull",) or args[:1] == ("rebase",):
                return ""
            if args[:1] == ("fetch",):
                return ""
            if args[:1] == ("push",):
                return ""
            if args[:2] == ("branch", "--show-current"):
                return "dev\n"
            raise AssertionError(args)

        pipeline.git = git  # type: ignore[method-assign]
        pipeline.tutor_confirm = lambda *a, **k: None  # type: ignore[method-assign]
        pipeline._reject_sensitive_paths = lambda paths, cwd=None: list(paths)  # type: ignore[method-assign]
        pipeline._commit_message = lambda **k: "local work"  # type: ignore[method-assign]

        pipeline.commit_and_publish_dev()

        rebased = any(
            (c[0] == "pull" and "--rebase" in c) or c[0] == "rebase"
            for c in calls
        )
        self.assertTrue(rebased, f"expected rebase/pull --rebase in {calls}")
        self.assertTrue(any(c[0] == "push" for c in calls), f"expected push in {calls}")

    def test_commit_and_publish_unstages_prestaged_secret(self) -> None:
        """Mixed staged secret + safe file: unstage secret, commit the rest (no abort)."""
        pipeline = ENGINE.Pipeline.__new__(ENGINE.Pipeline)
        pipeline.options = ENGINE.Options(
            dry_run=False,
            yes=True,
            config_path=None,
            message="local work",
            color="never",
        )
        pipeline.root = Path("/repo")
        pipeline.dev = "dev"
        pipeline.remote = "origin"
        calls: list[tuple] = []
        cached_reads = {"n": 0}
        rev_list_phase = {"n": 0}

        def git(*args, capture: bool = False, check: bool = True, mutating: bool = False, cwd=None):
            calls.append(args)
            if args[:2] == ("status", "--porcelain"):
                return "A  .env\n M app.py\n"
            if args[:1] == ("add",):
                self.assertNotIn(".env", args)
                return ""
            if args[:2] == ("diff", "--cached") and args[2:3] == ("--name-only",):
                cached_reads["n"] += 1
                if cached_reads["n"] == 1:
                    return ".env\napp.py\n"
                return "app.py\n"
            if args[:2] == ("restore", "--staged"):
                self.assertIn(".env", args)
                return ""
            if args[:2] == ("diff", "--cached") and args[2:3] == ("--check",):
                return ""
            if args[:1] == ("commit",):
                return ""
            if args[:3] == ("rev-list", "--left-right", "--count"):
                rev_list_phase["n"] += 1
                # After commit: ahead only; after push sync assert: 0/0.
                if rev_list_phase["n"] == 1:
                    return "0\t1\n"
                return "0\t0\n"
            if args[:1] == ("push",):
                return ""
            if args[:2] == ("branch", "--show-current"):
                return "dev\n"
            raise AssertionError(args)

        pipeline.git = git  # type: ignore[method-assign]
        pipeline.tutor_confirm = lambda *a, **k: None  # type: ignore[method-assign]
        pipeline.explain = lambda *a, **k: None  # type: ignore[method-assign]
        pipeline.ask_yes_no = lambda *a, **k: False  # type: ignore[method-assign]
        pipeline.status = lambda *a, **k: None  # type: ignore[method-assign]
        pipeline._commit_message = lambda **k: "local work"  # type: ignore[method-assign]
        # Use real sensitivity helpers so leaked .env is detected.
        pipeline._is_sensitive_path = ENGINE.Pipeline._is_sensitive_path  # type: ignore[method-assign]
        pipeline._gitignore_patterns_for = ENGINE.Pipeline._gitignore_patterns_for  # type: ignore[method-assign]
        pipeline._reject_sensitive_paths = ENGINE.Pipeline._reject_sensitive_paths.__get__(  # type: ignore[method-assign]
            pipeline, ENGINE.Pipeline
        )

        pipeline.commit_and_publish_dev()

        restore_calls = [c for c in calls if c[:2] == ("restore", "--staged")]
        self.assertEqual(len(restore_calls), 1)
        self.assertIn(".env", restore_calls[0])
        self.assertTrue(any(c[0] == "commit" for c in calls))
        self.assertFalse(
            any(c[0] == "add" and ".env" in c for c in calls),
            "must never git-add the secret",
        )


if __name__ == "__main__":
    unittest.main()
