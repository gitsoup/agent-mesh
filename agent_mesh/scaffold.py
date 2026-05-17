"""Repo scaffold support."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List

from agent_mesh.config import ProjectConfig
from agent_mesh.skills.catalog import SKILLS, SkillDefinition
from agent_mesh.state.storage import atomic_write_json
from agent_mesh.utils.paths import ensure_directory

SUPPORTED_ADAPTERS = ["generic", "claude", "codex", "cursor", "opencode", "pi", "windsurf"]

WORKFLOW_STEPS: Dict[str, List[str]] = {
    "align": [
        "Determine affected context from `CONTEXT-MAP.md`.",
        "Read relevant context files and ADRs.",
        "Identify ambiguous or conflicting terms.",
        "Challenge the plan against existing code and constraints.",
        "Ask decision-shaping questions only when needed.",
        "Recommend defaults and update context if terminology is clarified.",
        "Create an ADR only for durable decisions.",
        "Output an alignment summary.",
    ],
    "to-prd": [
        "Summarize the problem.",
        "Define goals and non-goals.",
        "Define user or technical flows.",
        "Define acceptance criteria.",
        "Define risks and open questions.",
        "Save the PRD.",
    ],
    "to-tasks": [
        "Identify vertical slices.",
        "Create tasks with acceptance criteria.",
        "Mark the execution mode.",
        "Add dependencies.",
        "Write `.agentic/work/*.json` files.",
    ],
    "triage": [
        "Check clarity, dependencies, testability, and risk.",
        "Set the task status.",
    ],
    "claim": [
        "Validate the work item.",
        "Check for an existing claim.",
        "Create the claim file.",
        "Create or verify the branch and worktree.",
        "Output the next implementation steps.",
    ],
    "implement": [
        "Read the work item, claim, PRD, context, and ADRs.",
        "Plan the smallest vertical slice.",
        "Add or update tests.",
        "Implement and run verification.",
        "Record evidence.",
        "Stop before opening a PR.",
    ],
    "diagnose": [
        "Reproduce the problem.",
        "Minimize the failing case.",
        "Form and test hypotheses.",
        "Fix the issue and add regression tests.",
    ],
    "prototype": [
        "State the question being answered.",
        "Keep the prototype isolated.",
        "Summarize findings and recommend the next action.",
    ],
    "pr": [
        "Validate the branch and claim status.",
        "Check verification status.",
        "Generate the PR body.",
        "Create a review packet.",
        "Open the PR only when not in dry-run mode.",
    ],
    "review": [
        "Read the review packet, task, PRD, context, and ADRs.",
        "Inspect the diff and acceptance criteria.",
        "Produce structured review findings.",
    ],
    "address": [
        "Group review feedback.",
        "Fix blockers first.",
        "Re-run verification and update evidence.",
        "Reply with what changed.",
    ],
    "merge": [
        "Verify approval and checks.",
        "Merge according to the configured strategy.",
        "Mark work done and archive the claim.",
        "Sync dashboard state.",
    ],
    "handoff": [
        "Reference durable artifacts.",
        "Summarize current state and next action.",
        "List risks and open questions.",
        "Save the handoff.",
    ],
    "sync": [
        "Fetch or inspect repo state as configured.",
        "Detect stale claims and summarize active work.",
        "Rebuild dashboard state.",
    ],
}


@dataclass(frozen=True)
class InitResult:
    created: List[Path]
    skipped: List[Path]


def init_repo(
    repo_root: Path,
    project_name: str,
    project_key: str,
    provider: str,
    adapters: Iterable[str],
    force: bool = False,
    dashboard: bool = True,
) -> InitResult:
    created: List[Path] = []
    skipped: List[Path] = []
    selected_adapters = normalize_adapters(adapters)

    config = ProjectConfig(
        project_name=project_name,
        project_key=project_key,
        planning={"provider": provider, "external_project": None},
        adapters=selected_adapters,
        dashboard={"enabled": dashboard, "output_dir": ".agentic/dashboard"},
    )

    required_directories = [
        repo_root / ".agentic",
        repo_root / ".agentic/context",
        repo_root / ".agentic/context/adr",
        repo_root / ".agentic/work",
        repo_root / ".agentic/claims",
        repo_root / ".agentic/reviews",
        repo_root / ".agentic/handoffs",
        repo_root / ".agentic/workflows",
        repo_root / ".agentic/skills",
        repo_root / ".agentic/adapters",
        repo_root / ".github/workflows",
    ]
    if dashboard:
        required_directories.append(repo_root / ".agentic/dashboard")

    for directory in required_directories:
        ensure_directory(directory)

    record_result(
        write_json(repo_root / ".agentic/project.json", config.model_dump(), force=force),
        created,
        skipped,
    )
    record_result(
        write_text(repo_root / ".agentic/config.toml", render_config_toml(config), force=force),
        created,
        skipped,
    )
    record_result(
        write_text(repo_root / "AGENTS.md", render_agents_md(project_name), force=force),
        created,
        skipped,
    )
    record_result(
        write_text(
            repo_root / ".agentic/context/CONTEXT.md",
            "# Context\n\nDocument stable domain language, key concepts, and durable decisions here.\n",
            force=force,
        ),
        created,
        skipped,
    )
    record_result(
        write_text(
            repo_root / ".agentic/context/CONTEXT-MAP.md",
            "# Context Map\n\nMap major modules, boundaries, and where durable context lives.\n",
            force=force,
        ),
        created,
        skipped,
    )
    record_result(
        write_text(
            repo_root / ".agentic/context/adr/README.md",
            "# ADRs\n\nStore architecture decision records here when decisions are durable and hard to reverse.\n",
            force=force,
        ),
        created,
        skipped,
    )

    for folder_name in ["work", "claims", "reviews", "handoffs", "adapters"]:
        record_result(
            write_text(
                repo_root / ".agentic" / folder_name / "README.md",
                "# README\n\nThis directory stores human-readable Agent Mesh coordination state.\n",
                force=force,
            ),
            created,
            skipped,
        )

    for skill in SKILLS:
        record_result(
            write_text(
                repo_root / ".agentic/workflows" / "{0}.md".format(skill.name),
                render_workflow(skill),
                force=force,
            ),
            created,
            skipped,
        )

        skill_dir = repo_root / ".agentic/skills" / skill.name
        ensure_directory(skill_dir)
        record_result(
            write_text(skill_dir / "SKILL.md", render_skill(skill), force=force),
            created,
            skipped,
        )

    record_result(
        write_text(
            repo_root / ".github/workflows/agent-mesh-status.yml",
            render_status_workflow(),
            force=force,
        ),
        created,
        skipped,
    )

    adapter_result = install_adapters(repo_root, selected_adapters, force=force)
    created.extend(adapter_result.created)
    skipped.extend(adapter_result.skipped)
    return InitResult(created=created, skipped=skipped)


def install_adapters(repo_root: Path, adapters: Iterable[str], force: bool = False) -> InitResult:
    created: List[Path] = []
    skipped: List[Path] = []
    for adapter_name in normalize_adapters(adapters):
        if adapter_name == "generic":
            continue
        if adapter_name == "claude":
            result = install_skill_wrapper(repo_root / ".claude/skills", force)
            created.extend(result.created)
            skipped.extend(result.skipped)
            record_result(
                write_text(
                    repo_root / "CLAUDE.md",
                    "# Claude Code\n\nRead `AGENTS.md` and `.agentic/workflows/` first.\n",
                    force=force,
                ),
                created,
                skipped,
            )
        elif adapter_name == "codex":
            result = install_skill_wrapper(repo_root / ".agents/skills", force)
            created.extend(result.created)
            skipped.extend(result.skipped)
        elif adapter_name == "pi":
            result = install_skill_wrapper(repo_root / ".agents/skills", force)
            created.extend(result.created)
            skipped.extend(result.skipped)
            prompt_dir = repo_root / ".pi/prompts"
            ensure_directory(prompt_dir)
            for skill in SKILLS:
                record_result(
                    write_text(
                        prompt_dir / "{0}.md".format(skill.name),
                        "Read `AGENTS.md`, then follow `.agentic/workflows/{0}.md`.\n".format(
                            skill.name
                        ),
                        force=force,
                    ),
                    created,
                    skipped,
                )
        elif adapter_name == "cursor":
            record_result(
                write_text(
                    repo_root / ".cursor/rules/agent-mesh.mdc",
                    "Read `AGENTS.md` and `.agentic/workflows/` before acting.\n",
                    force=force,
                ),
                created,
                skipped,
            )
        elif adapter_name == "opencode":
            record_result(
                write_text(
                    repo_root / "OPENCODE.md",
                    "# OpenCode\n\nUse `AGENTS.md` and `.agentic/workflows/` as the canonical instructions.\n",
                    force=force,
                ),
                created,
                skipped,
            )
        elif adapter_name == "windsurf":
            record_result(
                write_text(
                    repo_root / ".windsurfrules",
                    "Read AGENTS.md and .agentic/workflows/ before acting.\n",
                    force=force,
                ),
                created,
                skipped,
            )
    return InitResult(created=created, skipped=skipped)


def install_skill_wrapper(base_dir: Path, force: bool) -> InitResult:
    created: List[Path] = []
    skipped: List[Path] = []
    for skill in SKILLS:
        skill_dir = base_dir / skill.name
        ensure_directory(skill_dir)
        record_result(
            write_text(
                skill_dir / "SKILL.md",
                "Read `AGENTS.md`, then follow `.agentic/workflows/{0}.md`.\n".format(skill.name),
                force=force,
            ),
            created,
            skipped,
        )
    return InitResult(created=created, skipped=skipped)


def normalize_adapters(adapters: Iterable[str]) -> List[str]:
    normalized: List[str] = []
    for adapter in adapters:
        name = adapter.strip().lower()
        if not name:
            continue
        if name not in SUPPORTED_ADAPTERS:
            raise ValueError("Unsupported adapter: {0}".format(adapter))
        if name not in normalized:
            normalized.append(name)
    if not normalized:
        return ["generic"]
    return normalized


def write_text(path: Path, content: str, force: bool = False) -> tuple[Path, bool]:
    ensure_directory(path.parent)
    if path.exists() and not force:
        return path, False
    path.write_text(content, encoding="utf-8")
    return path, True


def write_json(path: Path, content: dict, force: bool = False) -> tuple[Path, bool]:
    ensure_directory(path.parent)
    if path.exists() and not force:
        return path, False
    atomic_write_json(path, content)
    return path, True


def record_result(result: tuple[Path, bool], created: List[Path], skipped: List[Path]) -> None:
    path, was_created = result
    if was_created:
        created.append(path)
    else:
        skipped.append(path)


def render_agents_md(project_name: str) -> str:
    return """# AGENTS.md

