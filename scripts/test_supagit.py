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
    def setUp(self) -> None:
        MODULE.supagit_i18n.set_lang("en")
        os.environ[MODULE.supagit_update.SKIP_ENV] = "1"
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
        self.assertIn("[Y/n]", prompt)

    def test_confirmation_empty_enter_defaults_to_yes(self) -> None:
        pipeline = MODULE.Pipeline.__new__(MODULE.Pipeline)
        pipeline.options = MODULE.Options(False, False, None, None, "never")
        with patch("builtins.input", return_value="") as mocked_input:
            pipeline.confirm("Continue with the pipeline?")
        self.assertIn("[Y/n]", mocked_input.call_args.args[0])

    def test_confirmation_n_aborts(self) -> None:
        pipeline = MODULE.Pipeline.__new__(MODULE.Pipeline)
        pipeline.options = MODULE.Options(False, False, None, None, "never")
        with patch("builtins.input", return_value="n"):
            with self.assertRaises(MODULE.UserAborted):
                pipeline.confirm("Continue with the pipeline?")

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

    def test_explain_uses_cyan_when_color_forced(self) -> None:
        pipeline = MODULE.Pipeline.__new__(MODULE.Pipeline)
        pipeline.options = MODULE.Options(False, False, None, None, "always")
        with patch("builtins.print") as mocked_print:
            pipeline.explain("Tutor text")
        mocked_print.assert_called_once_with(
            f"{MODULE.CYAN}Tutor text{MODULE.RESET}"
        )

    def test_tutor_confirm_prints_cyan_then_green_confirm(self) -> None:
        pipeline = MODULE.Pipeline.__new__(MODULE.Pipeline)
        pipeline.options = MODULE.Options(False, False, None, None, "always")
        with patch("builtins.print") as mocked_print, patch("builtins.input", return_value="") as mocked_input:
            pipeline.tutor_confirm("Will publish main.", "Continue?")
        mocked_print.assert_called_once_with(
            f"{MODULE.CYAN}Will publish main.{MODULE.RESET}"
        )
        prompt = mocked_input.call_args.args[0]
        self.assertTrue(prompt.startswith(MODULE.Pipeline.GREEN))
        self.assertIn("[Y/n]", prompt)
        self.assertIn("Continue?", prompt)

    def test_tutor_confirm_skips_under_yes(self) -> None:
        pipeline = MODULE.Pipeline.__new__(MODULE.Pipeline)
        pipeline.options = MODULE.Options(False, True, None, None, "always")
        with patch("builtins.print") as mocked_print, patch("builtins.input") as mocked_input:
            pipeline.tutor_confirm("Will publish main.", "Continue?")
        mocked_print.assert_not_called()
        mocked_input.assert_not_called()

    def test_tutor_confirm_explain_under_dry_run(self) -> None:
        pipeline = MODULE.Pipeline.__new__(MODULE.Pipeline)
        pipeline.options = MODULE.Options(True, False, None, None, "always")
        with patch("builtins.print") as mocked_print, patch("builtins.input") as mocked_input:
            pipeline.tutor_confirm("Will publish main.", "Continue?")
        mocked_print.assert_called_once_with(
            f"{MODULE.CYAN}Will publish main.{MODULE.RESET}"
        )
        mocked_input.assert_not_called()

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


