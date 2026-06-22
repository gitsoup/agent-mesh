"""Repo scaffold support."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List

from agent_mesh.config import ProjectConfig
from agent_mesh.skills.catalog import SKILLS, SkillDefinition
from agent_mesh.state.storage import atomic_write_json
from agent_mesh.utils.paths import ensure_directory

SUPPORTED_ADAPTERS = ["generic", "claude", "codex", "cursor", "opencode", "pi", "windsurf"]
AGENTS_BOOTSTRAP_START = "<!-- BEGIN AGENT-MESH BOOTSTRAP -->"
AGENTS_BOOTSTRAP_END = "<!-- END AGENT-MESH BOOTSTRAP -->"

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
    "ongoing": [
        "Startup inspection sequence: read `.agentic/project.json`, handoffs, claims, reviews, then work items — in that order.",
        "Surface any handoff found in `.agentic/handoffs/` before acting on anything else.",
        "Identify active claims (within `claim_stale_after_minutes` from project.json), stale claims, and open reviews.",
        "Report a compact summary of current coordination state.",
        "If an open review exists, resolve the workspace and prompt the user before starting new work.",
        "Otherwise, recommend the best ready task or resume in-progress work.",
        "Proceed with `/claim`, `/implement`, `/pr`, `/review`, `/address`, `/merge`, or `/handoff` as appropriate.",
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
    coordination_root: Path | None = None,
) -> InitResult:
    """Scaffold Agent Mesh state.

    coordination_root: where .agentic/ files are written. Defaults to repo_root
    for backward compat; pass the coordination worktree path to write state
    there instead of the shared root.
    """
    created: List[Path] = []
    skipped: List[Path] = []
    # state_root: where live coordination files (work, claims, reviews, handoffs) go.
    # Config and definition files always stay in repo_root so load_project_config(repo_root)
    # is always authoritative and there is exactly one project.json.
    state_root = coordination_root if coordination_root is not None else repo_root
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
        dashboard={"enabled": dashboard, "output_dir": "dist/mesh-dashboard"},
    )

    # Config/definition directories always go to repo_root
    config_directories = [
        repo_root / ".agentic",
        repo_root / ".agentic/context",
        repo_root / ".agentic/context/adr",
        repo_root / ".agentic/examples",
        repo_root / ".agentic/workflows",
        repo_root / ".agentic/skills",
        repo_root / ".agentic/adapters",
        repo_root / ".github/workflows",
    ]
    # Live-state directories go to state_root (= coordination_root when set)
    state_directories = [
        state_root / ".agentic",
        state_root / ".agentic/examples",
        state_root / ".agentic/work",
        state_root / ".agentic/claims",
        state_root / ".agentic/claims/archive",
        state_root / ".agentic/reviews",
        state_root / ".agentic/handoffs",
    ]
    seen: set = set()
    for directory in config_directories + state_directories:
        if directory not in seen:
            ensure_directory(directory)
            seen.add(directory)

    # project.json and config.toml always go to repo_root — one authoritative copy
    record_result(
        write_json(repo_root / ".agentic/project.json", config.model_dump(), force=True),
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
            repo_root / ".agentic/AGENTS-BOOTSTRAP.md",
            render_agents_bootstrap_snippet(project_name),
            force=force,
        ),
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
    record_result(
        write_text(
            repo_root / ".agentic/examples/bootstrap-tasks.json",
            render_bootstrap_tasks_example(project_key),
            force=force,
        ),
        created,
        skipped,
    )
    if state_root != repo_root:
        record_result(
            write_json(state_root / ".agentic/project.json", config.model_dump(), force=True),
            created,
            skipped,
        )
        record_result(
            write_text(
                state_root / ".agentic/config.toml",
                render_config_toml(config),
                force=force,
            ),
            created,
            skipped,
        )
        record_result(
            write_text(
                state_root / ".agentic/AGENTS-BOOTSTRAP.md",
                render_agents_bootstrap_snippet(project_name),
                force=force,
            ),
            created,
            skipped,
        )
        record_result(
            write_text(
                state_root / ".agentic/context/CONTEXT.md",
                (
                    "# Context\n\n"
                    "Document stable domain language, key concepts, and durable decisions here.\n"
                ),
                force=force,
            ),
            created,
            skipped,
        )
        record_result(
            write_text(
                state_root / ".agentic/context/CONTEXT-MAP.md",
                (
                    "# Context Map\n\n"
                    "Map major modules, boundaries, and where durable context lives.\n"
                ),
                force=force,
            ),
            created,
            skipped,
        )
        record_result(
            write_text(
                state_root / ".agentic/context/adr/README.md",
                (
                    "# ADRs\n\n"
                    "Store architecture decision records here when decisions are durable "
                    "and hard to reverse.\n"
                ),
                force=force,
            ),
            created,
            skipped,
        )
        record_result(
            write_text(
                state_root / ".agentic/examples/bootstrap-tasks.json",
                render_bootstrap_tasks_example(project_key),
                force=force,
            ),
            created,
            skipped,
        )

    # State README files go to state_root (coordination worktree when set)
    for folder_name in ["work", "claims", "reviews", "handoffs", "adapters"]:
        record_result(
            write_text(
                state_root / ".agentic" / folder_name / "README.md",
                "# README\n\nThis directory stores human-readable Agent Mesh coordination state.\n",
                force=force,
            ),
            created,
            skipped,
        )
    record_result(
        write_text(
            state_root / ".agentic/claims/archive/README.md",
            "# Archived Claims\n\nThis directory stores completed or superseded claim records.\n",
            force=force,
        ),
        created,
        skipped,
    )

    # Workflow and skill definitions go to repo_root
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
        if state_root != repo_root:
            record_result(
                write_text(
                    state_root / ".agentic/workflows" / "{0}.md".format(skill.name),
                    render_workflow(skill),
                    force=force,
                ),
                created,
                skipped,
            )
            state_skill_dir = state_root / ".agentic/skills" / skill.name
            ensure_directory(state_skill_dir)
            record_result(
                write_text(state_skill_dir / "SKILL.md", render_skill(skill), force=force),
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

    record_result(
        install_git_hook(repo_root, force=force),
        created,
        skipped,
    )

    adapter_result = install_adapters(repo_root, selected_adapters, force=force)
    created.extend(adapter_result.created)
    skipped.extend(adapter_result.skipped)
    return InitResult(created=created, skipped=skipped)


def upgrade_definition_files(repo_root: Path) -> InitResult:
    """Re-install Mesh-owned definition files without touching coordination state.

    Safe to run on any repo that has already had `mesh init`. Updates:
    - .agentic/workflows/*.md
    - .agentic/skills/*/SKILL.md
    - .agentic/examples/bootstrap-tasks.json
    - .agentic/AGENTS-BOOTSTRAP.md
    - .github/workflows/agent-mesh-status.yml
    - .git/hooks/post-commit (the mesh sync hook)

    Does NOT touch: project.json, work/, claims/, reviews/, handoffs/,
    AGENTS.md, CONTEXT.md, CONTEXT-MAP.md, or any user-authored files.
    """
    from agent_mesh.config import load_project_config
    from agent_mesh.state.storage import resolve_coordination_root

    created: List[Path] = []
    skipped: List[Path] = []

    try:
        config = load_project_config(repo_root)
        project_key = config.project_key
        project_name = config.project_name
    except FileNotFoundError:
        raise RuntimeError(
            "No .agentic/project.json found. Run `mesh init` first."
        )

    state_root = resolve_coordination_root(repo_root)

    # Workflow and skill definition files (Mesh-authored, always safe to overwrite)
    for skill in SKILLS:
        for root in {repo_root, state_root}:
            record_result(
                write_text(
                    root / ".agentic/workflows" / "{0}.md".format(skill.name),
                    render_workflow(skill),
                    force=True,
                ),
                created,
                skipped,
            )
            skill_dir = root / ".agentic/skills" / skill.name
            ensure_directory(skill_dir)
            record_result(
                write_text(skill_dir / "SKILL.md", render_skill(skill), force=True),
                created,
                skipped,
            )

    # Bootstrap example (Mesh-authored template, not user coordination state)
    for root in {repo_root, state_root}:
        record_result(
            write_text(
                root / ".agentic/examples/bootstrap-tasks.json",
                render_bootstrap_tasks_example(project_key),
                force=True,
            ),
            created,
            skipped,
        )
        record_result(
            write_text(
                root / ".agentic/AGENTS-BOOTSTRAP.md",
                render_agents_bootstrap_snippet(project_name),
                force=True,
            ),
            created,
            skipped,
        )

    # GitHub Actions workflow
    record_result(
        write_text(
            repo_root / ".github/workflows/agent-mesh-status.yml",
            render_status_workflow(),
            force=True,
        ),
        created,
        skipped,
    )

    # Git hook (idempotent — appends if third-party hook exists)
    record_result(install_git_hook(repo_root, force=True), created, skipped)

    return InitResult(created=created, skipped=skipped)


def install_git_hook(repo_root: Path, force: bool = False) -> tuple[Path, bool]:
    """Install a post-commit git hook that auto-syncs .agentic/ state to mesh/state.

    Works for any agent (Claude Code, Codex, Cursor, etc.) — fires on every git commit.
    If a post-commit hook already exists and force=False, the hook is not overwritten;
    instead the mesh sync call is appended only if not already present.
    """
    hooks_dir = repo_root / ".git" / "hooks"
    if not hooks_dir.exists():
        return hooks_dir / "post-commit", False  # not a real git repo yet

    hook_path = hooks_dir / "post-commit"
    mesh_marker = "# mesh-state-sync"
    hook_body = render_git_post_commit_hook()

    if hook_path.exists() and not force:
        existing = hook_path.read_text(encoding="utf-8")
        if mesh_marker in existing:
            return hook_path, False  # already installed
        # Append to existing hook rather than overwriting
        updated = existing.rstrip("\n") + "\n\n" + hook_body
        hook_path.write_text(updated, encoding="utf-8")
        hook_path.chmod(0o755)
        return hook_path, True

    hook_path.write_text(hook_body, encoding="utf-8")
    hook_path.chmod(0o755)
    return hook_path, True


def render_git_post_commit_hook() -> str:
    return """\
