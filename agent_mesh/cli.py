"""CLI entrypoint for Agent Mesh."""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

from agent_mesh import __version__
from agent_mesh.config import PROJECT_FILE
from agent_mesh.skills.catalog import SKILLS
from agent_mesh.utils.slug import slugify

try:
    from rich.console import Console
except ModuleNotFoundError:  # pragma: no cover - exercised only in thin envs
    Console = None

console = Console() if Console is not None else None
SUPPORTED_ADAPTERS = ["generic", "claude", "codex", "cursor", "opencode", "pi", "windsurf"]


def emit(message: str) -> None:
    if console is not None and console.is_terminal:
        console.print(message, markup=False)
        return
    print(message)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mesh",
        description="Git-native coordination toolkit for parallel AI coding agents.",
    )
    parser.add_argument(
        "--no-heartbeat",
        action="store_true",
        default=False,
        help="Skip last_seen refresh for this invocation (useful for scripting/monitoring).",
    )
    subparsers = parser.add_subparsers(dest="command")

    version_parser = subparsers.add_parser("version", help="Print the installed Agent Mesh version.")
    version_parser.set_defaults(func=handle_version)

    init_parser = subparsers.add_parser("init", help="Initialize Agent Mesh in the current repo.")
    init_parser.add_argument("--project-name")
    init_parser.add_argument("--project-key")
    init_parser.add_argument("--provider", default="local")
    init_parser.add_argument("--adapters", default="generic")
    init_parser.add_argument("--force", action="store_true")
    init_parser.add_argument("--yes", action="store_true")
    init_parser.add_argument("--dashboard", dest="dashboard", action="store_true", default=True)
    init_parser.add_argument("--no-dashboard", dest="dashboard", action="store_false")
    init_parser.add_argument(
        "--worktree-policy",
        choices=["required", "preferred", "off"],
        default="required",
    )
    init_parser.add_argument("--worktree-root")
    init_parser.add_argument("--claim-stale-after-minutes", type=int, default=120)
    init_parser.set_defaults(func=handle_init)

    doctor_parser = subparsers.add_parser("doctor", help="Validate Agent Mesh config and state.")
    doctor_parser.set_defaults(func=handle_doctor)

    status_parser = subparsers.add_parser("status", help="Summarize local Agent Mesh state.")
    status_parser.add_argument("--skip-dashboard-rebuild", action="store_true")
    status_parser.set_defaults(func=handle_status)

    skill_parser = subparsers.add_parser("skill", help="Skill catalog commands.")
    skill_subparsers = skill_parser.add_subparsers(dest="skill_command")
    skill_list_parser = skill_subparsers.add_parser("list", help="List canonical skills.")
    skill_list_parser.set_defaults(func=handle_skill_list)

    adapter_parser = subparsers.add_parser("adapter", help="Adapter commands.")
    adapter_subparsers = adapter_parser.add_subparsers(dest="adapter_command")
    adapter_list_parser = adapter_subparsers.add_parser("list", help="List supported adapters.")
    adapter_list_parser.set_defaults(func=handle_adapter_list)
    adapter_install_parser = adapter_subparsers.add_parser(
        "install", help="Install one or more adapters into the current repo."
    )
    adapter_install_parser.add_argument("adapters")
    adapter_install_parser.add_argument("--force", action="store_true")
    adapter_install_parser.set_defaults(func=handle_adapter_install)

    task_parser = subparsers.add_parser("task", help="Work item commands.")
    task_subparsers = task_parser.add_subparsers(dest="task_command")

    task_add_parser = task_subparsers.add_parser("add", help="Create a local work item.")
    task_add_parser.add_argument("title")
    task_add_parser.add_argument("--description", default="")
    task_add_parser.add_argument("--module")
    task_add_parser.add_argument("--kind", default="feature")
    task_add_parser.add_argument("--status", default="ready")
    task_add_parser.add_argument("--execution", default="afk_safe")
    task_add_parser.add_argument("--risk", default="medium")
    task_add_parser.add_argument(
        "--acceptance",
        action="append",
        default=[],
        help="Acceptance criterion. Repeat the flag for multiple entries.",
    )
    task_add_parser.set_defaults(func=handle_task_add)

    task_list_parser = task_subparsers.add_parser("list", help="List local work items.")
    task_list_parser.set_defaults(func=handle_task_list)

    task_show_parser = task_subparsers.add_parser("show", help="Show one local work item.")
    task_show_parser.add_argument("work_id")
    task_show_parser.set_defaults(func=handle_task_show)

    claim_parser = subparsers.add_parser("claim", help="Claim a local work item.")
    claim_parser.add_argument("work_id")
    claim_parser.add_argument("--agent", default="agent")
    claim_parser.add_argument("--role", default="implementer")
    claim_parser.add_argument("--machine", default=socket.gethostname())
    claim_parser.add_argument("--workspace-id")
    claim_parser.add_argument("--worktree")
    claim_parser.add_argument("--branch")
    claim_parser.add_argument("--resume", action="store_true")
    claim_parser.add_argument("--takeover", action="store_true")
    claim_parser.add_argument("--no-push", action="store_true")
    claim_parser.set_defaults(func=handle_claim)

    pr_parser = subparsers.add_parser("pr", help="Prepare a pull request body.")
    pr_parser.add_argument("--work-id", required=True)
    pr_parser.add_argument("--dry-run", action="store_true")
    pr_parser.set_defaults(func=handle_pr)

    review_parser = subparsers.add_parser(
        "review-packet", help="Generate a review packet for a work item."
    )
    review_parser.add_argument("--work-id", required=True)
    review_parser.set_defaults(func=handle_review_packet)

    review_route_parser = subparsers.add_parser(
        "review", help="Resolve a review packet to the correct workspace."
    )
    review_route_parser.add_argument("target")
    review_route_parser.set_defaults(func=handle_review)

    dashboard_parser = subparsers.add_parser("dashboard", help="Dashboard commands.")
    dashboard_subparsers = dashboard_parser.add_subparsers(dest="dashboard_command")
    dashboard_build_parser = dashboard_subparsers.add_parser(
        "build", help="Build a static dashboard."
    )
    dashboard_build_parser.set_defaults(func=handle_dashboard_build)

    sync_parser = subparsers.add_parser("sync", help="Refresh local status artifacts.")
    sync_parser.set_defaults(func=handle_sync)

    merge_parser = subparsers.add_parser("merge", help="Finalize a merged work item and clean up.")
    merge_parser.add_argument("work_id", help="Work item ID (e.g. APP-1).")
    merge_parser.add_argument("--no-push", action="store_true", help="Skip remote branch deletion.")
    merge_parser.add_argument("--skip-merge-check", action="store_true", help="Skip check that branch is merged into default branch.")
    merge_parser.add_argument("--discard-uncommitted", action="store_true", help="Remove worktree even if it has uncommitted changes.")
    merge_parser.set_defaults(func=handle_merge)

    return parser


