"""CLI entrypoint for Agent Mesh."""

from __future__ import annotations

import argparse
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
    claim_parser.add_argument("--agent", default="codex")
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

    return parser


def app(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    if not hasattr(args, "func"):
        parser.print_help()
        return 0
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
    )
    emit("Initialized Agent Mesh in {0}".format(repo_root))
    emit("Created {0} files.".format(len(result.created)))
    emit("Skipped {0} existing files.".format(len(result.skipped)))
    if args.worktree_policy != "off" and git_head_available(repo_root):
        try:
            coordination = ensure_coordination_worktree(repo_root, load_project_config(repo_root))
            emit(
                "Coordination worktree {0}: {1} @ {2}".format(
                    coordination.action,
                    coordination.branch,
                    coordination.path,
                )
            )
        except RuntimeError as error:
            emit("WARN: {0}".format(error))
    return 0


def handle_doctor(_: argparse.Namespace) -> int:
    from agent_mesh.state.storage import resolve_repo_root
    from agent_mesh.state.validate import validate_state_tree

    repo_root = resolve_repo_root(Path.cwd())
    errors = validate_state_tree(repo_root)
    if errors:
        for error in errors:
            emit("ERROR: {0}".format(error))
        return 1
    emit("OK: Agent Mesh state is valid.")
    return 0


def handle_status(_: argparse.Namespace) -> int:
    from agent_mesh.config import load_project_config
    from agent_mesh.state.storage import list_claims, list_reviews, list_work_items, resolve_repo_root
    from agent_mesh.topology import inspect_coordination_worktree

    repo_root = resolve_repo_root(Path.cwd())
    config = load_project_config(repo_root)
    work_items = list_work_items(repo_root)
    claims = list_claims(repo_root)
    reviews = list_reviews(repo_root)
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
        return "installed" if (repo_root / "OPENCODE.md").exists() else "missing"
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
    from agent_mesh.state.storage import next_work_item_id, resolve_repo_root, save_model_json

    repo_root = resolve_repo_root(Path.cwd())
    config = load_project_config(repo_root)
    work_id = next_work_item_id(repo_root, config.project_key)
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
    path = repo_root / ".agentic/work" / "{0}.json".format(work_id)
    save_model_json(path, work_item)
    emit("Created task {0}".format(work_id))
    return 0


def handle_task_list(_: argparse.Namespace) -> int:
    from agent_mesh.state.storage import list_work_items, resolve_repo_root

    repo_root = resolve_repo_root(Path.cwd())
    for work_item in list_work_items(repo_root):
        emit("{0}\t{1}\t{2}".format(work_item.id, work_item.status, work_item.title))
    return 0


def handle_task_show(args: argparse.Namespace) -> int:
    from agent_mesh.state.models import WorkItem
    from agent_mesh.state.storage import load_model, resolve_repo_root

    repo_root = resolve_repo_root(Path.cwd())
    work_item = load_model(repo_root / ".agentic/work" / "{0}.json".format(args.work_id), WorkItem)
    emit(work_item.model_dump_json(indent=2))
    return 0