#!/bin/bash
# mesh-state-sync
# Auto-syncs .agentic/work/ and .agentic/claims/ changes to the mesh/state
# coordination worktree after every commit. Works for any agent or tool.

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
if [ -z "$REPO_ROOT" ]; then exit 0; fi

# Find the mesh/state worktree
MESH_WORKTREE=$(git worktree list --porcelain | awk '/^worktree/{wt=$2} /^branch refs\\/heads\\/mesh\\/state/{print wt}')
if [ -z "$MESH_WORKTREE" ]; then exit 0; fi

# Collect .agentic/work/ and .agentic/claims/ files changed in this commit
CHANGED=$(git diff-tree --no-commit-id -r --name-only HEAD | grep -E '^\\.(agentic/(work|claims)/[^/]+\\.json)$')
if [ -z "$CHANGED" ]; then exit 0; fi

COMMITTED=0
while IFS= read -r REL; do
    SRC="$REPO_ROOT/$REL"
    DST="$MESH_WORKTREE/$REL"
    if [ ! -f "$SRC" ]; then continue; fi
    mkdir -p "$(dirname "$DST")"
    cp "$SRC" "$DST"
    git -C "$MESH_WORKTREE" add "$REL"
    COMMITTED=1
done <<< "$CHANGED"

if [ "$COMMITTED" -eq 0 ]; then exit 0; fi
git -C "$MESH_WORKTREE" diff --cached --quiet && exit 0

