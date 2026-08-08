#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import supagit_inventory
import supagit_layout


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


if __name__ == "__main__":
    unittest.main()
