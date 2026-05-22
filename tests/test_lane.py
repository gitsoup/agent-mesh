"""Tests for mesh lane command and mesh init --lanes."""

import json
import subprocess
from pathlib import Path

from agent_mesh.cli import app


def run_cli(args, capsys):
    exit_code = app(args)
    output = capsys.readouterr()
    return exit_code, output.out


def init_repo(tmp_path: Path, monkeypatch, capsys, lanes: int = 0) -> Path:
    repo_root = tmp_path / "demo-repo"
    (repo_root / ".git").mkdir(parents=True)
    monkeypatch.chdir(repo_root)
    cli_args = [
        "init",
        "--project-name", "demo",
        "--project-key", "APP",
        "--worktree-policy", "off",
    ]
    if lanes:
        cli_args += ["--lanes", str(lanes)]
    exit_code, output = run_cli(cli_args, capsys)
    assert exit_code == 0, output
    return repo_root


def load_config(repo_root: Path) -> dict:
    return json.loads((repo_root / ".agentic/project.json").read_text(encoding="utf-8"))


def test_init_no_lanes_stores_empty_lanes(tmp_path, monkeypatch, capsys):
    repo_root = init_repo(tmp_path, monkeypatch, capsys)
    config = load_config(repo_root)
    assert config["coordination"]["lanes"] == []


def test_init_with_lanes_stores_lane_metadata(tmp_path, monkeypatch, capsys):
    from agent_mesh.topology import resolve_lane_worktree_path

    repo_root = init_repo(tmp_path, monkeypatch, capsys, lanes=2)
    config = load_config(repo_root)
    lanes = config["coordination"]["lanes"]
    assert len(lanes) == 2
    # Both lanes get unique names
    names = [l["name"] for l in lanes]
    assert len(set(names)) == 2
    # workspace_id matches name
    for lane in lanes:
        assert lane["workspace_id"] == lane["name"]
    for lane in lanes:
        assert lane.get("worktree_path") in (None, "")
        path = resolve_lane_worktree_path(repo_root, lane["workspace_id"], config["coordination"]["worktree_root"])
        assert path.parent == repo_root.parent


def test_init_lanes_idempotent(tmp_path, monkeypatch, capsys):
    repo_root = init_repo(tmp_path, monkeypatch, capsys, lanes=1)
    first_config = load_config(repo_root)
    first_name = first_config["coordination"]["lanes"][0]["name"]

    # Re-run init with --lanes 2: should add one more, not duplicate
    exit_code, _ = run_cli(
        ["init", "--project-name", "demo", "--project-key", "APP",
         "--worktree-policy", "off", "--lanes", "2"],
        capsys,
    )
    assert exit_code == 0
    config = load_config(repo_root)
    lanes = config["coordination"]["lanes"]
    assert len(lanes) == 2
    assert lanes[0]["name"] == first_name  # original lane preserved

    # Re-run init with --lanes 1: already have 2, nothing added
    exit_code, output = run_cli(
        ["init", "--project-name", "demo", "--project-key", "APP",
         "--worktree-policy", "off", "--lanes", "1"],
        capsys,
    )
    assert exit_code == 0
    config = load_config(repo_root)
    assert len(config["coordination"]["lanes"]) == 2


def test_lane_list_no_lanes(tmp_path, monkeypatch, capsys):
    repo_root = init_repo(tmp_path, monkeypatch, capsys)
    exit_code, output = run_cli(["lane", "list"], capsys)
    assert exit_code == 0
    assert "No lanes provisioned" in output


def test_lane_list_shows_registered_lanes(tmp_path, monkeypatch, capsys):
    repo_root = init_repo(tmp_path, monkeypatch, capsys, lanes=1)
    exit_code, output = run_cli(["lane", "list"], capsys)
    assert exit_code == 0
    config = load_config(repo_root)
    lane_name = config["coordination"]["lanes"][0]["name"]
    assert lane_name in output
    # Status is missing because worktree-policy is off (path doesn't exist)
    assert "missing" in output