TASK_IDS=$(echo "$CHANGED" | xargs -I{} basename {} .json | tr '\\n' ',' | sed 's/,$//')
git -C "$MESH_WORKTREE" commit -m "chore(state): sync $TASK_IDS [post-commit]" --no-gpg-sign
"""


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
            record_result(
                install_opencode_config(repo_root, force),
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


def install_opencode_config(repo_root: Path, force: bool = False) -> tuple[Path, bool]:
    opencode_config = repo_root / "opencode.json"
    ensure_directory(opencode_config.parent)
    if opencode_config.exists() and not force:
        existing = json.loads(opencode_config.read_text(encoding="utf-8"))
        skills = existing.get("skills", {})
        paths = skills.get("paths", [])
        if ".agents/skills" in paths:
            return opencode_config, False
        paths.append(".agents/skills")
        skills["paths"] = paths
        existing["skills"] = skills
        atomic_write_json(opencode_config, existing)
        return opencode_config, True
    config = {
        "$schema": "https://opencode.ai/config.json",
        "skills": {
            "paths": [".agents/skills"],
        },
    }
    atomic_write_json(opencode_config, config)
    return opencode_config, True


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

1. If the `mesh` CLI is not installed locally yet, install Agent Mesh first, then run `mesh doctor`. When the CLI is available, invoke `mesh` directly rather than `uv run mesh`.
2. Read `.agentic/context/CONTEXT.md` and `.agentic/context/CONTEXT-MAP.md` first.
3. Detect repo mode before choosing a workflow:
   - `greenfield`: little or no durable product/code context yet → `/setup`, `/align`, `/to-prd`, `/to-tasks`
   - `brownfield adoption`: meaningful repo context exists, but Mesh state does not → `/setup`
   - `ongoing coordination`: `.agentic/` already exists with work/claim/review state → `/ongoing`
4. Inspect `.agentic/project.json` and current coordination state before proposing `/setup` or `/claim`.
5. If `.agentic/work/` has no meaningful work items yet, inspect the repo and any available planning sources, then persist initial tasks with `mesh bootstrap-tasks`.
6. Use `.agentic/workflows/*.md` as the canonical workflow definitions.
7. Install adapter-specific wrappers only when the active agent/runtime needs them.
8. Keep coordination state human-readable and reviewable.
9. Claims should use a dedicated worktree and branch unless the project explicitly disables worktree isolation.
10. Worktrees should be named by reusable workspace or lane identity, not by task ID.
11. The shared root should stay on `{default_branch}`; live coordination state belongs on the `{coordination_branch}` branch in a dedicated coordination worktree.
12. Stale claims should be resumed or explicitly taken over; safe takeover should keep the branch but allocate a new workspace by default.
13. Do not implement claimed work from the shared root checkout when worktree isolation is enabled.
14. Do not overwrite existing work without explicit confirmation.
15. Prefer local-first flows; cloud runners are optional and future-facing.
""".format(
        project_name=project_name,
        default_branch="main",
        coordination_branch="mesh/state",
    )


