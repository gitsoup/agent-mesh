import subprocess
import json
from pathlib import Path

from agent_mesh.cli import app


def run_cli(args, capsys):
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
            "--adapters",
            "generic,codex,claude",
            "--worktree-policy",
            "off",
            "--yes",
        ],
        capsys,
    )
    assert exit_code == 0
    assert "Initialized Agent Mesh" in output
    return repo_root


def test_init_creates_agentic_scaffold(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root = init_repo(tmp_path, monkeypatch, capsys)

    assert (repo_root / ".agentic/project.json").exists()
    assert (repo_root / ".agentic/context/CONTEXT.md").exists()
    assert (repo_root / ".agentic/workflows/claim.md").exists()
    assert (repo_root / ".agentic/skills/claim/SKILL.md").exists()
    assert (repo_root / ".agents/skills/claim/SKILL.md").exists()
    assert (repo_root / ".claude/skills/claim/SKILL.md").exists()
    assert (repo_root / ".github/workflows/agent-mesh-status.yml").exists()


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
            "--adapters",
            "generic,codex,claude",
            "--worktree-policy",
            "off",
            "--yes",
        ],
        capsys,
    )

    assert exit_code == 0
    assert "Skipped" in output
    assert agents_path.read_text(encoding="utf-8") == "custom instructions\n"


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
    assert "Tasks: 1" in output
    assert "in_progress: 1" in output
    assert "Claims: 1" in output
    assert "APP-1: codex on feat/APP-1-implement-auth-endpoint" in output

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
    dashboard = repo_root / ".agentic/dashboard/index.html"
    assert dashboard.exists()
    assert "Task Summary" in dashboard.read_text(encoding="utf-8")


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
            "--adapters",
            "generic,codex,claude",
            "--worktree-policy",
            "required",
            "--yes",
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
    assert "Next: cd" in output

    claim = json.loads((repo_root / ".agentic/claims/APP-1.json").read_text(encoding="utf-8"))
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