def test_lane_add_explicit_name(tmp_path, monkeypatch, capsys):
    repo_root = init_repo(tmp_path, monkeypatch, capsys)
    exit_code, output = run_cli(["lane", "add", "my-lane"], capsys)
    assert exit_code == 0
    assert "my-lane" in output
    config = load_config(repo_root)
    names = [l["name"] for l in config["coordination"]["lanes"]]
    assert "my-lane" in names


def test_lane_add_auto_name(tmp_path, monkeypatch, capsys):
    repo_root = init_repo(tmp_path, monkeypatch, capsys)
    exit_code, output = run_cli(["lane", "add"], capsys)
    assert exit_code == 0
    config = load_config(repo_root)
    assert len(config["coordination"]["lanes"]) == 1


def test_lane_add_rejects_duplicate_name(tmp_path, monkeypatch, capsys):
    repo_root = init_repo(tmp_path, monkeypatch, capsys)
    run_cli(["lane", "add", "my-lane"], capsys)
    exit_code, output = run_cli(["lane", "add", "my-lane"], capsys)
    assert exit_code == 1
    assert "already registered" in output


def test_lane_add_is_idempotent_across_calls(tmp_path, monkeypatch, capsys):
    repo_root = init_repo(tmp_path, monkeypatch, capsys)
    run_cli(["lane", "add", "lane-a"], capsys)
    run_cli(["lane", "add", "lane-b"], capsys)
    config = load_config(repo_root)
    names = [l["name"] for l in config["coordination"]["lanes"]]
    assert "lane-a" in names
    assert "lane-b" in names
    assert len(names) == 2


# ---------------------------------------------------------------------------
# Integration tests — require real git repo
# ---------------------------------------------------------------------------

