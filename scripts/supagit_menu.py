#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from supagit_inventory import BranchInfo, RepoInventory, default_integrate_names
from supagit_i18n import t


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


def parse_integrate_line(inventory: RepoInventory, line: str) -> tuple[str, ...]:
    stripped = line.strip()
    if not stripped:
        return default_integrate_names(inventory)

    lowered = stripped.lower()
    if lowered in {"none", "ninguno", "integrate: none"}:
        return ()

    by_name = _branch_by_name(inventory)
    base = inventory.first_branch
    seen: set[str] = set()
    names: list[str] = []
    for token in _parse_tokens(stripped):
        if token.isdigit():
            raise MenuError("Menu numbers are only for pipeline order, not integrate branches")
        if token not in by_name:
            raise MenuError(f"Unknown branch: {token}")
        branch = by_name[token]
        if branch.is_pipeline:
            raise MenuError(f"Integrate branch cannot be in pipeline: {token}")
        if branch.contained_in_first:
            raise MenuError(t("error_contained_integrate", branch=token, base=base))
        if token in seen:
            continue
        seen.add(token)
        names.append(token)
    return tuple(names)


def parse_pipeline_line(
    inventory: RepoInventory,
    line: str,
    default_pipeline: Sequence[str],
) -> tuple[str, ...]:
    stripped = line.strip()
    if not stripped:
        pipeline = tuple(default_pipeline)
    else:
        _, _, pipeline_branches = classify_menu_branches(inventory)
        pipeline_names = [branch.name for branch in pipeline_branches]
        by_name = _branch_by_name(inventory)
        seen: set[str] = set()
        names: list[str] = []
        for token in _parse_tokens(stripped):
            if token.isdigit():
                index = int(token) - 1
                if index < 0 or index >= len(pipeline_names):
                    raise MenuError(f"Invalid pipeline menu number: {token}")
                name = pipeline_names[index]
            else:
                if token not in by_name:
                    raise MenuError(f"Unknown branch: {token}")
                if not by_name[token].is_pipeline:
                    raise MenuError(f"Not a pipeline branch: {token}")
                name = token
            if name in seen:
                continue
            seen.add(name)
            names.append(name)
        pipeline = tuple(names)

    if not pipeline:
        raise MenuError("Pipeline must include at least one branch")
    return pipeline


def parse_menu_responses(
    inventory: RepoInventory,
    pipeline_line: str,
    integrate_line: str,
    *,
    default_pipeline: Sequence[str],
) -> MenuSelection:
    pipeline = parse_pipeline_line(inventory, pipeline_line, default_pipeline)
    integrate = parse_integrate_line(inventory, integrate_line)

    pipeline_set = set(pipeline)
    for name in integrate:
        if name in pipeline_set:
            raise MenuError(f"Integrate branch cannot be in pipeline: {name}")

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


def classify_menu_branches(
    inventory: RepoInventory,
) -> tuple[list[BranchInfo], list[BranchInfo], list[BranchInfo]]:
    worktrees: list[BranchInfo] = []
    other_work: list[BranchInfo] = []
    pipeline: list[BranchInfo] = []
    for branch in inventory.branches:
        if branch.is_pipeline:
            pipeline.append(branch)
        elif branch.has_worktree:
            worktrees.append(branch)
        else:
            other_work.append(branch)
    return worktrees, other_work, pipeline


def _work_branch_check(branch: BranchInfo) -> str:
    if branch.contained_in_first:
        return t("menu_check_off")
    return t("menu_check_on")


def _work_branch_notes(branch: BranchInfo, base: str) -> list[str]:
    notes: list[str] = []
    if branch.has_worktree and branch.worktree_path is not None:
        notes.append(t("menu_note_worktree", path=branch.worktree_path))
    if branch.dirty:
        notes.append(t("menu_note_dirty"))
    if branch.contained_in_first:
        notes.append(t("menu_note_contained", base=base))
    return notes


def _format_work_branch_line(branch: BranchInfo, base: str) -> str:
    check = _work_branch_check(branch)
    notes = _work_branch_notes(branch, base)
    suffix = f"  {'  '.join(notes)}" if notes else ""
    return f"{check} {branch.name}{suffix}"


def _pipeline_sync_note(branch: BranchInfo) -> str:
    parts: list[str] = []
    if branch.ahead:
        parts.append(f"+{branch.ahead}")
    if branch.behind:
        parts.append(f"-{branch.behind}")
    return f"  {' '.join(parts)}" if parts else ""


def _format_pipeline_line(index: int, branch: BranchInfo) -> str:
    sync = _pipeline_sync_note(branch)
    return f"{index}. {branch.name}{sync}"


def render_sweeper_menu(inventory: RepoInventory) -> str:
    worktrees, other_work, pipeline = classify_menu_branches(inventory)
    base = inventory.first_branch
    lines: list[str] = []

    if worktrees:
        lines.append(t("menu_section_worktrees"))
        for branch in worktrees:
            lines.append(_format_work_branch_line(branch, base))

    if other_work:
        if lines:
            lines.append("")
        lines.append(t("menu_section_other_work"))
        for branch in other_work:
            lines.append(_format_work_branch_line(branch, base))

    if pipeline:
        if lines:
            lines.append("")
        lines.append(t("menu_section_pipeline"))
        for index, branch in enumerate(pipeline, start=1):
            lines.append(_format_pipeline_line(index, branch))

    return "\n".join(lines)


def render_branch_menu(inventory: RepoInventory) -> str:
    return render_sweeper_menu(inventory)


def render_execution_plan(
    selection: MenuSelection,
    *,
    first_branch: str | None = None,
    remote: str | None = None,
) -> str:
    lines: list[str] = [t("plan_header")]
    base = selection.pipeline[0]

    if selection.integrate:
        for branch in selection.integrate:
            lines.append(t("plan_integrate_item", branch=branch, base=base))
    else:
        lines.append(t("plan_none_integrate"))

    publish_branch = first_branch or base
    if remote is not None:
        lines.append(t("plan_publish_item", branch=publish_branch, remote=remote))

    for source, target in zip(selection.pipeline, selection.pipeline[1:]):
        lines.append(t("plan_promote_item", source=source, target=target))

    return "\n".join(lines)
