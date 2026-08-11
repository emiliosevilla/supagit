# scripts/test_supagit_situation.py
import importlib.util
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

SPEC = importlib.util.spec_from_file_location("supagit_situation", SCRIPTS / "supagit_situation.py")
SIT = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = SIT
SPEC.loader.exec_module(SIT)


class ClassifySyncTests(unittest.TestCase):
    def test_in_sync(self) -> None:
        self.assertEqual(SIT.classify_sync_counts(0, 0), SIT.SyncStatus.IN_SYNC)

    def test_ahead_only(self) -> None:
        self.assertEqual(SIT.classify_sync_counts(2, 0), SIT.SyncStatus.AHEAD_ONLY)

    def test_behind_only(self) -> None:
        self.assertEqual(SIT.classify_sync_counts(0, 3), SIT.SyncStatus.BEHIND_ONLY)

    def test_diverged(self) -> None:
        self.assertEqual(SIT.classify_sync_counts(1, 1), SIT.SyncStatus.DIVERGED)

    def test_negative_rejected(self) -> None:
        with self.assertRaises(ValueError):
            SIT.classify_sync_counts(-1, 0)


class ParseAheadBehindTests(unittest.TestCase):
    def test_ok(self) -> None:
        self.assertEqual(SIT.parse_ahead_behind("2\t5"), (2, 5))

    def test_malformed_raises(self) -> None:
        with self.assertRaises(SIT.SituationError):
            SIT.parse_ahead_behind("nope")


class BuildBranchSyncTests(unittest.TestCase):
    def test_behind_clean_feature(self) -> None:
        def git(*args, **kwargs):
            cmd = list(args)
            if cmd[:2] == ["rev-parse", "--verify"]:
                return "abc\n"
            if cmd[:2] == ["branch", "--show-current"]:
                return "feature\n"
            if cmd[0] == "status":
                return ""
            if cmd[:2] == ["rev-parse", "--abbrev-ref"]:
                return "origin/feature\n"
            if cmd[:3] == ["rev-list", "--left-right", "--count"]:
                return "2\t0\n"
            raise AssertionError(cmd)

        sync, finding = SIT.build_branch_sync(
            git, "feature", remote="origin", role="feature", worktree_path="/wt"
        )
        self.assertEqual(sync.sync, SIT.SyncStatus.BEHIND_ONLY)
        self.assertEqual(sync.behind, 2)
        self.assertEqual(sync.ahead, 0)
        self.assertFalse(sync.dirty)
        self.assertEqual(sync.upstream, "origin/feature")
        self.assertEqual(finding.cure_id, "ff_only")

    def test_pipeline0_ignores_dirty_when_other_branch_checked_out(self) -> None:
        def git(*args, **kwargs):
            cmd = list(args)
            if cmd[:2] == ["rev-parse", "--verify"]:
                return "abc\n"
            if cmd[:2] == ["branch", "--show-current"]:
                return "work\n"
            if cmd[0] == "status":
                return " M README.md\n"
            if cmd[:2] == ["rev-parse", "--abbrev-ref"]:
                return "origin/main\n"
            if cmd[:3] == ["rev-list", "--left-right", "--count"]:
                return "0\t0\n"
            raise AssertionError(cmd)

        sync, finding = SIT.build_branch_sync(
            git, "main", remote="origin", role="pipeline0", worktree_path="/repo"
        )
        self.assertFalse(sync.dirty)
        self.assertEqual(finding.cure_id, "none")

    def test_feature_dirty_when_checked_out(self) -> None:
        def git(*args, **kwargs):
            cmd = list(args)
            if cmd[:2] == ["rev-parse", "--verify"]:
                return "abc\n"
            if cmd[:2] == ["branch", "--show-current"]:
                return "work\n"
            if cmd[0] == "status":
                return " M README.md\n"
            if cmd[:2] == ["rev-parse", "--abbrev-ref"]:
                return "origin/work\n"
            if cmd[:3] == ["rev-list", "--left-right", "--count"]:
                return "0\t0\n"
            raise AssertionError(cmd)

        sync, finding = SIT.build_branch_sync(
            git, "work", remote="origin", role="feature", worktree_path="/repo"
        )
        self.assertTrue(sync.dirty)
        self.assertEqual(finding.cure_id, "commit_feature")

    def test_no_worktree_never_dirty(self) -> None:
        def git(*args, **kwargs):
            cmd = list(args)
            if cmd[:2] == ["rev-parse", "--verify"]:
                return "abc\n"
            if cmd[0] == "status":
                raise AssertionError("status must not run without a worktree")
            if cmd[:2] == ["rev-parse", "--abbrev-ref"]:
                return "origin/main\n"
            if cmd[:3] == ["rev-list", "--left-right", "--count"]:
                return "0\t0\n"
            raise AssertionError(cmd)

        sync, finding = SIT.build_branch_sync(
            git, "main", remote="origin", role="pipeline0", worktree_path=None
        )
        self.assertFalse(sync.dirty)
        self.assertEqual(finding.cure_id, "none")

    def test_missing_branch_raises(self) -> None:
        def git(*args, **kwargs):
            if list(args)[:2] == ["rev-parse", "--verify"]:
                raise RuntimeError("bad ref")
            raise AssertionError(args)

        with self.assertRaises(SIT.SituationError):
            SIT.build_branch_sync(
                git, "missing", remote="origin", role="feature", worktree_path=None
            )

    def test_no_upstream_info_finding(self) -> None:
        def git(*args, **kwargs):
            cmd = list(args)
            if cmd[:2] == ["rev-parse", "--verify"]:
                return "abc\n"
            if cmd[0] == "status":
                return ""
            if cmd[:2] == ["rev-parse", "--abbrev-ref"]:
                raise RuntimeError("no upstream")
            raise AssertionError(cmd)

        sync, finding = SIT.build_branch_sync(
            git, "feature", remote="origin", role="feature", worktree_path=None
        )
        self.assertEqual(sync.sync, SIT.SyncStatus.NO_UPSTREAM)
        self.assertIsNone(sync.upstream)
        self.assertEqual(finding.policy, SIT.PolicyClass.INFO)
        self.assertEqual(finding.cure_id, "none")