def _init_real_git_repo(tmp_path, monkeypatch, capsys):
    repo_root = tmp_path / "demo-repo"
    repo_root.mkdir(parents=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=repo_root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "mesh@test.com"], cwd=repo_root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Agent Mesh Tests"], cwd=repo_root, check=True, capture_output=True)
    (repo_root / "README.md").write_text("demo\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo_root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo_root, check=True, capture_output=True)
    monkeypatch.chdir(repo_root)
    exit_code, output = run_cli(
        ["init", "--project-name", "demo", "--project-key", "APP",
         "--worktree-policy", "required"],
        capsys,
    )
    assert exit_code == 0, output
    return repo_root


def test_init_with_lanes_creates_actual_worktrees(tmp_path, monkeypatch, capsys):
    from agent_mesh.topology import resolve_lane_worktree_path

    repo_root = _init_real_git_repo(tmp_path, monkeypatch, capsys)

    exit_code, output = run_cli(["init", "--project-name", "demo", "--project-key", "APP",
                                  "--worktree-policy", "required", "--lanes", "2"], capsys)
    assert exit_code == 0

    config = load_config(repo_root)
    lanes = config["coordination"]["lanes"]
    assert len(lanes) == 2
    for lane in lanes:
        path = resolve_lane_worktree_path(repo_root, lane["workspace_id"], config["coordination"]["worktree_root"])
        assert path.exists(), "lane worktree not created: {0}".format(path)
        assert (path / ".git").exists()

    # Each lane branch should exist
    result = subprocess.run(["git", "branch"], cwd=repo_root, capture_output=True, text=True)
    for lane in lanes:
        assert "wt/{0}".format(lane["workspace_id"]) in result.stdout


def test_lane_add_with_worktree_policy_creates_worktree(tmp_path, monkeypatch, capsys):
    from agent_mesh.topology import resolve_lane_worktree_path

    repo_root = _init_real_git_repo(tmp_path, monkeypatch, capsys)

    exit_code, output = run_cli(["lane", "add", "my-lane"], capsys)
    assert exit_code == 0

    config = load_config(repo_root)
    lane = next(l for l in config["coordination"]["lanes"] if l["name"] == "my-lane")
    path = resolve_lane_worktree_path(repo_root, lane["workspace_id"], config["coordination"]["worktree_root"])
    assert path.exists()
    assert (path / ".git").exists()

    # Branch should exist
    result = subprocess.run(["git", "branch"], cwd=repo_root, capture_output=True, text=True)
    assert "wt/my-lane" in result.stdout


def test_provision_lane_failure_not_registered(tmp_path, monkeypatch, capsys):
    """A lane that fails to provision must not appear in the registry."""
    repo_root = _init_real_git_repo(tmp_path, monkeypatch, capsys)
    config = load_config(repo_root)

    # Manually create a directory at the expected lane path to force git worktree add to fail
    from agent_mesh.config import LaneEntry, load_project_config
    from agent_mesh.topology import resolve_lane_worktree_path
    proj_cfg = load_project_config(repo_root)
    blocking_path = resolve_lane_worktree_path(repo_root, "agent-mesh-tests-1", proj_cfg.coordination.worktree_root)
    blocking_path.mkdir(parents=True)
    (blocking_path / "blocker.txt").write_text("blocking\n")

    exit_code, output = run_cli(
        ["init", "--project-name", "demo", "--project-key", "APP",
         "--worktree-policy", "required", "--lanes", "1"],
        capsys,
    )
    # init succeeds (WARN emitted) but failed lane is NOT in registry
    assert exit_code == 0
    assert "WARN" in output
    config = load_config(repo_root)
    assert len(config["coordination"]["lanes"]) == 0


def test_lane_base_branch_diverged_detects_stale_lane(tmp_path):
    """lane_base_branch_diverged returns True when origin/main has commits the lane branch lacks."""
    repo_root = tmp_path / "demo-repo"
    repo_root.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo_root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=repo_root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=repo_root, check=True, capture_output=True)
    (repo_root / "a.txt").write_text("a\n")
    subprocess.run(["git", "add", "."], cwd=repo_root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "c1"], cwd=repo_root, check=True, capture_output=True)

    # Create the lane branch at this commit
    subprocess.run(["git", "branch", "wt/test-lane"], cwd=repo_root, check=True, capture_output=True)

    # Advance main by one commit
    (repo_root / "b.txt").write_text("b\n")
    subprocess.run(["git", "add", "."], cwd=repo_root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "c2"], cwd=repo_root, check=True, capture_output=True)

    # Simulate origin/main pointing to the new commit via a remote-tracking ref
    new_sha = subprocess.run(
        ["git", "rev-parse", "main"], cwd=repo_root, capture_output=True, text=True
    ).stdout.strip()
    subprocess.run(
        ["git", "update-ref", "refs/remotes/origin/main", new_sha],
        cwd=repo_root, check=True, capture_output=True,
    )

    from agent_mesh.config import LaneEntry
    from agent_mesh.topology import lane_base_branch_diverged
    lane = LaneEntry(name="test-lane", workspace_id="test-lane", worktree_path=str(tmp_path / "lane"))
    assert lane_base_branch_diverged(repo_root, lane, "main") is True


def test_lane_base_branch_diverged_returns_false_when_synced(tmp_path):
    """lane_base_branch_diverged returns False when the lane branch is up-to-date."""
    repo_root = tmp_path / "demo-repo"
    repo_root.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo_root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=repo_root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=repo_root, check=True, capture_output=True)
    (repo_root / "a.txt").write_text("a\n")
    subprocess.run(["git", "add", "."], cwd=repo_root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "c1"], cwd=repo_root, check=True, capture_output=True)

    sha = subprocess.run(
        ["git", "rev-parse", "main"], cwd=repo_root, capture_output=True, text=True
    ).stdout.strip()
    subprocess.run(["git", "branch", "wt/test-lane"], cwd=repo_root, check=True, capture_output=True)
    # origin/main at the same commit as the lane branch
    subprocess.run(
        ["git", "update-ref", "refs/remotes/origin/main", sha],
        cwd=repo_root, check=True, capture_output=True,
    )

    from agent_mesh.config import LaneEntry
    from agent_mesh.topology import lane_base_branch_diverged
    lane = LaneEntry(name="test-lane", workspace_id="test-lane", worktree_path=str(tmp_path / "lane"))
    assert lane_base_branch_diverged(repo_root, lane, "main") is False