class I18nAndUpdateTests(unittest.TestCase):
    def setUp(self) -> None:
        MODULE.supagit_i18n.set_lang("en")
        os.environ[MODULE.supagit_update.SKIP_ENV] = "1"

    def test_tutor_i18n_keys_exist_in_en_and_es(self) -> None:
        keys = (
            "explain_integrate",
            "menu_section_worktrees",
            "menu_section_pipeline",
            "plan_header",
            "error_contained_integrate",
        )
        for lang in ("en", "es"):
            MODULE.supagit_i18n.set_lang(lang)
            for key in keys:
                text = MODULE.t(key, branch="x", base="dev", default="dev → pre")
                self.assertNotEqual(text, key, msg=f"missing {lang}:{key}")

    def test_t_switches_language(self) -> None:
        MODULE.supagit_i18n.set_lang("en")
        self.assertEqual(MODULE.t("user_aborted"), "Operation cancelled by the user.")
        MODULE.supagit_i18n.set_lang("es")
        self.assertEqual(MODULE.t("user_aborted"), "Operación cancelada por el usuario.")

    def test_resolve_lang_from_arg_and_env(self) -> None:
        self.assertEqual(
            MODULE.supagit_i18n.resolve_lang_from_env_and_args("es", yes=True, stdin_isatty=False),
            "es",
        )
        with patch.dict(os.environ, {"SUPAGIT_LANG": "en"}, clear=False):
            self.assertEqual(
                MODULE.supagit_i18n.resolve_lang_from_env_and_args(None, yes=True, stdin_isatty=False),
                "en",
            )

    def test_yes_without_lang_raises(self) -> None:
        with patch.dict(os.environ, {"SUPAGIT_LANG": ""}, clear=False):
            with patch.object(MODULE.supagit_i18n.sys.stdin, "isatty", return_value=False):
                with self.assertRaisesRegex(RuntimeError, "lang_required_yes"):
                    MODULE.supagit_i18n.ensure_language(None, yes=True)

    def test_confirm_spanish_suffix_and_si(self) -> None:
        MODULE.supagit_i18n.set_lang("es")
        pipeline = MODULE.Pipeline.__new__(MODULE.Pipeline)
        pipeline.options = MODULE.Options(False, False, None, None, "never")
        with patch("builtins.input", return_value="sí") as mocked_input:
            pipeline.confirm("¿Continuar?")
        self.assertIn("[S/n]", mocked_input.call_args.args[0])

    def test_auto_create_config_writes_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".supagit.json"
            pipeline = MODULE.Pipeline.__new__(MODULE.Pipeline)
            pipeline.options = MODULE.Options(
                dry_run=False,
                yes=True,
                config_path=path,
                message=None,
                color="never",
                backend="none",
            )
            pipeline.root = Path(tmp)
            with patch("builtins.print"):
                pipeline._auto_create_config(path)
            self.assertTrue(path.is_file())
            data = path.read_text(encoding="utf-8")
            self.assertIn('"provider": "none"', data)

    def test_auto_create_config_refuses_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".supagit.json"
            path.write_text("{}\n", encoding="utf-8")
            pipeline = MODULE.Pipeline.__new__(MODULE.Pipeline)
            pipeline.options = MODULE.Options(
                dry_run=False,
                yes=True,
                config_path=path,
                message=None,
                color="never",
                backend="none",
            )
            with patch("builtins.print"):
                with self.assertRaisesRegex(MODULE.ShipError, "refusing to overwrite"):
                    pipeline._auto_create_config(path)

    def test_needs_update_true_when_behind(self) -> None:
        update = MODULE.supagit_update

        def fake_run(cwd, *args):
            cmd = list(args)
            if cmd[:3] == ["git", "remote", "get-url"]:
                return "https://github.com/emiliosevilla/supagit.git"
            if cmd[:2] == ["git", "fetch"]:
                return ""
            if "rev-list" in cmd:
                return "2\t0"
            raise AssertionError(cmd)

        with patch.object(update, "_run", side_effect=fake_run):
            self.assertTrue(update.needs_update(Path("/tmp")))

    def test_needs_update_false_when_current(self) -> None:
        update = MODULE.supagit_update

        def fake_run(cwd, *args):
            cmd = list(args)
            if cmd[:3] == ["git", "remote", "get-url"]:
                return "https://github.com/emiliosevilla/supagit.git"
            if cmd[:2] == ["git", "fetch"]:
                return ""
            if "rev-list" in cmd:
                return "0\t0"
            raise AssertionError(cmd)

        with patch.object(update, "_run", side_effect=fake_run):
            self.assertFalse(update.needs_update(Path("/tmp")))

    def test_needs_skip_update_env(self) -> None:
        with patch.dict(os.environ, {MODULE.supagit_update.SKIP_ENV: "1"}):
            self.assertTrue(MODULE.needs_skip_update())
        with patch.dict(os.environ, {MODULE.supagit_update.SKIP_ENV: "0"}):
            self.assertFalse(MODULE.needs_skip_update())


class WelcomeAndBusyTests(unittest.TestCase):
    def setUp(self) -> None:
        MODULE.supagit_i18n.set_lang("en")

    def test_welcome_banner_includes_name_and_author(self) -> None:
        from io import StringIO

        stream = StringIO()
        MODULE.print_welcome(colour_enabled=False, stream=stream)
        text = stream.getvalue()
        self.assertIn("supagit", text)
        self.assertIn("Author: Emilio Sevilla", text)
        self.assertIn("Ctrl+C", text)

    def test_welcome_banner_spanish(self) -> None:
        from io import StringIO

        MODULE.supagit_i18n.set_lang("es")
        stream = StringIO()
        MODULE.print_welcome(colour_enabled=False, stream=stream)
        text = stream.getvalue()
        self.assertIn("Autor: Emilio Sevilla", text)
        self.assertIn("trabajando", MODULE.t("busy_working"))

    def test_busy_spinner_disabled_is_noop(self) -> None:
        from io import StringIO

        stream = StringIO()
        with MODULE.BusySpinner(enabled=False, stream=stream, delay_s=0.0):
            pass
        self.assertEqual(stream.getvalue(), "")

    def test_busy_spinner_writes_cyan_working_line(self) -> None:
        from io import StringIO
        import time

        stream = StringIO()
        with MODULE.BusySpinner(enabled=True, stream=stream, delay_s=0.0, interval_s=0.05):
            time.sleep(0.12)
        output = stream.getvalue()
        self.assertIn("supagit is working", output)
        self.assertIn("Ctrl+C", output)
        self.assertIn(MODULE.CYAN, output)


if __name__ == "__main__":
    unittest.main()
