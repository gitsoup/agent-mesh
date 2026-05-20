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
    assert (repo_root / ".agents/skills/claim/SKILL.md").exists()
    assert (repo_root / ".claude/skills/claim/SKILL.md").exists()
    assert (repo_root / ".github/workflows/agent-mesh-status.yml").exists()
    assert (repo_root / ".agents/skills/claim/SKILL.md").read_text(encoding="utf-8").startswith(
        "---\nname: claim\n"
    )
    assert (repo_root / ".claude/skills/claim/SKILL.md").read_text(encoding="utf-8").startswith(
        "---\nname: claim\n"
    )


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


def test_skill_list_shows_adapter_install_status_in_configured_repo(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    repo_root = init_repo(tmp_path, monkeypatch, capsys)

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
    assert "Agent Mesh" in dashboard.read_text(encoding="utf-8")


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
    assert "REQUIRED: cd" in output

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
            "--yes",
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
            "--yes",
        ],
        capsys,
    )
    assert exit_code == 0
    assert run_cli(["task", "add", "Implement auth endpoint", "--module", "api"], capsys)[0] == 0
    assert run_cli(["claim", "APP-1", "--agent", "codex", "--role", "implementer"], capsys)[0] == 0

    claim = json.loads((repo_root / ".agentic/claims/APP-1.json").read_text(encoding="utf-8"))
    monkeypatch.chdir(Path(claim["worktree"]))

    exit_code, output = run_cli(["pr", "--dry-run", "--work-id", "APP-1"], capsys)
    assert exit_code == 0
    expected_path = repo_root / ".agentic/reviews/PR-APP-1.json"
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
            "--yes",
        ],
        capsys,
    )
    assert exit_code == 0

    coordination_path = repo_root.parent / "{0}-mesh-state".format(repo_root.name)
    subprocess.run(["git", "worktree", "remove", str(coordination_path)], cwd=repo_root, check=True, capture_output=True)
    assert not coordination_path.exists()

    exit_code, output = run_cli(["sync"], capsys)
    assert exit_code == 0
    assert "Coordination worktree created: mesh/state @" in output
    assert coordination_path.exists()


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
    repo_root, claim = _setup_repo_with_claim(tmp_path, monkeypatch, capsys)
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
    repo_root, claim = _setup_repo_with_claim(tmp_path, monkeypatch, capsys)
    monkeypatch.chdir(Path(claim["worktree"]))
    assert run_cli(["pr", "--dry-run", "--work-id", "APP-1"], capsys)[0] == 0

    # inject a PR URL into the review packet
    packet_path = repo_root / ".agentic/reviews/PR-APP-1.json"
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    packet["pr"]["url"] = "https://github.com/example/repo/pull/42"
    packet_path.write_text(json.dumps(packet, indent=2), encoding="utf-8")

    monkeypatch.chdir(repo_root)
    exit_code, output = run_cli(["review", "PR-APP-1"], capsys)
    assert exit_code == 0
    assert "PR: https://github.com/example/repo/pull/42" in output


