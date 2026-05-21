"""Helpers for shared-root and worktree topology."""

from __future__ import annotations

import os
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


@dataclass(frozen=True)
class CoordinationRepairResult:
    branch: str
    path: Path
    action: str
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


def ensure_coordination_worktree(repo_root: Path, config: ProjectConfig) -> CoordinationRepairResult:
    status = inspect_coordination_worktree(repo_root, config)
    branch = config.coordination.branch
    path = status.path

    if status.state == "ready":
        return CoordinationRepairResult(
            branch=branch,
            path=path,
            action="noop",
            state="ready",
        )

    if status.state == "missing":
        create_coordination_worktree(repo_root, config, path)
        return CoordinationRepairResult(
            branch=branch,
            path=path,
            action="created",
            state="ready",
        )

    if status.state == "wrong_branch":
        checkout_coordination_branch(repo_root, config, path)
        return CoordinationRepairResult(
            branch=branch,
            path=path,
            action="repaired",
            state="ready",
            detail="switched coordination worktree to {0}".format(branch),
        )

    if status.state == "dirty":
        raise RuntimeError(
            "coordination worktree at {0} is dirty; clean it before running sync".format(path)
        )

    raise RuntimeError(
        "coordination worktree at {0} is invalid{1}".format(
            path,
            ": {0}".format(status.detail) if status.detail else "",
        )
    )


def create_coordination_worktree(repo_root: Path, config: ProjectConfig, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    branch = config.coordination.branch
    if branch_exists(repo_root, branch):
        args = ["worktree", "add", str(path), branch]
        result = subprocess.run(
            ["git", *args],
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
        )
    else:
        # Create orphan branch: no shared history with main
        result = _create_orphan_coordination_worktree(repo_root, branch, path)

    if result.returncode == 0:
        return

    detail = (result.stderr or result.stdout).strip()
    raise RuntimeError("failed to create coordination worktree: {0}".format(detail))


_EMPTY_TREE_SHA = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


def _create_orphan_coordination_worktree(
    repo_root: Path, branch: str, path: Path
) -> subprocess.CompletedProcess:
    """Create mesh/state as an orphan branch with no shared history with main."""
    # Try git worktree add --orphan (git >= 2.36)
    result = subprocess.run(
        ["git", "worktree", "add", "--orphan", "-b", branch, str(path)],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        # Create initial empty commit so the branch has a ref
        subprocess.run(
            ["git", "commit", "--allow-empty", "-m", "Initialize {0} coordination branch".format(branch)],
            cwd=path,
            check=False,
            capture_output=True,
        )
        return result

    # Fallback for git < 2.36: use low-level plumbing — never touches the working directory
    return _create_orphan_via_commit_tree(repo_root, branch, path)


def _create_orphan_via_commit_tree(
    repo_root: Path, branch: str, path: Path
) -> subprocess.CompletedProcess:
    """Create orphan branch via commit-tree + update-ref; does not modify the working directory."""
    env = os.environ.copy()
    # Provide committer/author identity defaults when git user config is absent
    for probe_key, env_key, default in [
        ("user.name", "GIT_AUTHOR_NAME", "Agent Mesh"),
        ("user.email", "GIT_AUTHOR_EMAIL", "mesh@local"),
    ]:
        probe = subprocess.run(
            ["git", "config", probe_key], cwd=repo_root, capture_output=True, text=True
        )
        if probe.returncode != 0:
            env[env_key] = default
    env.setdefault("GIT_COMMITTER_NAME", env.get("GIT_AUTHOR_NAME", "Agent Mesh"))
    env.setdefault("GIT_COMMITTER_EMAIL", env.get("GIT_AUTHOR_EMAIL", "mesh@local"))

    commit = subprocess.run(
        ["git", "commit-tree", _EMPTY_TREE_SHA, "-m", "Initialize {0} coordination branch".format(branch)],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    if commit.returncode != 0:
        return commit

    commit_hash = commit.stdout.strip()
    ref = subprocess.run(
        ["git", "update-ref", "refs/heads/{0}".format(branch), commit_hash],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if ref.returncode != 0:
        return ref

    return subprocess.run(
        ["git", "worktree", "add", str(path), branch],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )


def checkout_coordination_branch(repo_root: Path, config: ProjectConfig, path: Path) -> None:
    dirty = run_git_text(path, ["status", "--porcelain"])
    if dirty is None:
        raise RuntimeError("failed to inspect coordination worktree status")
    if dirty.strip():
        raise RuntimeError(
            "coordination worktree at {0} is dirty; clean it before repair".format(path)
        )

    branch = config.coordination.branch
    if branch_exists(repo_root, branch):
        args = ["switch", branch]
    else:
        args = ["switch", "-c", branch, config.default_branch]

    result = subprocess.run(
        ["git", *args],
        cwd=path,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return

    detail = (result.stderr or result.stdout).strip()
    raise RuntimeError("failed to repair coordination worktree: {0}".format(detail))


def branch_exists(repo_root: Path, branch: str) -> bool:
    result = subprocess.run(
        ["git", "show-ref", "--verify", "--quiet", "refs/heads/{0}".format(branch)],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0
