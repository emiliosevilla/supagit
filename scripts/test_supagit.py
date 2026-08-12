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
        with patch(
            "builtins.input", return_value="release message"
        ) as mocked_input:
            pipeline.dev = "main"
            message = pipeline._commit_message()

        self.assertEqual(message, "release message")
        self.assertEqual(mocked_input.call_count, 1)
        prompt = mocked_input.call_args.args[0]
        self.assertTrue(prompt.startswith(MODULE.Pipeline.GREEN))
        self.assertTrue(prompt.endswith(MODULE.Pipeline.RESET))
        self.assertIn("Commit message for main: ", prompt)
        self.assertNotIn("Continue?", prompt)

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
        with patch("builtins.print") as mocked_print, patch("builtins.input", return_value="") as mocked_input:
            pipeline.explain("Tutor text")
        mocked_print.assert_called_once_with(
            f"{MODULE.CYAN}Tutor text{MODULE.RESET}"
        )
        prompt = mocked_input.call_args.args[0]
        self.assertTrue(prompt.startswith(MODULE.Pipeline.GREEN))
        self.assertIn("Continue?", prompt)
        self.assertIn("[Y/n]", prompt)

    def test_explain_skips_confirm_under_yes(self) -> None:
        pipeline = MODULE.Pipeline.__new__(MODULE.Pipeline)
        pipeline.options = MODULE.Options(False, True, None, None, "always")
        with patch("builtins.print") as mocked_print, patch("builtins.input") as mocked_input:
            pipeline.explain("Tutor text")
        mocked_print.assert_called_once()
        mocked_input.assert_not_called()

    def test_tutor_prompt_skips_continue_before_answer(self) -> None:
        pipeline = MODULE.Pipeline.__new__(MODULE.Pipeline)
        pipeline.options = MODULE.Options(False, False, None, None, "always")
        with patch("builtins.print") as mocked_print, patch(
            "builtins.input", return_value="none"
        ) as mocked_input:
            answer = pipeline.tutor_prompt("Pick branches.", "Integrate: ")
        self.assertEqual(answer, "none")
        mocked_print.assert_called_once_with(
            f"{MODULE.CYAN}Pick branches.{MODULE.RESET}"
        )
        self.assertEqual(mocked_input.call_count, 1)
        prompt = mocked_input.call_args.args[0]
        self.assertTrue(prompt.startswith(MODULE.Pipeline.GREEN))
        self.assertIn("Integrate:", prompt)
        self.assertNotIn("Continue?", prompt)

    def test_init_tutor_prompt_skips_continue_before_answer(self) -> None:
        with patch("builtins.print") as mocked_print, patch(
            "builtins.input", return_value="supabase"
        ) as mocked_input:
            answer = MODULE.init_tutor_prompt(
                "Choose backend.", "Backend: ", "always"
            )
        self.assertEqual(answer, "supabase")
        mocked_print.assert_called_once()
        self.assertEqual(mocked_input.call_count, 1)
        self.assertIn("Backend:", mocked_input.call_args.args[0])
        self.assertNotIn("Continue?", mocked_input.call_args.args[0])

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
        self.assertEqual(mocked_input.call_count, 1)

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
        # Routine confirms are skipped under --dry-run.
        mocked_input.assert_not_called()

    def test_confirm_waits_under_dry_run_when_forced(self) -> None:
        pipeline = MODULE.Pipeline.__new__(MODULE.Pipeline)
        pipeline.options = MODULE.Options(True, False, None, None, "always")
        with patch("builtins.input", return_value="") as mocked_input:
            pipeline.confirm("Run these steps?", force=True)
        prompt = mocked_input.call_args.args[0]
        self.assertIn("Run these steps?", prompt)
        self.assertIn("[Y/n]", prompt)

    def test_explain_skips_continue_under_dry_run(self) -> None:
        pipeline = MODULE.Pipeline.__new__(MODULE.Pipeline)
        pipeline.options = MODULE.Options(True, False, None, None, "always")
        with patch("builtins.print") as mocked_print, patch("builtins.input") as mocked_input:
            pipeline.explain("Tutor text")
        mocked_print.assert_called_once()
        mocked_input.assert_not_called()

    def test_explain_force_confirm_waits_under_dry_run(self) -> None:
        pipeline = MODULE.Pipeline.__new__(MODULE.Pipeline)
        pipeline.options = MODULE.Options(True, False, None, None, "always")
        with patch("builtins.print"), patch("builtins.input", return_value="") as mocked_input:
            pipeline.explain("Plan text", force_confirm=True)
        prompt = mocked_input.call_args.args[0]
        self.assertIn("Continue?", prompt)

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
        en_keys = set(MODULE.supagit_i18n._MESSAGES["en"])
        es_keys = set(MODULE.supagit_i18n._MESSAGES["es"])
        self.assertEqual(en_keys, es_keys)

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
                pipeline_order="main",
            )
            pipeline.root = Path(tmp)
            with patch("builtins.print"):
                pipeline._auto_create_config(path)
            self.assertTrue(path.is_file())
            data = path.read_text(encoding="utf-8")
            self.assertIn('"provider": "none"', data)
            self.assertIn('"main"', data)

    def test_auto_create_config_interactive_asks_branches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".supagit.json"
            pipeline = MODULE.Pipeline.__new__(MODULE.Pipeline)
            pipeline.options = MODULE.Options(
                dry_run=False,
                yes=False,
                config_path=path,
                message=None,
                color="never",
                backend="none",
            )
            pipeline.root = Path(tmp)

            def git(*args, **kwargs):
                if args[:2] == ("branch", "--show-current"):
                    return "topic\n"
                raise AssertionError(args)

            pipeline.git = git  # type: ignore[method-assign]
            pipeline.tutor_prompt = lambda explanation, prompt: "main"  # type: ignore[method-assign]
            with patch("builtins.print"), patch("sys.stdin.isatty", return_value=True):
                pipeline._auto_create_config(path)
            config = __import__("json").loads(path.read_text(encoding="utf-8"))
            self.assertEqual(config["branches"], ["main"])

    def test_auto_create_config_yes_without_pipeline_fails(self) -> None:
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
                with self.assertRaises(MODULE.ShipError) as ctx:
                    pipeline._auto_create_config(path)
            self.assertIn("--pipeline", str(ctx.exception))

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
                pipeline_order="main",
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

    def test_needs_update_false_when_ahead_only(self) -> None:
        update = MODULE.supagit_update

        def fake_run(cwd, *args):
            cmd = list(args)
            if cmd[:3] == ["git", "remote", "get-url"]:
                return "https://github.com/emiliosevilla/supagit.git"
            if cmd[:2] == ["git", "fetch"]:
                return ""
            if "rev-list" in cmd:
                return "0\t3"
            raise AssertionError(cmd)

        with patch.object(update, "_run", side_effect=fake_run):
            self.assertFalse(update.needs_update(Path("/tmp/source")))

    def test_needs_update_raises_when_diverged(self) -> None:
        MODULE.supagit_i18n.set_lang("en")
        update = MODULE.supagit_update

        def fake_run(cwd, *args):
            cmd = list(args)
            if cmd[:3] == ["git", "remote", "get-url"]:
                return "https://github.com/emiliosevilla/supagit.git"
            if cmd[:2] == ["git", "fetch"]:
                return ""
            if "rev-list" in cmd:
                return "1\t1"
            raise AssertionError(cmd)

        with patch.object(update, "_run", side_effect=fake_run):
            with self.assertRaises(update.UpdateError) as ctx:
                update.needs_update(Path("/tmp/source"))
        text = str(ctx.exception)
        self.assertIn("diverged", text.lower())
        self.assertIn("git fetch", text)
        self.assertIn("origin/main...HEAD", text)

    def test_pull_and_reinstall_refuses_diverged(self) -> None:
        MODULE.supagit_i18n.set_lang("en")
        update = MODULE.supagit_update

        def fake_run(cwd, *args):
            cmd = list(args)
            if cmd[:3] == ["git", "remote", "get-url"]:
                return "https://github.com/emiliosevilla/supagit.git"
            if cmd[:2] == ["git", "fetch"]:
                return ""
            if "rev-list" in cmd:
                return "2\t1"
            if cmd[:2] == ["git", "pull"]:
                raise AssertionError("must not pull when diverged")
            raise AssertionError(cmd)

        with patch.object(update, "_run", side_effect=fake_run):
            with self.assertRaises(update.UpdateError) as ctx:
                update.pull_and_reinstall(Path("/tmp/source"))
        self.assertIn("diverged", str(ctx.exception).lower())
        self.assertNotIn("pull", str(ctx.exception).lower())

    def test_resolve_update_lang_from_argv_and_env(self) -> None:
        update = MODULE.supagit_update
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(update.resolve_update_lang(["--lang", "es"]), "es")
            self.assertEqual(update.resolve_update_lang(["--lang=EN"]), "en")
            self.assertEqual(update.resolve_update_lang([]), "en")
        with patch.dict(os.environ, {"SUPAGIT_LANG": "es"}, clear=True):
            self.assertEqual(update.resolve_update_lang([]), "es")
            self.assertEqual(update.resolve_update_lang(["--lang", "en"]), "en")

    def test_pull_and_reinstall_runs_installer_with_lang(self) -> None:
        update = MODULE.supagit_update
        installer_calls: list[tuple] = []

        def fake_run(cwd, *args):
            cmd = list(args)
            if cmd[:3] == ["git", "remote", "get-url"]:
                return "https://github.com/emiliosevilla/supagit.git"
            if cmd[:2] == ["git", "fetch"]:
                return ""
            if "rev-list" in cmd:
                return "1\t0"
            if cmd[:2] == ["git", "pull"]:
                return ""
            raise AssertionError(cmd)

        def fake_installer(cwd, installer, lang):
            installer_calls.append((cwd, installer, lang))

        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)
            scripts = source / "scripts"
            scripts.mkdir()
            (scripts / "install-supagit-global.sh").write_text("#!/bin/sh\n", encoding="utf-8")
            with patch.object(update, "_run", side_effect=fake_run):
                with patch.object(update, "_run_installer", side_effect=fake_installer):
                    update.pull_and_reinstall(source, lang="es")
        self.assertEqual(
            installer_calls,
            [(source, source / "scripts" / "install-supagit-global.sh", "es")],
        )

    def test_needs_skip_update_env(self) -> None:
        with patch.dict(os.environ, {MODULE.supagit_update.SKIP_ENV: "1"}):
            self.assertTrue(MODULE.needs_skip_update())
        with patch.dict(os.environ, {MODULE.supagit_update.SKIP_ENV: "0"}):
            self.assertFalse(MODULE.needs_skip_update())

    def test_git_command_mutating_classifier(self) -> None:
        self.assertFalse(MODULE._git_command_is_mutating(("rev-list", "--count", "a...b")))
        self.assertFalse(MODULE._git_command_is_mutating(("rev-parse", "main")))
        self.assertFalse(MODULE._git_command_is_mutating(("remote", "get-url", "origin")))
        self.assertFalse(MODULE._git_command_is_mutating(("branch", "--show-current")))
        self.assertFalse(MODULE._git_command_is_mutating(("worktree", "list", "--porcelain")))
        self.assertTrue(MODULE._git_command_is_mutating(("fetch", "origin", "main")))
        self.assertTrue(MODULE._git_command_is_mutating(("merge", "--ff-only", "origin/main")))
        self.assertTrue(MODULE._git_command_is_mutating(("push", "origin", "main")))


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

    def test_busy_spinner_writes_green_working_line(self) -> None:
        from io import StringIO
        import time

        stream = StringIO()
        with MODULE.BusySpinner(enabled=True, stream=stream, delay_s=0.0, interval_s=0.05):
            time.sleep(0.12)
        output = stream.getvalue()
        self.assertIn("supagit is working", output)
        self.assertIn("Ctrl+C", output)
        self.assertIn(MODULE.GREEN, output)
        self.assertNotIn(MODULE.CYAN, output)

    def test_main_update_uses_spinner_while_reinstalling(self) -> None:
        source = Path("/tmp/supagit-source")
        with patch.object(MODULE, "needs_skip_update", return_value=False):
            with patch.object(MODULE.supagit_update, "source_root_from_marker", return_value=source):
                with patch.object(MODULE.supagit_update, "needs_update", return_value=True):
                    with patch.object(MODULE.supagit_update, "pull_and_reinstall") as pull:
                        with patch.object(MODULE, "BusySpinner") as spinner_cls:
                            spinner_cls.return_value.__enter__.return_value = None
                            spinner_cls.return_value.__exit__.return_value = None
                            with patch("os.execve", side_effect=SystemExit(0)) as execve:
                                with patch("builtins.print"):
                                    with self.assertRaises(SystemExit):
                                        MODULE.main(["--lang", "en", "--yes", "--no-sweep"])
        spinner_cls.assert_called()
        kwargs = spinner_cls.call_args.kwargs
        self.assertIn("enabled", kwargs)
        self.assertIsInstance(kwargs["enabled"], bool)
        self.assertEqual(kwargs.get("delay_s"), 0.0)
        pull.assert_called_once_with(source, lang="en")
        execve.assert_called_once()


