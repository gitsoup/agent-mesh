import json
import subprocess
from pathlib import Path

import pytest

from agent_mesh.config import ProjectConfig
from agent_mesh.state.storage import atomic_write_json, load_json, resolve_repo_root
from agent_mesh.state.validate import validate_state_tree
from agent_mesh.topology import inspect_coordination_worktree, resolve_coordination_worktree_path


def test_atomic_write_json_round_trips_payload(tmp_path: Path) -> None:
    path = tmp_path / ".agentic" / "project.json"
    payload = {"project_name": "demo", "project_key": "APP"}

    atomic_write_json(path, payload)

    assert load_json(path) == payload


def test_resolve_repo_root_finds_git_ancestor(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    nested = repo_root / "src" / "pkg"
    (repo_root / ".git").mkdir(parents=True)
    nested.mkdir(parents=True)

    assert resolve_repo_root(nested) == repo_root


def test_resolve_repo_root_raises_when_git_root_missing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        resolve_repo_root(tmp_path)


def test_resolve_repo_root_uses_primary_worktree_for_linked_worktree(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    linked_worktree = tmp_path / "repo-linked"
    repo_root.mkdir(parents=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=repo_root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "mesh@example.com"], cwd=repo_root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Agent Mesh Tests"], cwd=repo_root, check=True, capture_output=True)
    (repo_root / "README.md").write_text("demo\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo_root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo_root, check=True, capture_output=True)
    subprocess.run(["git", "worktree", "add", str(linked_worktree)], cwd=repo_root, check=True, capture_output=True)

    assert resolve_repo_root(linked_worktree) == repo_root


def test_validate_state_tree_accepts_valid_project_file(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / ".git").mkdir(parents=True)
    project_file = repo_root / ".agentic" / "project.json"
    project_file.parent.mkdir(parents=True)
    for required_path in [
        repo_root / ".agentic/context",
        repo_root / ".agentic/work",
        repo_root / ".agentic/claims",
        repo_root / ".agentic/reviews",
        repo_root / ".agentic/workflows",
        repo_root / ".agentic/skills",
    ]:
        required_path.mkdir(parents=True, exist_ok=True)
    (repo_root / ".agentic/context/CONTEXT.md").write_text("# Context\n", encoding="utf-8")
    (repo_root / ".agentic/context/CONTEXT-MAP.md").write_text("# Context Map\n", encoding="utf-8")
    project_file.write_text(
        ProjectConfig(project_name="demo", project_key="APP").to_json(),
        encoding="utf-8",
    )

    assert validate_state_tree(repo_root) == []


def test_validate_state_tree_reports_missing_project_file(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / ".git").mkdir(parents=True)

    errors = validate_state_tree(repo_root)

    assert errors == ["Missing .agentic/project.json"]


def test_validate_state_tree_reports_invalid_project_file(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / ".git").mkdir(parents=True)
    project_file = repo_root / ".agentic" / "project.json"
    project_file.parent.mkdir(parents=True)
    project_file.write_text(json.dumps({"project_name": "demo"}), encoding="utf-8")

    errors = validate_state_tree(repo_root)

    assert errors
    assert "project_key" in errors[0]


def test_resolve_coordination_worktree_path_uses_repo_sibling_by_default(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    config = ProjectConfig(project_name="demo", project_key="APP")

    assert resolve_coordination_worktree_path(repo_root, config) == tmp_path / "repo-mesh-state"


def test_validate_state_tree_rejects_wrong_branch_coordination_worktree(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    coordination_root = tmp_path / "repo-mesh-state"
    repo_root.mkdir(parents=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=repo_root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "mesh@example.com"], cwd=repo_root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Agent Mesh Tests"], cwd=repo_root, check=True, capture_output=True)
    (repo_root / "README.md").write_text("demo\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo_root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo_root, check=True, capture_output=True)
    subprocess.run(["git", "worktree", "add", str(coordination_root)], cwd=repo_root, check=True, capture_output=True)

    project_file = repo_root / ".agentic" / "project.json"
    project_file.parent.mkdir(parents=True)
    for required_path in [
        repo_root / ".agentic/context",
        repo_root / ".agentic/work",
        repo_root / ".agentic/claims",
        repo_root / ".agentic/reviews",
        repo_root / ".agentic/workflows",
        repo_root / ".agentic/skills",
    ]:
        required_path.mkdir(parents=True, exist_ok=True)
    (repo_root / ".agentic/context/CONTEXT.md").write_text("# Context\n", encoding="utf-8")
    (repo_root / ".agentic/context/CONTEXT-MAP.md").write_text("# Context Map\n", encoding="utf-8")
    project_file.write_text(
        ProjectConfig(project_name="demo", project_key="APP").to_json(),
        encoding="utf-8",
    )

    errors = validate_state_tree(repo_root)

    assert len(errors) == 1
    assert errors[0].startswith(
        "Invalid coordination worktree at {0} for mesh/state: checked out on ".format(
            coordination_root
        )
    )


def test_inspect_coordination_worktree_reports_missing_path(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    config = ProjectConfig(project_name="demo", project_key="APP")

    status = inspect_coordination_worktree(repo_root, config)

    assert status.branch == "mesh/state"
    assert status.state == "missing"