def handle_claim(args: argparse.Namespace) -> int:
    from agent_mesh.config import load_project_config
    from agent_mesh.state.models import Claim, ClaimEvent, WorkItem
    from agent_mesh.state.storage import load_model, resolve_repo_root, save_model_json

    repo_root = resolve_repo_root(Path.cwd())
    config = load_project_config(repo_root)
    work_path = repo_root / ".agentic/work" / "{0}.json".format(args.work_id)
    work_item = load_model(work_path, WorkItem)

    existing_claim_path = repo_root / ".agentic/claims" / "{0}.json".format(args.work_id)
    if args.resume and args.takeover:
        emit("ERROR: choose only one of --resume or --takeover")
        return 1
    if existing_claim_path.exists():
        claim = load_model(existing_claim_path, Claim)
        return handle_existing_claim(
            repo_root=repo_root,
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
        emit("Next: cd {0}".format(worktree))
    return 0


def handle_pr(args: argparse.Namespace) -> int:
    from agent_mesh.config import load_project_config
    from agent_mesh.state.models import Claim, WorkItem
    from agent_mesh.state.storage import load_model, resolve_repo_root, save_model_json

    repo_root = resolve_repo_root(Path.cwd())
    config = load_project_config(repo_root)
    work_item = load_model(repo_root / ".agentic/work" / "{0}.json".format(args.work_id), WorkItem)
    claim = load_model(repo_root / ".agentic/claims" / "{0}.json".format(args.work_id), Claim)

    body = render_pr_body(work_item, claim)
    emit(body)

    review_packet = create_review_packet(config, work_item, claim)
    review_packet_path = repo_root / ".agentic/reviews" / "{0}.json".format(review_packet.id)
    save_model_json(review_packet_path, review_packet)

    work_item.status = "pr_open"
    work_item.updated_at = utc_now()
    save_model_json(repo_root / ".agentic/work" / "{0}.json".format(args.work_id), work_item)

    if args.dry_run:
        emit("Dry-run: review packet written to {0}".format(review_packet_path))
    return 0


def handle_review_packet(args: argparse.Namespace) -> int:
    from agent_mesh.config import load_project_config
    from agent_mesh.state.models import Claim, WorkItem
    from agent_mesh.state.storage import load_model, resolve_repo_root, save_model_json

    repo_root = resolve_repo_root(Path.cwd())
    config = load_project_config(repo_root)
    work_item = load_model(repo_root / ".agentic/work" / "{0}.json".format(args.work_id), WorkItem)
    claim = load_model(repo_root / ".agentic/claims" / "{0}.json".format(args.work_id), Claim)
    review_packet = create_review_packet(config, work_item, claim)
    review_packet_path = repo_root / ".agentic/reviews" / "{0}.json".format(review_packet.id)
    save_model_json(review_packet_path, review_packet)
    emit("Wrote review packet {0}".format(review_packet_path))
    return 0


def handle_review(args: argparse.Namespace) -> int:
    from agent_mesh.state.models import Claim, ReviewPacket, WorkItem
    from agent_mesh.state.storage import load_model, resolve_repo_root

    repo_root = resolve_repo_root(Path.cwd())
    review_path = resolve_review_packet_path(repo_root, args.target)
    if review_path is None:
        emit("ERROR: could not find review packet for {0}".format(args.target))
        return 1

    review_packet = load_model(review_path, ReviewPacket)
    claim = load_model(repo_root / review_packet.context.claim, Claim)
    work_item = load_model(repo_root / review_packet.context.work_item, WorkItem)
    current_path = Path.cwd().resolve()
    target_worktree = Path(claim.worktree).resolve() if claim.worktree else None

    emit("Review packet: {0}".format(review_packet.id))
    emit("Work item: {0} ({1})".format(work_item.id, work_item.title))
    emit("Branch: {0} -> {1}".format(review_packet.pr.branch, review_packet.pr.base))
    emit("Requested role: {0}".format(review_packet.requested_role))
    emit("Workspace: {0}".format(claim.workspace_id or "unspecified"))
    emit("Worktree: {0}".format(claim.worktree or "shared repo"))
    emit("Current path: {0}".format(current_path))
    emit("Review status: {0}".format(review_packet.status))

    for context_file in review_packet.context.context_files:
        emit("Context: {0}".format(context_file))

    if target_worktree is not None and current_path != target_worktree:
        emit("Resolved workspace differs from the current path.")
        emit("Next: cd {0}".format(target_worktree))
        emit("Then: mesh review {0}".format(review_packet.id))
        return 0

    emit("Current path matches the resolved review workspace.")
    emit("Next: inspect the diff and review against the task contract.")
    return 0


def handle_dashboard_build(_: argparse.Namespace) -> int:
    from agent_mesh.config import load_project_config
    from agent_mesh.state.storage import list_claims, list_reviews, list_work_items, resolve_repo_root

    repo_root = resolve_repo_root(Path.cwd())
    config = load_project_config(repo_root)
    output_path = repo_root / config.dashboard.output_dir / "index.html"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    work_items = list_work_items(repo_root)
    claims = list_claims(repo_root)
    reviews = list_reviews(repo_root)
    output_path.write_text(render_dashboard_html(config, work_items, claims, reviews), encoding="utf-8")
    emit("Built dashboard at {0}".format(output_path))
    return 0


def handle_sync(_: argparse.Namespace) -> int:
    from agent_mesh.config import load_project_config
    from agent_mesh.state.storage import resolve_repo_root
    from agent_mesh.topology import ensure_coordination_worktree

    repo_root = resolve_repo_root(Path.cwd())
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
        except RuntimeError as error:
            emit("ERROR: {0}".format(error))
            return 1
    if config.dashboard.enabled:
        handle_dashboard_build(argparse.Namespace())
    return handle_doctor(argparse.Namespace())


def derive_project_key(project_name: str) -> str:
    letters = [char for char in project_name.upper() if char.isalnum()]
    return "".join(letters[:4]) or "APP"


def parse_csv(raw: str) -> List[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def git_head_available(repo_root: Path) -> bool:
    result = run_git(repo_root, ["rev-parse", "--verify", "HEAD"])
    return result.returncode == 0


def resolve_review_packet_path(repo_root: Path, target: str) -> Optional[Path]:
    candidates = [
        repo_root / ".agentic/reviews" / "{0}.json".format(target),
        repo_root / ".agentic/reviews" / "PR-{0}.json".format(target),
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


def handle_existing_claim(repo_root, config, work_item, claim, claim_path, args) -> int:
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
            save_model_json(repo_root / ".agentic/work" / "{0}.json".format(work_item.id), work_item)
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
            save_model_json(repo_root / ".agentic/work" / "{0}.json".format(work_item.id), work_item)
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
    work_items = list(work_items)
    claims = list(claims)
    reviews = list(reviews)
    work_summary = "".join(
        "<li>{0}: {1}</li>".format(status, count)
        for status, count in sorted(count_by_status(work_items).items())
    )
    work_list = "".join(
        "<li>{0} [{1}] {2}</li>".format(item.id, item.status, item.title) for item in work_items
    )
    claim_list = "".join(
        "<li>{0} [{1}] {2}</li>".format(item.work_id, item.agent_runtime, item.branch)
        for item in claims
    )
    review_list = "".join(
        "<li>{0} [{1}]</li>".format(item.id, item.status) for item in reviews
    )
    return """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>{0} Agent Mesh Dashboard</title>
    <style>
      body {{ font-family: sans-serif; margin: 2rem auto; max-width: 960px; line-height: 1.5; }}
      .meta {{ color: #555; }}
      .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 1.5rem; }}
      .panel {{ border: 1px solid #ddd; border-radius: 10px; padding: 1rem; }}
      code {{ background: #f3f3f3; padding: 0.1rem 0.3rem; border-radius: 4px; }}
    </style>
  </head>
  <body>
    <h1>{0} Agent Mesh Dashboard</h1>
    <p class="meta">Project key: <code>{4}</code></p>
    <div class="grid">
      <section class="panel">
        <h2>Task Summary</h2>
        <ul>{1}</ul>
      </section>
      <section class="panel">
        <h2>Active Claims</h2>
        <ul>{2}</ul>
      </section>
      <section class="panel">
        <h2>Pending Reviews</h2>
        <ul>{3}</ul>
      </section>
    </div>
    <section class="panel">
      <h2>Task Details</h2>
      <ul>{5}</ul>
    </section>
  </body>
</html>
""".format(
        config.project_name,
        work_summary or "<li>None</li>",
        claim_list or "<li>None</li>",
        review_list or "<li>None</li>",
        config.project_key,
        work_list or "<li>None</li>",
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