def test_review_renders_evidence_when_present_and_omits_when_absent(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root, claim = _setup_repo_with_claim(tmp_path, monkeypatch, capsys)
    monkeypatch.chdir(Path(claim["worktree"]))
    assert run_cli(["pr", "--dry-run", "--work-id", "APP-1"], capsys)[0] == 0

    packet_path = repo_root / ".agentic/reviews/PR-APP-1.json"

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
    repo_root, claim = _setup_repo_with_claim(tmp_path, monkeypatch, capsys)
    monkeypatch.chdir(Path(claim["worktree"]))
    assert run_cli(["pr", "--dry-run", "--work-id", "APP-1"], capsys)[0] == 0

    _, output_from_worktree = run_cli(["review", "PR-APP-1"], capsys)
    monkeypatch.chdir(repo_root)
    _, output_from_root = run_cli(["review", "PR-APP-1"], capsys)

    assert output_from_worktree == output_from_root


def test_review_works_when_worktree_policy_off(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root, claim = _setup_repo_with_claim(tmp_path, monkeypatch, capsys, worktree_policy="off")
    assert not claim.get("worktree"), "precondition: worktree_policy=off must not record a worktree"
    assert run_cli(["pr", "--dry-run", "--work-id", "APP-1"], capsys)[0] == 0

    exit_code, output = run_cli(["review", "PR-APP-1"], capsys)
    assert exit_code == 0
    assert "Review packet: PR-APP-1" in output
    assert "Next: review the PR" in output


def test_review_errors_on_missing_packet(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root, _ = _setup_repo_with_claim(tmp_path, monkeypatch, capsys)
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
         "--adapters", "generic,codex,claude", "--worktree-policy", "required", "--yes"],
        capsys,
    )
    run_cli(["task", "add", "Implement auth endpoint", "--module", "api"], capsys)
    run_cli(["claim", "APP-1", "--agent", "codex", "--role", "implementer", "--no-push"], capsys)
    run_cli(["pr", "--dry-run", "--work-id", "APP-1"], capsys)

    claim = json.loads((repo_root / ".agentic/claims/APP-1.json").read_text(encoding="utf-8"))
    worktree_path = Path(claim["worktree"])
    assert worktree_path.exists()

    exit_code, output = run_cli(["merge", "APP-1", "--no-push", "--skip-merge-check"], capsys)

    assert exit_code == 0
    assert "Removed worktree:" in output
    assert not worktree_path.exists()
    assert not (repo_root / ".agentic/claims/APP-1.json").exists()
    assert (repo_root / ".agentic/claims/archive/APP-1.json").exists()


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
         "--adapters", "generic,codex,claude", "--worktree-policy", "required", "--yes"],
        capsys,
    )
    run_cli(["task", "add", "Implement auth endpoint", "--module", "api"], capsys)
    run_cli(["claim", "APP-1", "--agent", "codex", "--role", "implementer", "--no-push"], capsys)

    # Simulate worktree already removed (e.g. by a previous partial merge)
    claim_data = json.loads((repo_root / ".agentic/claims/APP-1.json").read_text(encoding="utf-8"))
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
         "--adapters", "generic,codex,claude", "--worktree-policy", "required", "--yes"],
        capsys,
    )
    run_cli(["task", "add", "Implement auth endpoint", "--module", "api"], capsys)
    run_cli(["claim", "APP-1", "--agent", "codex", "--role", "implementer", "--no-push"], capsys)

    # Manually point the claim worktree to the coordination worktree path
    coordination_path = repo_root.parent / "{0}-mesh-state".format(repo_root.name)
    claim_data = json.loads((repo_root / ".agentic/claims/APP-1.json").read_text(encoding="utf-8"))
    claim_data["worktree"] = str(coordination_path)
    (repo_root / ".agentic/claims/APP-1.json").write_text(
        json.dumps(claim_data, indent=2) + "\n", encoding="utf-8"
    )

    exit_code, output = run_cli(["merge", "APP-1", "--no-push", "--skip-merge-check"], capsys)

    assert exit_code == 1
    assert "refusing to remove" in output
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
         "--adapters", "generic,codex,claude", "--worktree-policy", worktree_policy, "--yes"],
        capsys,
    )
    return repo_root


