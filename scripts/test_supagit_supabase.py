#!/usr/bin/env python3
"""Tests for Supabase CLI auth preflight (Task 16)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import supagit_i18n
import supagit_supabase


class EnsureSupabaseReadyTests(unittest.TestCase):
    def setUp(self) -> None:
        supagit_i18n.set_lang("en")

    def test_dry_run_skips_probe(self) -> None:
        calls: list[list[str]] = []

        def run_raw(cmd, **kwargs):
            calls.append(list(cmd))
            raise AssertionError("dry-run must not probe supabase")

        with patch.object(supagit_supabase.shutil, "which", return_value="/bin/supabase"):
            supagit_supabase.ensure_supabase_ready(
                "supabase", dry_run=True, run_raw=run_raw
            )
        self.assertEqual(calls, [])

    def test_missing_cli_fails_with_install_hint(self) -> None:
        with patch.object(supagit_supabase.shutil, "which", return_value=None):
            with self.assertRaises(supagit_supabase.SupabaseError) as ctx:
                supagit_supabase.ensure_supabase_ready("supabase", dry_run=False)
        message = str(ctx.exception).lower()
        self.assertIn("not installed", message)
        self.assertIn("brew install", message)

    def test_projects_list_ok_returns(self) -> None:
        calls: list[list[str]] = []

        def run_raw(cmd, **kwargs):
            calls.append(list(cmd))
            if cmd[:2] == ["supabase", "projects"]:
                return "│ ref │ name │\n"
            raise AssertionError(cmd)

        with patch.object(supagit_supabase.shutil, "which", return_value="/bin/supabase"):
            supagit_supabase.ensure_supabase_ready(
                "supabase", dry_run=False, run_raw=run_raw
            )
        self.assertEqual(calls, [["supabase", "projects", "list"]])

    def test_auth_failure_login_once_on_tty(self) -> None:
        calls: list[list[str]] = []
        attempts = {"list": 0}

        def run_raw(cmd, **kwargs):
            calls.append(list(cmd))
            if cmd[:2] == ["supabase", "projects"]:
                attempts["list"] += 1
                if attempts["list"] == 1:
                    raise RuntimeError(
                        "You need to be logged-in in order to use Management API commands."
                    )
                return ""
            if cmd[:2] == ["supabase", "login"]:
                return ""
            raise AssertionError(cmd)

        with patch.object(supagit_supabase.shutil, "which", return_value="/bin/supabase"):
            with patch.object(sys.stdin, "isatty", return_value=True):
                supagit_supabase.ensure_supabase_ready(
                    "supabase", dry_run=False, run_raw=run_raw
                )
        self.assertEqual(
            calls,
            [
                ["supabase", "projects", "list"],
                ["supabase", "login"],
                ["supabase", "projects", "list"],
            ],
        )
        self.assertEqual(attempts["list"], 2)

    def test_auth_failure_non_tty_fails_closed(self) -> None:
        calls: list[list[str]] = []

        def run_raw(cmd, **kwargs):
            calls.append(list(cmd))
            if cmd[:2] == ["supabase", "projects"]:
                raise RuntimeError(
                    "You need to be logged-in in order to use Management API commands."
                )
            raise AssertionError(f"unexpected command (no login without TTY): {cmd}")

        with patch.object(supagit_supabase.shutil, "which", return_value="/bin/supabase"):
            with patch.object(sys.stdin, "isatty", return_value=False):
                with self.assertRaises(supagit_supabase.SupabaseError) as ctx:
                    supagit_supabase.ensure_supabase_ready(
                        "supabase", dry_run=False, run_raw=run_raw
                    )
        message = str(ctx.exception).lower()
        self.assertIn("logged", message)
        self.assertNotIn("run `supabase login`", message)
        self.assertNotIn("ejecuta `supabase login`", message)
        self.assertEqual(calls, [["supabase", "projects", "list"]])

    def test_login_failure_on_tty_fails_closed(self) -> None:
        calls: list[list[str]] = []

        def run_raw(cmd, **kwargs):
            calls.append(list(cmd))
            if cmd[:2] == ["supabase", "projects"]:
                raise RuntimeError("Access token not provided. Supply an access token")
            if cmd[:2] == ["supabase", "login"]:
                raise RuntimeError("login cancelled")
            raise AssertionError(cmd)

        with patch.object(supagit_supabase.shutil, "which", return_value="/bin/supabase"):
            with patch.object(sys.stdin, "isatty", return_value=True):
                with self.assertRaises(supagit_supabase.SupabaseError) as ctx:
                    supagit_supabase.ensure_supabase_ready(
                        "supabase", dry_run=False, run_raw=run_raw
                    )
        message = str(ctx.exception).lower()
        self.assertIn("login", message)
        self.assertNotIn("run `supabase login`", message)
        self.assertEqual(calls[1], ["supabase", "login"])
        self.assertEqual(len(calls), 2)

    def test_still_unauthenticated_after_login(self) -> None:
        def run_raw(cmd, **kwargs):
            if cmd[:2] == ["supabase", "projects"]:
                raise RuntimeError("You need to be logged-in")
            if cmd[:2] == ["supabase", "login"]:
                return ""
            raise AssertionError(cmd)

        with patch.object(supagit_supabase.shutil, "which", return_value="/bin/supabase"):
            with patch.object(sys.stdin, "isatty", return_value=True):
                with self.assertRaises(supagit_supabase.SupabaseError) as ctx:
                    supagit_supabase.ensure_supabase_ready(
                        "supabase", dry_run=False, run_raw=run_raw
                    )
        self.assertIn("still", str(ctx.exception).lower())

    def test_non_auth_probe_failure_does_not_login(self) -> None:
        calls: list[list[str]] = []

        def run_raw(cmd, **kwargs):
            calls.append(list(cmd))
            if cmd[:2] == ["supabase", "projects"]:
                raise RuntimeError("network unreachable")
            raise AssertionError(cmd)

        with patch.object(supagit_supabase.shutil, "which", return_value="/bin/supabase"):
            with patch.object(sys.stdin, "isatty", return_value=True):
                with self.assertRaises(supagit_supabase.SupabaseError) as ctx:
                    supagit_supabase.ensure_supabase_ready(
                        "supabase", dry_run=False, run_raw=run_raw
                    )
        self.assertIn("network unreachable", str(ctx.exception))
        self.assertEqual(calls, [["supabase", "projects", "list"]])

    def test_custom_cli_name_used_in_probe(self) -> None:
        calls: list[list[str]] = []

        def run_raw(cmd, **kwargs):
            calls.append(list(cmd))
            return ""

        with patch.object(supagit_supabase.shutil, "which", return_value="/opt/sb"):
            supagit_supabase.ensure_supabase_ready(
                "sb", dry_run=False, run_raw=run_raw
            )
        self.assertEqual(calls, [["sb", "projects", "list"]])


class MigrationStateTests(unittest.TestCase):
    def test_local_migration_versions_from_filenames(self) -> None:
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            migrations = Path(directory) / "supabase" / "migrations"
            migrations.mkdir(parents=True)
            (migrations / "20240101000000_init.sql").write_text("x\n", encoding="utf-8")
            (migrations / "20240202000000_add.sql").write_text("y\n", encoding="utf-8")
            (migrations / "readme.txt").write_text("ignore\n", encoding="utf-8")
            versions = supagit_supabase.local_migration_versions(migrations)
        self.assertEqual(versions, {"20240101000000", "20240202000000"})

    def test_parse_migration_list_remote_versions(self) -> None:
        output = (
            "        LOCAL      │     REMOTE     │     TIME (UTC)\n"
            "  ─────────────────┼────────────────┼──────────────────────\n"
            "   20240101000000  │ 20240101000000 │ 2024-01-01 00:00:00\n"
            "                   │ 20240202000000 │ 2024-02-02 00:00:00\n"
            "   20240303000000  │                │ 2024-03-03 00:00:00\n"
        )
        remote = supagit_supabase.parse_migration_list_remote(output)
        self.assertEqual(remote, {"20240101000000", "20240202000000"})

    def test_assert_migration_state_matches_detects_drift(self) -> None:
        with self.assertRaises(supagit_supabase.SupabaseError) as ctx:
            supagit_supabase.assert_migration_state_matches(
                local={"20240101000000"},
                remote={"20240101000000", "20240202000000"},
                label="pre",
            )
        self.assertIn("pre", str(ctx.exception))
        self.assertIn("20240202000000", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
