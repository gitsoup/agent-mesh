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
    "setup": [
        "Detect repo mode before making changes.",
        "Read `AGENTS.md`, `CONTEXT.md`, and `CONTEXT-MAP.md`.",
        "If `.agentic/` already exists, inspect current work, claims, reviews, and handoffs first.",
        "If the repo is `greenfield`, scaffold Agent Mesh state and route into `/align`, `/to-prd`, and `/to-tasks`.",
        "If the repo is `brownfield adoption`, derive durable context from existing code, docs, and conventions before normalizing them into `.agentic/` state.",
        "Install or refresh adapters only after deciding setup or adoption work is needed.",
        "Do not overwrite existing coordination state without explicit confirmation.",
    ],
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
        "Confirm the repo is in `ongoing coordination` mode, or finish setup/adoption work first.",
        "Inspect current status, claims, reviews, and handoffs.",
        "Validate the work item.",
        "Check for an existing claim.",
        "Create or verify a dedicated worktree and task branch unless worktree isolation is disabled.",
        "Create the claim file.",
        "Output the next implementation steps, including the worktree path to enter.",
    ],
    "implement": [
        "Read the work item, claim, PRD, context, and ADRs.",
        "Plan the smallest vertical slice.",
        "Add or update tests.",
        "Implement and run verification.",
        "Inspect `git diff` and `git status` in the claimed workspace.",
        "Remove accidental files, debug leftovers, and unrelated edits.",
        "Record evidence, including commands and outcomes.",
        "Stop only when the branch is in a deliberate reviewable state.",
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
        "Confirm the current checkout matches the claimed workspace.",
        "Check `git status` and `git diff` for unintended changes.",
        "Refuse PR creation until the workspace is deliberate and reviewable.",
        "Check verification status and summarize evidence.",
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
    worktree_policy: str = "required",
    worktree_root: str | None = None,
    claim_stale_after_minutes: int = 120,
) -> InitResult:
    created: List[Path] = []
    skipped: List[Path] = []
    selected_adapters = normalize_adapters(adapters)

    config = ProjectConfig(
        project_name=project_name,
        project_key=project_key,
        planning={"provider": provider, "external_project": None},
        adapters=selected_adapters,
        coordination={
            "strategy": "git_files",
            "branch": "mesh/state",
            "work_dir": ".agentic/work",
            "claims_dir": ".agentic/claims",
            "reviews_dir": ".agentic/reviews",
            "handoffs_dir": ".agentic/handoffs",
            "worktree_policy": worktree_policy,
            "worktree_root": worktree_root,
            "coordination_worktree": None,
            "claim_stale_after_minutes": claim_stale_after_minutes,
        },
        dashboard={"enabled": dashboard, "output_dir": ".agentic/dashboard"},
    )

    required_directories = [
        repo_root / ".agentic",
        repo_root / ".agentic/context",
        repo_root / ".agentic/context/adr",
        repo_root / ".agentic/work",
        repo_root / ".agentic/claims",
        repo_root / ".agentic/claims/archive",
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
    record_result(
        write_text(
            repo_root / ".agentic/claims/archive/README.md",
            "# Archived Claims\n\nThis directory stores completed or superseded claim records.\n",
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
                    "# Claude Code\n\nStart with `AGENTS.md` and follow its repo-mode detection before picking a workflow from `.agentic/workflows/`.\n",
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
                        "Read `AGENTS.md`, use its repo-mode detection, then follow `.agentic/workflows/{0}.md`.\n".format(skill.name),
                        force=force,
                    ),
                    created,
                    skipped,
                )
        elif adapter_name == "cursor":
            record_result(
                write_text(
                    repo_root / ".cursor/rules/agent-mesh.mdc",
                    "Read `AGENTS.md`, determine repo mode, then use `.agentic/workflows/`.\n",
                    force=force,
                ),
                created,
                skipped,
            )
        elif adapter_name == "opencode":
            record_result(
                write_text(
                    repo_root / "OPENCODE.md",
                    "# OpenCode\n\nUse `AGENTS.md` for repo-mode detection, then follow `.agentic/workflows/` as the canonical instructions.\n",
                    force=force,
                ),
                created,
                skipped,
            )
        elif adapter_name == "windsurf":
            record_result(
                write_text(
                    repo_root / ".windsurfrules",
                    "Read AGENTS.md, determine repo mode, then use .agentic/workflows/.\n",
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
                render_skill_wrapper(skill),
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
2. Detect repo mode before choosing a workflow:
   - `greenfield`: little or no durable product/code context yet
   - `brownfield adoption`: meaningful repo context exists, but Mesh state does not
   - `ongoing coordination`: `.agentic/` already exists with work/claim/review state
3. Inspect `.agentic/project.json` and current coordination state before proposing `/setup` or `/claim`.
4. Use `.agentic/workflows/*.md` as the canonical workflow definitions.
5. Keep coordination state human-readable and reviewable.
6. Claims should use a dedicated worktree and branch unless the project explicitly disables worktree isolation.
7. Worktrees should be named by reusable workspace or lane identity, not by task ID.
8. The shared root should stay on `{default_branch}`; live coordination state belongs on the `{coordination_branch}` branch in a dedicated coordination worktree.
9. Stale claims should be resumed or explicitly taken over; safe takeover should keep the branch but allocate a new workspace by default.
10. Do not implement claimed work from the shared root checkout when worktree isolation is enabled.
11. Do not overwrite existing work without explicit confirmation.
12. Prefer local-first flows; cloud runners are optional and future-facing.
""".format(
        project_name=project_name,
        default_branch="main",
        coordination_branch="mesh/state",
    )


def render_config_toml(config: ProjectConfig) -> str:
    return """schema_version = "{0}"
project_name = "{1}"
project_key = "{2}"
default_branch = "{3}"
provider = "{4}"
dashboard_enabled = {5}
coordination_branch = "{6}"
coordination_worktree = {7}
worktree_policy = "{8}"
claim_stale_after_minutes = {9}
""".format(
        config.schema_version,
        config.project_name,
        config.project_key,
        config.default_branch,
        config.planning.provider,
        "true" if config.dashboard.enabled else "false",
        config.coordination.branch,
        (
            '"{0}"'.format(config.coordination.coordination_worktree)
            if config.coordination.coordination_worktree
            else "null"
        ),
        config.coordination.worktree_policy,
        config.coordination.claim_stale_after_minutes,
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

Read `AGENTS.md` first, use its repo-mode detection, then follow `.agentic/workflows/{0}.md`.
""".format(skill.name, skill.summary)


def render_skill_wrapper(skill: SkillDefinition) -> str:
    return """---
name: {0}
description: {1}
---

Read `AGENTS.md`, use its repo-mode detection, then follow `.agentic/workflows/{0}.md`.
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