def test_merge_blocks_on_dirty_worktree_without_flag(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root = _init_real_git_repo(tmp_path, monkeypatch, capsys)
    run_cli(["task", "add", "Implement auth endpoint", "--module", "api"], capsys)
    run_cli(["claim", "APP-1", "--agent", "codex", "--role", "implementer", "--no-push"], capsys)
    run_cli(["pr", "--dry-run", "--work-id", "APP-1"], capsys)

    claim = json.loads((repo_root / ".agentic/claims/APP-1.json").read_text(encoding="utf-8"))
    # Write an uncommitted file into the task worktree
    (Path(claim["worktree"]) / "dirty.txt").write_text("unfinished\n", encoding="utf-8")

    exit_code, output = run_cli(["merge", "APP-1", "--no-push", "--skip-merge-check"], capsys)

    assert exit_code == 1
    assert "uncommitted changes" in output
    assert (repo_root / ".agentic/claims/APP-1.json").exists()


def test_merge_discard_uncommitted_proceeds_and_rebuilds_dashboard(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root = _init_real_git_repo(tmp_path, monkeypatch, capsys)
    run_cli(["task", "add", "Implement auth endpoint", "--module", "api"], capsys)
    run_cli(["claim", "APP-1", "--agent", "codex", "--role", "implementer", "--no-push"], capsys)
    run_cli(["pr", "--dry-run", "--work-id", "APP-1"], capsys)

    claim = json.loads((repo_root / ".agentic/claims/APP-1.json").read_text(encoding="utf-8"))
    (Path(claim["worktree"]) / "dirty.txt").write_text("unfinished\n", encoding="utf-8")

    exit_code, output = run_cli(
        ["merge", "APP-1", "--no-push", "--skip-merge-check", "--discard-uncommitted"], capsys
    )

    assert exit_code == 0
    assert "--discard-uncommitted" in output
    assert "Marked APP-1 done" in output
    assert "Built dashboard" in output


def test_merge_from_inside_task_worktree_completes_dashboard_rebuild(tmp_path: Path, monkeypatch, capsys) -> None:
    # Regression test for MESH-15: mesh merge called from inside the task
    # worktree crashed on dashboard rebuild because Path.cwd() raised
    # FileNotFoundError after the worktree directory was removed.
    repo_root = _init_real_git_repo(tmp_path, monkeypatch, capsys)
    run_cli(["task", "add", "Implement auth endpoint", "--module", "api"], capsys)
    run_cli(["claim", "APP-1", "--agent", "agent", "--role", "implementer", "--no-push"], capsys)
    run_cli(["pr", "--dry-run", "--work-id", "APP-1"], capsys)

    claim = json.loads((repo_root / ".agentic/claims/APP-1.json").read_text(encoding="utf-8"))
    # Simulate the user running mesh merge from inside the task worktree
    monkeypatch.chdir(Path(claim["worktree"]))

    exit_code, output = run_cli(["merge", "APP-1", "--no-push", "--skip-merge-check"], capsys)

    assert exit_code == 0, output
    assert "Removed worktree" in output
    assert "Built dashboard" in output
    assert (repo_root / ".agentic/claims/archive/APP-1.json").exists()


def test_dashboard_escapes_html_in_task_fields(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root = init_repo(tmp_path, monkeypatch, capsys)
    run_cli(
        ["task", "add", '<script>alert("xss")</script> & "quoted"', "--module", "<mod>"],
        capsys,
    )

    exit_code, output = run_cli(["dashboard", "build"], capsys)
    assert exit_code == 0

    html = (repo_root / ".agentic/dashboard/index.html").read_text(encoding="utf-8")
    assert '<script>alert(' not in html
    assert "&lt;script&gt;" in html
    assert "&amp;" in html
    assert "&quot;quoted&quot;" in html
    assert "&lt;mod&gt;" in html


def test_init_with_opencode_adapter_creates_opencode_json(tmp_path: Path, monkeypatch, capsys) -> None:
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
            "generic,opencode",
            "--worktree-policy",
            "off",
            "--yes",
        ],
        capsys,
    )
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
            "--adapters",
            "generic,opencode",
            "--worktree-policy",
            "off",
            "--yes",
        ],
        capsys,
    )

    config_before = json.loads((repo_root / "opencode.json").read_text(encoding="utf-8"))

    exit_code, output = run_cli(
        ["adapter", "install", "opencode"],
        capsys,
    )
    assert exit_code == 0

    config_after = json.loads((repo_root / "opencode.json").read_text(encoding="utf-8"))
    assert config_before == config_after


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
            "--adapters",
            "generic,opencode",
            "--worktree-policy",
            "off",
            "--yes",
        ],
        capsys,
    )

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
            "--adapters",
            "generic,opencode",
            "--worktree-policy",
            "off",
            "--yes",
        ],
        capsys,
    )

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
         "--adapters", "generic,codex,claude", "--worktree-policy", worktree_policy, "--yes"],
        capsys,
    )
    run_cli(["task", "add", "Implement auth endpoint", "--module", "api"], capsys)
    run_cli(["claim", "APP-1", "--agent", "agent", "--role", "implementer", "--no-push"], capsys)
    claim = json.loads((repo_root / ".agentic/claims/APP-1.json").read_text(encoding="utf-8"))
    return repo_root, claim


