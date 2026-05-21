"""Helpers for shared-root and worktree topology."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from agent_mesh.config import LaneEntry, ProjectConfig


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


# ---------------------------------------------------------------------------
# Lane topology helpers (ADR 0004)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LaneStatus:
    name: str
    workspace_id: str
    worktree_path: Path
    base_branch: str
    status: str  # idle | active | missing
    current_branch: Optional[str] = None
    detail: Optional[str] = None


def get_user_slug(repo_root: Path) -> str:
    from agent_mesh.utils.slug import slugify
    result = subprocess.run(
        ["git", "config", "user.name"],
        cwd=repo_root, check=False, capture_output=True, text=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        return slugify(result.stdout.strip()) or "mesh"
    return "mesh"


def next_lane_name(existing_names: set, user_slug: str) -> str:
    n = 1
    while True:
        candidate = "{0}-{1}".format(user_slug, n)
        if candidate not in existing_names:
            return candidate
        n += 1


def resolve_lane_worktree_path(repo_root: Path, workspace_id: str, worktree_root: Optional[str]) -> Path:
    if worktree_root:
        root = Path(worktree_root).expanduser()
        root = (repo_root / root).resolve() if not root.is_absolute() else root.resolve()
        return root / "{0}-{1}".format(repo_root.name, workspace_id)
    return repo_root.parent / "{0}-{1}".format(repo_root.name, workspace_id)


def inspect_lane_status(lane: LaneEntry) -> LaneStatus:
    path = Path(lane.worktree_path)
    base_branch = "wt/{0}".format(lane.workspace_id)

    if not path.exists() or not (path / ".git").exists():
        return LaneStatus(
            name=lane.name,
            workspace_id=lane.workspace_id,
            worktree_path=path,
            base_branch=base_branch,
            status="missing",
        )

    current = run_git_text(path, ["branch", "--show-current"])
    if current is None:
        return LaneStatus(
            name=lane.name,
            workspace_id=lane.workspace_id,
            worktree_path=path,
            base_branch=base_branch,
            status="missing",
            detail="failed to read branch",
        )
    current = current.strip()
    status = "idle" if current == base_branch else "active"
    return LaneStatus(
        name=lane.name,
        workspace_id=lane.workspace_id,
        worktree_path=path,
        base_branch=base_branch,
        status=status,
        current_branch=current or None,
    )


def lane_base_branch_diverged(repo_root: Path, lane: LaneEntry, default_branch: str) -> bool:
    base_branch = "wt/{0}".format(lane.workspace_id)
    if not branch_exists(repo_root, base_branch):
        return False
    result = run_git_text(
        repo_root,
        ["rev-list", "--count", "origin/{0}..{1}".format(default_branch, base_branch)],
    )
    if result is None:
        return False
    try:
        return int(result.strip()) > 0
    except ValueError:
        return False


def lane_name_conflicts(repo_root: Path, config: ProjectConfig, name: str) -> Optional[str]:
    existing_names = {lane.name for lane in config.coordination.lanes}
    if name in existing_names:
        return "lane '{0}' already registered".format(name)
    if branch_exists(repo_root, "wt/{0}".format(name)):
        return "branch 'wt/{0}' already exists".format(name)
    path = resolve_lane_worktree_path(repo_root, name, config.coordination.worktree_root)
    if path.exists():
        return "worktree path '{0}' already exists".format(path)
    return None


def provision_lane(repo_root: Path, config: ProjectConfig, workspace_id: str) -> Path:
    path = resolve_lane_worktree_path(repo_root, workspace_id, config.coordination.worktree_root)
    base_branch = "wt/{0}".format(workspace_id)

    if path.exists() and (path / ".git").exists():
        return path

    path.parent.mkdir(parents=True, exist_ok=True)

    if branch_exists(repo_root, base_branch):
        args = ["worktree", "add", str(path), base_branch]
    else:
        args = ["worktree", "add", "-b", base_branch, str(path), config.default_branch]

    result = subprocess.run(
        ["git", *args], cwd=repo_root, check=False, capture_output=True, text=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError("failed to provision lane: {0}".format(detail))
    return path
