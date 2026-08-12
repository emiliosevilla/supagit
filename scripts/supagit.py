#!/usr/bin/env python3
"""Fail-closed promotion pipeline for supagit.

This script is intentionally independent from the repository's existing
deployment commands. A project may use Supabase or no backend at all.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import supagit_i18n
import supagit_inventory
import supagit_layout
import supagit_menu
import supagit_situation
import supagit_sweep
import supagit_update
from supagit_busy import BusySpinner, print_welcome
from supagit_i18n import t
from supagit_inventory import RepoInventory
from supagit_menu import MenuSelection
from supagit_situation import Situation

GREEN = "\033[32m"
RED = "\033[31m"
CYAN = "\033[36m"
RESET = "\033[0m"


def _git_command_is_mutating(args: Sequence[str]) -> bool:
    """Return True when a git subcommand may change the working tree or refs."""
    if not args:
        return False
    cmd = args[0]
    if cmd in {
        "rev-parse",
        "rev-list",
        "status",
        "diff",
        "log",
        "show",
        "ls-files",
        "ls-remote",
        "for-each-ref",
        "merge-base",
        "cat-file",
        "name-rev",
        "symbolic-ref",
    }:
        return False
    if cmd == "remote" and len(args) >= 2 and args[1] == "get-url":
        return False
    if cmd == "branch" and "--show-current" in args:
        return False
    if cmd == "worktree" and len(args) >= 2 and args[1] == "list":
        return False
    return True


class ShipError(RuntimeError):
    pass


class UserAborted(ShipError):
    pass


@dataclass
class Options:
    dry_run: bool
    yes: bool
    config_path: Path | None
    message: str | None
    color: str
    no_sweep: bool = False
    integrate: str | None = None
    pipeline_order: str | None = None
    cleanup: bool | None = None
    lang: str | None = None
    backend: str | None = None


@dataclass(frozen=True)
class BackendConfig:
    provider: str
    cli: str | None
    targets: dict[str, str]


def colour_enabled(mode: str, stream) -> bool:
    if mode == "always":
        return True
    if mode == "never" or "NO_COLOR" in os.environ:
        return False
    return bool(sys.stdin.isatty() and stream.isatty() and os.environ.get("TERM") != "dumb")


def colour_text(text: str, colour: str, enabled: bool) -> str:
    return f"{colour}{text}{RESET}" if enabled else text


_YES_ANSWERS = frozenset({"", "y", "yes", "s", "si", "sí"})


def confirm_default_yes(message: str, *, colour_on: bool) -> None:
    """Green [Y/n] gate; empty Enter accepts. Shared by Pipeline and welcome."""
    prompt = f"{message}{t('confirm_suffix')}"
    if colour_on:
        prompt = f"{GREEN}{prompt}{RESET}"
    answer = input(prompt).strip().lower()
    if answer in _YES_ANSWERS:
        return
    raise UserAborted(t("user_aborted"))


def init_project_config(
    backend: str,
    pre_ref_env: str,
    prod_ref_env: str,
    branch_names: Sequence[str] | None = None,
) -> dict:
    config = {
        "remote": "origin",
        "branches": list(branch_names) if branch_names else {"dev": None, "pre": None, "prod": None},
        "branch_aliases": {
            "dev": ["dev", "develop", "development", "desarrollo", "work"],
            "pre": ["pre", "preview", "staging", "stage", "qa", "beta"],
            "prod": ["prod", "production", "produccion", "real", "live"],
        },
        "checks": [],
    }
    if backend == "none":
        config["backend"] = {"provider": "none"}
    else:
        config["backend"] = {
            "provider": "supabase",
            "cli": "supabase",
            "auto_detect": True,
            "environments": {
                "pre": {"project_ref_env": pre_ref_env},
                "prod": {"project_ref_env": prod_ref_env},
            },
        }
    return config


def git_root_for_init() -> Path:
    completed = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != 0:
        details = completed.stderr.strip() or "not inside a Git repository"
        raise ShipError(f"Cannot initialize supagit here: {details}.")
    return Path(completed.stdout.strip()).resolve()


def init_prompt(message: str, color: str) -> str:
    prompt = colour_text(message, GREEN, colour_enabled(color, sys.stdout))
    return input(prompt).strip()


def init_tutor_prompt(
    explanation: str, message: str, color: str, *, yes: bool = False
) -> str:
    # Cyan context + green answer field; no Continue? — the prompt is the gate.
    # `yes` is accepted for call-site compatibility; --yes still uses flags for
    # non-interactive init rather than this helper's Continue (removed as redundant).
    _ = yes
    print(colour_text(explanation, CYAN, colour_enabled(color, sys.stdout)))
    return init_prompt(message, color)


def initialise_project(args: argparse.Namespace, options: Options) -> int:
    if args.config is not None:
        raise ShipError("--config cannot be used with supagit init.")
    if args.backend == "none" and (args.pre_ref_env or args.prod_ref_env):
        raise ShipError("--pre-ref-env and --prod-ref-env only apply to --backend supabase.")

    root = git_root_for_init()
    config_path = root / ".supagit.json"
    if config_path.exists():
        raise ShipError(
            f"Configuration already exists at {config_path}; refusing to overwrite it."
        )

    backend = args.backend
    if backend is None:
        if not sys.stdin.isatty():
            raise ShipError("supagit init requires --backend none|supabase when no TTY is available.")
        backend = (
            init_tutor_prompt(
                t("explain_backend"), t("backend_prompt"), options.color, yes=options.yes
            ).lower()
            or "none"
        )
    if backend not in {"none", "supabase"}:
        raise ShipError("Backend must be 'none' or 'supabase'.")

    pre_ref_env = args.pre_ref_env or "SUPABASE_PRE_PROJECT_REF"
    prod_ref_env = args.prod_ref_env or "SUPABASE_PROD_PROJECT_REF"
    if backend == "supabase" and args.pre_ref_env is None and sys.stdin.isatty():
        pre_ref_env = init_tutor_prompt(
            "Environment variable name holding the Supabase pre/staging project ref.",
            f"Variable for Supabase pre project ref ({pre_ref_env}): ",
            options.color,
            yes=options.yes,
        ) or pre_ref_env
    if backend == "supabase" and args.prod_ref_env is None and sys.stdin.isatty():
        prod_ref_env = init_tutor_prompt(
            "Environment variable name holding the Supabase production project ref.",
            f"Variable for Supabase prod project ref ({prod_ref_env}): ",
            options.color,
            yes=options.yes,
        ) or prod_ref_env

    branch_names = None
    if args.branches:
        branch_names = [branch.strip() for branch in args.branches.split(",") if branch.strip()]
        if not branch_names or len(set(branch_names)) != len(branch_names):
            raise ShipError("--branches must contain one or more unique comma-separated branch names.")
    config = init_project_config(backend, pre_ref_env, prod_ref_env, branch_names)
    rendered = json.dumps(config, indent=2, ensure_ascii=False) + "\n"
    if options.dry_run:
        print(f"DRY-RUN: would create {config_path}")
        print(rendered, end="")
        return 0

    try:
        with config_path.open("x", encoding="utf-8") as stream:
            stream.write(rendered)
    except FileExistsError as exc:
        raise ShipError(
            f"Configuration appeared at {config_path}; refusing to overwrite it."
        ) from exc
    print(colour_text(f"Created project configuration: {config_path}", GREEN, colour_enabled(options.color, sys.stdout)))
    return 0


class Pipeline:
    DEFAULT_BRANCH_ALIASES = {
        "dev": ("dev", "develop", "development", "desarrollo", "work"),
        "pre": ("pre", "preview", "staging", "stage", "qa", "beta"),
        "prod": ("prod", "production", "produccion", "real", "live"),
    }
    GREEN = GREEN
    RED = RED
    RESET = RESET

    def __init__(self, options: Options) -> None:
        self.options = options
        self.layout = self._resolve_layout()
        self.launch_root = self.layout.launch_root
        self.main_root = self.layout.main_root
        self.root = self.main_root
        self._branch_check_on_main = self.layout.is_linked_launch
        self.config = self._load_config()
        self.remote = self.config.get("remote", "origin")
        self.backend = self._resolve_backend()
        self.cli = self.backend.cli
        self.linked_ref: str | None = None
        # Measure the launch checkout (linked worktree or main), not always main_root.
        self.original_branch = self.git(
            "branch", "--show-current", capture=True, cwd=self.launch_root
        ).strip()
        self.project_name = self._project_name()
        self.branches = self._resolve_branches()
        self.dev = self.branches[0]
        self.pre = self.branches[1] if len(self.branches) > 1 else None
        self.prod = self.branches[-1]

    def _resolve_layout(self) -> supagit_layout.RepoLayout:
        try:
            return supagit_layout.resolve_repo_layout()
        except supagit_layout.LayoutError as exc:
            message = str(exc)
            if "not a git repository" in message.lower():
                raise ShipError(t("not_git_repo")) from exc
            raise ShipError(t("layout_unsupported", detail=exc)) from exc

    def _load_config(self) -> dict:
        path = self.options.config_path
        if path is None:
            path = self.root / ".supagit.json"
        elif not path.is_absolute():
            path = (Path.cwd() / path).resolve()
        if not path.is_file():
            self._auto_create_config(path)
        try:
            config = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ShipError(f"Invalid configuration: {path}: {exc}") from exc
        self._validate_config(config, path)
        self.config_path = path
        return config

    def _auto_create_config(self, path: Path) -> None:
        print(t("missing_config_creating", path=path))
        backend = self.options.backend
        if backend is None:
            if self.options.yes or not sys.stdin.isatty():
                raise ShipError(t("missing_config_need_backend", path=path))
            backend = (
                self.tutor_prompt(t("explain_backend"), t("backend_prompt")) or "none"
            ).lower()
        if backend not in {"none", "supabase"}:
            raise ShipError(t("backend_invalid"))
        branch_names = None
        if self.options.pipeline_order:
            branch_names = [
                part.strip()
                for part in self.options.pipeline_order.split(",")
                if part.strip()
            ]
        if not branch_names:
            if self.options.yes or not sys.stdin.isatty():
                raise ShipError(t("missing_config_need_branches", path=path))
            live = self.git("branch", "--show-current", capture=True).strip() or "main"
            answer = self.tutor_prompt(
                t("explain_branches_init"),
                t("branches_prompt", default=live),
            )
            branch_names = [
                part.strip() for part in answer.split(",") if part.strip()
            ] or [live]
        config = init_project_config(
            backend,
            "SUPABASE_PRE_PROJECT_REF",
            "SUPABASE_PROD_PROJECT_REF",
            branch_names,
        )
        rendered = json.dumps(config, indent=2, ensure_ascii=False) + "\n"
        try:
            with path.open("x", encoding="utf-8") as stream:
                stream.write(rendered)
        except FileExistsError as exc:
            raise ShipError(
                f"Configuration appeared at {path}; refusing to overwrite it."
            ) from exc
        print(
            colour_text(
                t("created_config", path=path),
                GREEN,
                colour_enabled(self.options.color, sys.stdout),
            )
        )

    @staticmethod
    def _validate_config(config: dict, path: Path) -> None:
        if not isinstance(config, dict):
            raise ShipError(f"Invalid configuration in {path}: the root must be a JSON object.")
        try:
            branches = config["branches"]
        except (KeyError, TypeError) as exc:
            raise ShipError(
                f"Incomplete configuration in {path}: branches are required."
            ) from exc
        if isinstance(branches, dict):
            if set(branches) != {"dev", "pre", "prod"}:
                raise ShipError("Legacy branches must define exactly dev, pre, and prod.")
            if any(value is not None and (not isinstance(value, str) or not value.strip()) for value in branches.values()):
                raise ShipError("Each legacy branch must be a non-empty string or null for auto-detection.")
        elif isinstance(branches, list):
            if not branches or any(not isinstance(value, str) or not value.strip() for value in branches):
                raise ShipError("branches must be a non-empty list of branch names.")
            if len(set(branches)) != len(branches):
                raise ShipError("branches must not contain duplicate branch names.")
        else:
            raise ShipError("branches must be either a legacy role object or an ordered list of names.")

        backend = config.get("backend")
        if backend is None:
            supabase = config.get("supabase")
            try:
                refs = [supabase["pruebas_project_ref"], supabase["prod_project_ref"]]
            except (KeyError, TypeError) as exc:
                raise ShipError(
                    f"Incomplete configuration in {path}: add backend.provider or the legacy "
                    "supabase.pruebas_project_ref/prod_project_ref."
                ) from exc
            if not all(isinstance(value, str) and value.strip() for value in refs):
                raise ShipError("Both legacy Supabase project refs must be non-empty strings.")
            if refs[0] == refs[1]:
                raise ShipError("The testing and production project refs must be different.")
            return

        if not isinstance(backend, dict):
            raise ShipError("backend must be an object.")
        provider = backend.get("provider")
        if provider not in {"none", "supabase"}:
            raise ShipError("backend.provider must be 'none' or 'supabase'.")
        if "auto_detect" in backend and not isinstance(backend["auto_detect"], bool):
            raise ShipError("backend.auto_detect must be a boolean.")
        if provider == "none":
            return

        environments = backend.get("environments", {})
        if not isinstance(environments, dict):
            raise ShipError("backend.environments must be an object.")
        for role, target in environments.items():
            if not isinstance(role, str) or not role.strip():
                raise ShipError("backend.environments keys must be non-empty strings.")
            if not isinstance(target, dict):
                raise ShipError(f"backend.environments.{role} must be an object.")
            for key in ("project_ref", "project_ref_env", "url_env"):
                if key in target and (not isinstance(target[key], str) or not target[key].strip()):
                    raise ShipError(f"backend.environments.{role}.{key} must be a non-empty string.")

    def _resolve_backend(self) -> BackendConfig:
        return self._resolve_backend_from_config(self.config)

    def _resolve_backend_from_config(self, config: dict) -> BackendConfig:
        backend = config.get("backend")
        if backend is None:
            supabase = config["supabase"]
            return BackendConfig(
                provider="supabase",
                cli=supabase.get("cli", "supabase"),
                targets={
                    "pre": supabase["pruebas_project_ref"],
                    "prod": supabase["prod_project_ref"],
                },
            )

        provider = backend["provider"]
        if provider == "none":
            print("Backend: none; database migration checkpoints will be skipped.")
            return BackendConfig(provider="none", cli=None, targets={})

        environments = backend.get("environments", {})
        auto_detect = backend.get("auto_detect", True)
        targets = {
            role: self._resolve_supabase_target(role, target, auto_detect)
            for role, target in environments.items()
        }
        if targets:
            print("Backend: Supabase; targets resolved for " + ", ".join(targets))
        else:
            print("Backend: Supabase; no branch-specific migration targets configured.")
        return BackendConfig(
            provider="supabase",
            cli=backend.get("cli", "supabase"),
            targets=targets,
        )

    @staticmethod
    def _project_ref_from_value(value: str) -> str | None:
        text = value.strip().strip("'\"")
        if re.fullmatch(r"[a-z0-9][a-z0-9-]{4,62}", text):
            return text
        match = re.match(r"https?://([a-z0-9][a-z0-9-]{4,62})\.supabase\.co(?:/|$)", text)
        return match.group(1) if match else None

    @staticmethod
    def _parse_env_file(path: Path) -> dict[str, str]:
        values: dict[str, str] = {}
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return values
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.startswith("export "):
                stripped = stripped[7:].lstrip()
            key, separator, value = stripped.partition("=")
            if not separator or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key.strip()):
                continue
            values[key.strip()] = value.strip().strip("'\"")
        return values

    def _environment_values(self) -> dict[str, str]:
        values: dict[str, str] = {}
        for path in sorted(self.root.glob(".env*")):
            if path.is_file():
                values.update(self._parse_env_file(path))
        values.update(os.environ)
        return values

    @staticmethod
    def _role_tokens(role: str) -> tuple[str, ...]:
        normalised = re.sub(r"[^a-z0-9]+", "-", role.lower()).strip("-")
        if normalised in {"pre", "pruebas", "test", "staging", "stage", "qa", "preview"}:
            return ("PRE", "PRUEBAS", "TEST", "STAGING", "STAGE", "QA", "PREVIEW")
        if normalised in {"prod", "production", "real", "live"}:
            return ("PROD", "PRODUCTION", "REAL", "LIVE")
        return (role.upper(),)

    @classmethod
    def _key_matches_role(cls, key: str, role: str) -> bool:
        normalised = re.sub(r"[^A-Z0-9]+", "_", key.upper())
        return any(re.search(rf"(?:^|_){re.escape(token)}(?:_|$)", normalised) for token in cls._role_tokens(role))

    @classmethod
    def _filename_matches_role(cls, filename: str, role: str) -> bool:
        normalised = re.sub(r"[^A-Z0-9]+", "_", filename.upper())
        return any(token in normalised.split("_") for token in cls._role_tokens(role))

    def _detect_supabase_project_ref(self, role: str) -> str:
        candidates: dict[str, set[str]] = {}
        values = self._environment_values()
        for key, value in values.items():
            upper_key = key.upper()
            if "SUPABASE" not in upper_key or not ("URL" in upper_key or "REF" in upper_key or "PROJECT" in upper_key):
                continue
            if not self._key_matches_role(key, role):
                continue
            ref = self._project_ref_from_value(value)
            if ref:
                candidates.setdefault(ref, set()).add(f"environment variable {key}")

        for path in sorted(self.root.glob(".env*")):
            if not path.is_file() or not self._filename_matches_role(path.name, role):
                continue
            for key, value in self._parse_env_file(path).items():
                upper_key = key.upper()
                if "SUPABASE" not in upper_key or not ("URL" in upper_key or "REF" in upper_key or "PROJECT" in upper_key):
                    continue
                ref = self._project_ref_from_value(value)
                if ref:
                    candidates.setdefault(ref, set()).add(f"{path.name}:{key}")

        if len(candidates) == 1:
            return next(iter(candidates))
        if not candidates:
            raise ShipError(
                f"Could not detect the Supabase project ref for {role}. Configure "
                f"backend.environments.{role}.project_ref, project_ref_env, or url_env, "
                "or expose a role-specific Supabase variable."
            )
        details = "; ".join(f"{ref} ({', '.join(sources)})" for ref, sources in sorted(candidates.items()))
        raise ShipError(f"Ambiguous Supabase project ref detection for {role}: {details}.")

    def _resolve_supabase_target(self, role: str, target: dict, auto_detect: bool) -> str:
        if target.get("project_ref"):
            ref = self._project_ref_from_value(target["project_ref"])
            if ref:
                return ref
            raise ShipError(f"Invalid Supabase project ref for {role}: {target['project_ref']!r}.")

        values = self._environment_values()
        for key in ("project_ref_env", "url_env"):
            env_name = target.get(key)
            if not env_name:
                continue
            raw_value = values.get(env_name)
            if not raw_value:
                raise ShipError(f"Environment variable {env_name} for Supabase {role} is not set.")
            ref = self._project_ref_from_value(raw_value)
            if ref:
                return ref
            raise ShipError(f"Environment variable {env_name} does not contain a valid Supabase ref or URL.")

        if not auto_detect:
            raise ShipError(
                f"Supabase project ref for {role} is not configured and backend.auto_detect is false."
            )
        return self._detect_supabase_project_ref(role)

    def _project_name(self) -> str:
        remote_url = self.git("remote", "get-url", self.remote, capture=True).strip()
        cleaned = remote_url.removesuffix(".git").rstrip("/")
        if "://" in cleaned:
            path = cleaned.split("://", 1)[1].split("/", 1)[-1]
        elif ":" in cleaned and "@" in cleaned.split(":", 1)[0]:
            path = cleaned.split(":", 1)[1]
        else:
            path = cleaned.rsplit("/", 1)[-1]
        return path or self.root.name

    def _remote_branches(self) -> tuple[str, ...]:
        output = self.git("ls-remote", "--heads", self.remote, capture=True)
        branches = []
        for line in output.splitlines():
            if "refs/heads/" in line:
                branches.append(line.split("refs/heads/", 1)[1].strip())
        return tuple(sorted(set(branches)))

    @staticmethod
    def _normalise_branch(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")

    @classmethod
    def rank_branch_candidates(cls, role: str, branches: Sequence[str], aliases: Sequence[str] | None = None) -> list[tuple[int, str]]:
        names = tuple(aliases or cls.DEFAULT_BRANCH_ALIASES[role])
        ranked: list[tuple[int, str]] = []
        for branch in branches:
            normalised = cls._normalise_branch(branch)
            score = 0
            for alias in names:
                alias_normalised = cls._normalise_branch(alias)
                if normalised == alias_normalised:
                    score = max(score, 100)
                elif normalised.endswith(f"-{alias_normalised}") or normalised.startswith(f"{alias_normalised}-"):
                    score = max(score, 70)
            if score:
                ranked.append((score, branch))
        return sorted(ranked, key=lambda item: (-item[0], item[1]))

    def _resolve_branches(self) -> tuple[str, ...]:
        configured = self.config["branches"]
        remote_branches = self._remote_branches()
        if isinstance(configured, list):
            missing = [branch for branch in configured if branch not in remote_branches]
            if missing:
                raise ShipError(
                    "Configured branches do not exist on "
                    f"{self.remote}: "
                    + ", ".join(missing)
                    + ". Available remote branches: "
                    + ", ".join(remote_branches)
                    + "."
                )
            resolved = tuple(configured)
            print(f"Detected project: {self.project_name}; branches: {' → '.join(resolved)}")
            return resolved

        aliases_config = self.config.get("branch_aliases", {})
        resolved: dict[str, str] = {}
        for role in ("dev", "pre", "prod"):
            explicit = configured.get(role)
            if explicit:
                if explicit not in remote_branches:
                    raise ShipError(f"Configured {role} branch {explicit!r} does not exist on {self.remote}.")
                resolved[role] = explicit
                continue
            aliases = aliases_config.get(role, self.DEFAULT_BRANCH_ALIASES[role])
            ranked = self.rank_branch_candidates(role, remote_branches, aliases)
            if not ranked:
                raise ShipError(
                    t(
                        "error_branch_detection",
                        role=role,
                        available=", ".join(remote_branches),
                        path=self.config_path,
                    )
                )
            top_score = ranked[0][0]
            top = [branch for score, branch in ranked if score == top_score]
            if len(top) != 1:
                raise ShipError(
                    t(
                        "error_branch_ambiguous",
                        role=role,
                        candidates=", ".join(top),
                        path=self.config_path,
                    )
                )
            resolved[role] = top[0]
        print(
            f"Detected project: {self.project_name}; "
            f"branches: {resolved['dev']} → {resolved['pre']} → {resolved['prod']}"
        )
        return resolved["dev"], resolved["pre"], resolved["prod"]

    def _colour_enabled(self) -> bool:
        return colour_enabled(self.options.color, sys.stdout)

    def status(self, message: str, colour: str) -> None:
        print(colour_text(message, colour, self._colour_enabled()))

    def warning(self, message: str) -> None:
        print(
            colour_text(
                t("warning", detail=message),
                self.RED,
                colour_enabled(self.options.color, sys.stderr),
            ),
            file=sys.stderr,
        )

    def run_raw(
        self,
        command: Sequence[str],
        *,
        capture: bool = False,
        check: bool = True,
        cwd: Path | None = None,
        mutating: bool = False,
    ) -> str:
        rendered = shlex.join(str(part) for part in command)
        print(f"$ {rendered}")
        if self.options.dry_run and mutating:
            return ""
        spinner_enabled = (
            colour_enabled(self.options.color, sys.stderr)
            and sys.stderr.isatty()
        )
        with BusySpinner(enabled=spinner_enabled):
            completed = subprocess.run(
                [str(part) for part in command],
                cwd=str(cwd or getattr(self, "root", Path.cwd())),
                text=True,
                stdout=subprocess.PIPE if capture else None,
                stderr=subprocess.PIPE,
            )
        if capture and completed.stdout:
            print(completed.stdout, end="")
        if completed.returncode != 0 and check:
            details = completed.stderr.strip() if completed.stderr else "no error output"
            if completed.stderr:
                print(
                    colour_text(
                        completed.stderr.rstrip("\n"),
                        RED,
                        colour_enabled(self.options.color, sys.stderr),
                    ),
                    file=sys.stderr,
                )
            raise ShipError(f"Command failed: {rendered}: {details}")
        if not capture and completed.stderr:
            print(completed.stderr, end="", file=sys.stderr)
        return completed.stdout if capture else ""

    def git(
        self,
        *args: str,
        capture: bool = False,
        check: bool = True,
        mutating: bool = False,
        cwd: Path | None = None,
    ) -> str:
        return self.run_raw(
            ["git", *args],
            capture=capture,
            check=check,
            mutating=mutating,
            cwd=cwd,
        )

    def confirm(self, message: str, *, force: bool = False) -> None:
        # --yes never prompts. --dry-run skips routine continues, but force=True
        # keeps the execution-plan gate so the user can still review the plan.
        if self.options.yes:
            return
        if self.options.dry_run and not force:
            return
        confirm_default_yes(message, colour_on=self._colour_enabled())

    def ask_yes_no(self, message: str, *, default_yes: bool = True) -> bool:
        """Optional yes/no that does not abort the run on 'no'."""
        if self.options.yes:
            return default_yes
        if self.options.dry_run:
            return False
        prompt = f"{message}{t('confirm_suffix')}"
        if self._colour_enabled():
            prompt = f"{self.GREEN}{prompt}{self.RESET}"
        answer = input(prompt).strip().lower()
        if answer in _YES_ANSWERS:
            return True
        if answer in {"n", "no"}:
            return False
        return default_yes

    def explain(
        self, message: str, *, ask_continue: bool = True, force_confirm: bool = False
    ) -> None:
        self._print_cyan(message)
        if ask_continue:
            self.confirm(t("confirm_continue"), force=force_confirm)

    def _print_cyan(self, message: str) -> None:
        print(colour_text(message, CYAN, self._colour_enabled()))

    def tutor_prompt(self, explanation: str, prompt_message: str) -> str:
        # Cyan context + green answer field; no Continue? — the prompt is the gate.
        self.explain(explanation, ask_continue=False)
        return self.prompt(prompt_message)

    def tutor_confirm(self, explanation: str, confirm_message: str) -> None:
        if self.options.yes:
            return
        # Cyan block + one green Sí/No (action-specific text; default yes).
        self.explain(explanation, ask_continue=False)
        self.confirm(confirm_message)

    def prompt(self, message: str) -> str:
        if self._colour_enabled():
            message = f"{self.GREEN}{message}{self.RESET}"
        return input(message).strip()

    def announce_launch_checkout(self) -> None:
        current = self.git(
            "branch", "--show-current", capture=True, cwd=self.launch_root
        ).strip()
        if not current:
            sha = self.git(
                "rev-parse", "--short", "HEAD", capture=True, cwd=self.launch_root
            ).strip()
            current = t("detached_label", sha=sha or "HEAD")
        self.explain(t("startup_any_branch", branch=current))

    def maybe_return_to_start_branch(self) -> None:
        if self.options.dry_run:
            return
        start = (self.original_branch or "").strip()
        if not start or start == self.dev:
            return
        if self.options.yes:
            self.explain(
                t("return_skipped_yes", pipeline=self.dev, branch=start)
            )
            return
        self.explain(
            t("explain_return", pipeline=self.dev, branch=start),
            ask_continue=False,
        )
        if not self.ask_yes_no(t("confirm_return", branch=start), default_yes=True):
            return
        start_cwd = self._cwd_for_branch(start)
        if start_cwd.resolve() != self.root.resolve():
            # Start branch already lives in another worktree — nothing to switch here.
            self.status(t("return_done", branch=start), self.GREEN)
            return
        status = self.git("status", "--porcelain", capture=True, cwd=self.root)
        if status.strip():
            self.explain(
                t("return_skipped_dirty", pipeline=self.dev, branch=start)
            )
            return
        self.git("checkout", start, mutating=True, cwd=self.root)
        self.status(t("return_done", branch=start), self.GREEN)

    def preflight_repo(self) -> None:
        if self.layout.is_linked_launch:
            print(
                f"Launch worktree: {self.launch_root}; promotion checkout: {self.root}"
            )
        worktrees = self.git("worktree", "list", "--porcelain", capture=True)
        if worktrees.count("worktree ") > 1 and not self.layout.is_linked_launch:
            self.warning("registered worktrees exist, but the current checkout is the main repository.")
        print(f"Repository: {self.project_name}")
        self.git("remote", "get-url", self.remote)
        # Measure GitHub CLI health up front; refresh stale tokens before we
        # open or merge any PR, so the pipeline does not stop halfway.
        remote_url = self.git("remote", "get-url", self.remote, capture=True).strip()
        if "github.com" in remote_url.lower():
            gh = supagit_sweep.GhClient(
                self._gh_run_raw, dry_run=self.options.dry_run
            )
            try:
                gh.ensure_ready()
            except supagit_sweep.SweepError as exc:
                raise ShipError(str(exc)) from exc
        self.announce_launch_checkout()

    def validate_pipeline_head(self) -> None:
        self.git(
            "fetch",
            self.remote,
            f"refs/heads/{self.dev}:refs/remotes/{self.remote}/{self.dev}",
            mutating=True,
        )
        if not self.options.dry_run:
            ahead_behind = self.git(
                "rev-list",
                "--left-right",
                "--count",
                f"{self.remote}/{self.dev}...{self.dev}",
                capture=True,
            ).strip()
            remote_only, local_only = (int(part) for part in ahead_behind.split())
            if remote_only and local_only:
                raise ShipError(
                    t(
                        "error_diverged_head",
                        branch=self.dev,
                        remote=self.remote,
                        counts=ahead_behind,
                    )
                )
            elif remote_only:
                print(
                    t(
                        "head_behind_note",
                        branch=self.dev,
                        remote=self.remote,
                        counts=ahead_behind,
                    )
                )
            elif local_only:
                print(
                    t(
                        "head_ahead_note",
                        branch=self.dev,
                        remote=self.remote,
                        counts=ahead_behind,
                    )
                )

    @staticmethod
    def _is_sensitive_path(path: str) -> bool:
        normalized = path.replace("\\", "/").lower()
        name = normalized.rsplit("/", 1)[-1]
        if name in {".env", "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519"}:
            return True
        if name.startswith(".env.") and name not in {".env.example", ".env.sample", ".env.template"}:
            return True
        return name.endswith((".pem", ".key", ".p12", ".pfx"))

    def _reject_sensitive_paths(self, paths: Sequence[str]) -> None:
        sensitive = sorted({path for path in paths if self._is_sensitive_path(path)})
        if sensitive:
            raise ShipError(
                "Potential secrets detected among the changes: "
                + ", ".join(sensitive)
                + ". Remove them from the commit and run the pipeline again."
            )

    def _commit_message(self, *, branch: str | None = None) -> str:
        label = branch or self.dev
        if self.options.message and self.options.message.strip():
            return self.options.message.strip()
        if self.options.dry_run:
            return "<commit-message-required>"
        if self.options.yes:
            raise ShipError(t("commit_message_yes", branch=label))
        message = self.tutor_prompt(
            t("explain_commit_message"),
            t("commit_message_prompt", branch=label),
        )
        if not message:
            raise ShipError(t("commit_message_empty"))
        return message

    def _assert_dev_checkout(self) -> None:
        if self.options.dry_run:
            return
        current = self.git("branch", "--show-current", capture=True).strip()
        if current != self.dev:
            raise ShipError(
                f"The checkout is no longer on {self.dev}: it is on {current or '(detached HEAD)'}."
            )

    def _assert_dev_synced(self) -> None:
        self._assert_dev_checkout()
        if self.options.dry_run:
            return
        ahead_behind = self.git(
            "rev-list",
            "--left-right",
            "--count",
            f"{self.remote}/{self.dev}...{self.dev}",
            capture=True,
        ).strip()
        remote_only, local_only = (int(part) for part in ahead_behind.split())
        if remote_only or local_only:
            raise ShipError(
                f"After publishing {self.dev}, synchronization with {self.remote}/{self.dev} is not "
                f"zero-zero ({ahead_behind}). The pipeline is stopping."
            )

    def commit_and_publish_dev(self, *, integrate: Sequence[str] = ()) -> None:
        print(f"\n=== PUBLISH LOCAL CHANGES TO {self.dev} ===")
        status = self.git("status", "--porcelain", capture=True)
        status_paths = [line[3:] for line in status.splitlines() if len(line) >= 4]
        self._reject_sensitive_paths(status_paths)

        if status.strip() and integrate:
            raise ShipError(
                t(
                    "error_dirty_pipeline_with_integrate",
                    pipeline=self.dev,
                    features=", ".join(integrate),
                )
            )

        if status.strip():
            message = self._commit_message()
            self.tutor_confirm(
                t("explain_commit_publish", branch=self.dev, remote=self.remote),
                t("confirm_commit_publish", branch=self.dev, remote=self.remote),
            )
            self.git("add", "-A", mutating=True)
            staged = self.git("diff", "--cached", "--name-only", capture=True)
            self._reject_sensitive_paths(staged.splitlines())
            self.git("diff", "--cached", "--check")
            self.git("commit", "-m", message, mutating=True)
            relation = self.git(
                "rev-list",
                "--left-right",
                "--count",
                f"{self.remote}/{self.dev}...{self.dev}",
                capture=True,
            ).strip()
            remote_only, local_only = (int(part) for part in relation.split())
            if remote_only > 0:
                print(
                    t(
                        "publish_skip_push_behind",
                        branch=self.dev,
                        remote=self.remote,
                    )
                )
                return
        else:
            relation = self.git(
                "rev-list",
                "--left-right",
                "--count",
                f"{self.remote}/{self.dev}...{self.dev}",
                capture=True,
            ).strip()
            remote_only, local_only = (int(part) for part in relation.split())
            if remote_only == 0 and local_only == 0:
                print(
                    f"Local {self.dev} is already synchronized with "
                    f"{self.remote}/{self.dev}; there is no commit to create."
                )
                self._assert_dev_synced()
                return
            if remote_only > 0 and local_only == 0:
                print(
                    t(
                        "publish_defer_behind",
                        branch=self.dev,
                        remote=self.remote,
                    )
                )
                return
            if remote_only > 0 and local_only > 0:
                raise ShipError(
                    f"Local {self.dev} has diverged from {self.remote}/{self.dev} "
                    f"({relation}). Reconcile manually before publishing."
                )
            print(f"Local {self.dev} contains unpublished commits ({relation}).")
            self.tutor_confirm(
                t("explain_publish_existing", branch=self.dev, remote=self.remote),
                t("confirm_publish_existing", branch=self.dev, remote=self.remote),
            )

        self.git("push", self.remote, self.dev, mutating=True)
        self._assert_dev_synced()

    def validate_clean_after_checks(self) -> None:
        if self.options.dry_run:
            print("DRY-RUN: a clean tree is not required because checks were not run.")
            return
        status = self.git("status", "--porcelain", capture=True)
        if status.strip():
            raise ShipError(
                "Checks left changes in the tree. The pipeline stops before migrating any database."
            )

    def run_checks(self) -> None:
        checks = self.config.get("checks", [])
        for check in checks:
            if not isinstance(check, list) or not check or not all(isinstance(item, str) for item in check):
                raise ShipError("Each check must be a list of arguments, for example [\"npm\", \"run\", \"lint\"].")
            self.run_raw(check, mutating=True)

    def link_supabase(self, project_ref: str) -> None:
        self.run_raw([self.cli, "link", "--project-ref", project_ref, "--yes"], mutating=True)
        marker = self.root / "supabase" / ".temp" / "project-ref"
        if not self.options.dry_run:
            actual = marker.read_text(encoding="utf-8").strip() if marker.is_file() else ""
            if actual != project_ref:
                raise ShipError(f"Supabase is linked to {actual or '(unknown)'}, not to {project_ref}.")
        self.linked_ref = project_ref

    def unlink_supabase(self) -> None:
        if self.linked_ref is None:
            return
        self.run_raw([self.cli, "unlink", "--yes"], mutating=True)
        self.linked_ref = None

    def database_checkpoint(self, label: str, project_ref: str) -> None:
        print(f"\n=== DATABASE {label}: {project_ref} ===")
        self.link_supabase(project_ref)
        try:
            dry_output = self.run_raw(
                [self.cli, "db", "push", "--dry-run", "--linked", "--include-all"],
                capture=True,
                mutating=True,
            )
            if not self.options.dry_run and "Remote database is up to date" not in dry_output:
                self.tutor_confirm(
                    t("explain_migrate", label=label, ref=project_ref),
                    t("confirm_migrate", label=label, ref=project_ref),
                )
            self.run_raw(
                [self.cli, "db", "push", "--linked", "--yes", "--include-all"],
                mutating=True,
            )
            verify = self.run_raw(
                [self.cli, "db", "push", "--dry-run", "--linked", "--include-all"],
                capture=True,
                mutating=True,
            )
            if not self.options.dry_run and "Remote database is up to date" not in verify:
                raise ShipError(f"The post-migration check does not confirm that {label} is up to date.")
        finally:
            self.unlink_supabase()

    def fetch_branch(self, branch: str) -> None:
        self.git("fetch", self.remote, f"refs/heads/{branch}:refs/heads/{branch}", mutating=True)

    def promote(self, source: str, target: str) -> None:
        print(f"\n=== CODE {source} → {target} ===")
        remote_url = self.git(
            "remote", "get-url", self.remote, capture=True, cwd=self.root
        ).strip()
        gate: supagit_sweep.PromoteGate | None = None
        try:
            gate = supagit_sweep.inspect_promote_gate(
                lambda command, **_kwargs: self.run_raw(
                    list(command), capture=True, mutating=False
                ),
                remote_url,
                target,
            )
        except supagit_sweep.SweepError as exc:
            raise ShipError(str(exc)) from exc

        if gate is None:
            self.explain(
                t(
                    "explain_promote_direct",
                    source=source,
                    target=target,
                    detail=t("promote_gate_non_github"),
                ),
                ask_continue=False,
            )
            self.tutor_confirm(
                t("explain_promote", source=source, target=target),
                t("confirm_promote", source=source, target=target),
            )
            self._promote_direct(source, target)
            return

        mode_label = (
            t("promote_mode_pr")
            if gate.requires_pull_request
            else t("promote_mode_direct")
        )
        self.explain(
            t(
                "promote_gate_summary",
                owner=gate.owner,
                repo=gate.repo,
                branch=gate.branch,
                visibility=gate.visibility,
                mode=mode_label,
            ),
            ask_continue=False,
        )
        if gate.requires_pull_request:
            self.tutor_confirm(
                t(
                    "explain_promote_pr",
                    source=source,
                    target=target,
                    visibility=gate.visibility,
                ),
                t("confirm_promote", source=source, target=target),
            )
            try:
                self._promote_via_pr(source, target, remote_url)
            except supagit_sweep.SweepError as exc:
                raise ShipError(str(exc)) from exc
            return

        self.tutor_confirm(
            t("explain_promote", source=source, target=target),
            t("confirm_promote", source=source, target=target),
        )
        self._promote_direct(source, target)

    def _promote_direct(self, source: str, target: str) -> None:
        self.fetch_branch(target)
        target_cwd = self._cwd_for_branch(target)
        current = self.git(
            "branch", "--show-current", capture=True, cwd=target_cwd
        ).strip()
        if current != target:
            locked = self._worktree_path_for_branch(target)
            if locked is not None and locked != target_cwd.resolve():
                raise ShipError(
                    t(
                        "error_first_branch_in_worktree",
                        branch=target,
                        path=str(locked),
                    )
                )
            self.git("checkout", target, mutating=True, cwd=target_cwd)
        try:
            self.git("merge", source, "--no-edit", mutating=True, cwd=target_cwd)
            self.git("push", self.remote, target, mutating=True, cwd=target_cwd)
        except Exception:
            print(
                colour_text(
                    f"ERROR: {target} may be in an intermediate state; it will not be reverted automatically.",
                    self.RED,
                    colour_enabled(self.options.color, sys.stderr),
                ),
                file=sys.stderr,
            )
            raise

    def _promote_via_pr(self, source: str, target: str, remote_url: str) -> None:
        gh = supagit_sweep.GhClient(self._gh_run_raw, dry_run=self.options.dry_run)
        gh.ensure_ready()
        gh.ensure_github_remote(remote_url)
        # Source tip must be on the remote before opening/merging the PR.
        try:
            self.git("checkout", source, mutating=True, cwd=self.root)
        except Exception:
            pass
        supagit_sweep.push_branch(
            self._sweep_git,
            self.remote,
            source,
            cwd=self.root,
            dry_run=self.options.dry_run,
        )
        pr_number = gh.find_open_pr(source, target)
        if pr_number is None:
            try:
                supagit_sweep.assert_commits_for_pr(
                    self._sweep_git,
                    head=source,
                    base=target,
                    remote=self.remote,
                    cwd=self.root,
                )
            except supagit_sweep.SweepError as exc:
                raise ShipError(str(exc)) from exc
            title = f"supagit: promote {source} → {target}"
            pr_number = gh.create_promote_pr(source, target, title)
            self.explain(t("promote_pr_created", number=pr_number, source=source, target=target))
        else:
            self.explain(t("promote_pr_reused", number=pr_number, source=source, target=target))
        try:
            gh.merge_pr(pr_number, admin=True, delete_branch=False)
        except Exception as exc:
            raise ShipError(
                t(
                    "error_promote_pr_merge_failed",
                    number=pr_number,
                    source=source,
                    target=target,
                )
            ) from exc
        if self.options.dry_run:
            return
        self.git(
            "fetch",
            self.remote,
            f"refs/heads/{target}:refs/heads/{target}",
            mutating=True,
            cwd=self.root,
        )
        self.git(
            "fetch",
            self.remote,
            f"refs/heads/{target}:refs/remotes/{self.remote}/{target}",
            mutating=True,
            cwd=self.root,
        )

    def return_to_dev(self) -> None:
        # Prefer the worktree that already holds pipeline[0] (common with linked launches).
        held = self._worktree_path_for_branch(self.dev)
        if held is not None:
            self.root = held
            return
        if self.options.dry_run:
            self.git("checkout", self.dev, mutating=True, cwd=self.main_root)
            self.root = self.main_root
            return
        current = self.git(
            "branch", "--show-current", capture=True, cwd=self.main_root
        ).strip()
        if current != self.dev:
            merge_path = self.git(
                "rev-parse", "--git-path", "MERGE_HEAD", capture=True, cwd=self.main_root
            ).strip()
            merge_head = Path(merge_path)
            if not merge_head.is_absolute():
                merge_head = self.main_root / merge_head
            if not merge_head.exists():
                self.git("checkout", self.dev, mutating=True, cwd=self.main_root)
        self.root = self.main_root

    def _backend_target_for_branch(self, branch: str, index: int) -> str | None:
        if self.backend.provider != "supabase":
            return None
        if branch in self.backend.targets:
            return self.backend.targets[branch]
        if len(self.branches) == 3:
            legacy_role = "pre" if index == 1 else "prod" if index == 2 else None
            if legacy_role and legacy_role in self.backend.targets:
                return self.backend.targets[legacy_role]
        return None

    def _require_noninteractive_selection(self) -> None:
        if self.options.yes and not self.options.no_sweep:
            if self.options.integrate is None or self.options.pipeline_order is None:
                raise ShipError(t("yes_need_flags"))

    def _sweep_git(self, *args: str, cwd: Path | None = None, capture: bool = True) -> str:
        return self.git(
            *args,
            capture=capture,
            mutating=_git_command_is_mutating(args),
            cwd=cwd or self.root,
        )

    def _gh_run_raw(self, command: Sequence[str], **kwargs) -> str:
        return self.run_raw(list(command), capture=True, mutating=True)

    def build_inventory(self, *, first_branch: str | None = None) -> RepoInventory:
        return supagit_inventory.build_inventory(
            self.layout,
            self.branches,
            self.remote,
            git_runner=self.git,
            first_branch=first_branch,
        )

    def _resolve_selection(
        self,
        inventory: RepoInventory,
        pipeline_line: str,
        integrate_line: str,
        default_pipeline: Sequence[str],
        *,
        interactive: bool = False,
    ) -> MenuSelection:
        pipeline = supagit_menu.parse_pipeline_line(
            inventory, pipeline_line, default_pipeline
        )
        if pipeline[0] != inventory.first_branch:
            inventory = self.build_inventory(first_branch=pipeline[0])
            notice = t("menu_base_changed", base=pipeline[0])
            if interactive:
                current = self.original_branch or None
                self.explain(
                    notice
                    + "\n"
                    + supagit_menu.render_sweeper_menu(
                        inventory, current_branch=current
                    ),
                    ask_continue=False,
                )
            else:
                print(notice)
        return supagit_menu.selection_with_base(inventory, pipeline, integrate_line)

    def run_branch_menu(self, inventory: RepoInventory) -> MenuSelection:
        self._require_noninteractive_selection()
        try:
            if self.options.yes:
                integrate = self.options.integrate or "none"
                pipeline = self.options.pipeline_order or ""
                selection = self._resolve_selection(
                    inventory, pipeline, integrate, default_pipeline=()
                )
                self._explain_situation_preflight(selection, inventory)
            else:
                current = self.original_branch or None
                # Menu is context for the integrate/pipeline prompts; those green
                # fields are the gates — no Continue? after the cyan list.
                self.explain(
                    supagit_menu.render_sweeper_menu(
                        inventory, current_branch=current
                    ),
                    ask_continue=False,
                )
                worktrees, other_work, pipeline_branches = (
                    supagit_menu.classify_menu_branches(inventory)
                )
                base = inventory.first_branch
                if worktrees or other_work:
                    integrate_line = self.tutor_prompt(
                        t("explain_integrate", base=base),
                        t("integrate_prompt"),
                    )
                else:
                    self.explain(
                        t("explain_integrate_none", base=base),
                        ask_continue=False,
                    )
                    integrate_line = "none"
                default_chain = " → ".join(self.branches)
                if len(pipeline_branches) <= 1 and not self.options.pipeline_order:
                    only = (
                        pipeline_branches[0].name
                        if pipeline_branches
                        else (self.branches[0] if self.branches else base)
                    )
                    self.explain(
                        t("explain_pipeline_single", branch=only),
                        ask_continue=False,
                    )
                    pipeline_line = only
                else:
                    pipeline_line = self.tutor_prompt(
                        t("explain_pipeline_order"),
                        t("pipeline_order_prompt", default=default_chain),
                    )
                selection = self._resolve_selection(
                    inventory,
                    pipeline_line,
                    integrate_line,
                    default_pipeline=self.branches,
                    interactive=True,
                )
                situation = self._explain_situation_preflight(selection, inventory)
                self.explain(
                    supagit_menu.render_execution_plan(
                        selection,
                        first_branch=selection.pipeline[0],
                        remote=self.remote,
                        situation=situation,
                    )
                    + "\n"
                    + t("explain_plan"),
                    force_confirm=True,
                )
                # force_confirm keeps the plan gate even under --dry-run.
        except supagit_menu.MenuError as exc:
            raise ShipError(str(exc)) from exc

        return selection

    def _situation_git(self, *args, **kwargs) -> str:
        cwd = kwargs.get("cwd")
        return self.git(
            *args,
            capture=True,
            cwd=Path(cwd) if cwd is not None else self.root,
        )

    def build_situation_for_selection(
        self, selection: MenuSelection, inventory: RepoInventory
    ) -> Situation:
        by_name = {branch.name: branch for branch in inventory.branches}
        findings: list[supagit_situation.Finding] = []
        feature_syncs: list[supagit_situation.BranchSync] = []

        first = selection.pipeline[0]
        first_info = by_name.get(first)
        # Only measure dirty on pipeline0 when that branch is checked out in a
        # worktree. Falling back to self.root while another branch is checked
        # out there falsely attributes feature dirtiness to pipeline0.
        first_wt = (
            str(first_info.worktree_path)
            if first_info is not None and first_info.worktree_path is not None
            else None
        )
        try:
            pipeline0, finding0 = supagit_situation.build_branch_sync(
                self._situation_git,
                first,
                remote=self.remote,
                role="pipeline0",
                worktree_path=first_wt,
            )
        except supagit_situation.SituationError as exc:
            raise ShipError(str(exc)) from exc
        findings.append(finding0)

        for name in selection.integrate:
            info = by_name.get(name)
            wt = (
                str(info.worktree_path)
                if info is not None and info.worktree_path is not None
                else None
            )
            try:
                sync, finding = supagit_situation.build_branch_sync(
                    self._situation_git,
                    name,
                    remote=self.remote,
                    role="feature",
                    worktree_path=wt,
                )
            except supagit_situation.SituationError as exc:
                raise ShipError(str(exc)) from exc
            feature_syncs.append(sync)
            findings.append(finding)

        current = (self.original_branch or "").strip() or first
        dirty = any(f.dirty for f in findings) or pipeline0.dirty
        return Situation(
            current_branch=current,
            dirty=dirty,
            pipeline0=pipeline0,
            features=tuple(feature_syncs),
            findings=tuple(findings),
            gh_ready=None,
            self_update=None,
        )

    def _explain_situation_preflight(
        self, selection: MenuSelection, inventory: RepoInventory
    ) -> Situation:
        situation = self.build_situation_for_selection(selection, inventory)
        self.explain(
            supagit_situation.render_preflight(situation),
            ask_continue=False,
        )
        for finding in situation.findings:
            if finding.policy != supagit_situation.PolicyClass.BLOCKED:
                continue
            branch = selection.pipeline[0]
            upstream: str | None = None
            if finding.role == "pipeline0" and situation.pipeline0 is not None:
                branch = situation.pipeline0.name
                upstream = situation.pipeline0.upstream
            elif finding.role == "feature":
                feature_findings = [
                    f for f in situation.findings if f.role == "feature"
                ]
                for feat_finding, sync in zip(feature_findings, situation.features):
                    if feat_finding is finding:
                        branch = sync.name
                        upstream = sync.upstream
                        break
            raise ShipError(
                supagit_situation.format_blocked_error(
                    finding, branch=branch, upstream=upstream
                )
            )
        return situation

    def apply_menu_selection(self, selection: MenuSelection) -> None:
        self.branches = tuple(selection.pipeline)
        self.dev = self.branches[0]
        self.pre = self.branches[1] if len(self.branches) > 1 else None
        self.prod = self.branches[-1]

    @staticmethod
    def _format_dirty_paths(status: str) -> str:
        paths = [line[3:] for line in status.splitlines() if len(line) >= 4]
        shown = paths[:5]
        lines = [f"  {path}" for path in shown]
        remaining = len(paths) - len(shown)
        if remaining > 0:
            lines.append(t("error_dirty_reposition_more", count=remaining))
        return "\n".join(lines)

    def _worktree_path_for_branch(self, branch: str) -> Path | None:
        porcelain = self.git(
            "worktree", "list", "--porcelain", capture=True, cwd=self.main_root
        )
        for entry in supagit_inventory.parse_worktree_porcelain(porcelain):
            if entry.get("branch") != branch:
                continue
            return Path(str(entry["path"])).resolve()
        return None

    def _first_branch_worktree(self) -> Path | None:
        """Return another worktree that already has pipeline[0], if any."""
        held = self._worktree_path_for_branch(self.dev)
        if held is None:
            return None
        if held == self.root.resolve():
            return None
        return held

    def _cwd_for_branch(self, branch: str) -> Path:
        """Worktree where ``branch`` is checked out, else the main checkout."""
        held = self._worktree_path_for_branch(branch)
        return held if held is not None else self.main_root

    def _adopt_first_branch_worktree(self, path: Path) -> None:
        self.root = path.resolve()
        self.explain(
            t(
                "adopt_first_branch_worktree",
                branch=self.dev,
                path=str(self.root),
            ),
            ask_continue=False,
        )

    def _ensure_first_branch_ref(self) -> None:
        local_ref = f"refs/heads/{self.dev}"
        remote_ref = f"refs/remotes/{self.remote}/{self.dev}"

        def verifies(ref: str) -> bool:
            try:
                self.git("rev-parse", "--verify", ref, capture=True, cwd=self.main_root)
                return True
            except ShipError:
                return False

        if verifies(local_ref) or verifies(remote_ref):
            return
        self.git(
            "fetch",
            self.remote,
            f"refs/heads/{self.dev}:refs/remotes/{self.remote}/{self.dev}",
            mutating=True,
            cwd=self.main_root,
        )

    def ensure_checkout_on_first_branch(self) -> str | None:
        """Move to pipeline[0]. Return feature name if a pre-move commit was made.

        When pipeline[0] is already checked out in a linked worktree, adopt that
        worktree instead of failing — Git forbids the same branch in two worktrees.
        """
        current = self.git(
            "branch", "--show-current", capture=True, cwd=self.root
        ).strip()
        if current == self.dev:
            return None

        other = self._first_branch_worktree()

        current_label = current
        if current == "":
            sha = self.git(
                "rev-parse", "--short", "HEAD", capture=True, cwd=self.root
            ).strip()
            contains = self.git(
                "branch",
                "--contains",
                "HEAD",
                "--format=%(refname:short)",
                capture=True,
                cwd=self.root,
            ).strip()
            if not contains:
                raise ShipError(t("error_detached_unreachable", sha=sha))
            current_label = t("detached_label", sha=sha)

        committed_on: str | None = None
        status = self.git("status", "--porcelain", capture=True, cwd=self.root)
        if status.strip():
            if current == "":
                raise ShipError(
                    t(
                        "error_dirty_reposition",
                        current=current_label,
                        target=self.dev,
                        files=self._format_dirty_paths(status),
                    )
                )
            self._commit_dirty_before_reposition(current, status)
            committed_on = current
            if not self.options.dry_run:
                status = self.git(
                    "status", "--porcelain", capture=True, cwd=self.root
                )
                if status.strip():
                    raise ShipError(
                        t(
                            "error_dirty_reposition",
                            current=current_label,
                            target=self.dev,
                            files=self._format_dirty_paths(status),
                        )
                    )

        if other is not None:
            self._adopt_first_branch_worktree(other)
            return committed_on

        self._ensure_first_branch_ref()
        self.tutor_confirm(
            t("explain_reposition", current=current_label, target=self.dev),
            t("confirm_reposition", current=current_label, target=self.dev),
        )
        self.git("checkout", self.dev, mutating=True, cwd=self.root)
        return committed_on

    def _extend_integrate_after_pre_commit(
        self, selection: MenuSelection, committed_on: str | None
    ) -> MenuSelection:
        """If a pre-reposition commit left commits outside pipeline[0], integrate that branch.

        The sweeper menu may have marked the feature as already contained before
        the commit ran; without this, those new commits never get a PR.
        """
        if not committed_on or committed_on == self.dev:
            return selection
        if committed_on in selection.integrate or committed_on in selection.pipeline:
            return selection
        if self.options.no_sweep:
            raise ShipError(
                t(
                    "error_pre_commit_needs_integrate",
                    branch=committed_on,
                    base=self.dev,
                )
            )
        needs_integrate = self.options.dry_run or not supagit_inventory.branch_contained(
            committed_on, self.dev, self.git
        )
        if not needs_integrate:
            return selection
        print(
            t(
                "integrate_after_pre_commit",
                branch=committed_on,
                base=self.dev,
            )
        )
        return MenuSelection(
            integrate=selection.integrate + (committed_on,),
            pipeline=selection.pipeline,
        )

    def _commit_dirty_before_reposition(self, branch: str, status: str) -> None:
        """Save uncommitted work on the current feature before moving to pipeline[0]."""
        status_paths = [line[3:] for line in status.splitlines() if len(line) >= 4]
        self._reject_sensitive_paths(status_paths)
        message = self._commit_message(branch=branch)
        self.tutor_confirm(
            t(
                "explain_commit_before_reposition",
                branch=branch,
                target=self.dev,
            ),
            t(
                "confirm_commit_before_reposition",
                branch=branch,
                target=self.dev,
            ),
        )
        try:
            supagit_sweep.commit_dirty_tree(
                self._sweep_git,
                cwd=self.root,
                message=message,
                reject_sensitive=self._reject_sensitive_paths,
                dry_run=self.options.dry_run,
            )
        except supagit_sweep.SweepError as exc:
            raise ShipError(str(exc)) from exc

    def verify_final_checkout(self) -> None:
        # Dry-run never repositions; comparing live checkout would false-alarm.
        if self.options.dry_run:
            return
        actual = self.git(
            "branch", "--show-current", capture=True, cwd=self.root
        ).strip()
        if actual != self.dev:
            self.warning(
                t(
                    "final_checkout_mismatch",
                    expected=self.dev,
                    actual=actual or "(detached HEAD)",
                )
            )

    def sweep_features(self, selection: MenuSelection, inventory: RepoInventory) -> None:
        remote_url = self.git("remote", "get-url", self.remote, capture=True, cwd=self.root).strip()
        gh = supagit_sweep.GhClient(self._gh_run_raw, dry_run=self.options.dry_run)
        by_name = {branch.name: branch for branch in inventory.branches}
        base = selection.pipeline[0]

        for branch in selection.integrate:
            info = by_name.get(branch)
            if info is None:
                raise ShipError(f"Unknown branch: {branch}")
            cwd = info.worktree_path or self.root
            try:
                supagit_sweep.integrate_branch(
                    self._sweep_git,
                    gh=gh,
                    remote=self.remote,
                    remote_url=remote_url,
                    branch=branch,
                    base=base,
                    cwd=cwd,
                    message_provider=self._commit_message,
                    reject_sensitive=self._reject_sensitive_paths,
                    dry_run=self.options.dry_run,
                    contained_in_first=info.contained_in_first,
                )
            except supagit_sweep.SweepError as exc:
                raise ShipError(str(exc)) from exc

    def ff_sync_first_branch(self) -> None:
        try:
            supagit_sweep.ff_sync_branch(
                self._sweep_git,
                self.dev,
                self.remote,
                dry_run=self.options.dry_run,
            )
        except supagit_sweep.SweepError as exc:
            raise ShipError(str(exc)) from exc

    def optional_cleanup(self, inventory: RepoInventory, selection: MenuSelection) -> None:
        if self.options.cleanup is False:
            return
        inventory = self.build_inventory()
        plan = supagit_sweep.plan_cleanup(
            inventory, selection.pipeline, selection.integrate
        )
        if not plan.items:
            print(t("cleanup_nothing"))
            return
        print(t("cleanup_candidates"))
        for item in plan.items:
            print(f"  - {item.kind}: {item.name} {item.path or ''}")
        if self.options.cleanup is None:
            self.tutor_confirm(t("explain_cleanup"), t("confirm_cleanup"))
        elif self.options.yes and self.options.cleanup is True:
            pass
        supagit_sweep.apply_cleanup(
            self._sweep_git,
            plan,
            dry_run=self.options.dry_run,
            into=self.dev,
        )

    def run(self) -> None:
        if not self.options.no_sweep:
            self._require_noninteractive_selection()
        self.preflight_repo()
        inventory = self.build_inventory()
        if self.options.no_sweep:
            selection = MenuSelection(integrate=(), pipeline=tuple(self.branches))
            self._explain_situation_preflight(selection, inventory)
        else:
            selection = self.run_branch_menu(inventory)
        self.apply_menu_selection(selection)
        committed_on = self.ensure_checkout_on_first_branch()
        selection = self._extend_integrate_after_pre_commit(selection, committed_on)
        self.validate_pipeline_head()
        inventory = self.build_inventory()
        self.commit_and_publish_dev(integrate=selection.integrate)
        if selection.integrate:
            self.sweep_features(selection, inventory)
        self.ff_sync_first_branch()
        self._assert_dev_synced()
        self.run_checks()
        self.validate_clean_after_checks()
        self.tutor_confirm(
            t("explain_pipeline", chain=" → ".join(self.branches)),
            t("confirm_pipeline", chain=" → ".join(self.branches)),
        )

        if self.backend.provider == "none":
            print("\n=== BACKEND NONE: database migration skipped ===")
        for index, (source, target) in enumerate(zip(self.branches, self.branches[1:]), start=1):
            project_ref = self._backend_target_for_branch(target, index)
            if self.backend.provider == "supabase" and project_ref:
                self.database_checkpoint(target, project_ref)
            elif self.backend.provider == "supabase":
                print(f"No database migration target configured for branch {target}; skipping checkpoint.")
            self.promote(source, target)
        self.return_to_dev()
        self.optional_cleanup(inventory, selection)
        self.verify_final_checkout()
        self.status(
            t("pipeline_completed", chain=" → ".join(self.branches), branch=self.dev),
            self.GREEN,
        )
        self.maybe_return_to_start_branch()


def parse_args(argv: Sequence[str]) -> tuple[argparse.Namespace, Options]:
    parser = argparse.ArgumentParser(
        prog="supagit",
        description="Initializes project configuration or promotes an ordered branch pipeline.",
    )
    parser.add_argument("command", nargs="?", choices=("init",), help="Initialize .supagit.json in the current Git project.")
    parser.add_argument("--config", type=Path, help="Path to the project configuration.")
    parser.add_argument("--dry-run", action="store_true", help="Show the plan without modifying Git or Supabase.")
    parser.add_argument("--yes", action="store_true", help="Skip confirmations; use only with explicit authorization.")
    parser.add_argument("-m", "--message", help="Initial commit message for the first pipeline branch; required with --yes when changes exist.")
    parser.add_argument("--backend", choices=("none", "supabase"), help="Backend for `supagit init` or auto-init when `.supagit.json` is missing.")
    parser.add_argument("--branches", help="Comma-separated ordered branches for `supagit init`.")
    parser.add_argument("--pre-ref-env", help="Environment variable name for the Supabase pre project ref.")
    parser.add_argument("--prod-ref-env", help="Environment variable name for the Supabase prod project ref.")
    parser.add_argument("--color", choices=("auto", "always", "never"), default="auto", help="Confirmation color: auto, always, or never.")
    parser.add_argument("--no-color", action="store_true", help="Use --color never.")
    parser.add_argument("--lang", choices=("en", "es"), help="UI language: en or es.")
    parser.add_argument("--no-sweep", action="store_true")
    parser.add_argument("--integrate", help="Comma-separated feature branches, or 'none'")
    parser.add_argument("--pipeline", dest="pipeline_order", help="Comma-separated ordered pipeline branches")
    parser.add_argument("--cleanup", action="store_true", default=None)
    parser.add_argument("--no-cleanup", action="store_true")
    args = parser.parse_args(argv)
    color = "never" if args.no_color else args.color
    if args.no_cleanup:
        cleanup: bool | None = False
    elif args.cleanup:
        cleanup = True
    else:
        cleanup = None
    return args, Options(
        dry_run=args.dry_run,
        yes=args.yes,
        config_path=args.config,
        message=args.message,
        color=color,
        no_sweep=args.no_sweep,
        integrate=args.integrate,
        pipeline_order=args.pipeline_order,
        cleanup=cleanup,
        lang=args.lang,
        backend=args.backend,
    )


def main(argv: Sequence[str] | None = None) -> int:
    options: Options | None = None
    try:
        raw_argv = list(argv if argv is not None else sys.argv[1:])
        # Self-update before language so a stale install refreshes first.
        print("[supagit] Checking for updates… / Comprobando actualizaciones…")
        try:
            if not needs_skip_update():
                source = supagit_update.source_root_from_marker()
                if source is None:
                    candidate = _SCRIPT_DIR.parent
                    if (candidate / "scripts" / "install-supagit-global.sh").is_file():
                        source = candidate
                if source is None:
                    raise ShipError(
                        "Cannot locate the registered supagit source-root clone. "
                        "Re-run scripts/install-supagit-global.sh from a clone of "
                        "https://github.com/emiliosevilla/supagit.git"
                    )
                if supagit_update.needs_update(source):
                    print("[supagit] Update available; pulling and reinstalling… / Hay actualización…")
                    update_lang = supagit_update.resolve_update_lang(raw_argv)
                    supagit_update.pull_and_reinstall(
                        source, lang=update_lang, progress=sys.stderr
                    )
                    print("[supagit] Update installed; restarting… / Actualización instalada; reiniciando…")
                    env = os.environ.copy()
                    env[supagit_update.SKIP_ENV] = "1"
                    script = Path(__file__).resolve()
                    os.execve(sys.executable, [sys.executable, str(script), *raw_argv], env)
                else:
                    print("[supagit] Already on the latest supagit (origin/main). [build: 2026-08-12]")
        except ShipError:
            raise
        except supagit_update.UpdateError as exc:
            raise ShipError(
                f"Could not update supagit from GitHub / No se pudo actualizar: {exc}"
            ) from exc

        args, options = parse_args(raw_argv)
        try:
            supagit_i18n.ensure_language(options.lang, yes=options.yes)
        except RuntimeError as exc:
            key = str(exc)
            if key == "lang_required_yes":
                raise ShipError(t("lang_required_yes")) from exc
            raise ShipError(t("lang_invalid", value=key)) from exc
        except ValueError as exc:
            raise ShipError(t("lang_invalid", value=str(exc))) from exc

        print_welcome(colour_enabled=colour_enabled(options.color, sys.stdout))
        if not options.yes and not options.dry_run:
            # Welcome is the first cyan block; gate before any further work.
            confirm_default_yes(
                t("confirm_continue"),
                colour_on=colour_enabled(options.color, sys.stdout),
            )

        if args.command == "init":
            return initialise_project(args, options)
        Pipeline(options).run()
        return 0
    except UserAborted as exc:
        enabled = colour_enabled(options.color, sys.stderr) if options else sys.stderr.isatty()
        print(colour_text(t("aborted", detail=str(exc)), RED, enabled), file=sys.stderr)
        return 2
    except ShipError as exc:
        enabled = colour_enabled(options.color, sys.stderr) if options else sys.stderr.isatty()
        print(colour_text(t("error", detail=str(exc)), RED, enabled), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        enabled = colour_enabled(options.color, sys.stderr) if options else sys.stderr.isatty()
        print(colour_text(t("aborted_interrupt"), RED, enabled), file=sys.stderr)
        return 130


def needs_skip_update() -> bool:
    return os.environ.get(supagit_update.SKIP_ENV) == "1"


if __name__ == "__main__":
    raise SystemExit(main())
