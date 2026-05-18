"""Validation helpers for `.agentic/` state."""

from __future__ import annotations

from pathlib import Path
from typing import List

from pydantic import ValidationError

from agent_mesh.config import PROJECT_FILE, ProjectConfig
from agent_mesh.state.models import Claim, ReviewPacket, WorkItem
from agent_mesh.state.storage import (
    iter_json_files,
    list_claims,
    list_reviews,
    list_work_items,
    load_json,
)
from agent_mesh.topology import inspect_coordination_worktree


def validate_state_tree(repo_root: Path) -> List[str]:
    errors: List[str] = []
    project_file = repo_root / PROJECT_FILE
    if not project_file.exists():
        errors.append("Missing {0}".format(PROJECT_FILE))
        return errors

    config: ProjectConfig | None = None
    try:
        config = ProjectConfig.model_validate(load_json(project_file))
    except ValidationError as exc:
        errors.append("Invalid .agentic/project.json: {0}".format(exc))

    errors.extend(validate_directory(repo_root / ".agentic/work", WorkItem))
    errors.extend(validate_directory(repo_root / ".agentic/claims", Claim))
    errors.extend(validate_directory(repo_root / ".agentic/reviews", ReviewPacket))
    errors.extend(validate_required_paths(repo_root))
    if config is not None:
        errors.extend(validate_coordination_topology(repo_root, config))
    if not errors:
        errors.extend(validate_relationships(repo_root))
    return errors


def validate_directory(path: Path, model_type: object) -> List[str]:
    errors: List[str] = []
    if not path.exists():
        return errors

    for item in iter_json_files(path):
        try:
            model = model_type.model_validate(load_json(item))  # type: ignore[attr-defined]
            if path.name == "work" and item.stem != model.id:
                errors.append("Filename mismatch for {0}: expected {1}.json".format(item, model.id))
            if path.name == "claims" and item.stem != model.work_id:
                errors.append(
                    "Filename mismatch for {0}: expected {1}.json".format(item, model.work_id)
                )
        except ValidationError as exc:
            errors.append("Invalid {0}: {1}".format(item, exc))
    return errors


def validate_required_paths(repo_root: Path) -> List[str]:
    required = [
        repo_root / ".agentic/context/CONTEXT.md",
        repo_root / ".agentic/context/CONTEXT-MAP.md",
        repo_root / ".agentic/work",
        repo_root / ".agentic/claims",
        repo_root / ".agentic/reviews",
        repo_root / ".agentic/workflows",
        repo_root / ".agentic/skills",
    ]
    errors: List[str] = []
    for path in required:
        if not path.exists():
            errors.append("Missing required path: {0}".format(path.relative_to(repo_root)))
    return errors


def validate_relationships(repo_root: Path) -> List[str]:
    errors: List[str] = []
    work_items = {item.id: item for item in list_work_items(repo_root)}
    claims = list_claims(repo_root)
    reviews = list_reviews(repo_root)

    for claim in claims:
        if claim.work_id not in work_items:
            errors.append("Claim references missing work item: {0}".format(claim.work_id))
        elif work_items[claim.work_id].status not in ["ready", "in_progress", "pr_open"]:
            errors.append(
                "Claim/work status mismatch for {0}: task is {1}".format(
                    claim.work_id, work_items[claim.work_id].status
                )
            )

    for review in reviews:
        if review.work_id not in work_items:
            errors.append("Review references missing work item: {0}".format(review.work_id))
        if not (repo_root / review.context.claim).exists():
            errors.append("Review references missing claim file: {0}".format(review.context.claim))
        if not (repo_root / review.context.work_item).exists():
            errors.append("Review references missing work file: {0}".format(review.context.work_item))
    return errors


def validate_coordination_topology(repo_root: Path, config: ProjectConfig) -> List[str]:
    coordination = inspect_coordination_worktree(repo_root, config)
    if coordination.state not in {"invalid", "wrong_branch"}:
        return []

    detail = ": {0}".format(coordination.detail) if coordination.detail else ""
    return [
        "Invalid coordination worktree at {0} for {1}{2}".format(
            coordination.path,
            coordination.branch,
            detail,
        )
    ]
