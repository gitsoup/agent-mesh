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
