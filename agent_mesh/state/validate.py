"""Validation helpers for `.agentic/` state."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from agent_mesh.config import PROJECT_FILE, ProjectConfig
from agent_mesh.skills.catalog import SKILLS
from agent_mesh.state.models import Claim, ReviewPacket, WorkItem
from agent_mesh.state.storage import (
    iter_json_files,
    list_claims,
    list_reviews,
    list_work_items,
    load_json,
)
from agent_mesh.topology import inspect_coordination_worktree


def validate_state_tree(repo_root: Path) -> list[str]:
    errors: list[str] = []
    project_file = repo_root / PROJECT_FILE
    if not project_file.exists():
        errors.append(f"Missing {PROJECT_FILE}")
        return errors

    config: ProjectConfig | None = None
    try:
        config = ProjectConfig.model_validate(load_json(project_file))
    except ValidationError as exc:
        errors.append(f"Invalid .agentic/project.json: {exc}")

    errors.extend(validate_directory(repo_root / ".agentic/work", WorkItem))
    errors.extend(validate_directory(repo_root / ".agentic/claims", Claim))
    errors.extend(validate_directory(repo_root / ".agentic/reviews", ReviewPacket))
    errors.extend(validate_required_paths(repo_root))
    if config is not None:
        errors.extend(validate_adapter_artifacts(repo_root, config))
        errors.extend(validate_coordination_topology(repo_root, config))
    if not errors:
        errors.extend(validate_relationships(repo_root))
    return errors


def validate_directory(path: Path, model_type: object) -> list[str]:
    errors: list[str] = []
    if not path.exists():
        return errors

    for item in iter_json_files(path):
        try:
            model = model_type.model_validate(load_json(item))  # type: ignore[attr-defined]
            if path.name == "work" and item.stem != model.id:
                errors.append(f"Filename mismatch for {item}: expected {model.id}.json")
            if path.name == "claims" and item.stem != model.work_id:
                errors.append(f"Filename mismatch for {item}: expected {model.work_id}.json")
        except ValidationError as exc:
            errors.append(f"Invalid {item}: {exc}")
    return errors


def validate_required_paths(repo_root: Path) -> list[str]:
    required = [
        repo_root / ".agentic/context/CONTEXT.md",
        repo_root / ".agentic/context/CONTEXT-MAP.md",
        repo_root / ".agentic/work",
        repo_root / ".agentic/claims",
        repo_root / ".agentic/reviews",
        repo_root / ".agentic/workflows",
        repo_root / ".agentic/skills",
    ]
    errors: list[str] = []
    for path in required:
        if not path.exists():
            errors.append(f"Missing required path: {path.relative_to(repo_root)}")
    return errors


def validate_adapter_artifacts(repo_root: Path, config: ProjectConfig) -> list[str]:
    errors: list[str] = []
    for adapter in config.adapters:
        if adapter == "generic":
            continue
        if adapter == "claude":
            errors.extend(
                validate_skill_wrapper_tree(repo_root, repo_root / ".claude/skills", "claude")
            )
            if not (repo_root / "CLAUDE.md").exists():
                errors.append("Missing adapter artifact for claude: CLAUDE.md")
        elif adapter == "codex":
            errors.extend(
                validate_skill_wrapper_tree(repo_root, repo_root / ".agents/skills", "codex")
            )
        elif adapter == "pi":
            errors.extend(
                validate_skill_wrapper_tree(repo_root, repo_root / ".agents/skills", "pi")
            )
        elif adapter == "cursor":
            if not (repo_root / ".cursor/rules/agent-mesh.mdc").exists():
                errors.append("Missing adapter artifact for cursor: .cursor/rules/agent-mesh.mdc")
        elif adapter == "opencode":
            if not (repo_root / "OPENCODE.md").exists():
                errors.append("Missing adapter artifact for opencode: OPENCODE.md")
            if not (repo_root / "opencode.json").exists():
                errors.append("Missing adapter artifact for opencode: opencode.json")
            else:
                try:
                    config = json.loads((repo_root / "opencode.json").read_text(encoding="utf-8"))
                    paths = config.get("skills", {}).get("paths", [])
                    if ".agents/skills" not in paths:
                        errors.append("opencode.json missing skills.paths entry for .agents/skills")
                except Exception as exc:
                    errors.append(f"Invalid opencode.json: {exc}")
        elif adapter == "windsurf":
            if not (repo_root / ".windsurfrules").exists():
                errors.append("Missing adapter artifact for windsurf: .windsurfrules")
    return errors


def validate_skill_wrapper_tree(repo_root: Path, base_dir: Path, adapter: str) -> list[str]:
    errors: list[str] = []
    if not base_dir.exists():
        errors.append(
            f"Missing adapter artifact directory for {adapter}: "
            f"{base_dir.relative_to(repo_root)}"
        )
        return errors

    for skill in SKILLS:
        skill_path = base_dir / skill.name / "SKILL.md"
        if not skill_path.exists():
            errors.append(
                f"Missing adapter skill wrapper for {adapter}: "
                f"{skill_path.relative_to(repo_root)}"
            )
    return errors


def validate_relationships(repo_root: Path) -> list[str]:
    errors: list[str] = []
    work_items = {item.id: item for item in list_work_items(repo_root)}
    claims = list_claims(repo_root)
    reviews = list_reviews(repo_root)

    for claim in claims:
        if claim.work_id not in work_items:
            errors.append(f"Claim references missing work item: {claim.work_id}")
        elif work_items[claim.work_id].status not in ["ready", "in_progress", "pr_open"]:
            errors.append(
                f"Claim/work status mismatch for {claim.work_id}: "
                f"task is {work_items[claim.work_id].status}"
            )

    for review in reviews:
        if review.work_id not in work_items:
            errors.append(f"Review references missing work item: {review.work_id}")
        if review.status != "merged" and not (repo_root / review.context.claim).exists():
            errors.append(f"Review references missing claim file: {review.context.claim}")
        if not (repo_root / review.context.work_item).exists():
            errors.append(f"Review references missing work file: {review.context.work_item}")
    return errors


def validate_coordination_topology(repo_root: Path, config: ProjectConfig) -> list[str]:
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
