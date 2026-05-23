import io
import os
import subprocess
import json
from pathlib import Path

from agent_mesh.cli import _bootstrap_project_json, app, derive_project_key


def run_cli(args, capsys):
    exit_code = app(args)
    output = capsys.readouterr()
    return exit_code, output.out


def run_cli_with_stdin(args, stdin_text: str, capsys, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO(stdin_text))
    exit_code = app(args)
    output = capsys.readouterr()
    return exit_code, output.out


def init_repo(tmp_path: Path, monkeypatch, capsys) -> Path:
    repo_root = tmp_path / "demo-repo"
    (repo_root / ".git").mkdir(parents=True)
    monkeypatch.chdir(repo_root)
    exit_code, output = run_cli(
        [
            "init",
            "--project-name",
            "demo",
            "--project-key",
            "APP",
            "--provider",
            "local",
            "--worktree-policy",
            "off",
        ],
        capsys,
    )
    assert exit_code == 0
    assert "Initialized Agent Mesh" in output
    return repo_root


def init_real_repo(tmp_path: Path, monkeypatch, capsys, *, lanes: int = 0) -> Path:
    repo_root = tmp_path / "demo-repo"
    repo_root.mkdir(parents=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=repo_root, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "mesh@example.com"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Agent Mesh Tests"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    (repo_root / "README.md").write_text("demo\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo_root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo_root, check=True, capture_output=True)
    monkeypatch.chdir(repo_root)

    cli_args = [
        "init",
        "--project-name",
        "demo",
        "--project-key",
        "APP",
        "--provider",
        "local",
        "--worktree-policy",
        "required",
    ]
    if lanes:
        cli_args += ["--lanes", str(lanes)]
    exit_code, output = run_cli(cli_args, capsys)
    assert exit_code == 0
    assert "Initialized Agent Mesh" in output
    return repo_root


def init_real_repo_without_identity(tmp_path: Path, monkeypatch) -> Path:
    repo_root = tmp_path / "demo-repo"
    repo_root.mkdir(parents=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=repo_root, check=True, capture_output=True)
    (repo_root / "README.md").write_text("demo\n", encoding="utf-8")
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Agent Mesh Tests",
        "GIT_AUTHOR_EMAIL": "mesh@example.com",
        "GIT_COMMITTER_NAME": "Agent Mesh Tests",
        "GIT_COMMITTER_EMAIL": "mesh@example.com",
    }
    subprocess.run(["git", "add", "README.md"], cwd=repo_root, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        env=env,
    )
    monkeypatch.chdir(repo_root)
    return repo_root


def create_pending_coordination_scaffold(tmp_path: Path, monkeypatch) -> Path:
    from agent_mesh.config import load_project_config
    from agent_mesh.scaffold import init_repo
    from agent_mesh.topology import ensure_coordination_worktree

    repo_root = init_real_repo_without_identity(tmp_path, monkeypatch)
    _bootstrap_project_json(
        repo_root,
        "demo",
        "APP",
        "local",
        ["generic"],
        True,
        "required",
        None,
        120,
    )
    config = load_project_config(repo_root)
    coordination = ensure_coordination_worktree(repo_root, config)
    init_repo(
        repo_root=repo_root,
        project_name="demo",
        project_key="APP",
        provider="local",
        adapters=["generic"],
        worktree_policy="required",
        coordination_root=coordination.path,
    )
    return repo_root