This repository uses Agent Mesh for local-first coordination.

## Project

- Project name: `{project_name}`
- Canonical coordination state: `.agentic/`

## Working rules

1. Read `.agentic/context/CONTEXT.md` and `.agentic/context/CONTEXT-MAP.md` first.
2. Use `.agentic/workflows/*.md` as the canonical workflow definitions.
3. Keep coordination state human-readable and reviewable.
4. Do not overwrite existing work without explicit confirmation.
5. Prefer local-first flows; cloud runners are optional and future-facing.
""".format(project_name=project_name)


def render_config_toml(config: ProjectConfig) -> str:
    return """schema_version = "{0}"
project_name = "{1}"
project_key = "{2}"
default_branch = "{3}"
provider = "{4}"
dashboard_enabled = {5}
""".format(
        config.schema_version,
        config.project_name,
        config.project_key,
        config.default_branch,
        config.planning.provider,
        "true" if config.dashboard.enabled else "false",
    )


def render_workflow(skill: SkillDefinition) -> str:
    steps = WORKFLOW_STEPS.get(skill.name, ["Follow the canonical workflow for this skill."])
    body = "\n".join(
        "{0}. {1}".format(index, step) for index, step in enumerate(steps, start=1)
    )
    return "# /{0}\n\n{1}\n\n## Steps\n\n{2}\n".format(skill.name, skill.summary, body)


def render_skill(skill: SkillDefinition) -> str:
    return """---
name: {0}
description: {1}
---

Read `AGENTS.md` first, then follow `.agentic/workflows/{0}.md`.
""".format(skill.name, skill.summary)


def render_status_workflow() -> str:
    return """name: agent-mesh-status

on:
  pull_request:
  workflow_dispatch:

jobs:
  status:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Show Agent Mesh state
        run: |
          test -d .agentic || exit 0
          find .agentic -maxdepth 2 -type f | sort
"""