def test_pr_workspace_guard_blocks_run_from_wrong_directory(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root, claim = _setup_repo_with_claim(tmp_path, monkeypatch, capsys)
    # remain in shared root — wrong location for mesh pr
    monkeypatch.chdir(repo_root)
    exit_code, output = run_cli(["pr", "--dry-run", "--work-id", "APP-1"], capsys)
    assert exit_code == 1
    assert "ERROR: mesh pr must be run from the claimed worktree." in output
    assert "REQUIRED:" in output
    assert claim["worktree"] in output


def test_pr_workspace_guard_passes_from_correct_worktree(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root, claim = _setup_repo_with_claim(tmp_path, monkeypatch, capsys)
    monkeypatch.chdir(Path(claim["worktree"]))
    exit_code, output = run_cli(["pr", "--dry-run", "--work-id", "APP-1"], capsys)
    assert exit_code == 0
    assert "Dry-run: review packet written to" in output


def test_pr_workspace_guard_skipped_when_no_worktree_recorded(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root, claim = _setup_repo_with_claim(tmp_path, monkeypatch, capsys, worktree_policy="off")
    assert not claim.get("worktree"), "precondition: worktree_policy=off must not record a worktree"
    monkeypatch.chdir(repo_root)
    exit_code, output = run_cli(["pr", "--dry-run", "--work-id", "APP-1"], capsys)
    assert exit_code == 0
    assert "Dry-run: review packet written to" in output


# MESH-13: auto-refresh claim last_seen on mesh command runs

def test_last_seen_refreshed_when_running_from_claimed_worktree(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root, claim = _setup_repo_with_claim(tmp_path, monkeypatch, capsys)
    worktree = Path(claim["worktree"])

    # Backdate last_seen far enough to be stale
    stale_ts = "2020-01-01T00:00:00Z"
    claim_path = repo_root / ".agentic/claims/APP-1.json"
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
    repo_root, claim = _setup_repo_with_claim(tmp_path, monkeypatch, capsys)
    worktree = Path(claim["worktree"])

    # Backdate last_seen far past the stale threshold (default 120 min)
    stale_ts = "2020-01-01T00:00:00Z"
    claim_path = repo_root / ".agentic/claims/APP-1.json"
    data = json.loads(claim_path.read_text(encoding="utf-8"))
    data["last_seen"] = stale_ts
    claim_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    monkeypatch.chdir(worktree)
    exit_code, output = run_cli(["status"], capsys)
    assert exit_code == 0
    assert "[active]" in output, "claim should show [active] when running from its worktree"
    assert "[stale]" not in output


def test_last_seen_not_refreshed_from_outside_worktree(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root, claim = _setup_repo_with_claim(tmp_path, monkeypatch, capsys)

    stale_ts = "2020-01-01T00:00:00Z"
    claim_path = repo_root / ".agentic/claims/APP-1.json"
    data = json.loads(claim_path.read_text(encoding="utf-8"))
    data["last_seen"] = stale_ts
    claim_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    # Run from shared root, not the worktree
    monkeypatch.chdir(repo_root)
    run_cli(["version"], capsys)

    updated = json.loads(claim_path.read_text(encoding="utf-8"))
    assert updated["last_seen"] == stale_ts, "last_seen must not change when running from outside the worktree"


def test_no_heartbeat_flag_skips_last_seen_refresh(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root, claim = _setup_repo_with_claim(tmp_path, monkeypatch, capsys)
    worktree = Path(claim["worktree"])

    stale_ts = "2020-01-01T00:00:00Z"
    claim_path = repo_root / ".agentic/claims/APP-1.json"
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

    repo_root, claim = _setup_repo_with_claim(tmp_path, monkeypatch, capsys)
    worktree = Path(claim["worktree"])
    claim_path = repo_root / ".agentic/claims/APP-1.json"

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