def render_agents_bootstrap_snippet(project_name: str) -> str:
    return """{start}
## Agent Mesh Bootstrap

This repository uses Agent Mesh for local-first coordination.

Before following the rest of this file:

1. Read `.agentic/project.json`.
2. Read `.agentic/context/CONTEXT.md` and `.agentic/context/CONTEXT-MAP.md`.
3. Detect repo mode before choosing a workflow:
   - `greenfield`: little or no durable product/code context yet → `/setup`, `/align`, `/to-prd`, `/to-tasks`
   - `brownfield adoption`: meaningful repo context exists, but Mesh state does not → `/setup`
   - `ongoing coordination`: `.agentic/` already exists with work/claim/review state → `/ongoing`
4. Inspect `.agentic/project.json` and current coordination state before proposing `/setup` or `/claim`.
5. If `.agentic/work/` has no meaningful work items yet, inspect the repo and any available planning sources, then persist initial tasks with `mesh bootstrap-tasks`.
6. Use `.agentic/workflows/*.md` as the canonical workflow definitions.
7. Apply any repo-specific rules below this bootstrap after the Mesh startup checks above.

Project: `{project_name}`
Canonical coordination state: `.agentic/`
{end}
""".format(
        project_name=project_name,
        start=AGENTS_BOOTSTRAP_START,
        end=AGENTS_BOOTSTRAP_END,
    )


def has_mesh_agents_bootstrap(path: Path) -> bool:
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    if AGENTS_BOOTSTRAP_START in text and AGENTS_BOOTSTRAP_END in text:
        return True

    required_markers = [
        "Agent Mesh",
        ".agentic/project.json",
        ".agentic/context/CONTEXT.md",
        ".agentic/context/CONTEXT-MAP.md",
        ".agentic/workflows/",
    ]
    return all(marker in text for marker in required_markers)


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


def render_bootstrap_tasks_example(project_key: str) -> str:
    example = {
        "tasks": [
            {
                "title": "Map existing architecture and ownership",
                "description": (
                    "Review current docs, code boundaries, and known owner areas before "
                    "creating implementation work."
                ),
                "kind": "research",
                "module": "adoption",
                "status": "needs_triage",
                "execution": "hitl",
                "risk": "low",
                "acceptance_criteria": [
                    "Key modules and ownership boundaries are documented",
                    "Existing planning sources are listed without importing claims automatically",
                    "Coordination state committed to mesh/state on claim and on completion",
                ],
            },
            {
                "id": "{0}-2".format(project_key),
                "title": "Create first implementation slice",
                "description": (
                    "Convert one reviewed brownfield improvement into a ready Mesh work item."
                ),
                "kind": "feature",
                "module": "example",
                "status": "ready",
                "execution": "afk_safe",
                "risk": "medium",
                "planning": {
                    "provider": "local",
                    "url": None,
                    "external_id": None,
                },
                "acceptance_criteria": [
                    "Scope is small enough for one claim",
                    "Expected verification command is clear",
                    "Coordination state committed to mesh/state on claim and on completion",
                ],
                "dependencies": [],
            },
        ]
    }
    return json.dumps(example, indent=2) + "\n"


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
