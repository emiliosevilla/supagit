#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from supagit_inventory import BranchInfo, RepoInventory, default_integrate_names


class MenuError(RuntimeError):
    pass


@dataclass(frozen=True)
class MenuSelection:
    integrate: tuple[str, ...]
    pipeline: tuple[str, ...]


def _branch_by_name(inventory: RepoInventory) -> dict[str, BranchInfo]:
    return {branch.name: branch for branch in inventory.branches}


def _parse_tokens(line: str) -> list[str]:
    return [token.strip() for token in line.split(",") if token.strip()]


def _resolve_token(token: str, inventory: RepoInventory) -> str:
    if token.isdigit():
        index = int(token) - 1
        if index < 0 or index >= len(inventory.branches):
            raise MenuError(f"Invalid menu number: {token}")
        return inventory.branches[index].name

    by_name = _branch_by_name(inventory)
    if token not in by_name:
        raise MenuError(f"Unknown branch: {token}")
    return token


def _resolve_unique_names(tokens: Sequence[str], inventory: RepoInventory) -> tuple[str, ...]:
    seen: set[str] = set()
    names: list[str] = []
    for token in tokens:
        name = _resolve_token(token, inventory)
        if name in seen:
            continue
        seen.add(name)
        names.append(name)
    return tuple(names)


def _normalize_integrate_line(integrate_line: str) -> str:
    stripped = integrate_line.strip()
    if stripped.lower() in {"none", "integrate: none"}:
        return "none"
    return stripped


def parse_menu_responses(
    inventory: RepoInventory,
    pipeline_line: str,
    integrate_line: str,
    *,
    default_pipeline: Sequence[str],
) -> MenuSelection:
    pipeline_tokens = _parse_tokens(pipeline_line)
    if pipeline_tokens:
        pipeline = _resolve_unique_names(pipeline_tokens, inventory)
    else:
        pipeline = tuple(default_pipeline)

    if not pipeline:
        raise MenuError("Pipeline must include at least one branch")

    normalized_integrate = _normalize_integrate_line(integrate_line)
    if not normalized_integrate:
        integrate = default_integrate_names(inventory)
    elif normalized_integrate == "none":
        integrate = ()
    else:
        integrate = _resolve_unique_names(_parse_tokens(normalized_integrate), inventory)

    pipeline_set = set(pipeline)
    by_name = _branch_by_name(inventory)
    for name in integrate:
        if name not in by_name:
            raise MenuError(f"Unknown branch: {name}")
        if name in pipeline_set:
            raise MenuError(f"Integrate branch cannot be in pipeline: {name}")

    for name in pipeline:
        if name not in by_name:
            raise MenuError(f"Unknown branch: {name}")

    return MenuSelection(integrate=integrate, pipeline=pipeline)


def selection_from_flags(
    inventory: RepoInventory,
    pipeline_csv: str,
    integrate_csv: str,
) -> MenuSelection:
    return parse_menu_responses(
        inventory,
        pipeline_line=pipeline_csv,
        integrate_line=integrate_csv,
        default_pipeline=(),
    )


def _format_branch_line(index: int, branch: BranchInfo) -> str:
    tags: list[str] = []
    if branch.is_pipeline:
        tags.append("pipeline")
    if branch.has_worktree:
        tags.append("worktree")
    if branch.dirty:
        tags.append("dirty")
    if branch.contained_in_first:
        tags.append("contained")
    if branch.ahead:
        tags.append(f"+{branch.ahead}")
    if branch.behind:
        tags.append(f"-{branch.behind}")
    suffix = f" [{', '.join(tags)}]" if tags else ""
    return f"{index}. {branch.name}{suffix}"


def render_branch_menu(inventory: RepoInventory) -> str:
    lines = ["Local branches:"]
    for index, branch in enumerate(inventory.branches, start=1):
        lines.append(_format_branch_line(index, branch))
    lines.append("")
    lines.append("Pipeline order (comma-separated numbers or names; Enter = default):")
    lines.append("Integrate branches (comma-separated numbers or names, 'none', or Enter = default):")
    return "\n".join(lines)