class CheckoutFlexTests(unittest.TestCase):
    def setUp(self) -> None:
        MODULE.supagit_i18n.set_lang("en")

    def test_build_inventory_first_branch_override(self) -> None:
        layout = MODULE.supagit_layout.RepoLayout(
            launch_root=Path("/repo"),
            main_root=Path("/repo"),
            common_dir=Path("/repo/.git"),
            is_linked_launch=False,
        )
        calls: list[tuple] = []

        def git_runner(*args, **kwargs):
            calls.append(args)
            if args[:2] == ("worktree", "list"):
                return "worktree /repo\nbranch refs/heads/dev\n"
            if args[0] == "for-each-ref":
                return "dev\npre\nprod\nfeature/x\n"
            if args[:2] == ("rev-parse", "--verify"):
                return "ok"
            if args[:2] == ("rev-parse", "--abbrev-ref"):
                raise RuntimeError("no upstream")
            if args[:2] == ("rev-list", "--left-right"):
                return "0\t0"
            if args[:2] == ("status", "--porcelain"):
                return ""
            if args[:2] == ("merge-base", "--is-ancestor"):
                # contained against first_branch (args[3])
                needle, haystack = args[2], args[3]
                if needle == "feature/x" and haystack == "pre":
                    return ""
                raise RuntimeError("not ancestor")
            raise AssertionError(args)

        inv = MODULE.supagit_inventory.build_inventory(
            layout,
            ("dev", "pre", "prod"),
            "origin",
            git_runner=git_runner,
            first_branch="pre",
        )
        self.assertEqual(inv.first_branch, "pre")
        by_name = {b.name: b for b in inv.branches}
        self.assertTrue(by_name["dev"].is_pipeline)
        self.assertTrue(by_name["pre"].is_pipeline)
        self.assertTrue(by_name["prod"].is_pipeline)
        self.assertTrue(by_name["feature/x"].contained_in_first)

    def test_resolve_layout_not_git_repo(self) -> None:
        pipeline = MODULE.Pipeline.__new__(MODULE.Pipeline)

        def boom(cwd=None):
            raise MODULE.supagit_layout.LayoutError(
                "fatal: not a git repository (or any of the parent directories): .git"
            )

        with patch.object(MODULE.supagit_layout, "resolve_repo_layout", side_effect=boom):
            with self.assertRaises(MODULE.ShipError) as ctx:
                pipeline._resolve_layout()
        self.assertEqual(str(ctx.exception), MODULE.t("not_git_repo"))

    def test_resolve_layout_unsupported(self) -> None:
        pipeline = MODULE.Pipeline.__new__(MODULE.Pipeline)
        detail = "Unsupported git common dir layout: /bare.git"

        def boom(cwd=None):
            raise MODULE.supagit_layout.LayoutError(detail)

        with patch.object(MODULE.supagit_layout, "resolve_repo_layout", side_effect=boom):
            with self.assertRaises(MODULE.ShipError) as ctx:
                pipeline._resolve_layout()
        self.assertIn("Unsupported repository layout", str(ctx.exception))
        self.assertIn(detail, str(ctx.exception))

    def test_main_returns_1_for_not_git_repo(self) -> None:
        def boom(*args, **kwargs):
            raise MODULE.ShipError(MODULE.t("not_git_repo"))

        with patch.object(MODULE, "Pipeline", side_effect=boom):
            with patch.object(MODULE.supagit_i18n, "ensure_language", return_value="en"):
                with patch.object(MODULE, "print_welcome"):
                    with patch.object(MODULE, "needs_skip_update", return_value=True):
                        code = MODULE.main(["--lang", "en", "--no-sweep", "--yes"])
        self.assertEqual(code, 1)

    def test_confirm_skips_under_dry_run(self) -> None:
        pipeline = MODULE.Pipeline.__new__(MODULE.Pipeline)
        pipeline.options = MODULE.Options(True, False, None, None, "always")
        with patch("builtins.input") as mocked_input:
            pipeline.confirm("Continue?")
        mocked_input.assert_not_called()

    def test_main_welcome_continue_on_interactive_run(self) -> None:
        with patch.object(MODULE.supagit_i18n, "ensure_language", return_value="en"):
            with patch.object(MODULE, "print_welcome"):
                with patch.object(MODULE, "needs_skip_update", return_value=True):
                    with patch("builtins.input", return_value="") as mocked_input:
                        with patch.object(MODULE, "Pipeline") as pipeline_cls:
                            pipeline_cls.return_value.run.return_value = None
                            code = MODULE.main(["--lang", "en", "--no-sweep"])
        self.assertEqual(code, 0)
        self.assertTrue(mocked_input.called)
        prompt = mocked_input.call_args.args[0]
        self.assertIn("Continue?", prompt)

    def test_main_welcome_continue_skipped_under_dry_run(self) -> None:
        with patch.object(MODULE.supagit_i18n, "ensure_language", return_value="en"):
            with patch.object(MODULE, "print_welcome"):
                with patch.object(MODULE, "needs_skip_update", return_value=True):
                    with patch("builtins.input") as mocked_input:
                        with patch.object(MODULE, "Pipeline") as pipeline_cls:
                            pipeline_cls.return_value.run.return_value = None
                            code = MODULE.main(["--lang", "en", "--no-sweep", "--dry-run"])
        self.assertEqual(code, 0)
        # Dry-run must not gate on welcome Continue?; Pipeline.run may still prompt
        # for plan with force=True, but welcome itself must not call input here
        # because Pipeline is mocked.
        mocked_input.assert_not_called()

    def test_main_welcome_continue_skipped_under_yes(self) -> None:
        with patch.object(MODULE.supagit_i18n, "ensure_language", return_value="en"):
            with patch.object(MODULE, "print_welcome"):
                with patch.object(MODULE, "needs_skip_update", return_value=True):
                    with patch("builtins.input") as mocked_input:
                        with patch.object(MODULE, "Pipeline") as pipeline_cls:
                            pipeline_cls.return_value.run.return_value = None
                            code = MODULE.main(["--lang", "en", "--no-sweep", "--yes"])
        self.assertEqual(code, 0)
        mocked_input.assert_not_called()

    def test_legacy_branch_detection_names_config_path(self) -> None:
        pipeline = MODULE.Pipeline.__new__(MODULE.Pipeline)
        pipeline.config = {
            "branches": {"dev": None, "pre": None, "prod": None},
            "branch_aliases": {},
        }
        pipeline.config_path = Path("/proj/.supagit.json")
        pipeline.remote = "origin"
        pipeline.project_name = "proj"
        pipeline.DEFAULT_BRANCH_ALIASES = MODULE.Pipeline.DEFAULT_BRANCH_ALIASES

        def remote_branches():
            return ["main", "feature/x"]

        pipeline._remote_branches = remote_branches  # type: ignore[method-assign]
        with patch("builtins.print"):
            with self.assertRaises(MODULE.ShipError) as ctx:
                pipeline._resolve_branches()
        text = str(ctx.exception)
        self.assertIn(".supagit.json", text)
        self.assertIn("branches", text)
        self.assertIn("supagit init --branches", text)

    def test_contained_integrate_names_rederived_base(self) -> None:
        inv = MODULE.supagit_inventory.RepoInventory(
            MODULE.supagit_layout.RepoLayout(
                Path("/repo"), Path("/repo"), Path("/repo/.git"), False
            ),
            (),
            (
                MODULE.supagit_inventory.BranchInfo(
                    "pre", True, False, None, 0, 0, True, None, False
                ),
                MODULE.supagit_inventory.BranchInfo(
                    "old", False, False, None, 0, 0, True, None, False
                ),
            ),
            "pre",
        )
        with self.assertRaises(MODULE.supagit_menu.MenuError) as ctx:
            MODULE.supagit_menu.parse_integrate_line(inv, "old")
        self.assertIn("pre", str(ctx.exception))

    def test_run_branch_menu_explains_situation_preflight(self) -> None:
        pipeline = MODULE.Pipeline.__new__(MODULE.Pipeline)
        pipeline.options = MODULE.Options(
            dry_run=True,
            yes=True,
            config_path=None,
            message=None,
            color="never",
            no_sweep=False,
            integrate="none",
            pipeline_order="dev",
        )
        pipeline.branches = ("dev",)
        pipeline.remote = "origin"
        pipeline.root = Path("/repo")
        pipeline.original_branch = "dev"
        explained: list[str] = []

        def explain(message: str, *, ask_continue: bool = True, force_confirm: bool = False) -> None:
            explained.append(message)

        inv = MODULE.supagit_inventory.RepoInventory(
            MODULE.supagit_layout.RepoLayout(
                Path("/repo"), Path("/repo"), Path("/repo/.git"), False
            ),
            (),
            (
                MODULE.supagit_inventory.BranchInfo(
                    "dev", True, True, Path("/repo"), 0, 0, True, "origin/dev", False
                ),
            ),
            "dev",
        )

        def situation_git(*args, **kwargs):
            cmd = list(args)
            if cmd[:2] == ["rev-parse", "--verify"]:
                return "abc\n"
            if cmd[0] == "status":
                return ""
            if cmd[:2] == ["rev-parse", "--abbrev-ref"]:
                return "origin/dev\n"
            if cmd[:3] == ["rev-list", "--left-right", "--count"]:
                return "0\t0\n"
            raise AssertionError(cmd)

        pipeline.explain = explain  # type: ignore[method-assign]
        pipeline._situation_git = situation_git  # type: ignore[method-assign]
        pipeline._require_noninteractive_selection = lambda: None  # type: ignore[method-assign]
        selection = pipeline.run_branch_menu(inv)
        self.assertEqual(selection.pipeline, ("dev",))
        self.assertTrue(any("situation" in e.lower() or "pipeline" in e.lower() for e in explained))
        self.assertTrue(
            any("Before running the pipeline" in e or "situation" in e.lower() for e in explained)
        )

    def test_situation_preflight_raises_on_diverged(self) -> None:
        pipeline = MODULE.Pipeline.__new__(MODULE.Pipeline)
        pipeline.options = MODULE.Options(
            dry_run=True,
            yes=True,
            config_path=None,
            message=None,
            color="never",
            no_sweep=False,
            integrate="none",
            pipeline_order="dev",
        )
        pipeline.branches = ("dev",)
        pipeline.remote = "origin"
        pipeline.root = Path("/repo")
        pipeline.original_branch = "dev"
        pipeline.explain = lambda *a, **k: None  # type: ignore[method-assign]

        inv = MODULE.supagit_inventory.RepoInventory(
            MODULE.supagit_layout.RepoLayout(
                Path("/repo"), Path("/repo"), Path("/repo/.git"), False
            ),
            (),
            (
                MODULE.supagit_inventory.BranchInfo(
                    "dev", True, True, Path("/repo"), 0, 0, True, "origin/dev", False
                ),
            ),
            "dev",
        )

        def situation_git(*args, **kwargs):
            cmd = list(args)
            if cmd[:2] == ["rev-parse", "--verify"]:
                return "abc\n"
            if cmd[0] == "status":
                return ""
            if cmd[:2] == ["rev-parse", "--abbrev-ref"]:
                return "origin/dev\n"
            if cmd[:3] == ["rev-list", "--left-right", "--count"]:
                return "1\t1\n"
            raise AssertionError(cmd)

        pipeline._situation_git = situation_git  # type: ignore[method-assign]
        selection = MODULE.supagit_menu.MenuSelection(integrate=(), pipeline=("dev",))
        with self.assertRaises(MODULE.ShipError) as ctx:
            pipeline._explain_situation_preflight(selection, inv)
        self.assertIn("git fetch", str(ctx.exception))
        self.assertIn("origin/dev...dev", str(ctx.exception))

    def test_commit_and_publish_defers_when_clean_and_behind(self) -> None:
        MODULE.supagit_i18n.set_lang("en")
        pipeline = MODULE.Pipeline.__new__(MODULE.Pipeline)
        pipeline.options = MODULE.Options(
            dry_run=False,
            yes=True,
            config_path=None,
            message=None,
            color="never",
        )
        pipeline.dev = "dev"
        pipeline.remote = "origin"
        calls: list[tuple] = []
        printed: list[str] = []

        def git(*args, capture: bool = False, check: bool = True, mutating: bool = False, cwd=None):
            calls.append(args)
            if args[:2] == ("status", "--porcelain"):
                return ""
            if args[:3] == ("rev-list", "--left-right", "--count"):
                return "2\t0\n"
            raise AssertionError(args)

        pipeline.git = git  # type: ignore[method-assign]
        import builtins

        original = builtins.print
        builtins.print = printed.append  # type: ignore[assignment]
        try:
            pipeline.commit_and_publish_dev()
        finally:
            builtins.print = original  # type: ignore[assignment]

        self.assertFalse(any(c[0] == "push" for c in calls))
        self.assertTrue(any("behind" in p.lower() for p in printed if isinstance(p, str)))


if __name__ == "__main__":
    unittest.main()