def app(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    if not hasattr(args, "func"):
        parser.print_help()
        return 0
    if not getattr(args, "no_heartbeat", False):
        try:
            from agent_mesh.state.storage import refresh_claim_last_seen, resolve_repo_root
            refresh_claim_last_seen(resolve_repo_root(Path.cwd()), Path.cwd())
        except Exception:
            pass
    return int(args.func(args) or 0)


def handle_version(_: argparse.Namespace) -> int:
    emit(__version__)
    return 0


def handle_init(args: argparse.Namespace) -> int:
    from agent_mesh.config import load_project_config
    from agent_mesh.scaffold import init_repo
    from agent_mesh.state.storage import resolve_repo_root
    from agent_mesh.topology import ensure_coordination_worktree

    repo_root = resolve_repo_root(Path.cwd())
    project_name = args.project_name or repo_root.name
    project_key = args.project_key or derive_project_key(project_name)
    adapters = parse_csv(args.adapters)

    # Set up coordination worktree first so scaffold can write .agentic/ there
    coordination_root = None
    if args.worktree_policy != "off" and git_head_available(repo_root):
        try:
            # Bootstrap: write a minimal project.json to repo_root so
            # load_project_config works, then move to coordination worktree.
            _bootstrap_project_json(
                repo_root, project_name, project_key, args.provider,
                args.dashboard, args.worktree_policy, args.worktree_root,
                args.claim_stale_after_minutes,
            )
            coordination = ensure_coordination_worktree(repo_root, load_project_config(repo_root))
            emit(
                "Coordination worktree {0}: {1} @ {2}".format(
                    coordination.action, coordination.branch, coordination.path,
                )
            )
            coordination_root = coordination.path
        except RuntimeError as error:
            emit("WARN: {0}".format(error))

    result = init_repo(
        repo_root=repo_root,
        project_name=project_name,
        project_key=project_key,
        provider=args.provider,
        adapters=adapters,
        force=args.force,
        dashboard=args.dashboard,
        worktree_policy=args.worktree_policy,
        worktree_root=args.worktree_root,
        claim_stale_after_minutes=args.claim_stale_after_minutes,
        coordination_root=coordination_root,
    )
    emit("Initialized Agent Mesh in {0}".format(repo_root))
    emit("Created {0} files.".format(len(result.created)))
    emit("Skipped {0} existing files.".format(len(result.skipped)))
    if coordination_root is not None and coordination_root != repo_root:
        _commit_coordination_scaffold(coordination_root)
    return 0


def _bootstrap_project_json(
    repo_root: Path,
    project_name: str,
    project_key: str,
    provider: str,
    dashboard: bool,
    worktree_policy: str,
    worktree_root: str | None,
    claim_stale_after_minutes: int,
) -> None:
    """Write a minimal project.json to repo_root so topology helpers can load config."""
    from agent_mesh.state.storage import atomic_write_json
    project_json = repo_root / ".agentic/project.json"
    if project_json.exists():
        return
    project_json.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(project_json, {
        "schema_version": "0.1",
        "project_name": project_name,
        "project_key": project_key,
        "default_branch": "main",
        "planning": {"provider": provider, "external_project": None},
        "coordination": {
            "strategy": "git_files",
            "branch": "mesh/state",
            "work_dir": ".agentic/work",
            "claims_dir": ".agentic/claims",
            "reviews_dir": ".agentic/reviews",
            "handoffs_dir": ".agentic/handoffs",
            "worktree_policy": worktree_policy,
            "worktree_root": worktree_root,
            "coordination_worktree": None,
            "claim_stale_after_minutes": claim_stale_after_minutes,
        },
        "adapters": ["generic"],
        "runner": {"default": "local_manual"},
        "dashboard": {"enabled": dashboard, "output_dir": ".agentic/dashboard"},
    })


def _commit_coordination_scaffold(coordination_root: Path) -> None:
    """Commit the initial .agentic/ scaffold to the coordination branch."""
    import subprocess as _sp
    _sp.run(["git", "add", ".agentic/"], cwd=coordination_root, check=False, capture_output=True)
    _sp.run(
        ["git", "commit", "-m", "Initialize .agentic/ coordination scaffold"],
        cwd=coordination_root,
        check=False,
        capture_output=True,
    )


def handle_doctor(_: argparse.Namespace) -> int:
    from agent_mesh.state.storage import resolve_coordination_root, resolve_repo_root
    from agent_mesh.state.validate import validate_state_tree

    repo_root = resolve_repo_root(Path.cwd())
    coordination_root = resolve_coordination_root(repo_root)
    errors = validate_state_tree(repo_root, coordination_root)
    if errors:
        for error in errors:
            emit("ERROR: {0}".format(error))
        return 1
    emit("OK: Agent Mesh state is valid.")
    return 0


def handle_status(args: argparse.Namespace) -> int:
    from agent_mesh.config import load_project_config
    from agent_mesh.state.storage import list_claims, list_reviews, list_work_items, resolve_coordination_root, resolve_repo_root
    from agent_mesh.topology import inspect_coordination_worktree

    repo_root = resolve_repo_root(Path.cwd())
    coordination_root = resolve_coordination_root(repo_root)
    config = load_project_config(repo_root)
    work_items = list_work_items(coordination_root)
    claims = list_claims(coordination_root)
    reviews = list_reviews(coordination_root)
    coordination = inspect_coordination_worktree(repo_root, config)

    emit("Project: {0} ({1})".format(config.project_name, config.project_key))
    emit("Shared root: {0}".format(repo_root))
    emit(
        "Coordination: {0} @ {1} [{2}]".format(
            coordination.branch,
            coordination.path,
            coordination.state,
        )
    )
    if coordination.detail:
        emit("Coordination detail: {0}".format(coordination.detail))
    emit("Tasks: {0}".format(len(work_items)))
    for line in summarize_work_items(work_items):
        emit(line)
    emit("Claims: {0}".format(len(claims)))
    for line in summarize_claims(claims, config.coordination.claim_stale_after_minutes):
        emit(line)
    emit("Reviews: {0}".format(len(reviews)))
    for line in summarize_reviews(reviews):
        emit(line)
    if config.dashboard.enabled and not args.skip_dashboard_rebuild:
        build_dashboard(repo_root, coordination_root)
    return 0


def handle_skill_list(_: argparse.Namespace) -> int:
    from agent_mesh.config import load_project_config
    from agent_mesh.state.storage import resolve_repo_root

    try:
        repo_root = resolve_repo_root(Path.cwd())
    except FileNotFoundError:
        repo_root = None

    if repo_root is None or not (repo_root / PROJECT_FILE).exists():
        for skill in SKILLS:
            emit("{0}\t{1}".format(skill.name, skill.summary))
        return 0

    config = load_project_config(repo_root)
    adapter_columns = ["canonical"] + [adapter for adapter in config.adapters if adapter != "generic"]
    emit("skill\tsummary\t{0}".format("\t".join(adapter_columns)))
    for skill in SKILLS:
        statuses = ["ok"]
        for adapter in adapter_columns[1:]:
            statuses.append(skill_install_status(repo_root, adapter, skill.name))
        emit("{0}\t{1}\t{2}".format(skill.name, skill.summary, "\t".join(statuses)))
    return 0


def skill_install_status(repo_root: Path, adapter: str, skill_name: str) -> str:
    if adapter == "claude":
        return "installed" if (repo_root / ".claude/skills" / skill_name / "SKILL.md").exists() else "missing"
    if adapter == "codex":
        return "installed" if (repo_root / ".agents/skills" / skill_name / "SKILL.md").exists() else "missing"
    if adapter == "pi":
        return "installed" if (repo_root / ".agents/skills" / skill_name / "SKILL.md").exists() else "missing"
    if adapter == "cursor":
        return "installed" if (repo_root / ".cursor/rules/agent-mesh.mdc").exists() else "missing"
    if adapter == "opencode":
        opencode_config = repo_root / "opencode.json"
        if not opencode_config.exists():
            return "missing"
        try:
            config = json.loads(opencode_config.read_text(encoding="utf-8"))
            paths = config.get("skills", {}).get("paths", [])
            return "installed" if ".agents/skills" in paths else "missing"
        except Exception:
            return "missing"
    if adapter == "windsurf":
        return "installed" if (repo_root / ".windsurfrules").exists() else "missing"
    return "unknown"


def handle_adapter_list(_: argparse.Namespace) -> int:
    for adapter in SUPPORTED_ADAPTERS:
        emit(adapter)
    return 0


def handle_adapter_install(args: argparse.Namespace) -> int:
    from agent_mesh.scaffold import install_adapters
    from agent_mesh.state.storage import resolve_repo_root

    repo_root = resolve_repo_root(Path.cwd())
    result = install_adapters(repo_root, parse_csv(args.adapters), force=args.force)
    emit("Installed adapter artifacts: {0}".format(len(result.created)))
    emit("Skipped adapter artifacts: {0}".format(len(result.skipped)))
    return 0


def handle_task_add(args: argparse.Namespace) -> int:
    from agent_mesh.config import load_project_config
    from agent_mesh.state.models import ProviderRef, WorkItem
    from agent_mesh.state.storage import next_work_item_id, resolve_coordination_root, resolve_repo_root, save_model_json

    repo_root = resolve_repo_root(Path.cwd())
    coordination_root = resolve_coordination_root(repo_root)
    config = load_project_config(repo_root)
    work_id = next_work_item_id(coordination_root, config.project_key)
    now = utc_now()

    description = args.description or args.title
    acceptance = args.acceptance or ["Define task-specific acceptance criteria."]
    work_item = WorkItem(
        id=work_id,
        title=args.title,
        description=description,
        kind=args.kind,
        status=args.status,
        execution=args.execution,
        module=args.module,
        planning=ProviderRef(provider=config.planning.provider),
        prd=None,
        acceptance_criteria=acceptance,
        dependencies=[],
        risk=args.risk,
        created_at=now,
        updated_at=now,
    )
    path = coordination_root / ".agentic/work" / "{0}.json".format(work_id)
    save_model_json(path, work_item)
    emit("Created task {0}".format(work_id))
    return 0


def handle_task_list(_: argparse.Namespace) -> int:
    from agent_mesh.state.storage import list_work_items, resolve_coordination_root, resolve_repo_root

    repo_root = resolve_repo_root(Path.cwd())
    coordination_root = resolve_coordination_root(repo_root)
    for work_item in list_work_items(coordination_root):
        emit("{0}\t{1}\t{2}".format(work_item.id, work_item.status, work_item.title))
    return 0


def handle_task_show(args: argparse.Namespace) -> int:
    from agent_mesh.state.models import WorkItem
    from agent_mesh.state.storage import load_model, resolve_coordination_root, resolve_repo_root

    repo_root = resolve_repo_root(Path.cwd())
    coordination_root = resolve_coordination_root(repo_root)
    work_item = load_model(coordination_root / ".agentic/work" / "{0}.json".format(args.work_id), WorkItem)
    emit(work_item.model_dump_json(indent=2))
    return 0


def handle_claim(args: argparse.Namespace) -> int:
    from agent_mesh.config import load_project_config
    from agent_mesh.state.models import Claim, ClaimEvent, WorkItem
    from agent_mesh.state.storage import load_model, resolve_coordination_root, resolve_repo_root, save_model_json

    repo_root = resolve_repo_root(Path.cwd())
    coordination_root = resolve_coordination_root(repo_root)
    config = load_project_config(repo_root)
    work_path = coordination_root / ".agentic/work" / "{0}.json".format(args.work_id)
    work_item = load_model(work_path, WorkItem)

    existing_claim_path = coordination_root / ".agentic/claims" / "{0}.json".format(args.work_id)
    if args.resume and args.takeover:
        emit("ERROR: choose only one of --resume or --takeover")
        return 1
    if existing_claim_path.exists():
        claim = load_model(existing_claim_path, Claim)
        return handle_existing_claim(
            repo_root=repo_root,
            coordination_root=coordination_root,
            config=config,
            work_item=work_item,
            claim=claim,
            claim_path=existing_claim_path,
            args=args,
        )
    if args.resume or args.takeover:
        emit("ERROR: no existing claim for {0}".format(args.work_id))
        return 1
    if work_item.status not in ["ready", "in_progress"]:
        emit("ERROR: work item {0} is not ready to claim".format(args.work_id))
        return 1

    now = utc_now()
    branch = args.branch or "feat/{0}-{1}".format(args.work_id, slugify(work_item.title))
    workspace_id = args.workspace_id or derive_workspace_id(args.agent, args.machine)
    try:
        worktree = prepare_claim_workspace(
            repo_root,
            config.default_branch,
            branch,
            workspace_id,
            args.worktree,
        )
    except RuntimeError as error:
        emit("ERROR: {0}".format(error))
        return 1
    claim = Claim(
        work_id=args.work_id,
        status="in_progress",
        claimed_by="agent:{0}:{1}".format(args.agent, args.machine),
        agent_runtime=args.agent,
        role=args.role,
        machine=args.machine,
        workspace_id=workspace_id,
        worktree=worktree,
        branch=branch,
        claimed_at=now,
        last_seen=now,
        events=[
            ClaimEvent(
                action="claimed",
                at=now,
                by="agent:{0}:{1}".format(args.agent, args.machine),
            )
        ],
    )
    save_model_json(existing_claim_path, claim)

    work_item.status = "in_progress"
    work_item.updated_at = now
    save_model_json(work_path, work_item)
    emit("Claimed {0} on branch {1}".format(args.work_id, branch))
    if worktree is not None:
        emit("Worktree: {0}".format(worktree))
        if workspace_id:
            emit("Workspace: {0}".format(workspace_id))
        emit("REQUIRED: cd {0}".format(worktree))
    return 0


def handle_pr(args: argparse.Namespace) -> int:
    from agent_mesh.config import load_project_config
    from agent_mesh.state.models import Claim, WorkItem
    from agent_mesh.state.storage import load_model, resolve_coordination_root, resolve_repo_root, save_model_json

    repo_root = resolve_repo_root(Path.cwd())
    coordination_root = resolve_coordination_root(repo_root)
    config = load_project_config(repo_root)
    work_item = load_model(coordination_root / ".agentic/work" / "{0}.json".format(args.work_id), WorkItem)
    claim = load_model(coordination_root / ".agentic/claims" / "{0}.json".format(args.work_id), Claim)

    if claim.worktree and Path(claim.worktree).exists():
        current_path = Path.cwd().resolve()
        target_worktree = Path(claim.worktree).resolve()
        if current_path != target_worktree:
            emit("ERROR: mesh pr must be run from the claimed worktree.")
            emit("Current: {0}".format(current_path))
            emit("Expected: {0}".format(target_worktree))
            emit("REQUIRED: cd {0}".format(target_worktree))
            return 1

    body = render_pr_body(work_item, claim)
    emit(body)

    review_packet = create_review_packet(config, work_item, claim)
    review_packet_path = coordination_root / ".agentic/reviews" / "{0}.json".format(review_packet.id)
    save_model_json(review_packet_path, review_packet)

    work_item.status = "pr_open"
    work_item.updated_at = utc_now()
    save_model_json(coordination_root / ".agentic/work" / "{0}.json".format(args.work_id), work_item)

    if args.dry_run:
        emit("Dry-run: review packet written to {0}".format(review_packet_path))
    return 0


def handle_review_packet(args: argparse.Namespace) -> int:
    from agent_mesh.config import load_project_config
    from agent_mesh.state.models import Claim, WorkItem
    from agent_mesh.state.storage import load_model, resolve_coordination_root, resolve_repo_root, save_model_json

    repo_root = resolve_repo_root(Path.cwd())
    coordination_root = resolve_coordination_root(repo_root)
    config = load_project_config(repo_root)
    work_item = load_model(coordination_root / ".agentic/work" / "{0}.json".format(args.work_id), WorkItem)
    claim = load_model(coordination_root / ".agentic/claims" / "{0}.json".format(args.work_id), Claim)
    review_packet = create_review_packet(config, work_item, claim)
    review_packet_path = coordination_root / ".agentic/reviews" / "{0}.json".format(review_packet.id)
    save_model_json(review_packet_path, review_packet)
    emit("Wrote review packet {0}".format(review_packet_path))
    return 0


def handle_review(args: argparse.Namespace) -> int:
    from agent_mesh.state.models import Claim, ReviewPacket, WorkItem
    from agent_mesh.state.storage import load_model, resolve_coordination_root, resolve_repo_root

    repo_root = resolve_repo_root(Path.cwd())
    coordination_root = resolve_coordination_root(repo_root)
    review_path = resolve_review_packet_path(coordination_root, args.target)
    if review_path is None:
        emit("ERROR: could not find review packet for {0}".format(args.target))
        return 1

    review_packet = load_model(review_path, ReviewPacket)
    claim = load_model(coordination_root / review_packet.context.claim, Claim)
    work_item = load_model(coordination_root / review_packet.context.work_item, WorkItem)

    emit("Review packet: {0}".format(review_packet.id))
    emit("Work item: {0} ({1})".format(work_item.id, work_item.title))
    emit("Branch: {0} -> {1}".format(review_packet.pr.branch, review_packet.pr.base))
    if review_packet.pr.url:
        emit("PR: {0}".format(review_packet.pr.url))
    emit("Requested role: {0}".format(review_packet.requested_role))
    emit("Workspace: {0}".format(claim.workspace_id or "unspecified"))
    emit("Review status: {0}".format(review_packet.status))

    if work_item.acceptance_criteria:
        emit("")
        emit("Acceptance criteria:")
        for criterion in work_item.acceptance_criteria:
            emit("  [ ] {0}".format(criterion))

    if review_packet.evidence:
        emit("")
        emit("Evidence:")
        for e in review_packet.evidence:
            emit("  [{0}] {1} -> {2}".format(e.kind, e.command, e.summary))

    if review_packet.context.context_files:
        emit("")
        for context_file in review_packet.context.context_files:
            emit("Context: {0}".format(context_file))

    emit("")
    emit("Next: review the PR and verify each acceptance criterion above.")
    return 0


def build_dashboard(repo_root: Path, coordination_root: Optional[Path] = None) -> None:
    from agent_mesh.config import load_project_config
    from agent_mesh.state.storage import list_claims, list_reviews, list_work_items, resolve_coordination_root

    if coordination_root is None:
        coordination_root = resolve_coordination_root(repo_root)
    config = load_project_config(repo_root)
    output_path = repo_root / config.dashboard.output_dir / "index.html"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    work_items = list_work_items(coordination_root)
    claims = list_claims(coordination_root)
    reviews = list_reviews(coordination_root)
    output_path.write_text(render_dashboard_html(config, work_items, claims, reviews), encoding="utf-8")
    emit("Built dashboard at {0}".format(output_path))


def handle_dashboard_build(_: argparse.Namespace) -> int:
    from agent_mesh.state.storage import resolve_coordination_root, resolve_repo_root

    repo_root = resolve_repo_root(Path.cwd())
    build_dashboard(repo_root, resolve_coordination_root(repo_root))
    return 0


def handle_merge(args: argparse.Namespace) -> int:
    import shutil

    from agent_mesh.config import load_project_config
    from agent_mesh.state.models import Claim, WorkItem
    from agent_mesh.state.storage import load_model, resolve_coordination_root, resolve_repo_root, save_model_json
    from agent_mesh.topology import resolve_coordination_worktree_path

    repo_root = resolve_repo_root(Path.cwd())
    coordination_root = resolve_coordination_root(repo_root)
    config = load_project_config(repo_root)
    warnings_fired = False

    work_path = coordination_root / ".agentic/work" / "{0}.json".format(args.work_id)
    if not work_path.exists():
        emit("ERROR: work item {0} not found".format(args.work_id))
        return 1
    work_item = load_model(work_path, WorkItem)

    claim_path = coordination_root / ".agentic/claims" / "{0}.json".format(args.work_id)
    if not claim_path.exists():
        emit("ERROR: no active claim for {0}".format(args.work_id))
        return 1
    claim = load_model(claim_path, Claim)

    # Guard: verify branch is merged into default branch before destroying anything
    if claim.branch and not getattr(args, "skip_merge_check", False):
        base = config.default_branch
        result = run_git(repo_root, ["branch", "--merged", "origin/{0}".format(base), "--list", claim.branch])
        if result.returncode != 0 or claim.branch not in result.stdout:
            emit(
                "ERROR: branch {0} does not appear merged into {1}. "
                "Merge the PR first, or use --skip-merge-check to override.".format(
                    claim.branch, base
                )
            )
            return 1

    coordination_worktree = resolve_coordination_worktree_path(repo_root, config)

    # Remove task worktree if it exists and is not the coordination worktree
    if config.coordination.worktree_policy != "off" and claim.worktree:
        worktree_path = Path(claim.worktree).resolve()
        if worktree_path == coordination_worktree.resolve():
            emit("ERROR: claim worktree matches the coordination worktree — refusing to remove it")
            return 1
        if worktree_path.exists() and (worktree_path / ".git").exists():
            dirty = run_git(worktree_path, ["status", "--porcelain"])
            if dirty.returncode == 0 and dirty.stdout.strip():
                if not getattr(args, "discard_uncommitted", False):
                    emit(
                        "ERROR: worktree {0} has uncommitted changes. "
                        "Commit or stash them, or use --discard-uncommitted to discard.".format(worktree_path)
                    )
                    return 1
                emit("Discarding uncommitted changes in worktree {0} (--discard-uncommitted)".format(worktree_path))
            result = run_git(repo_root, ["worktree", "remove", "--force", str(worktree_path)])
            if result.returncode == 0:
                emit("Removed worktree: {0}".format(worktree_path))
            else:
                emit("WARNING: could not remove worktree {0}: {1}".format(
                    worktree_path, (result.stderr or result.stdout).strip()
                ))
                warnings_fired = True
        else:
            emit("Worktree already absent: {0}".format(claim.worktree))

    # Delete remote branch
    if claim.branch and not args.no_push:
        result = run_git(repo_root, ["push", "origin", "--delete", claim.branch])
        if result.returncode == 0:
            emit("Deleted remote branch: {0}".format(claim.branch))
        else:
            detail = (result.stderr or result.stdout).strip()
            if "remote ref does not exist" in detail:
                emit("Remote branch already absent: {0}".format(claim.branch))
            else:
                emit("WARNING: could not delete remote branch {0}: {1}".format(claim.branch, detail))
                warnings_fired = True

    # Delete local branch (force since merge happened on remote via PR)
    if claim.branch and branch_exists(repo_root, claim.branch):
        result = run_git(repo_root, ["branch", "-D", claim.branch])
        if result.returncode == 0:
            emit("Deleted local branch: {0}".format(claim.branch))
        else:
            emit("WARNING: could not delete local branch {0}: {1}".format(
                claim.branch, (result.stderr or result.stdout).strip()
            ))
            warnings_fired = True

    # Update review packet status to merged if one exists
    review_packet_path = coordination_root / ".agentic/reviews" / "PR-{0}.json".format(args.work_id)
    if review_packet_path.exists():
        from agent_mesh.state.models import ReviewPacket
        review = load_model(review_packet_path, ReviewPacket)
        review.status = "merged"
        save_model_json(review_packet_path, review)
        emit("Marked review packet merged: PR-{0}".format(args.work_id))
    else:
        emit("WARNING: no review packet found for {0} — dashboard may show stale review state".format(args.work_id))
        warnings_fired = True

    # Mark work item done first — safer order: if archive fails, work item is
    # already done and the live claim can be retried
    now = utc_now()
    work_item.status = "done"
    work_item.updated_at = now
    save_model_json(work_path, work_item)
    emit("Marked {0} done".format(args.work_id))

    # Archive the claim last
    archive_dir = coordination_root / ".agentic/claims/archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_path = archive_dir / "{0}.json".format(args.work_id)
    try:
        shutil.move(str(claim_path), str(archive_path))
        emit("Archived claim: {0}".format(archive_path.name))
    except FileNotFoundError:
        emit("WARNING: claim file already moved by a concurrent process — skipping archive")
        warnings_fired = True

    if config.dashboard.enabled and not warnings_fired:
        build_dashboard(repo_root, coordination_root)
    elif config.dashboard.enabled:
        emit("Skipped dashboard rebuild due to warnings — run mesh sync to rebuild")

    return 2 if warnings_fired else 0


def handle_sync(_: argparse.Namespace) -> int:
    from agent_mesh.config import load_project_config
    from agent_mesh.state.storage import resolve_coordination_root, resolve_repo_root
    from agent_mesh.topology import ensure_coordination_worktree

    repo_root = resolve_repo_root(Path.cwd())
    coordination_root = resolve_coordination_root(repo_root)
    config = load_project_config(repo_root)
    if config.coordination.worktree_policy != "off" and git_head_available(repo_root):
        try:
            coordination = ensure_coordination_worktree(repo_root, config)
            emit(
                "Coordination worktree {0}: {1} @ {2}".format(
                    coordination.action,
                    coordination.branch,
                    coordination.path,
                )
            )
            # Re-probe after ensure in case the worktree was just created
            coordination_root = resolve_coordination_root(repo_root)
        except RuntimeError as error:
            emit("ERROR: {0}".format(error))
            return 1
    if config.dashboard.enabled:
        build_dashboard(repo_root, coordination_root)
    return handle_doctor(argparse.Namespace())


def derive_project_key(project_name: str) -> str:
    letters = [char for char in project_name.upper() if char.isalnum()]
    return "".join(letters[:4]) or "APP"


def parse_csv(raw: str) -> List[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def git_head_available(repo_root: Path) -> bool:
    result = run_git(repo_root, ["rev-parse", "--verify", "HEAD"])
    return result.returncode == 0


def resolve_review_packet_path(coordination_root: Path, target: str) -> Optional[Path]:
    candidates = [
        coordination_root / ".agentic/reviews" / "{0}.json".format(target),
        coordination_root / ".agentic/reviews" / "PR-{0}.json".format(target),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def parse_utc(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


def derive_workspace_id(agent: str, machine: str, suffix: Optional[str] = None) -> str:
    base = "{0}-{1}".format(slugify(agent), slugify(machine))
    if suffix:
        return "{0}-{1}".format(base, slugify(suffix))
    return base


def claim_activity(claim, stale_after_minutes: int, now: Optional[datetime] = None) -> str:
    now = now or datetime.now(timezone.utc)
    stale_after = now - timedelta(minutes=stale_after_minutes)
    return "stale" if parse_utc(claim.last_seen) < stale_after else "active"


def handle_existing_claim(repo_root, coordination_root, config, work_item, claim, claim_path, args) -> int:
    from agent_mesh.state.models import ClaimEvent
    from agent_mesh.state.storage import save_model_json

    now = utc_now()
    activity = claim_activity(claim, config.coordination.claim_stale_after_minutes)
    actor = "agent:{0}:{1}".format(args.agent, args.machine)

    if args.resume:
        claim.claimed_by = actor
        claim.agent_runtime = args.agent
        claim.role = args.role
        claim.machine = args.machine
        claim.workspace_id = claim.workspace_id or args.workspace_id or derive_workspace_id(
            args.agent, args.machine
        )
        claim.last_seen = now
        claim.status = "in_progress"
        claim.events.append(ClaimEvent(action="resumed", at=now, by=actor))
        save_model_json(claim_path, claim)
        if work_item.status == "ready":
            work_item.status = "in_progress"
            work_item.updated_at = now
            save_model_json(coordination_root / ".agentic/work" / "{0}.json".format(work_item.id), work_item)
        emit("Resumed {0} on branch {1}".format(work_item.id, claim.branch))
        if claim.worktree:
            emit("Worktree: {0}".format(claim.worktree))
            if claim.workspace_id:
                emit("Workspace: {0}".format(claim.workspace_id))
            emit("Next: cd {0}".format(claim.worktree))
        return 0

    if args.takeover:
        if activity != "stale":
            emit(
                "ERROR: claim for {0} is still active; use --resume to continue it or wait until it is stale".format(
                    work_item.id
                )
            )
            return 1
        requested_branch = args.branch or claim.branch
        takeover_workspace_id = args.workspace_id or derive_workspace_id(
            args.agent, args.machine, now.replace(":", "").replace("-", "").lower()
        )
        requested_worktree = args.worktree
        try:
            release_stale_worktree_branch(claim)
            claim.worktree = prepare_claim_workspace(
                repo_root,
                config.default_branch,
                requested_branch,
                takeover_workspace_id,
                requested_worktree,
            )
        except RuntimeError as error:
            emit("ERROR: {0}".format(error))
            return 1
        previous_owner = claim.claimed_by
        claim.claimed_by = actor
        claim.agent_runtime = args.agent
        claim.role = args.role
        claim.machine = args.machine
        claim.workspace_id = takeover_workspace_id
        claim.branch = requested_branch
        claim.last_seen = now
        claim.status = "in_progress"
        claim.events.append(
            ClaimEvent(
                action="taken_over",
                at=now,
                by=actor,
                note="previous owner: {0}".format(previous_owner),
            )
        )
        save_model_json(claim_path, claim)
        if work_item.status == "ready":
            work_item.status = "in_progress"
            work_item.updated_at = now
            save_model_json(coordination_root / ".agentic/work" / "{0}.json".format(work_item.id), work_item)
        emit("Took over stale claim for {0} on branch {1}".format(work_item.id, claim.branch))
        if claim.worktree:
            emit("Worktree: {0}".format(claim.worktree))
            if claim.workspace_id:
                emit("Workspace: {0}".format(claim.workspace_id))
            emit("Next: cd {0}".format(claim.worktree))
        return 0

    emit(
        "ERROR: claim already exists for {0} ({1}); use --resume to continue it or --takeover if it becomes stale".format(
            work_item.id, activity
        )
    )
    return 1


def run_git(repo_root: Path, args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )


def branch_exists(repo_root: Path, branch: str) -> bool:
    result = run_git(repo_root, ["show-ref", "--verify", "--quiet", "refs/heads/{0}".format(branch)])
    return result.returncode == 0


def ensure_git_ok(result: subprocess.CompletedProcess[str], action: str) -> None:
    if result.returncode == 0:
        return
    detail = (result.stderr or result.stdout).strip() or "unknown git error"
    raise RuntimeError("{0}: {1}".format(action, detail))


def default_worktree_path(repo_root: Path, workspace_id: str, configured_root: Optional[str]) -> Path:
    if configured_root:
        root_path = Path(configured_root).expanduser()
        if not root_path.is_absolute():
            root_path = (repo_root / root_path).resolve()
        else:
            root_path = root_path.resolve()
        return root_path / "{0}-{1}".format(repo_root.name, workspace_id)
    return repo_root.parent / "{0}-{1}".format(repo_root.name, workspace_id)


def prepare_claim_workspace(
    repo_root: Path,
    default_branch: str,
    branch: str,
    workspace_id: str,
    requested_worktree: Optional[str],
) -> Optional[str]:
    from agent_mesh.config import load_project_config

    config = load_project_config(repo_root)
    policy = config.coordination.worktree_policy
    if policy == "off":
        return requested_worktree

    worktree_path = Path(requested_worktree).expanduser() if requested_worktree else default_worktree_path(
        repo_root, workspace_id, config.coordination.worktree_root
    )
    if not worktree_path.is_absolute():
        worktree_path = (repo_root / worktree_path).resolve()
    else:
        worktree_path = worktree_path.resolve()

    if worktree_path == repo_root.resolve():
        if policy == "preferred":
            return str(worktree_path)
        raise RuntimeError("worktree policy requires a dedicated worktree, not the shared repo root")

    if worktree_path.exists():
        git_dir = worktree_path / ".git"
        if git_dir.exists():
            ensure_worktree_ready(repo_root, worktree_path, default_branch, branch)
            return str(worktree_path)
        raise RuntimeError("worktree path already exists and is not a git worktree: {0}".format(worktree_path))

    base_ref = branch if branch_exists(repo_root, branch) else default_branch
    git_args = ["worktree", "add"]
    if not branch_exists(repo_root, branch):
        git_args.extend(["-b", branch])
    git_args.extend([str(worktree_path), base_ref])
    ensure_git_ok(run_git(repo_root, git_args), "failed to create worktree")
    return str(worktree_path)


def ensure_worktree_ready(
    repo_root: Path,
    worktree_path: Path,
    default_branch: str,
    branch: str,
) -> None:
    current_branch = run_git(worktree_path, ["branch", "--show-current"])
    ensure_git_ok(current_branch, "failed to inspect existing worktree branch")
    active_branch = current_branch.stdout.strip()
    if active_branch == branch:
        return

    dirty = run_git(worktree_path, ["status", "--porcelain"])
    ensure_git_ok(dirty, "failed to inspect existing worktree status")
    if dirty.stdout.strip():
        raise RuntimeError(
            "existing worktree is dirty on branch {0}; choose a different workspace or clean it first".format(
                active_branch or "<detached>"
            )
        )

    if branch_exists(repo_root, branch):
        switch_result = run_git(worktree_path, ["switch", branch])
        ensure_git_ok(switch_result, "failed to switch reusable worktree to existing branch")
        return

    switch_result = run_git(worktree_path, ["switch", "-c", branch, default_branch])
    ensure_git_ok(switch_result, "failed to switch reusable worktree to a new branch")


def release_stale_worktree_branch(claim) -> None:
    if not claim.worktree:
        return
    worktree_path = Path(claim.worktree)
    if not worktree_path.exists() or not (worktree_path / ".git").exists():
        return

    current_branch = run_git(worktree_path, ["branch", "--show-current"])
    ensure_git_ok(current_branch, "failed to inspect stale worktree branch")
    if current_branch.stdout.strip() != claim.branch:
        return

    detach_result = run_git(worktree_path, ["switch", "--detach", claim.branch])
    ensure_git_ok(detach_result, "failed to detach stale worktree from claimed branch")


def render_pr_body(work_item, claim) -> str:
    criteria = "\n".join("- {0}".format(item) for item in work_item.acceptance_criteria)
    evidence_lines = "\n".join(
        "- `{0}`: {1} ({2})".format(item.command, item.summary, item.result) for item in claim.evidence
    )
    checklist = "\n".join(
        [
            "- [ ] Acceptance criteria verified",
            "- [ ] Tests or other evidence reviewed",
            "- [ ] Risks and follow-ups understood",
        ]
    )
    return """# {0}: {1}

## Summary

- Work item: `{0}`
- Module: `{4}`
- Branch: `{2}`
- Role: `{3}`
- Execution: `{5}`
- Risk: `{6}`

## Description

{7}

## Acceptance Criteria

{8}

## Evidence

{9}

## Review Checklist

{10}
""".format(
        work_item.id,
        work_item.title,
        claim.branch,
        claim.role,
        work_item.module or "unspecified",
        work_item.execution,
        work_item.risk,
        work_item.description,
        criteria or "- None provided",
        evidence_lines or "- No recorded evidence yet",
        checklist,
    )


def create_review_packet(config, work_item, claim):
    from agent_mesh.state.models import PullRequestRef, ReviewAuthor, ReviewContext, ReviewPacket

    created_at = utc_now()
    packet_id = "PR-{0}".format(work_item.id)
    return ReviewPacket(
        type="review_request",
        id=packet_id,
        work_id=work_item.id,
        pr=PullRequestRef(branch=claim.branch, base=config.default_branch),
        author=ReviewAuthor(agent_runtime=claim.agent_runtime, role=claim.role),
        requested_role="reviewer",
        context=ReviewContext(
            work_item=".agentic/work/{0}.json".format(work_item.id),
            claim=".agentic/claims/{0}.json".format(work_item.id),
            prd=work_item.prd,
            context_files=[".agentic/context/CONTEXT.md", ".agentic/context/CONTEXT-MAP.md"],
        ),
        evidence=claim.evidence,
        status="pending_review",
        created_at=created_at,
    )


def render_dashboard_html(config, work_items: Iterable[object], claims: Iterable[object], reviews: Iterable[object]) -> str:
    import html as _html
    e = _html.escape

    work_items = list(work_items)
    claims = list(claims)
    reviews = list(reviews)

    counts = count_by_status(work_items)
    total = sum(counts.values())
    done = counts.get("done", 0)
    progress_pct = int(done / total * 100) if total else 0

    status_colors = {
        "done": ("#16a34a", "#dcfce7"),
        "ready": ("#2563eb", "#dbeafe"),
        "in_progress": ("#d97706", "#fef3c7"),
        "blocked": ("#dc2626", "#fee2e2"),
        "review": ("#7c3aed", "#ede9fe"),
    }
    kind_colors = {
        "bug": ("#dc2626", "#fee2e2"),
        "feature": ("#0891b2", "#cffafe"),
        "security": ("#7c3aed", "#ede9fe"),
        "refactor": ("#4b5563", "#f3f4f6"),
    }
    risk_colors = {"high": "#dc2626", "medium": "#d97706", "low": "#16a34a"}

    def badge(text, fg, bg):
        return '<span style="display:inline-block;padding:1px 8px;border-radius:12px;font-size:0.75rem;font-weight:600;color:{0};background:{1}">{2}</span>'.format(fg, bg, e(text))

    def status_badge(s):
        fg, bg = status_colors.get(s, ("#374151", "#f3f4f6"))
        return badge(s, fg, bg)

    def kind_badge(k):
        fg, bg = kind_colors.get(k, ("#374151", "#f3f4f6"))
        return badge(k, fg, bg)

    def risk_dot(r):
        color = risk_colors.get(r, "#9ca3af")
        return '<span title="risk: {0}" style="display:inline-block;width:8px;height:8px;border-radius:50%;background:{1};margin-right:4px"></span>'.format(e(r), color)

    summary_chips = "".join(
        '<span style="display:inline-flex;align-items:center;gap:6px;padding:4px 14px;border-radius:20px;background:{1};color:{0};font-weight:600;font-size:0.85rem">'
        '<span style="font-size:1.1rem">{3}</span>{2}: {4}</span>'.format(
            fg, bg,
            e(status),
            {"done": "✓", "ready": "○", "in_progress": "◉", "blocked": "✗", "review": "⟳"}.get(status, "·"),
            count,
            *((fg, bg) for fg, bg in [status_colors.get(status, ("#374151", "#f3f4f6"))]),
        )
        for status, count in sorted(counts.items())
        for fg, bg in [status_colors.get(status, ("#374151", "#f3f4f6"))]
    )

    task_rows = "".join(
        '<tr class="task-row" data-status="{status}" data-kind="{kind}">'
        '<td style="padding:10px 12px;font-family:monospace;font-size:0.85rem;white-space:nowrap">{id}</td>'
        '<td style="padding:10px 12px">{status_b}</td>'
        '<td style="padding:10px 12px">{kind_b}</td>'
        '<td style="padding:10px 6px">{risk_d}</td>'
        '<td style="padding:10px 12px;max-width:420px">'
        '<span style="font-weight:500">{title}</span>'
        '<div class="task-detail" style="display:none;margin-top:6px;font-size:0.82rem;color:#4b5563;line-height:1.6">'
        '<strong>Module:</strong> {module}&nbsp;&nbsp;<strong>Risk:</strong> {risk}'
        '</div>'
        '</td>'
        '</tr>'.format(
            id=e(item.id),
            status=e(item.status),
            kind=e(getattr(item, "kind", "")),
            status_b=status_badge(item.status),
            kind_b=kind_badge(getattr(item, "kind", "")),
            risk_d=risk_dot(getattr(item, "risk", "")),
            risk=e(getattr(item, "risk", "—")),
            title=e(item.title),
            module=e(getattr(item, "module", "—")),
        )
        for item in sorted(work_items, key=lambda x: (x.status != "in_progress", x.status != "review", x.status != "ready", x.id))
    )

    claim_cards = "".join(
        '<div style="border:1px solid #e5e7eb;border-radius:8px;padding:12px 14px;margin-bottom:10px">'
        '<div style="display:flex;justify-content:space-between;align-items:center">'
        '<span style="font-family:monospace;font-weight:700;color:#1d4ed8">{work_id}</span>'
        '{status_b}'
        '</div>'
        '<div style="font-size:0.82rem;color:#374151;margin-top:6px">'
        '<span style="margin-right:12px">🤖 {agent}</span>'
        '<span style="color:#6b7280;font-family:monospace;font-size:0.78rem">{branch}</span>'
        '</div>'
        '</div>'.format(
            work_id=e(c.work_id),
            status_b=status_badge("in_progress"),
            agent=e(getattr(c, "agent_runtime", "agent")),
            branch=e(getattr(c, "branch", "")),
        )
        for c in claims
    ) or '<p style="color:#9ca3af;font-size:0.9rem">No active claims</p>'

    review_cards = "".join(
        '<div style="display:flex;justify-content:space-between;align-items:center;'
        'border:1px solid #e5e7eb;border-radius:8px;padding:10px 14px;margin-bottom:8px">'
        '<span style="font-family:monospace;font-weight:600">{id}</span>'
        '{status_b}'
        '</div>'.format(
            id=e(r.id),
            status_b=status_badge(r.status),
        )
        for r in reviews
    ) or '<p style="color:#9ca3af;font-size:0.9rem">No reviews</p>'

    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{project_name} · Agent Mesh</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f8fafc; color: #1e293b; line-height: 1.5; }}
    header {{ background: linear-gradient(135deg, #0f172a 0%, #1e3a5f 100%); color: white; padding: 28px 32px; }}
    header h1 {{ font-size: 1.6rem; font-weight: 700; letter-spacing: -0.02em; }}
    header .sub {{ opacity: 0.65; font-size: 0.85rem; margin-top: 4px; font-family: monospace; }}
    .main {{ max-width: 1100px; margin: 0 auto; padding: 28px 24px; }}
    .progress-wrap {{ background: white; border-radius: 12px; padding: 20px 24px; margin-bottom: 24px; box-shadow: 0 1px 3px rgba(0,0,0,.06); }}
    .progress-label {{ display: flex; justify-content: space-between; font-size: 0.85rem; color: #475569; margin-bottom: 8px; }}
    .progress-bar {{ height: 10px; background: #e2e8f0; border-radius: 5px; overflow: hidden; }}
    .progress-fill {{ height: 100%; border-radius: 5px; background: linear-gradient(90deg, #16a34a, #4ade80); transition: width .4s ease; }}
    .chips {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }}
    .grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 24px; }}
    @media(max-width:680px) {{ .grid-2 {{ grid-template-columns: 1fr; }} }}
    .card {{ background: white; border-radius: 12px; padding: 20px 22px; box-shadow: 0 1px 3px rgba(0,0,0,.06); }}
    .card h2 {{ font-size: 0.95rem; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; color: #64748b; margin-bottom: 14px; }}
    .task-card {{ background: white; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,.06); overflow: hidden; }}
    .task-card-header {{ padding: 16px 22px; border-bottom: 1px solid #f1f5f9; display: flex; align-items: center; gap: 12px; }}
    .task-card-header h2 {{ font-size: 0.95rem; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; color: #64748b; flex: 1; }}
    .filters {{ display: flex; gap: 8px; flex-wrap: wrap; }}
    .filter-btn {{ border: 1px solid #e2e8f0; background: white; border-radius: 6px; padding: 3px 10px; font-size: 0.78rem; cursor: pointer; color: #475569; transition: all .15s; }}
    .filter-btn:hover, .filter-btn.active {{ background: #1e3a5f; color: white; border-color: #1e3a5f; }}
    table {{ width: 100%; border-collapse: collapse; }}
    thead th {{ padding: 10px 12px; text-align: left; font-size: 0.78rem; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; color: #94a3b8; border-bottom: 1px solid #f1f5f9; }}
    .task-row {{ border-bottom: 1px solid #f8fafc; cursor: pointer; transition: background .1s; }}
    .task-row:hover {{ background: #f8fafc; }}
    .task-row:last-child {{ border-bottom: none; }}
    .task-detail {{ border-top: 1px solid #f1f5f9; padding: 8px 12px 4px; background: #fafafa; }}
  </style>
</head>
<body>
  <header>
    <h1>⬡ {project_name}</h1>
    <div class="sub">Agent Mesh · <code>{project_key}</code></div>
  </header>
  <div class="main">
    <div class="progress-wrap">
      <div class="progress-label">
        <span>Overall progress</span>
        <span><strong>{done}</strong> / {total} tasks done ({pct}%)</span>
      </div>
      <div class="progress-bar"><div class="progress-fill" style="width:{pct}%"></div></div>
      <div class="chips">{summary_chips}</div>
    </div>
    <div class="grid-2">
      <div class="card">
        <h2>Active Claims</h2>
        {claim_cards}
      </div>
      <div class="card">
        <h2>Reviews</h2>
        {review_cards}
      </div>
    </div>
    <div class="task-card">
      <div class="task-card-header">
        <h2>Tasks</h2>
        <div class="filters">
          <button class="filter-btn active" onclick="filter(this,'all')">All</button>
          <button class="filter-btn" onclick="filter(this,'ready')">Ready</button>
          <button class="filter-btn" onclick="filter(this,'in_progress')">In Progress</button>
          <button class="filter-btn" onclick="filter(this,'done')">Done</button>
          <button class="filter-btn" onclick="filter(this,'bug')">Bugs</button>
          <button class="filter-btn" onclick="filter(this,'feature')">Features</button>
        </div>
      </div>
      <table>
        <thead><tr>
          <th>ID</th><th>Status</th><th>Kind</th><th>Risk</th><th>Title</th>
        </tr></thead>
        <tbody id="task-tbody">{task_rows}</tbody>
      </table>
    </div>
  </div>
  <script>
    document.querySelectorAll('.task-row').forEach(function(row) {{
      row.addEventListener('click', function() {{
        var detail = row.querySelector('.task-detail');
        detail.style.display = detail.style.display === 'none' ? 'block' : 'none';
      }});
    }});
    function filter(btn, val) {{
      document.querySelectorAll('.filter-btn').forEach(function(b) {{ b.classList.remove('active'); }});
      btn.classList.add('active');
      document.querySelectorAll('.task-row').forEach(function(row) {{
        var show = val === 'all' || row.dataset.status === val || row.dataset.kind === val;
        row.style.display = show ? '' : 'none';
      }});
    }}
  </script>
</body>
</html>""".format(
        project_name=e(config.project_name),
        project_key=e(config.project_key),
        done=done,
        total=total,
        pct=progress_pct,
        summary_chips=summary_chips,
        claim_cards=claim_cards,
        review_cards=review_cards,
        task_rows=task_rows,
    )


def count_by_status(items: Iterable[object]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        status = getattr(item, "status", "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts


def summarize_work_items(work_items: Iterable[object]) -> List[str]:
    counts = count_by_status(work_items)
    return ["  - {0}: {1}".format(status, count) for status, count in sorted(counts.items())]


def summarize_claims(claims: Iterable[object], stale_after_minutes: int) -> List[str]:
    return [
        "  - {0}: {1} [{2}] on {3}{4}{5}".format(
            claim.work_id,
            claim.agent_runtime,
            claim_activity(claim, stale_after_minutes),
            claim.branch,
            " via {0}".format(claim.workspace_id) if getattr(claim, "workspace_id", None) else "",
            " in {0}".format(claim.worktree) if claim.worktree else "",
        )
        for claim in list(claims)[:5]
    ]


def summarize_reviews(reviews: Iterable[object]) -> List[str]:
    return ["  - {0}: {1}".format(review.id, review.status) for review in list(reviews)[:5]]
