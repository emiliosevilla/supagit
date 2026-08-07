#!/usr/bin/env python3
"""Small unit tests for supagit's pure discovery helpers."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).with_name("supagit.py")
SPEC = importlib.util.spec_from_file_location("supagit_engine", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class BranchDiscoveryTests(unittest.TestCase):
    def test_exact_alias_beats_prefixed_branch(self) -> None:
        ranked = MODULE.Pipeline.rank_branch_candidates("dev", ["dev", "feature/dev"])
        self.assertEqual(ranked[0], (100, "dev"))

    def test_examples_from_other_projects_are_detected(self) -> None:
        self.assertEqual(
            MODULE.Pipeline.rank_branch_candidates("dev", ["work"])[0],
            (100, "work"),
        )
        self.assertEqual(
            MODULE.Pipeline.rank_branch_candidates("pre", ["preview"])[0],
            (100, "preview"),
        )
        self.assertEqual(
            MODULE.Pipeline.rank_branch_candidates("prod", ["production"])[0],
            (100, "production"),
        )

    def test_unrelated_branches_are_not_candidates(self) -> None:
        self.assertEqual(MODULE.Pipeline.rank_branch_candidates("prod", ["feature/login"]), [])

    def test_ordered_branch_list_is_valid(self) -> None:
        MODULE.Pipeline._validate_config(
            {"branches": ["main", "production"], "backend": {"provider": "none"}},
            Path(".supagit.json"),
        )

    def test_duplicate_ordered_branches_are_rejected(self) -> None:
        with self.assertRaisesRegex(MODULE.ShipError, "duplicate"):
            MODULE.Pipeline._validate_config(
                {"branches": ["main", "main"], "backend": {"provider": "none"}},
                Path(".supagit.json"),
            )

    def test_commit_prompt_uses_green_when_color_is_forced(self) -> None:
        pipeline = MODULE.Pipeline.__new__(MODULE.Pipeline)
        pipeline.options = MODULE.Options(
            dry_run=False,
            yes=False,
            config_path=None,
            message=None,
            color="always",
        )
        with patch("builtins.input", return_value="release message") as mocked_input:
            pipeline.dev = "main"
            message = pipeline._commit_message()

        self.assertEqual(message, "release message")
        prompt = mocked_input.call_args.args[0]
        self.assertTrue(prompt.startswith(MODULE.Pipeline.GREEN))
        self.assertTrue(prompt.endswith(MODULE.Pipeline.RESET))
        self.assertIn("Commit message for main: ", prompt)

    def test_success_status_uses_green_when_color_is_forced(self) -> None:
        pipeline = MODULE.Pipeline.__new__(MODULE.Pipeline)
        pipeline.options = MODULE.Options(False, False, None, None, "always")
        with patch("builtins.print") as mocked_print:
            pipeline.status("Pipeline completed", MODULE.Pipeline.GREEN)

        mocked_print.assert_called_once_with(
            f"{MODULE.Pipeline.GREEN}Pipeline completed{MODULE.Pipeline.RESET}"
        )

    def test_confirmation_prompt_uses_green_when_color_is_forced(self) -> None:
        pipeline = MODULE.Pipeline.__new__(MODULE.Pipeline)
        pipeline.options = MODULE.Options(False, False, None, None, "always")
        with patch("builtins.input", return_value="y") as mocked_input:
            pipeline.confirm("Continue with the pipeline?")

        prompt = mocked_input.call_args.args[0]
        self.assertTrue(prompt.startswith(MODULE.Pipeline.GREEN))
        self.assertTrue(prompt.endswith(MODULE.Pipeline.RESET))

    def test_warning_uses_red_when_color_is_forced(self) -> None:
        pipeline = MODULE.Pipeline.__new__(MODULE.Pipeline)
        pipeline.options = MODULE.Options(False, False, None, None, "always")
        with patch("builtins.print") as mocked_print:
            pipeline.warning("manual review required")

        mocked_print.assert_called_once_with(
            f"{MODULE.Pipeline.RED}WARNING: manual review required{MODULE.Pipeline.RESET}",
            file=sys.stderr,
        )

    def test_failure_status_uses_red_when_color_is_forced(self) -> None:
        self.assertEqual(
            MODULE.colour_text("ERROR: pipeline stopped", MODULE.RED, True),
            f"{MODULE.RED}ERROR: pipeline stopped{MODULE.RESET}",
        )

    def test_failed_command_colours_every_stderr_line(self) -> None:
        pipeline = MODULE.Pipeline.__new__(MODULE.Pipeline)
        pipeline.options = MODULE.Options(False, False, None, None, "always")
        completed = subprocess.CompletedProcess(
            args=["fake-command"],
            returncode=1,
            stdout="",
            stderr="error: first line\nerror: second line\n",
        )
        with patch("subprocess.run", return_value=completed), patch("builtins.print") as mocked_print:
            with self.assertRaises(MODULE.ShipError):
                pipeline.run_raw(["fake-command"])

        error_line = mocked_print.call_args_list[-1].args[0]
        self.assertEqual(
            error_line,
            f"{MODULE.RED}error: first line\nerror: second line{MODULE.RESET}",
        )


class BackendDiscoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pipeline = MODULE.Pipeline.__new__(MODULE.Pipeline)

    @staticmethod
    def base_config(backend: dict) -> dict:
        return {
            "branches": {"dev": None, "pre": None, "prod": None},
            "backend": backend,
        }

    def test_none_backend_is_valid(self) -> None:
        MODULE.Pipeline._validate_config(
            self.base_config({"provider": "none"}), Path(".supagit.json")
        )

    def test_legacy_supabase_config_is_still_valid(self) -> None:
        config = {
            "branches": {"dev": None, "pre": None, "prod": None},
            "supabase": {
                "pruebas_project_ref": "testing-ref",
                "prod_project_ref": "production-ref",
            },
        }
        MODULE.Pipeline._validate_config(config, Path(".supagit.json"))
        backend = self.pipeline._resolve_backend_from_config(config)
        self.assertEqual(backend.targets, {"pre": "testing-ref", "prod": "production-ref"})

    def test_none_backend_resolves_without_targets(self) -> None:
        backend = self.pipeline._resolve_backend_from_config({"backend": {"provider": "none"}})
        self.assertEqual(backend.provider, "none")
        self.assertEqual(backend.targets, {})

    def test_supabase_url_produces_project_ref(self) -> None:
        self.assertEqual(
            MODULE.Pipeline._project_ref_from_value("https://testing-ref.supabase.co"),
            "testing-ref",
        )

    def test_role_specific_env_file_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.pipeline.root = Path(directory)
            (self.pipeline.root / ".env.production").write_text(
                "VITE_SUPABASE_URL=https://production-ref.supabase.co\n",
                encoding="utf-8",
            )
            self.assertEqual(
                self.pipeline._detect_supabase_project_ref("prod"),
                "production-ref",
            )

    def test_ambiguous_role_detection_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.pipeline.root = Path(directory)
            (self.pipeline.root / ".env.staging").write_text(
                "VITE_SUPABASE_PRIMARY_URL=https://one-ref.supabase.co\n"
                "VITE_SUPABASE_SECONDARY_URL=https://two-ref.supabase.co\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(MODULE.ShipError, "Ambiguous Supabase project ref"):
                self.pipeline._detect_supabase_project_ref("pre")

    def test_explicit_environment_names_resolve_without_hardcoded_refs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.pipeline.root = Path(directory)
            config = {
                "backend": {
                    "provider": "supabase",
                    "environments": {
                        "pre": {"project_ref_env": "MY_TEST_DATABASE"},
                        "prod": {"url_env": "MY_PRODUCTION_URL"},
                    },
                }
            }
            with patch.dict(
                os.environ,
                {
                    "MY_TEST_DATABASE": "testing-ref",
                    "MY_PRODUCTION_URL": "https://production-ref.supabase.co",
                },
                clear=False,
            ):
                backend = self.pipeline._resolve_backend_from_config(config)

        self.assertEqual(backend.provider, "supabase")
        self.assertEqual(backend.targets, {"pre": "testing-ref", "prod": "production-ref"})


class ProjectInitTests(unittest.TestCase):
    def test_none_backend_config_contains_no_supabase_targets(self) -> None:
        config = MODULE.init_project_config("none", "PRE_REF", "PROD_REF")
        self.assertEqual(config["backend"], {"provider": "none"})
        self.assertNotIn("supabase", config)

    def test_supabase_init_config_contains_variable_names_only(self) -> None:
        config = MODULE.init_project_config("supabase", "MY_PRE_REF", "MY_PROD_REF")
        self.assertEqual(config["backend"]["provider"], "supabase")
        self.assertEqual(
            config["backend"]["environments"],
            {
                "pre": {"project_ref_env": "MY_PRE_REF"},
                "prod": {"project_ref_env": "MY_PROD_REF"},
            },
        )

    def test_init_config_accepts_one_or_more_ordered_branches(self) -> None:
        config = MODULE.init_project_config("none", "PRE_REF", "PROD_REF", ["main"])
        self.assertEqual(config["branches"], ["main"])


class PromotionTargetTests(unittest.TestCase):
    def test_branch_specific_backend_target_is_selected(self) -> None:
        pipeline = MODULE.Pipeline.__new__(MODULE.Pipeline)
        pipeline.branches = ("dev", "qa", "production")
        pipeline.backend = MODULE.BackendConfig(
            provider="supabase",
            cli="supabase",
            targets={"qa": "qa-ref", "production": "prod-ref"},
        )
        self.assertEqual(pipeline._backend_target_for_branch("qa", 1), "qa-ref")
        self.assertEqual(pipeline._backend_target_for_branch("production", 2), "prod-ref")

    def test_single_branch_has_no_promotion_target(self) -> None:
        pipeline = MODULE.Pipeline.__new__(MODULE.Pipeline)
        pipeline.branches = ("main",)
        pipeline.backend = MODULE.BackendConfig(provider="none", cli=None, targets={})
        self.assertIsNone(pipeline._backend_target_for_branch("main", 0))


if __name__ == "__main__":
    unittest.main()