class RenderPreflightTests(unittest.TestCase):
    def setUp(self) -> None:
        import supagit_i18n

        supagit_i18n.set_lang("en")

    def test_lists_blocked_and_safe(self) -> None:
        findings = (
            SIT.Finding(SIT.PolicyClass.BLOCKED, "stop_diverged", SIT.SyncStatus.DIVERGED, False, "pipeline0"),
            SIT.Finding(SIT.PolicyClass.SAFE_CURE, "ff_only", SIT.SyncStatus.BEHIND_ONLY, False, "feature"),
        )
        sit = SIT.Situation(
            current_branch="dev",
            dirty=False,
            pipeline0=None,
            features=(),
            findings=findings,
            gh_ready=True,
            self_update=SIT.SyncStatus.IN_SYNC,
        )
        text = SIT.render_preflight(sit)
        self.assertIn("diverg", text.lower())
        self.assertIn("fast-forward", text.lower())

    def test_format_blocked_diverged_includes_commands(self) -> None:
        f = SIT.Finding(
            SIT.PolicyClass.BLOCKED,
            "stop_diverged",
            SIT.SyncStatus.DIVERGED,
            False,
            "pipeline0",
        )
        text = SIT.format_blocked_error(f, branch="dev", upstream="origin/dev")
        self.assertIn("git fetch", text)
        self.assertIn("origin/dev...dev", text)

    def test_format_blocked_dirty_feature(self) -> None:
        f = SIT.Finding(
            SIT.PolicyClass.BLOCKED,
            "stop_dirty_feature",
            SIT.SyncStatus.BEHIND_ONLY,
            True,
            "feature",
        )
        text = SIT.format_blocked_error(f, branch="feature/x", upstream="origin/feature/x")
        self.assertIn("feature/x", text)
        self.assertIn("dirty", text.lower())

    def test_plan_cure_lines_orders_feature_then_pipeline0_ff(self) -> None:
        pipeline0 = SIT.BranchSync(
            "dev",
            "origin/dev",
            SIT.SyncStatus.BEHIND_ONLY,
            0,
            2,
            True,
            "/repo",
        )
        feature = SIT.BranchSync(
            "feature/x",
            "origin/feature/x",
            SIT.SyncStatus.BEHIND_ONLY,
            0,
            1,
            False,
            "/wt",
        )
        findings = (
            SIT.Finding(
                SIT.PolicyClass.SAFE_CURE,
                "publish_then_ff",
                SIT.SyncStatus.BEHIND_ONLY,
                True,
                "pipeline0",
            ),
            SIT.Finding(
                SIT.PolicyClass.SAFE_CURE,
                "ff_only",
                SIT.SyncStatus.BEHIND_ONLY,
                False,
                "feature",
            ),
        )
        sit = SIT.Situation(
            current_branch="dev",
            dirty=True,
            pipeline0=pipeline0,
            features=(feature,),
            findings=findings,
            gh_ready=None,
            self_update=None,
        )
        lines = SIT.plan_cure_lines(sit, remote="origin")
        self.assertEqual(len(lines), 2)
        self.assertIn("feature/x", lines[0])
        self.assertIn("before integrating", lines[0].lower())
        self.assertIn("dev", lines[1])
        self.assertIn("fast-forward", lines[1].lower())


class PolicyTests(unittest.TestCase):
    def test_diverged_blocked(self) -> None:
        f = SIT.classify_ref_finding(SIT.SyncStatus.DIVERGED, dirty=False, role="pipeline0")
        self.assertEqual(f.policy, SIT.PolicyClass.BLOCKED)
        self.assertEqual(f.cure_id, "stop_diverged")

    def test_behind_clean_safe_ff(self) -> None:
        f = SIT.classify_ref_finding(SIT.SyncStatus.BEHIND_ONLY, dirty=False, role="feature")
        self.assertEqual(f.policy, SIT.PolicyClass.SAFE_CURE)
        self.assertEqual(f.cure_id, "ff_only")

    def test_pipeline0_dirty_behind_publish_then_ff(self) -> None:
        f = SIT.classify_ref_finding(SIT.SyncStatus.BEHIND_ONLY, dirty=True, role="pipeline0")
        self.assertEqual(f.policy, SIT.PolicyClass.SAFE_CURE)
        self.assertEqual(f.cure_id, "publish_then_ff")

    def test_feature_dirty_behind_blocked(self) -> None:
        f = SIT.classify_ref_finding(SIT.SyncStatus.BEHIND_ONLY, dirty=True, role="feature")
        self.assertEqual(f.policy, SIT.PolicyClass.BLOCKED)
        self.assertEqual(f.cure_id, "stop_dirty_feature")

    def test_feature_dirty_in_sync_commit(self) -> None:
        f = SIT.classify_ref_finding(SIT.SyncStatus.IN_SYNC, dirty=True, role="feature")
        self.assertEqual(f.policy, SIT.PolicyClass.SAFE_CURE)
        self.assertEqual(f.cure_id, "commit_feature")


if __name__ == "__main__":
    unittest.main()