def test_init_creates_agentic_scaffold(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root = init_repo(tmp_path, monkeypatch, capsys)

    assert (repo_root / ".agentic/project.json").exists()
    project = json.loads((repo_root / ".agentic/project.json").read_text(encoding="utf-8"))
    assert project["coordination"]["branch"] == "mesh/state"
    assert project["coordination"]["coordination_worktree"] is None
    assert (repo_root / ".agentic/context/CONTEXT.md").exists()
    assert (repo_root / ".agentic/workflows/claim.md").exists()
    assert (repo_root / ".agentic/workflows/ongoing.md").exists()
    ongoing = (repo_root / ".agentic/workflows/ongoing.md").read_text(encoding="utf-8")
    assert "already uses Agent Mesh" in ongoing
    assert "Startup inspection sequence" in ongoing
    assert "claim_stale_after_minutes" in ongoing
    assert "handoff" in ongoing
    assert (repo_root / ".agentic/skills/claim/SKILL.md").exists()
    assert (repo_root / ".github/workflows/agent-mesh-status.yml").exists()
    assert project["adapters"] == ["generic"]


def test_derive_project_key_prefers_meaningful_repo_tokens() -> None:
    assert derive_project_key("agent-mesh") == "MESH"
    assert derive_project_key("billing-api") == "BILL"
    assert derive_project_key("user-service") == "USER"
    assert derive_project_key("mesh") == "MESH"
    assert derive_project_key("app") == "APP"


def test_init_outside_git_repo_returns_friendly_error(tmp_path: Path, monkeypatch, capsys) -> None:
    outside = tmp_path / "outside"
    outside.mkdir(parents=True)
    monkeypatch.chdir(outside)

    exit_code, output = run_cli(["init"], capsys)

    assert exit_code == 1
    assert "`mesh init` must be run inside a git repository" in output
    assert "git init" in output


def test_init_rerun_skips_existing_files_without_force(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root = init_repo(tmp_path, monkeypatch, capsys)
    agents_path = repo_root / "AGENTS.md"
    agents_path.write_text("custom instructions\n", encoding="utf-8")

    exit_code, output = run_cli(
        [
            "init",
            "--project-name",
            "demo",
            "--project-key",
            "APP",
            "--provider",
            "local",
            "--worktree-policy",
            "off",
        ],
        capsys,
    )

    assert exit_code == 0
    assert "Skipped" in output
    assert agents_path.read_text(encoding="utf-8") == "custom instructions\n"


def test_init_warns_when_existing_agents_md_lacks_mesh_bootstrap(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    repo_root = tmp_path / "demo-repo"
    (repo_root / ".git").mkdir(parents=True)
    agents_path = repo_root / "AGENTS.md"
    agents_path.write_text("custom instructions\n", encoding="utf-8")
    monkeypatch.chdir(repo_root)

    exit_code, output = run_cli(
        [
            "init",
            "--project-name",
            "demo",
            "--project-key",
            "APP",
            "--provider",
            "local",
            "--worktree-policy",
            "off",
        ],
        capsys,
    )

    assert exit_code == 0
    assert agents_path.read_text(encoding="utf-8") == "custom instructions\n"
    assert (repo_root / ".agentic/AGENTS-BOOTSTRAP.md").exists()
    assert "WARNING: brownfield adoption is incomplete" in output
    assert "merge the bootstrap block from .agentic/AGENTS-BOOTSTRAP.md into AGENTS.md" in output


def test_skill_list_shows_adapter_install_status_in_configured_repo(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    repo_root = init_repo(tmp_path, monkeypatch, capsys)
    run_cli(["adapter", "install", "codex,claude"], capsys)

    exit_code, output = run_cli(["skill", "list"], capsys)

    assert exit_code == 0
    assert "skill\tsummary\tcanonical\tcodex\tclaude" in output
    assert (
        "claim\tClaim a ready work item and prepare implementation context.\tok\tinstalled\tinstalled"
        in output
    )
    assert (
        "diagnose\tDebug using a disciplined diagnosis loop.\tok\tinstalled\tinstalled"
        in output
    )
    assert repo_root.exists()


def test_skill_list_reports_missing_codex_wrapper_in_configured_repo(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    repo_root = init_repo(tmp_path, monkeypatch, capsys)
    run_cli(["adapter", "install", "codex,claude"], capsys)
    (repo_root / ".agents/skills/claim/SKILL.md").unlink()

    exit_code, output = run_cli(["skill", "list"], capsys)

    assert exit_code == 0
    assert (
        "claim\tClaim a ready work item and prepare implementation context.\tok\tmissing\tinstalled"
        in output
    )


def test_doctor_status_and_task_lifecycle(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root = init_repo(tmp_path, monkeypatch, capsys)

    exit_code, output = run_cli(["doctor"], capsys)
    assert exit_code == 0
    assert "OK: Agent Mesh state is valid." in output

    exit_code, output = run_cli(
        [
            "task",
            "add",
            "Implement auth endpoint",
            "--module",
            "api",
            "--acceptance",
            "Endpoint validates email input",
            "--acceptance",
            "Tests cover valid and invalid inputs",
        ],
        capsys,
    )
    assert exit_code == 0
    assert "Created task APP-1" in output

    work_item = json.loads((repo_root / ".agentic/work/APP-1.json").read_text(encoding="utf-8"))
    assert work_item["module"] == "api"
    assert work_item["status"] == "ready"

    exit_code, output = run_cli(["task", "list"], capsys)
    assert exit_code == 0
    assert "APP-1" in output

    exit_code, output = run_cli(["task", "show", "APP-1"], capsys)
    assert exit_code == 0
    assert "Implement auth endpoint" in output

    exit_code, output = run_cli(
        ["claim", "APP-1", "--agent", "codex", "--role", "implementer", "--no-push"],
        capsys,
    )
    assert exit_code == 0
    assert "Claimed APP-1" in output

    claim = json.loads((repo_root / ".agentic/claims/APP-1.json").read_text(encoding="utf-8"))
    assert claim["agent_runtime"] == "codex"
    assert claim["status"] == "in_progress"
    assert claim["workspace_id"].startswith("codex-")

    exit_code, output = run_cli(["status"], capsys)
    assert exit_code == 0
    assert "Shared root:" in output
    assert "Coordination: mesh/state @" in output
    assert "[missing]" in output
    assert "Tasks: 1" in output
    assert "in_progress: 1" in output
    assert "Claims: 1" in output
    assert "APP-1: codex [active] on feat/APP-1-implement-auth-endpoint" in output
    assert "Built dashboard" in output
    assert (repo_root / "dist/mesh-dashboard/index.html").exists()

    exit_code, output = run_cli(["pr", "--dry-run", "--work-id", "APP-1"], capsys)
    assert exit_code == 0
    assert "# APP-1: Implement auth endpoint" in output
    assert "## Evidence" in output
    assert "## Review Checklist" in output
    assert "Dry-run: review packet written" in output

    review_packet = json.loads(
        (repo_root / ".agentic/reviews/PR-APP-1.json").read_text(encoding="utf-8")
    )
    assert review_packet["work_id"] == "APP-1"
    assert review_packet["status"] == "pending_review"
    assert review_packet["context"]["claim"] == ".agentic/claims/APP-1.json"

    exit_code, output = run_cli(["dashboard", "build"], capsys)
    assert exit_code == 0
    assert "Built dashboard" in output
    dashboard = repo_root / "dist/mesh-dashboard/index.html"
    assert dashboard.exists()
    html = dashboard.read_text(encoding="utf-8")
    assert "Agent Mesh dashboard" in html
    assert "Task Explorer" in html
    assert "task-search" in html
    assert "sort-filter" in html


def test_status_skips_dashboard_when_disabled_in_config(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root = tmp_path / "demo-repo"
    (repo_root / ".git").mkdir(parents=True)
    monkeypatch.chdir(repo_root)
    exit_code, output = run_cli(
        [
            "init",
            "--project-name",
            "demo",
            "--project-key",
            "APP",
            "--provider",
            "local",
            "--worktree-policy",
            "off",
            "--no-dashboard",
        ],
        capsys,
    )
    assert exit_code == 0
    assert "Initialized Agent Mesh" in output

    exit_code, output = run_cli(["status"], capsys)
    assert exit_code == 0
    assert "Built dashboard" not in output
    assert not (repo_root / "dist/mesh-dashboard/index.html").exists()


def test_status_skip_dashboard_rebuild_flag(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root = init_repo(tmp_path, monkeypatch, capsys)

    exit_code, output = run_cli(["status", "--skip-dashboard-rebuild"], capsys)
    assert exit_code == 0
    assert "Built dashboard" not in output
    assert not (repo_root / "dist/mesh-dashboard/index.html").exists()


def test_claim_creates_dedicated_worktree_when_required(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root = tmp_path / "demo-repo"
    repo_root.mkdir(parents=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=repo_root, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "mesh@example.com"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Agent Mesh Tests"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    (repo_root / "README.md").write_text("demo\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo_root, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    monkeypatch.chdir(repo_root)

    exit_code, _ = run_cli(
        [
            "init",
            "--project-name",
            "demo",
            "--project-key",
            "APP",
            "--provider",
            "local",
            "--worktree-policy",
            "required",
        ],
        capsys,
    )
    assert exit_code == 0

    exit_code, _ = run_cli(["task", "add", "Implement auth endpoint", "--module", "api"], capsys)
    assert exit_code == 0

    exit_code, output = run_cli(
        ["claim", "APP-1", "--agent", "codex", "--role", "implementer", "--no-push"],
        capsys,
    )
    assert exit_code == 0
    assert "Worktree:" in output
    assert "REQUIRED: cd" in output

    coordination_root = repo_root.parent / "{0}-mesh-state".format(repo_root.name)
    claim = json.loads((coordination_root / ".agentic/claims/APP-1.json").read_text(encoding="utf-8"))
    assert claim["worktree"] is not None
    assert claim["workspace_id"].startswith("codex-")
    assert Path(claim["worktree"]).exists()

    current_branch = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    assert current_branch.stdout.strip() == "main"

    worktree_branch = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=Path(claim["worktree"]),
        check=True,
        capture_output=True,
        text=True,
    )
    assert worktree_branch.stdout.strip() == "feat/APP-1-implement-auth-endpoint"

    exit_code, output = run_cli(["status"], capsys)
    assert exit_code == 0
    assert claim["worktree"] in output
    assert "[active]" in output
    assert "via {0}".format(claim["workspace_id"]) in output


def test_claim_auto_selects_first_idle_lane(tmp_path: Path, monkeypatch, capsys) -> None:
    from agent_mesh.topology import resolve_lane_worktree_path

    repo_root = init_real_repo(tmp_path, monkeypatch, capsys, lanes=2)
    assert run_cli(["task", "add", "Implement auth endpoint", "--module", "api"], capsys)[0] == 0

    config = json.loads((repo_root / ".agentic/project.json").read_text(encoding="utf-8"))
    first_lane = config["coordination"]["lanes"][0]
    first_lane_path = resolve_lane_worktree_path(repo_root, first_lane["workspace_id"], config["coordination"]["worktree_root"])
    coordination_root = repo_root.parent / "{0}-mesh-state".format(repo_root.name)

    exit_code, output = run_cli(
        ["claim", "APP-1", "--agent", "codex", "--role", "implementer", "--no-push"],
        capsys,
    )
    assert exit_code == 0
    assert "Workspace: {0}".format(first_lane["workspace_id"]) in output
    assert "REQUIRED: cd {0}".format(first_lane_path) in output

    claim = json.loads((coordination_root / ".agentic/claims/APP-1.json").read_text(encoding="utf-8"))
    assert claim["workspace_id"] == first_lane["workspace_id"]
    assert claim["worktree"] == str(first_lane_path)

    branch = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=first_lane_path,
        check=True,
        capture_output=True,
        text=True,
    )
    assert branch.stdout.strip() == "feat/APP-1-implement-auth-endpoint"


def test_claim_reuses_named_lane_worktree(tmp_path: Path, monkeypatch, capsys) -> None:
    from agent_mesh.topology import resolve_lane_worktree_path

    repo_root = init_real_repo(tmp_path, monkeypatch, capsys, lanes=1)
    assert run_cli(["task", "add", "Implement auth endpoint", "--module", "api"], capsys)[0] == 0

    config = json.loads((repo_root / ".agentic/project.json").read_text(encoding="utf-8"))
    lane = config["coordination"]["lanes"][0]
    lane_path = resolve_lane_worktree_path(repo_root, lane["workspace_id"], config["coordination"]["worktree_root"])
    coordination_root = repo_root.parent / "{0}-mesh-state".format(repo_root.name)

    exit_code, output = run_cli(
        ["claim", "APP-1", "--lane", lane["name"], "--agent", "codex", "--role", "implementer", "--no-push"],
        capsys,
    )
    assert exit_code == 0
    assert "Worktree: {0}".format(lane_path) in output

    claim = json.loads((coordination_root / ".agentic/claims/APP-1.json").read_text(encoding="utf-8"))
    assert claim["workspace_id"] == lane["workspace_id"]
    assert claim["worktree"] == str(lane_path)


def test_claim_rejects_active_lane_via_workspace_id(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root = init_real_repo(tmp_path, monkeypatch, capsys, lanes=2)
    assert run_cli(["task", "add", "First task", "--module", "api"], capsys)[0] == 0
    assert run_cli(["task", "add", "Second task", "--module", "api"], capsys)[0] == 0

    config = json.loads((repo_root / ".agentic/project.json").read_text(encoding="utf-8"))
    lane = config["coordination"]["lanes"][0]

    exit_code, _ = run_cli(
        ["claim", "APP-1", "--lane", lane["name"], "--agent", "codex", "--role", "implementer", "--no-push"],
        capsys,
    )
    assert exit_code == 0

    exit_code, output = run_cli(
        ["claim", "APP-2", "--workspace-id", lane["workspace_id"], "--agent", "codex", "--role", "implementer", "--no-push"],
        capsys,
    )
    assert exit_code == 1
    assert "is active on branch feat/APP-1-first-task" in output


def test_claim_recreates_missing_lane_worktree(tmp_path: Path, monkeypatch, capsys) -> None:
    from agent_mesh.topology import resolve_lane_worktree_path

    repo_root = init_real_repo(tmp_path, monkeypatch, capsys, lanes=1)
    assert run_cli(["task", "add", "Implement auth endpoint", "--module", "api"], capsys)[0] == 0

    config = json.loads((repo_root / ".agentic/project.json").read_text(encoding="utf-8"))
    lane = config["coordination"]["lanes"][0]
    lane_path = resolve_lane_worktree_path(repo_root, lane["workspace_id"], config["coordination"]["worktree_root"])
    subprocess.run(["git", "worktree", "remove", "--force", str(lane_path)], cwd=repo_root, check=True, capture_output=True)
    assert not lane_path.exists()

    exit_code, output = run_cli(
        ["claim", "APP-1", "--lane", lane["name"], "--agent", "codex", "--role", "implementer", "--no-push"],
        capsys,
    )
    assert exit_code == 0
    assert lane_path.exists()
    assert "REQUIRED: cd {0}".format(lane_path) in output


def test_claim_errors_when_all_lanes_are_active(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root = init_real_repo(tmp_path, monkeypatch, capsys, lanes=2)
    assert run_cli(["task", "add", "First task", "--module", "api"], capsys)[0] == 0
    assert run_cli(["task", "add", "Second task", "--module", "api"], capsys)[0] == 0
    assert run_cli(["task", "add", "Third task", "--module", "api"], capsys)[0] == 0

    config = json.loads((repo_root / ".agentic/project.json").read_text(encoding="utf-8"))
    lanes = config["coordination"]["lanes"]

    assert run_cli(
        ["claim", "APP-1", "--lane", lanes[0]["name"], "--agent", "codex", "--role", "implementer", "--no-push"],
        capsys,
    )[0] == 0
    assert run_cli(
        ["claim", "APP-2", "--lane", lanes[1]["name"], "--agent", "codex", "--role", "implementer", "--no-push"],
        capsys,
    )[0] == 0

    exit_code, output = run_cli(
        ["claim", "APP-3", "--agent", "codex", "--role", "implementer", "--no-push"],
        capsys,
    )
    assert exit_code == 1
    assert "no idle lanes available" in output


def test_claim_rejects_dirty_lane_worktree(tmp_path: Path, monkeypatch, capsys) -> None:
    from agent_mesh.topology import resolve_lane_worktree_path

    repo_root = init_real_repo(tmp_path, monkeypatch, capsys, lanes=1)
    assert run_cli(["task", "add", "Implement auth endpoint", "--module", "api"], capsys)[0] == 0

    config = json.loads((repo_root / ".agentic/project.json").read_text(encoding="utf-8"))
    lane = config["coordination"]["lanes"][0]
    lane_path = resolve_lane_worktree_path(repo_root, lane["workspace_id"], config["coordination"]["worktree_root"])
    (lane_path / "scratch.txt").write_text("dirty\n", encoding="utf-8")

    exit_code, output = run_cli(
        ["claim", "APP-1", "--lane", lane["name"], "--agent", "codex", "--role", "implementer", "--no-push"],
        capsys,
    )
    assert exit_code == 1
    assert "lane worktree is dirty on branch wt/{0}".format(lane["workspace_id"]) in output


def test_claim_retries_after_push_conflict(tmp_path: Path, monkeypatch, capsys) -> None:
    from subprocess import CompletedProcess

    repo_root = init_real_repo(tmp_path, monkeypatch, capsys, lanes=1)
    assert run_cli(["task", "add", "Implement auth endpoint", "--module", "api"], capsys)[0] == 0
    coordination_root = repo_root.parent / "{0}-mesh-state".format(repo_root.name)
    claim_path = coordination_root / ".agentic/claims/APP-1.json"

    push_attempts = {"count": 0}

    monkeypatch.setattr("agent_mesh.cli.coordination_remote_exists", lambda _: True)

    def fake_push(_coordination_root, _branch):
        push_attempts["count"] += 1
        if push_attempts["count"] == 1:
            return CompletedProcess(
                args=["git", "push"],
                returncode=1,
                stdout="",
                stderr="! [rejected] HEAD -> mesh/state (fetch first)",
            )
        return CompletedProcess(args=["git", "push"], returncode=0, stdout="", stderr="")

    def fake_sync(_coordination_root, _branch):
        if claim_path.exists():
            claim_path.unlink()

    monkeypatch.setattr("agent_mesh.cli.push_coordination_state", fake_push)
    monkeypatch.setattr("agent_mesh.cli.sync_coordination_state_from_remote", fake_sync)

    exit_code, output = run_cli(
        ["claim", "APP-1", "--agent", "codex", "--role", "implementer"],
        capsys,
    )
    assert exit_code == 0
    assert "Claimed APP-1" in output
    assert push_attempts["count"] == 2
    assert claim_path.exists()


def test_claim_retry_errors_when_work_item_status_changes(tmp_path: Path, monkeypatch, capsys) -> None:
    from subprocess import CompletedProcess

    repo_root = init_real_repo(tmp_path, monkeypatch, capsys, lanes=1)
    assert run_cli(["task", "add", "Implement auth endpoint", "--module", "api"], capsys)[0] == 0
    coordination_root = repo_root.parent / "{0}-mesh-state".format(repo_root.name)
    claim_path = coordination_root / ".agentic/claims/APP-1.json"
    work_path = coordination_root / ".agentic/work/APP-1.json"

    push_attempts = {"count": 0}
    monkeypatch.setattr("agent_mesh.cli.coordination_remote_exists", lambda _: True)

    def fake_push(_coordination_root, _branch):
        push_attempts["count"] += 1
        return CompletedProcess(
            args=["git", "push"],
            returncode=1,
            stdout="",
            stderr="! [rejected] HEAD -> mesh/state (fetch first)",
        )

    def fake_sync(_coordination_root, _branch):
        if claim_path.exists():
            claim_path.unlink()
        work_item = json.loads(work_path.read_text(encoding="utf-8"))
        work_item["status"] = "done"
        work_path.write_text(json.dumps(work_item, indent=2) + "\n", encoding="utf-8")

    monkeypatch.setattr("agent_mesh.cli.push_coordination_state", fake_push)
    monkeypatch.setattr("agent_mesh.cli.sync_coordination_state_from_remote", fake_sync)

    exit_code, output = run_cli(
        ["claim", "APP-1", "--agent", "codex", "--role", "implementer"],
        capsys,
    )
    assert exit_code == 1
    assert "claim lost push race for APP-1; work item is now done" in output
    assert push_attempts["count"] == 1


def test_init_creates_coordination_worktree_for_real_git_repo(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    repo_root = tmp_path / "demo-repo"
    repo_root.mkdir(parents=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=repo_root, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "mesh@example.com"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Agent Mesh Tests"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    (repo_root / "README.md").write_text("demo\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo_root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo_root, check=True, capture_output=True)
    monkeypatch.chdir(repo_root)

    exit_code, output = run_cli(
        [
            "init",
            "--project-name",
            "demo",
            "--project-key",
            "APP",
            "--provider",
            "local",
            "--adapters",
            "generic,codex,claude",
            "--worktree-policy",
            "required",
        ],
        capsys,
    )
    assert exit_code == 0
    assert "Coordination worktree created: mesh/state @" in output

    project = json.loads((repo_root / ".agentic/project.json").read_text(encoding="utf-8"))
    coordination_path = repo_root.parent / "{0}-mesh-state".format(repo_root.name)
    assert coordination_path.exists()
    assert (
        subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=coordination_path,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        == project["coordination"]["branch"]
    )


def test_init_without_git_identity_fails_preflight_before_writing_state(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    repo_root = init_real_repo_without_identity(tmp_path, monkeypatch)

    exit_code, output = run_cli(
        [
            "init",
            "--project-name",
            "demo",
            "--project-key",
            "APP",
            "--provider",
            "local",
            "--worktree-policy",
            "required",
        ],
        capsys,
    )

    assert exit_code == 1
    assert "ERROR: git identity is not configured for this repository." in output
    assert 'Run: git config user.name "Your Name"' in output
    assert 'Run: git config user.email "you@example.com"' in output

    coordination_path = repo_root.parent / "{0}-mesh-state".format(repo_root.name)
    assert not coordination_path.exists()
    assert not (repo_root / ".agentic/project.json").exists()


def test_sync_finalizes_pending_coordination_scaffold_after_git_identity_is_configured(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    repo_root = create_pending_coordination_scaffold(tmp_path, monkeypatch)
    subprocess.run(
        ["git", "config", "user.email", "mesh@example.com"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Agent Mesh Tests"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )

    exit_code, output = run_cli(["sync"], capsys)

    assert exit_code == 0
    assert "Committed pending coordination scaffold" in output
    assert "OK: Agent Mesh state is valid." in output

    coordination_path = repo_root.parent / "{0}-mesh-state".format(repo_root.name)
    head = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=coordination_path,
        check=False,
        capture_output=True,
        text=True,
    )
    assert head.returncode == 0
    status = subprocess.run(
        ["git", "status", "--short"],
        cwd=coordination_path,
        check=True,
        capture_output=True,
        text=True,
    )
    assert status.stdout.strip() == ""


def test_init_rerun_with_pending_coordination_scaffold_stays_actionable(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    repo_root = create_pending_coordination_scaffold(tmp_path, monkeypatch)

    exit_code, output = run_cli(
        [
            "init",
            "--project-name",
            "demo",
            "--project-key",
            "APP",
            "--provider",
            "local",
            "--worktree-policy",
            "required",
        ],
        capsys,
    )

    assert exit_code == 0
    assert "invalid" not in output
    assert "Coordination worktree noop: mesh/state @" in output
    assert "coordination scaffold is pending" in output


def test_init_rerun_with_ready_coordination_worktree_skips_scaffold_commit_noise(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    repo_root = init_real_repo(tmp_path, monkeypatch, capsys)

    exit_code, output = run_cli(
        [
            "init",
            "--project-name",
            "demo",
            "--project-key",
            "APP",
            "--provider",
            "local",
            "--worktree-policy",
            "required",
        ],
        capsys,
    )

    assert exit_code == 0
    assert "Coordination worktree noop: mesh/state @" in output
    assert "could not commit coordination scaffold" not in output


def test_init_recovers_when_coordination_worktree_path_was_deleted_manually(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    repo_root = init_real_repo(tmp_path, monkeypatch, capsys)
    coordination_path = repo_root.parent / "{0}-mesh-state".format(repo_root.name)
    subprocess.run(["rm", "-rf", str(coordination_path)], check=True, capture_output=True)

    exit_code, output = run_cli(
        [
            "init",
            "--project-name",
            "demo",
            "--project-key",
            "APP",
            "--provider",
            "local",
            "--worktree-policy",
            "required",
        ],
        capsys,
    )

    assert exit_code == 0
    assert "Coordination worktree created: mesh/state @" in output
    assert "failed to create coordination worktree" not in output
    assert coordination_path.exists()


def test_pr_dry_run_reports_review_packet_path_from_task_worktree(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    repo_root = tmp_path / "demo-repo"
    repo_root.mkdir(parents=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=repo_root, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "mesh@example.com"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Agent Mesh Tests"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    (repo_root / "README.md").write_text("demo\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo_root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo_root, check=True, capture_output=True)
    monkeypatch.chdir(repo_root)

    exit_code, _ = run_cli(
        [
            "init",
            "--project-name",
            "demo",
            "--project-key",
            "APP",
            "--provider",
            "local",
            "--adapters",
            "generic,codex,claude",
            "--worktree-policy",
            "required",
        ],
        capsys,
    )
    assert exit_code == 0
    assert run_cli(["task", "add", "Implement auth endpoint", "--module", "api"], capsys)[0] == 0
    assert run_cli(["claim", "APP-1", "--agent", "codex", "--role", "implementer"], capsys)[0] == 0

    coordination_root = repo_root.parent / "{0}-mesh-state".format(repo_root.name)
    claim = json.loads((coordination_root / ".agentic/claims/APP-1.json").read_text(encoding="utf-8"))
    monkeypatch.chdir(Path(claim["worktree"]))

    exit_code, output = run_cli(["pr", "--dry-run", "--work-id", "APP-1"], capsys)
    assert exit_code == 0
    expected_path = coordination_root / ".agentic/reviews/PR-APP-1.json"
    assert "Dry-run: review packet written to {0}".format(expected_path) in output
    assert expected_path.exists()


def test_sync_recreates_missing_coordination_worktree(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root = tmp_path / "demo-repo"
    repo_root.mkdir(parents=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=repo_root, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "mesh@example.com"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Agent Mesh Tests"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    (repo_root / "README.md").write_text("demo\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo_root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo_root, check=True, capture_output=True)
    monkeypatch.chdir(repo_root)

    exit_code, _ = run_cli(
        [
            "init",
            "--project-name",
            "demo",
            "--project-key",
            "APP",
            "--provider",
            "local",
            "--adapters",
            "generic,codex,claude",
            "--worktree-policy",
            "required",
        ],
        capsys,
    )
    assert exit_code == 0

    coordination_path = repo_root.parent / "{0}-mesh-state".format(repo_root.name)
    subprocess.run(["git", "worktree", "remove", "--force", str(coordination_path)], cwd=repo_root, check=True, capture_output=True)
    assert not coordination_path.exists()

    exit_code, output = run_cli(["sync"], capsys)
    assert exit_code == 0
    assert "Coordination worktree created: mesh/state @" in output
    assert coordination_path.exists()


def test_coordination_worktree_uses_orphan_branch(tmp_path: Path, monkeypatch, capsys) -> None:
    """mesh/state must be an orphan branch with no shared history with main."""
    repo_root = tmp_path / "demo-repo"
    repo_root.mkdir(parents=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=repo_root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "mesh@example.com"], cwd=repo_root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Agent Mesh Tests"], cwd=repo_root, check=True, capture_output=True)
    (repo_root / "README.md").write_text("demo\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo_root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo_root, check=True, capture_output=True)
    monkeypatch.chdir(repo_root)

    exit_code, _ = run_cli(
        ["init", "--project-name", "demo", "--project-key", "APP", "--provider", "local",
         "--adapters", "generic,codex,claude", "--worktree-policy", "required"],
        capsys,
    )
    assert exit_code == 0

    # The root commit of mesh/state must have no parent (orphan chain)
    root_result = subprocess.run(
        ["git", "rev-list", "--max-parents=0", "mesh/state"],
        cwd=repo_root, capture_output=True, text=True, check=True
    )
    root_commit = root_result.stdout.strip()
    parent_result = subprocess.run(
        ["git", "rev-parse", "{0}^".format(root_commit)],
        cwd=repo_root, capture_output=True, text=True
    )
    assert parent_result.returncode != 0, "root commit of mesh/state must have no parent (orphan branch)"

    # mesh/state and main must share no common ancestor
    main_root = subprocess.run(
        ["git", "rev-list", "--max-parents=0", "main"],
        cwd=repo_root, capture_output=True, text=True, check=True
    ).stdout.strip()
    assert root_commit != main_root, "mesh/state and main must have different root commits (no shared history)"


def test_claim_resume_updates_existing_claim(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root = init_repo(tmp_path, monkeypatch, capsys)

    exit_code, _ = run_cli(["task", "add", "Implement auth endpoint", "--module", "api"], capsys)
    assert exit_code == 0

    exit_code, _ = run_cli(
        ["claim", "APP-1", "--agent", "claude-code", "--role", "implementer", "--machine", "old-box"],
        capsys,
    )
    assert exit_code == 0

    exit_code, output = run_cli(
        ["claim", "APP-1", "--resume", "--agent", "codex", "--role", "implementer", "--machine", "new-box"],
        capsys,
    )
    assert exit_code == 0
    assert "Resumed APP-1" in output

    claim = json.loads((repo_root / ".agentic/claims/APP-1.json").read_text(encoding="utf-8"))
    assert claim["claimed_by"] == "agent:codex:new-box"
    assert claim["events"][-1]["action"] == "resumed"
    assert claim["workspace_id"] == "claude-code-old-box"


def test_claim_takeover_requires_stale_claim(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root = init_repo(tmp_path, monkeypatch, capsys)

    exit_code, _ = run_cli(["task", "add", "Implement auth endpoint", "--module", "api"], capsys)
    assert exit_code == 0

    exit_code, _ = run_cli(
        ["claim", "APP-1", "--agent", "claude-code", "--role", "implementer", "--machine", "old-box"],
        capsys,
    )
    assert exit_code == 0

    exit_code, output = run_cli(
        ["claim", "APP-1", "--takeover", "--agent", "codex", "--role", "implementer", "--machine", "new-box"],
        capsys,
    )
    assert exit_code == 1
    assert "still active" in output


def test_claim_takeover_reassigns_stale_claim(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root = init_repo(tmp_path, monkeypatch, capsys)

    exit_code, _ = run_cli(["task", "add", "Implement auth endpoint", "--module", "api"], capsys)
    assert exit_code == 0

    stale_claim_path = repo_root / ".agentic/claims/APP-1.json"
    stale_claim_path.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "work_id": "APP-1",
                "status": "in_progress",
                "claimed_by": "agent:claude-code:old-box",
                "agent_runtime": "claude-code",
                "role": "implementer",
                "machine": "old-box",
                "workspace_id": "claude-code-old-box",
                "worktree": None,
                "branch": "feat/APP-1-implement-auth-endpoint",
                "claimed_at": "2026-05-17T00:00:00Z",
                "last_seen": "2026-05-17T00:00:00Z",
                "evidence": [],
                "events": [],
            }
        ),
        encoding="utf-8",
    )
    work_item = json.loads((repo_root / ".agentic/work/APP-1.json").read_text(encoding="utf-8"))
    work_item["status"] = "in_progress"
    (repo_root / ".agentic/work/APP-1.json").write_text(json.dumps(work_item, indent=2) + "\n", encoding="utf-8")

    exit_code, output = run_cli(["status"], capsys)
    assert exit_code == 0
    assert "[stale]" in output

    exit_code, output = run_cli(
        ["claim", "APP-1", "--takeover", "--agent", "codex", "--role", "implementer", "--machine", "new-box"],
        capsys,
    )
    assert exit_code == 0
    assert "Took over stale claim" in output

    claim = json.loads(stale_claim_path.read_text(encoding="utf-8"))
    assert claim["claimed_by"] == "agent:codex:new-box"
    assert claim["events"][-1]["action"] == "taken_over"
    assert claim["workspace_id"].startswith("codex-new-box-")


def test_review_shows_acceptance_criteria_from_shared_root(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root, _, claim = _setup_repo_with_claim(tmp_path, monkeypatch, capsys)
    monkeypatch.chdir(Path(claim["worktree"]))
    assert run_cli(["pr", "--dry-run", "--work-id", "APP-1"], capsys)[0] == 0

    monkeypatch.chdir(repo_root)
    exit_code, output = run_cli(["review", "PR-APP-1"], capsys)
    assert exit_code == 0
    assert "Review packet: PR-APP-1" in output
    assert "Branch:" in output
    assert "Requested role:" in output
    assert "Next: review the PR" in output
    assert "Resolved workspace differs" not in output
    assert "REQUIRED: cd" not in output


def test_review_shows_pr_url_when_present(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root, coordination_root, claim = _setup_repo_with_claim(tmp_path, monkeypatch, capsys)
    monkeypatch.chdir(Path(claim["worktree"]))
    assert run_cli(["pr", "--dry-run", "--work-id", "APP-1"], capsys)[0] == 0

    # inject a PR URL into the review packet
    packet_path = coordination_root / ".agentic/reviews/PR-APP-1.json"
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    packet["pr"]["url"] = "https://github.com/example/repo/pull/42"
    packet_path.write_text(json.dumps(packet, indent=2), encoding="utf-8")

    monkeypatch.chdir(repo_root)
    exit_code, output = run_cli(["review", "PR-APP-1"], capsys)
    assert exit_code == 0
    assert "PR: https://github.com/example/repo/pull/42" in output


def test_review_renders_evidence_when_present_and_omits_when_absent(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root, coordination_root, claim = _setup_repo_with_claim(tmp_path, monkeypatch, capsys)
    monkeypatch.chdir(Path(claim["worktree"]))
    assert run_cli(["pr", "--dry-run", "--work-id", "APP-1"], capsys)[0] == 0

    packet_path = coordination_root / ".agentic/reviews/PR-APP-1.json"

    # without evidence — should not emit Evidence section
    monkeypatch.chdir(repo_root)
    _, output_no_evidence = run_cli(["review", "PR-APP-1"], capsys)
    assert "Evidence:" not in output_no_evidence

    # inject evidence
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    packet["evidence"] = [{"kind": "test", "command": "pytest -q", "summary": "44 passed", "result": "pass", "created_at": "2026-01-01T00:00:00Z"}]
    packet_path.write_text(json.dumps(packet, indent=2), encoding="utf-8")

    _, output_with_evidence = run_cli(["review", "PR-APP-1"], capsys)
    assert "Evidence:" in output_with_evidence
    assert "[test] pytest -q -> 44 passed" in output_with_evidence


def test_review_output_is_identical_from_worktree_and_shared_root(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root, _, claim = _setup_repo_with_claim(tmp_path, monkeypatch, capsys)
    monkeypatch.chdir(Path(claim["worktree"]))
    assert run_cli(["pr", "--dry-run", "--work-id", "APP-1"], capsys)[0] == 0

    _, output_from_worktree = run_cli(["review", "PR-APP-1"], capsys)
    monkeypatch.chdir(repo_root)
    _, output_from_root = run_cli(["review", "PR-APP-1"], capsys)

    assert output_from_worktree == output_from_root


def test_review_works_when_worktree_policy_off(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root, _, claim = _setup_repo_with_claim(tmp_path, monkeypatch, capsys, worktree_policy="off")
    assert not claim.get("worktree"), "precondition: worktree_policy=off must not record a worktree"
    assert run_cli(["pr", "--dry-run", "--work-id", "APP-1"], capsys)[0] == 0

    exit_code, output = run_cli(["review", "PR-APP-1"], capsys)
    assert exit_code == 0
    assert "Review packet: PR-APP-1" in output
    assert "Next: review the PR" in output


def test_review_errors_on_missing_packet(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root, _, _ = _setup_repo_with_claim(tmp_path, monkeypatch, capsys)
    monkeypatch.chdir(repo_root)
    exit_code, output = run_cli(["review", "PR-APP-NONEXISTENT"], capsys)
    assert exit_code == 1
    assert "ERROR:" in output


def test_doctor_reports_cross_file_errors(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root = init_repo(tmp_path, monkeypatch, capsys)
    bad_claim = repo_root / ".agentic/claims/APP-404.json"
    bad_claim.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "work_id": "APP-404",
                "status": "in_progress",
                "claimed_by": "agent:codex:testbox",
                "agent_runtime": "codex",
                "role": "implementer",
                "machine": "testbox",
                "worktree": None,
                "branch": "feat/APP-404-missing",
                "claimed_at": "2026-05-17T00:00:00Z",
                "last_seen": "2026-05-17T00:00:00Z",
                "evidence": [],
            }
        ),
        encoding="utf-8",
    )

    exit_code, output = run_cli(["doctor"], capsys)
    assert exit_code == 1
    assert "Claim references missing work item: APP-404" in output


def test_skill_list_falls_back_to_catalog_outside_configured_repo(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    repo_root = tmp_path / "demo-repo"
    (repo_root / ".git").mkdir(parents=True)
    monkeypatch.chdir(repo_root)

    exit_code, output = run_cli(["skill", "list"], capsys)

    assert exit_code == 0
    assert "skill\tsummary\tcanonical" not in output
    assert "claim\tClaim a ready work item and prepare implementation context." in output


def test_merge_archives_claim_and_marks_work_done(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root = init_repo(tmp_path, monkeypatch, capsys)

    run_cli(["task", "add", "Implement auth endpoint", "--module", "api"], capsys)
    run_cli(["claim", "APP-1", "--agent", "codex", "--role", "implementer", "--no-push"], capsys)
    run_cli(["pr", "--dry-run", "--work-id", "APP-1"], capsys)

    exit_code, output = run_cli(["merge", "APP-1", "--no-push", "--skip-merge-check"], capsys)

    assert exit_code == 0
    assert "Archived claim: APP-1.json" in output
    assert "Marked APP-1 done" in output
    assert not (repo_root / ".agentic/claims/APP-1.json").exists()
    assert (repo_root / ".agentic/claims/archive/APP-1.json").exists()
    work_item = json.loads((repo_root / ".agentic/work/APP-1.json").read_text(encoding="utf-8"))
    assert work_item["status"] == "done"
    review = json.loads((repo_root / ".agentic/reviews/PR-APP-1.json").read_text(encoding="utf-8"))
    assert review["status"] == "merged"


def test_merge_removes_task_worktree(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root = tmp_path / "demo-repo"
    repo_root.mkdir(parents=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=repo_root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "mesh@example.com"], cwd=repo_root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Agent Mesh Tests"], cwd=repo_root, check=True, capture_output=True)
    (repo_root / "README.md").write_text("demo\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo_root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo_root, check=True, capture_output=True)
    monkeypatch.chdir(repo_root)

    run_cli(
        ["init", "--project-name", "demo", "--project-key", "APP", "--provider", "local",
         "--adapters", "generic,codex,claude", "--worktree-policy", "required"],
        capsys,
    )
    run_cli(["task", "add", "Implement auth endpoint", "--module", "api"], capsys)
    run_cli(["claim", "APP-1", "--agent", "codex", "--role", "implementer", "--no-push"], capsys)

    coordination_root = repo_root.parent / "{0}-mesh-state".format(repo_root.name)
    claim = json.loads((coordination_root / ".agentic/claims/APP-1.json").read_text(encoding="utf-8"))
    worktree_path = Path(claim["worktree"])
    assert worktree_path.exists()

    # pr must run from the task worktree (workspace guard enforces this)
    monkeypatch.chdir(worktree_path)
    run_cli(["pr", "--dry-run", "--work-id", "APP-1"], capsys)
    monkeypatch.chdir(repo_root)

    exit_code, output = run_cli(["merge", "APP-1", "--no-push", "--skip-merge-check"], capsys)

    assert exit_code == 0
    assert "Removed worktree:" in output
    assert not worktree_path.exists()
    assert not (coordination_root / ".agentic/claims/APP-1.json").exists()
    assert (coordination_root / ".agentic/claims/archive/APP-1.json").exists()


def test_merge_returns_lane_to_idle_and_keeps_worktree(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root = init_real_repo(tmp_path, monkeypatch, capsys, lanes=1)
    run_cli(["task", "add", "Implement auth endpoint", "--module", "api"], capsys)
    run_cli(["claim", "APP-1", "--agent", "codex", "--role", "implementer", "--no-push"], capsys)

    coordination_root = repo_root.parent / "{0}-mesh-state".format(repo_root.name)
    config = json.loads((repo_root / ".agentic/project.json").read_text(encoding="utf-8"))
    lane = config["coordination"]["lanes"][0]
    claim = json.loads((coordination_root / ".agentic/claims/APP-1.json").read_text(encoding="utf-8"))
    worktree_path = Path(claim["worktree"])

    monkeypatch.chdir(worktree_path)
    run_cli(["pr", "--dry-run", "--work-id", "APP-1"], capsys)
    monkeypatch.chdir(repo_root)

    exit_code, output = run_cli(["merge", "APP-1", "--no-push", "--skip-merge-check"], capsys)

    assert exit_code == 0
    assert "Returned lane to base branch: wt/{0}".format(lane["workspace_id"]) in output
    assert "Reset lane worktree to " in output
    assert worktree_path.exists()
    assert not (coordination_root / ".agentic/claims/APP-1.json").exists()
    assert (coordination_root / ".agentic/claims/archive/APP-1.json").exists()

    branch_result = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=worktree_path,
        check=True,
        capture_output=True,
        text=True,
    )
    assert branch_result.stdout.strip() == "wt/{0}".format(lane["workspace_id"])

    lane_list_exit, lane_list_output = run_cli(["lane", "list"], capsys)
    assert lane_list_exit == 0
    assert "{0}\tidle\twt/{0}".format(lane["workspace_id"]) in lane_list_output


def test_merge_commits_coordination_state_changes(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root = _init_real_git_repo(tmp_path, monkeypatch, capsys)
    run_cli(["task", "add", "Implement auth endpoint", "--module", "api"], capsys)
    run_cli(["claim", "APP-1", "--agent", "codex", "--role", "implementer", "--no-push"], capsys)

    coordination_root = repo_root.parent / "{0}-mesh-state".format(repo_root.name)
    claim = json.loads((coordination_root / ".agentic/claims/APP-1.json").read_text(encoding="utf-8"))
    monkeypatch.chdir(Path(claim["worktree"]))
    run_cli(["pr", "--dry-run", "--work-id", "APP-1"], capsys)
    monkeypatch.chdir(repo_root)

    exit_code, output = run_cli(["merge", "APP-1", "--no-push", "--skip-merge-check"], capsys)

    assert exit_code == 0, output
    status = subprocess.run(
        ["git", "status", "--short"],
        cwd=coordination_root,
        check=True,
        capture_output=True,
        text=True,
    )
    assert status.stdout.strip() == ""

    latest_commit = subprocess.run(
        ["git", "log", "--oneline", "-1"],
        cwd=coordination_root,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "Close APP-1; archive claim, mark merged" in latest_commit.stdout


def test_merge_skips_worktree_removal_when_already_absent(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root = tmp_path / "demo-repo"
    repo_root.mkdir(parents=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=repo_root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "mesh@example.com"], cwd=repo_root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Agent Mesh Tests"], cwd=repo_root, check=True, capture_output=True)
    (repo_root / "README.md").write_text("demo\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo_root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo_root, check=True, capture_output=True)
    monkeypatch.chdir(repo_root)

    run_cli(
        ["init", "--project-name", "demo", "--project-key", "APP", "--provider", "local",
         "--adapters", "generic,codex,claude", "--worktree-policy", "required"],
        capsys,
    )
    run_cli(["task", "add", "Implement auth endpoint", "--module", "api"], capsys)
    run_cli(["claim", "APP-1", "--agent", "codex", "--role", "implementer", "--no-push"], capsys)

    # Simulate worktree already removed (e.g. by a previous partial merge)
    coordination_root = repo_root.parent / "{0}-mesh-state".format(repo_root.name)
    claim_data = json.loads((coordination_root / ".agentic/claims/APP-1.json").read_text(encoding="utf-8"))
    worktree_path = Path(claim_data["worktree"])
    subprocess.run(["git", "worktree", "remove", "--force", str(worktree_path)], cwd=repo_root, check=True, capture_output=True)
    assert not worktree_path.exists()
    run_cli(["pr", "--dry-run", "--work-id", "APP-1"], capsys)

    exit_code, output = run_cli(["merge", "APP-1", "--no-push", "--skip-merge-check"], capsys)

    assert exit_code == 0
    assert "Worktree already absent" in output
    assert "Marked APP-1 done" in output


def test_merge_errors_on_missing_claim(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root = init_repo(tmp_path, monkeypatch, capsys)
    run_cli(["task", "add", "Implement auth endpoint", "--module", "api"], capsys)

    exit_code, output = run_cli(["merge", "APP-1", "--no-push"], capsys)

    assert exit_code == 1
    assert "no active claim" in output


def test_merge_blocks_when_branch_not_merged(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root = init_repo(tmp_path, monkeypatch, capsys)
    run_cli(["task", "add", "Implement auth endpoint", "--module", "api"], capsys)
    run_cli(["claim", "APP-1", "--agent", "codex", "--role", "implementer", "--no-push"], capsys)

    exit_code, output = run_cli(["merge", "APP-1", "--no-push"], capsys)

    assert exit_code == 1
    assert "does not appear merged" in output
    assert (repo_root / ".agentic/claims/APP-1.json").exists()


def test_merge_skip_merge_check_bypasses_guard(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root = init_repo(tmp_path, monkeypatch, capsys)
    run_cli(["task", "add", "Implement auth endpoint", "--module", "api"], capsys)
    run_cli(["claim", "APP-1", "--agent", "codex", "--role", "implementer", "--no-push"], capsys)
    run_cli(["pr", "--dry-run", "--work-id", "APP-1"], capsys)

    exit_code, output = run_cli(["merge", "APP-1", "--no-push", "--skip-merge-check"], capsys)

    assert exit_code == 0
    assert "Marked APP-1 done" in output


def test_merge_warns_on_missing_review_packet(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root = init_repo(tmp_path, monkeypatch, capsys)
    run_cli(["task", "add", "Implement auth endpoint", "--module", "api"], capsys)
    run_cli(["claim", "APP-1", "--agent", "codex", "--role", "implementer", "--no-push"], capsys)

    exit_code, output = run_cli(["merge", "APP-1", "--no-push", "--skip-merge-check"], capsys)

    assert exit_code == 2
    assert "WARNING: no review packet found" in output
    assert "Marked APP-1 done" in output


def test_merge_returns_exit_2_on_warnings(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root = init_repo(tmp_path, monkeypatch, capsys)
    run_cli(["task", "add", "Implement auth endpoint", "--module", "api"], capsys)
    run_cli(["claim", "APP-1", "--agent", "codex", "--role", "implementer", "--no-push"], capsys)

    # No PR packet — triggers a warning → exit 2
    exit_code, output = run_cli(["merge", "APP-1", "--no-push", "--skip-merge-check"], capsys)

    assert exit_code == 2
    assert "WARNING" in output


def test_merge_reconciles_review_packet_with_nonstandard_filename(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root = init_repo(tmp_path, monkeypatch, capsys)
    run_cli(["task", "add", "Implement auth endpoint", "--module", "api"], capsys)
    run_cli(["claim", "APP-1", "--agent", "codex", "--role", "implementer", "--no-push"], capsys)
    run_cli(["pr", "--dry-run", "--work-id", "APP-1"], capsys)

    review_path = repo_root / ".agentic/reviews/PR-APP-1.json"
    renamed_path = repo_root / ".agentic/reviews/review-request-app-1.json"
    review_path.rename(renamed_path)

    exit_code, output = run_cli(["merge", "APP-1", "--no-push", "--skip-merge-check"], capsys)

    assert exit_code == 0
    assert "Marked review packet merged: PR-APP-1" in output
    review = json.loads(renamed_path.read_text(encoding="utf-8"))
    assert review["status"] == "merged"


def test_sync_reconciles_pending_review_for_completed_work(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root = init_repo(tmp_path, monkeypatch, capsys)
    run_cli(["task", "add", "Implement auth endpoint", "--module", "api"], capsys)
    run_cli(["claim", "APP-1", "--agent", "codex", "--role", "implementer", "--no-push"], capsys)
    run_cli(["pr", "--dry-run", "--work-id", "APP-1"], capsys)

    work_path = repo_root / ".agentic/work/APP-1.json"
    work_item = json.loads(work_path.read_text(encoding="utf-8"))
    work_item["status"] = "done"
    work_path.write_text(json.dumps(work_item, indent=2) + "\n", encoding="utf-8")

    claim_path = repo_root / ".agentic/claims/APP-1.json"
    archive_path = repo_root / ".agentic/claims/archive/APP-1.json"
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    claim_path.rename(archive_path)

    exit_code, output = run_cli(["sync"], capsys)

    assert exit_code == 0
    assert "Reconciled review packet to merged: PR-APP-1" in output
    review = json.loads((repo_root / ".agentic/reviews/PR-APP-1.json").read_text(encoding="utf-8"))
    assert review["status"] == "merged"


def test_merge_blocks_on_coordination_worktree(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root = tmp_path / "demo-repo"
    repo_root.mkdir(parents=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=repo_root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "mesh@example.com"], cwd=repo_root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Agent Mesh Tests"], cwd=repo_root, check=True, capture_output=True)
    (repo_root / "README.md").write_text("demo\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo_root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo_root, check=True, capture_output=True)
    monkeypatch.chdir(repo_root)

    run_cli(
        ["init", "--project-name", "demo", "--project-key", "APP", "--provider", "local",
         "--adapters", "generic,codex,claude", "--worktree-policy", "required"],
        capsys,
    )
    run_cli(["task", "add", "Implement auth endpoint", "--module", "api"], capsys)
    run_cli(["claim", "APP-1", "--agent", "codex", "--role", "implementer", "--no-push"], capsys)

    # Manually point the claim worktree to the coordination worktree path
    coordination_path = repo_root.parent / "{0}-mesh-state".format(repo_root.name)
    claim_data = json.loads((coordination_path / ".agentic/claims/APP-1.json").read_text(encoding="utf-8"))
    claim_data["worktree"] = str(coordination_path)
    (coordination_path / ".agentic/claims/APP-1.json").write_text(
        json.dumps(claim_data, indent=2) + "\n", encoding="utf-8"
    )

    exit_code, output = run_cli(["merge", "APP-1", "--no-push", "--skip-merge-check"], capsys)

    assert exit_code == 1
    assert "refusing to modify" in output
    assert coordination_path.exists()


def _init_real_git_repo(tmp_path, monkeypatch, capsys, worktree_policy="required"):
    repo_root = tmp_path / "demo-repo"
    repo_root.mkdir(parents=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=repo_root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "mesh@example.com"], cwd=repo_root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Agent Mesh Tests"], cwd=repo_root, check=True, capture_output=True)
    (repo_root / "README.md").write_text("demo\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo_root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo_root, check=True, capture_output=True)
    monkeypatch.chdir(repo_root)
    run_cli(
        ["init", "--project-name", "demo", "--project-key", "APP", "--provider", "local",
         "--adapters", "generic,codex,claude", "--worktree-policy", worktree_policy],
        capsys,
    )
    return repo_root


def test_merge_blocks_on_dirty_worktree_without_flag(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root = _init_real_git_repo(tmp_path, monkeypatch, capsys)
    run_cli(["task", "add", "Implement auth endpoint", "--module", "api"], capsys)
    run_cli(["claim", "APP-1", "--agent", "codex", "--role", "implementer", "--no-push"], capsys)
    run_cli(["pr", "--dry-run", "--work-id", "APP-1"], capsys)

    coordination_root = repo_root.parent / "{0}-mesh-state".format(repo_root.name)
    claim = json.loads((coordination_root / ".agentic/claims/APP-1.json").read_text(encoding="utf-8"))
    # Write an uncommitted file into the task worktree
    (Path(claim["worktree"]) / "dirty.txt").write_text("unfinished\n", encoding="utf-8")

    exit_code, output = run_cli(["merge", "APP-1", "--no-push", "--skip-merge-check"], capsys)

    assert exit_code == 1
    assert "uncommitted changes" in output
    assert (coordination_root / ".agentic/claims/APP-1.json").exists()


def test_merge_discard_uncommitted_proceeds_and_rebuilds_dashboard(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root = _init_real_git_repo(tmp_path, monkeypatch, capsys)
    run_cli(["task", "add", "Implement auth endpoint", "--module", "api"], capsys)
    run_cli(["claim", "APP-1", "--agent", "codex", "--role", "implementer", "--no-push"], capsys)

    coordination_root = repo_root.parent / "{0}-mesh-state".format(repo_root.name)
    claim = json.loads((coordination_root / ".agentic/claims/APP-1.json").read_text(encoding="utf-8"))
    # pr must run from the task worktree (workspace guard enforces this)
    monkeypatch.chdir(Path(claim["worktree"]))
    run_cli(["pr", "--dry-run", "--work-id", "APP-1"], capsys)
    monkeypatch.chdir(repo_root)

    (Path(claim["worktree"]) / "dirty.txt").write_text("unfinished\n", encoding="utf-8")

    exit_code, output = run_cli(
        ["merge", "APP-1", "--no-push", "--skip-merge-check", "--discard-uncommitted"], capsys
    )

    assert exit_code == 0
    assert "--discard-uncommitted" in output
    assert "Marked APP-1 done" in output
    assert "Built dashboard" in output


def test_merge_discard_uncommitted_returns_lane_to_idle(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root = init_real_repo(tmp_path, monkeypatch, capsys, lanes=1)
    run_cli(["task", "add", "Implement auth endpoint", "--module", "api"], capsys)
    run_cli(["claim", "APP-1", "--agent", "codex", "--role", "implementer", "--no-push"], capsys)

    coordination_root = repo_root.parent / "{0}-mesh-state".format(repo_root.name)
    config = json.loads((repo_root / ".agentic/project.json").read_text(encoding="utf-8"))
    lane = config["coordination"]["lanes"][0]
    claim = json.loads((coordination_root / ".agentic/claims/APP-1.json").read_text(encoding="utf-8"))
    worktree_path = Path(claim["worktree"])

    monkeypatch.chdir(worktree_path)
    run_cli(["pr", "--dry-run", "--work-id", "APP-1"], capsys)
    monkeypatch.chdir(repo_root)

    (worktree_path / "dirty.txt").write_text("unfinished\n", encoding="utf-8")

    exit_code, output = run_cli(
        ["merge", "APP-1", "--no-push", "--skip-merge-check", "--discard-uncommitted"], capsys
    )

    assert exit_code == 0
    assert "--discard-uncommitted" in output
    assert worktree_path.exists()
    branch_result = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=worktree_path,
        check=True,
        capture_output=True,
        text=True,
    )
    assert branch_result.stdout.strip() == "wt/{0}".format(lane["workspace_id"])
    assert not (worktree_path / "dirty.txt").exists()


def test_merge_warns_when_lane_worktree_is_missing(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root = init_real_repo(tmp_path, monkeypatch, capsys, lanes=1)
    run_cli(["task", "add", "Implement auth endpoint", "--module", "api"], capsys)
    run_cli(["claim", "APP-1", "--agent", "codex", "--role", "implementer", "--no-push"], capsys)

    coordination_root = repo_root.parent / "{0}-mesh-state".format(repo_root.name)
    claim = json.loads((coordination_root / ".agentic/claims/APP-1.json").read_text(encoding="utf-8"))
    worktree_path = Path(claim["worktree"])

    monkeypatch.chdir(worktree_path)
    run_cli(["pr", "--dry-run", "--work-id", "APP-1"], capsys)
    monkeypatch.chdir(repo_root)

    subprocess.run(["git", "worktree", "remove", "--force", str(worktree_path)], cwd=repo_root, check=True, capture_output=True)
    assert not worktree_path.exists()

    exit_code, output = run_cli(["merge", "APP-1", "--no-push", "--skip-merge-check"], capsys)

    assert exit_code == 2
    assert "WARNING: lane worktree missing during merge" in output
    assert "Marked APP-1 done" in output
    assert (coordination_root / ".agentic/claims/archive/APP-1.json").exists()


def test_merge_allows_immediate_reclaim_on_same_lane(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root = init_real_repo(tmp_path, monkeypatch, capsys, lanes=1)
    run_cli(["task", "add", "First task", "--module", "api"], capsys)
    run_cli(["task", "add", "Second task", "--module", "api"], capsys)
    run_cli(["claim", "APP-1", "--agent", "codex", "--role", "implementer", "--no-push"], capsys)

    coordination_root = repo_root.parent / "{0}-mesh-state".format(repo_root.name)
    first_claim = json.loads((coordination_root / ".agentic/claims/APP-1.json").read_text(encoding="utf-8"))
    worktree_path = Path(first_claim["worktree"])

    monkeypatch.chdir(worktree_path)
    run_cli(["pr", "--dry-run", "--work-id", "APP-1"], capsys)
    monkeypatch.chdir(repo_root)

    merge_exit, merge_output = run_cli(["merge", "APP-1", "--no-push", "--skip-merge-check"], capsys)
    assert merge_exit == 0, merge_output

    claim_exit, claim_output = run_cli(
        ["claim", "APP-2", "--agent", "codex", "--role", "implementer", "--no-push"],
        capsys,
    )
    assert claim_exit == 0
    assert "Worktree: {0}".format(worktree_path) in claim_output
    assert "Workspace: {0}".format(first_claim["workspace_id"]) in claim_output


def test_merge_from_inside_task_worktree_completes_dashboard_rebuild(tmp_path: Path, monkeypatch, capsys) -> None:
    # Regression test for MESH-15: mesh merge called from inside the task
    # worktree crashed on dashboard rebuild because Path.cwd() raised
    # FileNotFoundError after the worktree directory was removed.
    repo_root = _init_real_git_repo(tmp_path, monkeypatch, capsys)
    run_cli(["task", "add", "Implement auth endpoint", "--module", "api"], capsys)
    run_cli(["claim", "APP-1", "--agent", "agent", "--role", "implementer", "--no-push"], capsys)

    coordination_root = repo_root.parent / "{0}-mesh-state".format(repo_root.name)
    claim = json.loads((coordination_root / ".agentic/claims/APP-1.json").read_text(encoding="utf-8"))
    # pr must run from the task worktree (workspace guard enforces this)
    monkeypatch.chdir(Path(claim["worktree"]))
    run_cli(["pr", "--dry-run", "--work-id", "APP-1"], capsys)
    # Simulate the user running mesh merge from inside the task worktree
    monkeypatch.chdir(Path(claim["worktree"]))

    exit_code, output = run_cli(["merge", "APP-1", "--no-push", "--skip-merge-check"], capsys)

    assert exit_code == 0, output
    assert "Removed worktree" in output
    assert "Built dashboard" in output
    assert (coordination_root / ".agentic/claims/archive/APP-1.json").exists()


def test_dashboard_escapes_html_in_task_fields(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root = init_repo(tmp_path, monkeypatch, capsys)
    run_cli(
        ["task", "add", '<script>alert("xss")</script> & "quoted"', "--module", "<mod>"],
        capsys,
    )

    exit_code, output = run_cli(["dashboard", "build"], capsys)
    assert exit_code == 0

    html = (repo_root / "dist/mesh-dashboard/index.html").read_text(encoding="utf-8")
    assert '<script>alert(' not in html
    assert "\\u003cscript\\u003e" in html
    assert "\\u0026" in html
    assert '\\"quoted\\"' in html
    assert "\\u003cmod\\u003e" in html


def test_public_dashboard_build_redacts_sensitive_coordination_fields(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    repo_root = init_real_repo(tmp_path, monkeypatch, capsys)
    run_cli(["task", "add", "Implement auth endpoint", "--module", "api"], capsys)
    run_cli(
        [
            "claim",
            "APP-1",
            "--agent",
            "codex",
            "--role",
            "implementer",
            "--machine",
            "private-box",
            "--no-push",
        ],
        capsys,
    )
    coordination_root = repo_root.parent / "{0}-mesh-state".format(repo_root.name)
    claim = json.loads((coordination_root / ".agentic/claims/APP-1.json").read_text(encoding="utf-8"))
    monkeypatch.chdir(Path(claim["worktree"]))
    run_cli(["pr", "--dry-run", "--work-id", "APP-1"], capsys)
    monkeypatch.chdir(repo_root)

    exit_code, output = run_cli(
        ["dashboard", "build", "--public", "--output-dir", "dist/public-dashboard"],
        capsys,
    )
    assert exit_code == 0
    assert "Built public dashboard" in output

    html_path = repo_root / "dist/public-dashboard/index.html"
    data_path = repo_root / "dist/public-dashboard/dashboard-data.json"
    assert html_path.exists()
    assert data_path.exists()

    html = html_path.read_text(encoding="utf-8")
    assert "Public snapshot" in html
    assert "Task Explorer" in html

    payload = json.loads(data_path.read_text(encoding="utf-8"))
    assert payload["meta"]["public"] is True
    assert payload["tasks"][0]["title"] == "Implement auth endpoint"
    assert payload["activeWork"][0]["title"] == "Implement auth endpoint"
    assert payload["activeWork"][0]["agent"] is None
    assert payload["activeWork"][0]["branch"] is None
    assert payload["activeWork"][0]["workspaceId"] is None
    assert payload["activeWork"][0]["worktree"] is None
    assert payload["reviews"][0]["workId"] == "APP-1"
    assert "private-box" not in data_path.read_text(encoding="utf-8")
    assert "feat/APP-1-implement-auth-endpoint" not in data_path.read_text(encoding="utf-8")


def test_adapter_install_opencode_creates_opencode_json(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root = tmp_path / "demo-repo"
    (repo_root / ".git").mkdir(parents=True)
    monkeypatch.chdir(repo_root)
    exit_code, output = run_cli(
        [
            "init",
            "--project-name",
            "demo",
            "--project-key",
            "APP",
            "--provider",
            "local",
            "--worktree-policy",
            "off",
        ],
        capsys,
    )
    assert exit_code == 0
    exit_code, output = run_cli(["adapter", "install", "opencode"], capsys)
    assert exit_code == 0
    assert (repo_root / "opencode.json").exists()
    config = json.loads((repo_root / "opencode.json").read_text(encoding="utf-8"))
    assert config["$schema"] == "https://opencode.ai/config.json"
    assert ".agents/skills" in config["skills"]["paths"]
    assert (repo_root / "OPENCODE.md").exists()


def test_adapter_install_opencode_is_idempotent(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root = tmp_path / "demo-repo"
    (repo_root / ".git").mkdir(parents=True)
    monkeypatch.chdir(repo_root)
    run_cli(
        [
            "init",
            "--project-name",
            "demo",
            "--project-key",
            "APP",
            "--provider",
            "local",
            "--worktree-policy",
            "off",
        ],
        capsys,
    )
    run_cli(["adapter", "install", "opencode"], capsys)

    config_before = json.loads((repo_root / "opencode.json").read_text(encoding="utf-8"))

    exit_code, output = run_cli(
        ["adapter", "install", "opencode"],
        capsys,
    )
    assert exit_code == 0

    config_after = json.loads((repo_root / "opencode.json").read_text(encoding="utf-8"))
    assert config_before == config_after


def test_adapter_install_registers_adapter_in_project_config(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root = tmp_path / "demo-repo"
    (repo_root / ".git").mkdir(parents=True)
    monkeypatch.chdir(repo_root)
    exit_code, _ = run_cli(
        [
            "init",
            "--project-name",
            "demo",
            "--project-key",
            "APP",
            "--provider",
            "local",
            "--adapters",
            "generic",
            "--worktree-policy",
            "off",
        ],
        capsys,
    )
    assert exit_code == 0

    project_before = json.loads((repo_root / ".agentic/project.json").read_text(encoding="utf-8"))
    assert project_before["adapters"] == ["generic"]

    exit_code, output = run_cli(["adapter", "install", "claude"], capsys)
    assert exit_code == 0
    assert "Installed adapter artifacts" in output

    project_after = json.loads((repo_root / ".agentic/project.json").read_text(encoding="utf-8"))
    assert project_after["adapters"] == ["generic", "claude"]


def test_claim_emits_adapter_install_tip_for_detected_runtime(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root = tmp_path / "demo-repo"
    (repo_root / ".git").mkdir(parents=True)
    monkeypatch.chdir(repo_root)
    exit_code, _ = run_cli(
        [
            "init",
            "--project-name",
            "demo",
            "--project-key",
            "APP",
            "--provider",
            "local",
            "--adapters",
            "generic",
            "--worktree-policy",
            "off",
        ],
        capsys,
    )
    assert exit_code == 0

    run_cli(["task", "add", "Implement auth endpoint", "--module", "api"], capsys)
    exit_code, output = run_cli(
        ["claim", "APP-1", "--agent", "claude-code", "--role", "implementer", "--no-push"],
        capsys,
    )
    assert exit_code == 0
    assert "TIP: detected claude runtime. To enable Mesh wrappers for this repo, run: mesh adapter install claude" in output


def test_doctor_emits_adapter_install_hint_for_missing_configured_adapter(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    repo_root = tmp_path / "demo-repo"
    (repo_root / ".git").mkdir(parents=True)
    monkeypatch.chdir(repo_root)
    exit_code, _ = run_cli(
        [
            "init",
            "--project-name",
            "demo",
            "--project-key",
            "APP",
            "--provider",
            "local",
            "--adapters",
            "generic",
            "--worktree-policy",
            "off",
        ],
        capsys,
    )
    assert exit_code == 0
    project = json.loads((repo_root / ".agentic/project.json").read_text(encoding="utf-8"))
    project["adapters"] = ["generic", "codex"]
    (repo_root / ".agentic/project.json").write_text(json.dumps(project, indent=2) + "\n", encoding="utf-8")

    exit_code, output = run_cli(["doctor"], capsys)
    assert exit_code == 1
    assert "Missing adapter artifact directory for codex: .agents/skills" in output
    assert "TIP: Run: mesh adapter install codex" in output


def test_doctor_reports_missing_mesh_bootstrap_in_root_agents(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    repo_root = init_repo(tmp_path, monkeypatch, capsys)
    (repo_root / "AGENTS.md").write_text("custom instructions\n", encoding="utf-8")

    exit_code, output = run_cli(["doctor"], capsys)

    assert exit_code == 1
    assert (
        "Root AGENTS.md is missing Agent Mesh startup routing; merge .agentic/AGENTS-BOOTSTRAP.md into AGENTS.md"
        in output
    )


def test_doctor_emits_repo_runtime_adapter_hint_for_claude_files(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    repo_root = init_repo(tmp_path, monkeypatch, capsys)
    ensure_dir = repo_root / ".claude"
    ensure_dir.mkdir(parents=True, exist_ok=True)
    (repo_root / "CLAUDE.md").write_text("project-specific claude instructions\n", encoding="utf-8")

    exit_code, output = run_cli(["doctor"], capsys)

    assert exit_code == 0
    assert (
        "TIP: detected claude runtime files in this repo. To enable Mesh wrappers for this repo, run: mesh adapter install claude"
        in output
    )


def test_bootstrap_tasks_creates_normalized_work_items_from_stdin(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    repo_root = init_repo(tmp_path, monkeypatch, capsys)
    payload = json.dumps(
        {
            "tasks": [
                {
                    "title": "Map existing auth flows",
                    "description": "Inspect current auth boundaries and identify missing tests.",
                    "kind": "research",
                    "module": "auth",
                    "acceptance_criteria": ["Document current auth entry points"],
                },
                {
                    "id": "APP-9",
                    "title": "Create adoption checklist",
                    "status": "ready",
                    "execution": "hitl",
                    "risk": "low",
                    "planning": {"provider": "linear", "external_id": "MESH-9"},
                },
            ]
        }
    )

    exit_code, output = run_cli_with_stdin(["bootstrap-tasks"], payload, capsys, monkeypatch)

    assert exit_code == 0
    assert "Bootstrapped 2 tasks (2 created, 0 updated)." in output
    work_one = json.loads((repo_root / ".agentic/work/APP-1.json").read_text(encoding="utf-8"))
    work_two = json.loads((repo_root / ".agentic/work/APP-9.json").read_text(encoding="utf-8"))
    assert work_one["title"] == "Map existing auth flows"
    assert work_one["status"] == "needs_triage"
    assert work_one["planning"]["provider"] == "local"
    assert work_two["planning"]["provider"] == "linear"
    assert work_two["planning"]["external_id"] == "MESH-9"
    assert (repo_root / "dist/mesh-dashboard/index.html").exists()


def test_bootstrap_tasks_updates_existing_work_item_from_input_file(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    repo_root = init_repo(tmp_path, monkeypatch, capsys)
    run_cli(["task", "add", "Implement auth endpoint", "--module", "api"], capsys)
    payload_path = repo_root / "bootstrap.json"
    payload_path.write_text(
        json.dumps(
            [
                {
                    "id": "APP-1",
                    "title": "Implement auth endpoint",
                    "description": "Expanded scope and adoption notes.",
                    "status": "ready",
                    "dependencies": ["APP-2"],
                }
            ]
        ),
        encoding="utf-8",
    )

    exit_code, output = run_cli(["bootstrap-tasks", "--input", str(payload_path)], capsys)

    assert exit_code == 0
    assert "Bootstrapped 1 tasks (0 created, 1 updated)." in output
    work_item = json.loads((repo_root / ".agentic/work/APP-1.json").read_text(encoding="utf-8"))
    assert work_item["description"] == "Expanded scope and adoption notes."
    assert work_item["status"] == "ready"
    assert work_item["dependencies"] == ["APP-2"]


def test_status_and_dashboard_use_shared_root_work_items_with_coordination_worktree(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    repo_root = init_real_repo(tmp_path, monkeypatch, capsys)

    exit_code, _ = run_cli(["task", "add", "Seed brownfield backlog", "--module", "core"], capsys)
    assert exit_code == 0

    status_exit, status_output = run_cli(["status"], capsys)

    assert status_exit == 0
    assert "Tasks: 1" in status_output
    dashboard_html = (repo_root / "dist/mesh-dashboard/index.html").read_text(encoding="utf-8")
    assert "Seed brownfield backlog" in dashboard_html


def test_opencode_skill_list_shows_installed(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root = tmp_path / "demo-repo"
    (repo_root / ".git").mkdir(parents=True)
    monkeypatch.chdir(repo_root)
    run_cli(
        [
            "init",
            "--project-name",
            "demo",
            "--project-key",
            "APP",
            "--provider",
            "local",
            "--worktree-policy",
            "off",
        ],
        capsys,
    )
    run_cli(["adapter", "install", "opencode"], capsys)

    exit_code, output = run_cli(["skill", "list"], capsys)
    assert exit_code == 0
    lines = output.strip().split("\n")
    claim_line = [l for l in lines if l.startswith("claim\t")]
    assert len(claim_line) == 1
    assert "installed" in claim_line[0]


def test_doctor_validates_opencode_config(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root = tmp_path / "demo-repo"
    (repo_root / ".git").mkdir(parents=True)
    monkeypatch.chdir(repo_root)
    run_cli(
        [
            "init",
            "--project-name",
            "demo",
            "--project-key",
            "APP",
            "--provider",
            "local",
            "--worktree-policy",
            "off",
        ],
        capsys,
    )
    run_cli(["adapter", "install", "opencode"], capsys)

    (repo_root / "opencode.json").unlink()

    exit_code, output = run_cli(["doctor"], capsys)
    assert exit_code != 0
    assert "opencode.json" in output


def _setup_repo_with_claim(tmp_path: Path, monkeypatch, capsys, *, worktree_policy: str = "required"):
    repo_root = tmp_path / "demo-repo"
    repo_root.mkdir(parents=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=repo_root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "mesh@example.com"], cwd=repo_root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Agent Mesh Tests"], cwd=repo_root, check=True, capture_output=True)
    (repo_root / "README.md").write_text("demo\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo_root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo_root, check=True, capture_output=True)
    monkeypatch.chdir(repo_root)
    run_cli(
        ["init", "--project-name", "demo", "--project-key", "APP", "--provider", "local",
         "--adapters", "generic,codex,claude", "--worktree-policy", worktree_policy],
        capsys,
    )
    run_cli(["task", "add", "Implement auth endpoint", "--module", "api"], capsys)
    run_cli(["claim", "APP-1", "--agent", "agent", "--role", "implementer", "--no-push"], capsys)
    if worktree_policy != "off":
        coordination_root = repo_root.parent / "{0}-mesh-state".format(repo_root.name)
    else:
        coordination_root = repo_root
    claim = json.loads((coordination_root / ".agentic/claims/APP-1.json").read_text(encoding="utf-8"))
    return repo_root, coordination_root, claim


def test_pr_workspace_guard_blocks_run_from_wrong_directory(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root, _, claim = _setup_repo_with_claim(tmp_path, monkeypatch, capsys)
    # remain in shared root — wrong location for mesh pr
    monkeypatch.chdir(repo_root)
    exit_code, output = run_cli(["pr", "--dry-run", "--work-id", "APP-1"], capsys)
    assert exit_code == 1
    assert "ERROR: mesh pr must be run from the claimed worktree." in output
    assert "REQUIRED:" in output
    assert claim["worktree"] in output


def test_pr_workspace_guard_passes_from_correct_worktree(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root, _, claim = _setup_repo_with_claim(tmp_path, monkeypatch, capsys)
    monkeypatch.chdir(Path(claim["worktree"]))
    exit_code, output = run_cli(["pr", "--dry-run", "--work-id", "APP-1"], capsys)
    assert exit_code == 0
    assert "Dry-run: review packet written to" in output


def test_pr_workspace_guard_skipped_when_no_worktree_recorded(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root, _, claim = _setup_repo_with_claim(tmp_path, monkeypatch, capsys, worktree_policy="off")
    assert not claim.get("worktree"), "precondition: worktree_policy=off must not record a worktree"
    monkeypatch.chdir(repo_root)
    exit_code, output = run_cli(["pr", "--dry-run", "--work-id", "APP-1"], capsys)
    assert exit_code == 0
    assert "Dry-run: review packet written to" in output


# MESH-13: auto-refresh claim last_seen on mesh command runs

def test_last_seen_refreshed_when_running_from_claimed_worktree(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root, coordination_root, claim = _setup_repo_with_claim(tmp_path, monkeypatch, capsys)
    worktree = Path(claim["worktree"])

    # Backdate last_seen far enough to be stale
    stale_ts = "2020-01-01T00:00:00Z"
    claim_path = coordination_root / ".agentic/claims/APP-1.json"
    data = json.loads(claim_path.read_text(encoding="utf-8"))
    data["last_seen"] = stale_ts
    claim_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    monkeypatch.chdir(worktree)
    run_cli(["version"], capsys)

    updated = json.loads(claim_path.read_text(encoding="utf-8"))
    assert updated["last_seen"] != stale_ts, "last_seen should be refreshed after running from worktree"


def test_mesh_status_shows_active_after_last_seen_refresh_from_worktree(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    repo_root, coordination_root, claim = _setup_repo_with_claim(tmp_path, monkeypatch, capsys)
    worktree = Path(claim["worktree"])

    # Backdate last_seen far past the stale threshold (default 120 min)
    stale_ts = "2020-01-01T00:00:00Z"
    claim_path = coordination_root / ".agentic/claims/APP-1.json"
    data = json.loads(claim_path.read_text(encoding="utf-8"))
    data["last_seen"] = stale_ts
    claim_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    monkeypatch.chdir(worktree)
    exit_code, output = run_cli(["status"], capsys)
    assert exit_code == 0
    assert "[active]" in output, "claim should show [active] when running from its worktree"
    assert "[stale]" not in output


def test_last_seen_not_refreshed_from_outside_worktree(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root, coordination_root, claim = _setup_repo_with_claim(tmp_path, monkeypatch, capsys)

    stale_ts = "2020-01-01T00:00:00Z"
    claim_path = coordination_root / ".agentic/claims/APP-1.json"
    data = json.loads(claim_path.read_text(encoding="utf-8"))
    data["last_seen"] = stale_ts
    claim_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    # Run from shared root, not the worktree
    monkeypatch.chdir(repo_root)
    run_cli(["version"], capsys)

    updated = json.loads(claim_path.read_text(encoding="utf-8"))
    assert updated["last_seen"] == stale_ts, "last_seen must not change when running from outside the worktree"


def test_no_heartbeat_flag_skips_last_seen_refresh(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root, coordination_root, claim = _setup_repo_with_claim(tmp_path, monkeypatch, capsys)
    worktree = Path(claim["worktree"])

    stale_ts = "2020-01-01T00:00:00Z"
    claim_path = coordination_root / ".agentic/claims/APP-1.json"
    data = json.loads(claim_path.read_text(encoding="utf-8"))
    data["last_seen"] = stale_ts
    claim_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    monkeypatch.chdir(worktree)
    run_cli(["--no-heartbeat", "version"], capsys)

    updated = json.loads(claim_path.read_text(encoding="utf-8"))
    assert updated["last_seen"] == stale_ts, "--no-heartbeat must suppress the last_seen refresh"


def test_last_seen_refresh_silent_when_claim_unwritable(tmp_path: Path, monkeypatch, capsys) -> None:
    import os
    import stat

    repo_root, coordination_root, claim = _setup_repo_with_claim(tmp_path, monkeypatch, capsys)
    worktree = Path(claim["worktree"])
    claim_path = coordination_root / ".agentic/claims/APP-1.json"

    # Make the claim file read-only
    original_mode = claim_path.stat().st_mode
    claim_path.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    try:
        monkeypatch.chdir(worktree)
        # Must not raise or produce any error output
        exit_code, output = run_cli(["version"], capsys)
        assert exit_code == 0
        assert "ERROR" not in output
    finally:
        claim_path.chmod(original_mode)
