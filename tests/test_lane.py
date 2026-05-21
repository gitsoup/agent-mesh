"""Tests for mesh lane command and mesh init --lanes."""

import json
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
        "--yes",
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
    # worktree paths are siblings of the repo root
    for lane in lanes:
        path = Path(lane["worktree_path"])
        assert path.parent == repo_root.parent


def test_init_lanes_idempotent(tmp_path, monkeypatch, capsys):
    repo_root = init_repo(tmp_path, monkeypatch, capsys, lanes=1)
    first_config = load_config(repo_root)
    first_name = first_config["coordination"]["lanes"][0]["name"]

    # Re-run init with --lanes 2: should add one more, not duplicate
    exit_code, _ = run_cli(
        ["init", "--project-name", "demo", "--project-key", "APP",
         "--worktree-policy", "off", "--yes", "--lanes", "2"],
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
         "--worktree-policy", "off", "--yes", "--lanes", "1"],
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
