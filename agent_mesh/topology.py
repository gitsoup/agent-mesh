"""Helpers for shared-root and worktree topology."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from agent_mesh.config import ProjectConfig


@dataclass(frozen=True)
class CoordinationWorktreeStatus:
    branch: str
    path: Path
    state: str
    detail: str | None = None


def resolve_coordination_worktree_path(repo_root: Path, config: ProjectConfig) -> Path:
    configured_path = config.coordination.coordination_worktree
    if configured_path:
        path = Path(configured_path).expanduser()
        return (repo_root / path).resolve() if not path.is_absolute() else path.resolve()

    if config.coordination.worktree_root:
        root = Path(config.coordination.worktree_root).expanduser()
        root = (repo_root / root).resolve() if not root.is_absolute() else root.resolve()
        return root / "{0}-mesh-state".format(repo_root.name)

    return repo_root.parent / "{0}-mesh-state".format(repo_root.name)


def inspect_coordination_worktree(repo_root: Path, config: ProjectConfig) -> CoordinationWorktreeStatus:
    branch = config.coordination.branch
    path = resolve_coordination_worktree_path(repo_root, config)

    if not path.exists():
        return CoordinationWorktreeStatus(branch=branch, path=path, state="missing")

    if not (path / ".git").exists():
        return CoordinationWorktreeStatus(
            branch=branch,
            path=path,
            state="invalid",
            detail="path exists but is not a git worktree",
        )

    active_branch = run_git_text(path, ["branch", "--show-current"])
    if active_branch is None:
        return CoordinationWorktreeStatus(
            branch=branch,
            path=path,
            state="invalid",
            detail="failed to inspect coordination worktree branch",
        )

    active_branch = active_branch.strip()
    if active_branch != branch:
        return CoordinationWorktreeStatus(
            branch=branch,
            path=path,
            state="wrong_branch",
            detail="checked out on {0}".format(active_branch or "<detached>"),
        )

    dirty = run_git_text(path, ["status", "--porcelain"])
    if dirty is None:
        return CoordinationWorktreeStatus(
            branch=branch,
            path=path,
            state="invalid",
            detail="failed to inspect coordination worktree status",
        )

    if dirty.strip():
        return CoordinationWorktreeStatus(
            branch=branch,
            path=path,
            state="dirty",
            detail="coordination worktree has uncommitted changes",
        )

    return CoordinationWorktreeStatus(branch=branch, path=path, state="ready")


def run_git_text(repo_root: Path, args: list[str]) -> str | None:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout
