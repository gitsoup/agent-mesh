"""CLI entrypoint for Agent Mesh."""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import sys
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
RUNTIME_ADAPTER_ALIASES = {
    "claude": "claude",
    "claude-code": "claude",
    "codex": "codex",
    "cursor": "cursor",
    "opencode": "opencode",
    "pi": "pi",
    "windsurf": "windsurf",
}


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
    init_parser.add_argument(
        "--adapters",
        default="generic",
        help="Optional adapter wrappers to install during init. Defaults to generic; additional adapters can be installed later with `mesh adapter install`.",
    )
    init_parser.add_argument("--force", action="store_true")
    init_parser.add_argument("--dashboard", dest="dashboard", action="store_true", default=True)
    init_parser.add_argument("--no-dashboard", dest="dashboard", action="store_false")
    init_parser.add_argument(
        "--worktree-policy",
        choices=["required", "preferred", "off"],
        default="required",
    )
    init_parser.add_argument("--worktree-root")
    init_parser.add_argument("--claim-stale-after-minutes", type=int, default=120)
    init_parser.add_argument("--lanes", type=int, default=0, help="Number of lane worktrees to provision.")
    init_parser.set_defaults(func=handle_init)

    doctor_parser = subparsers.add_parser("doctor", help="Validate Agent Mesh config and state.")
    doctor_parser.set_defaults(func=handle_doctor)

    lane_parser = subparsers.add_parser("lane", help="Lane management commands.")
    lane_subparsers = lane_parser.add_subparsers(dest="lane_command")

    lane_list_parser = lane_subparsers.add_parser("list", help="List provisioned lanes.")
    lane_list_parser.set_defaults(func=handle_lane_list)

    lane_add_parser = lane_subparsers.add_parser("add", help="Provision a new lane.")
    lane_add_parser.add_argument("name", nargs="?", default=None, help="Lane name (auto-generated if omitted).")
    lane_add_parser.set_defaults(func=handle_lane_add)

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

    bootstrap_tasks_parser = subparsers.add_parser(
        "bootstrap-tasks",
        help="Persist agent-prepared bootstrap tasks into the coordination work list.",
    )
    bootstrap_tasks_parser.add_argument(
        "--input",
        help="Read bootstrap task JSON from a file path instead of stdin.",
    )
    bootstrap_tasks_parser.set_defaults(func=handle_bootstrap_tasks)

    claim_parser = subparsers.add_parser("claim", help="Claim a local work item.")
    claim_parser.add_argument("work_id")
    claim_parser.add_argument("--agent", default="agent")
    claim_parser.add_argument("--role", default="implementer")
    claim_parser.add_argument("--machine", default=socket.gethostname())
    claim_parser.add_argument("--lane")
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
    dashboard_build_parser.add_argument(
        "--public",
        action="store_true",
        help="Build a stakeholder-safe static export with redacted coordination details.",
    )
    dashboard_build_parser.add_argument(
        "--output-dir",
        help="Override the output directory. Defaults to dist/public-dashboard for --public or the configured dashboard output dir otherwise.",
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
    maybe_emit_runtime_adapter_tip(args)
    return int(args.func(args) or 0)


def handle_version(_: argparse.Namespace) -> int:
    emit(__version__)
    return 0


def handle_init(args: argparse.Namespace) -> int:
    from agent_mesh.config import load_project_config
    from agent_mesh.scaffold import init_repo
    from agent_mesh.state.storage import resolve_repo_root
    from agent_mesh.topology import ensure_coordination_worktree, inspect_coordination_worktree

    try:
        repo_root = resolve_repo_root(Path.cwd())
    except FileNotFoundError:
        emit(
            "ERROR: `mesh init` must be run inside a git repository. "
            "Clone a repo first, or run `git init` before initializing Mesh."
        )
        return 1
    project_name = args.project_name or repo_root.name
    project_key = args.project_key or derive_project_key(project_name)
    adapters = parse_csv(args.adapters)
    existing_project = repo_root / ".agentic/project.json"

    if args.worktree_policy != "off" and git_head_available(repo_root):
        identity_required = not existing_project.exists()
        if existing_project.exists():
            try:
                status = inspect_coordination_worktree(repo_root, load_project_config(repo_root))
                identity_required = status.state == "missing"
            except Exception:
                identity_required = True
        if identity_required and not git_identity_configured(repo_root):
            emit("ERROR: git identity is not configured for this repository.")
            emit('Run: git config user.name "Your Name"')
            emit('Run: git config user.email "you@example.com"')
            return 1

    # Stash existing lanes before init_repo rewrites project.json
    existing_lanes = []
    if existing_project.exists():
        try:
            existing_lanes = list(load_project_config(repo_root).coordination.lanes)
        except Exception as err:
            emit("WARN: could not read existing lanes from project.json: {0}".format(err))

    # Set up coordination worktree first so scaffold can write .agentic/ there
    coordination_root = None
    coordination = None
    if args.worktree_policy != "off" and git_head_available(repo_root):
        try:
            # Bootstrap: write a minimal project.json to repo_root so
            # load_project_config works, then move to coordination worktree.
            _bootstrap_project_json(
                repo_root, project_name, project_key, args.provider,
                adapters, args.dashboard, args.worktree_policy, args.worktree_root,
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
    emit("Adapter wrappers can be added later with: mesh adapter install <adapter>")
    if (
        coordination_root is not None
        and coordination_root != repo_root
        and coordination is not None
        and (coordination.action != "noop" or coordination.state == "pending_scaffold")
    ):
        _commit_coordination_scaffold(coordination_root)
    # Restore pre-existing lanes and add new ones in a single write cycle.
    if existing_lanes or args.lanes > 0:
        _provision_lanes(repo_root, args.lanes, args.worktree_policy, existing_lanes)
    return 0


def _provision_lanes(repo_root: Path, target_count: int, worktree_policy: str, pre_existing: list | None = None) -> None:
    from agent_mesh.config import LaneEntry, load_project_config, save_project_config
    from agent_mesh.topology import (
        get_user_slug, next_lane_name,
        provision_lane, resolve_lane_worktree_path,
    )

    config = load_project_config(repo_root)
    # Restore lanes stashed before init_repo rewrote project.json
    if pre_existing is not None:
        config.coordination.lanes = list(pre_existing)

    to_add = target_count - len(config.coordination.lanes)
    if to_add <= 0:
        if target_count > 0:
            emit("Lanes: {0} already provisioned, nothing to add.".format(len(config.coordination.lanes)))
        save_project_config(repo_root, config)
        return

    user_slug = get_user_slug(repo_root)
    for _ in range(to_add):
        existing_names = {lane.name for lane in config.coordination.lanes}
        workspace_id = next_lane_name(existing_names, user_slug)
        if worktree_policy != "off" and git_head_available(repo_root):
            try:
                path = provision_lane(repo_root, config, workspace_id)
            except RuntimeError as error:
                emit("WARN: lane {0} could not be provisioned: {1}".format(workspace_id, error))
                continue  # skip registration — don't pollute the lane registry with failed lanes
        else:
            path = resolve_lane_worktree_path(repo_root, workspace_id, config.coordination.worktree_root)
        config.coordination.lanes.append(LaneEntry(name=workspace_id, workspace_id=workspace_id))
        emit("Lane: {0} @ {1}".format(workspace_id, path))
    save_project_config(repo_root, config)


def _bootstrap_project_json(
    repo_root: Path,
    project_name: str,
    project_key: str,
    provider: str,
    adapters: list,
    dashboard: bool,
    worktree_policy: str,
    worktree_root: str | None,
    claim_stale_after_minutes: int,
) -> None:
    """Write project.json to repo_root so topology helpers can load config before init_repo runs.

    Uses the actual adapter list so the bootstrap and the final config are identical.
    init_repo overwrites this file (force=True for project.json) with the full config.
    """
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
        "adapters": adapters,
        "runner": {"default": "local_manual"},
        "dashboard": {"enabled": dashboard, "output_dir": "dist/mesh-dashboard"},
    })


def _commit_coordination_scaffold(coordination_root: Path) -> bool:
    """Commit the initial .agentic/ state scaffold to the coordination branch.

    Returns True when the scaffold commit succeeds. Emits a warning and returns
    False when the scaffold is left pending or the commit fails.
    """
    import subprocess as _sp
    add = _sp.run(["git", "add", ".agentic/"], cwd=coordination_root, check=False, capture_output=True)
    if add.returncode != 0:
        emit("WARN: could not stage coordination scaffold for commit: {0}".format(
            add.stderr.decode(errors="replace").strip() or add.stdout.decode(errors="replace").strip()
        ))
        return False
    commit = _sp.run(
        ["git", "commit", "-m", "Initialize .agentic/ coordination scaffold"],
        cwd=coordination_root,
        check=False,
        capture_output=True,
    )
    if commit.returncode != 0:
        detail = commit.stderr.decode(errors="replace").strip() or commit.stdout.decode(errors="replace").strip()
        if "Author identity unknown" in detail:
            emit(
                "WARN: git identity is not configured, so the coordination scaffold is pending in {0}. "
                "Set `git config user.name` and `git config user.email`, then run `mesh sync` to finalize it.".format(
                    coordination_root
                )
            )
        else:
            emit("WARN: could not commit coordination scaffold: {0}".format(detail))
        return False
    return True


def _coordination_head_exists(coordination_root: Path) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=coordination_root,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _finalize_pending_coordination_scaffold(coordination_root: Path) -> bool:
    if not coordination_root.exists():
        return False
    if _coordination_head_exists(coordination_root):
        return False
    if not (coordination_root / ".agentic").exists():
        return False
    if _commit_coordination_scaffold(coordination_root):
        emit("Committed pending coordination scaffold in {0}".format(coordination_root))
        return True
    return False


def handle_doctor(_: argparse.Namespace) -> int:
    from agent_mesh.config import load_project_config
    from agent_mesh.state.storage import resolve_coordination_root, resolve_repo_root
    from agent_mesh.state.validate import validate_state_tree
    from agent_mesh.topology import lane_base_branch_diverged

    repo_root = resolve_repo_root(Path.cwd())
    coordination_root = resolve_coordination_root(repo_root)
    errors = validate_state_tree(repo_root, coordination_root)

    config = load_project_config(repo_root)
    for lane in config.coordination.lanes:
        if lane_base_branch_diverged(repo_root, lane, config.default_branch):
            errors.append(
                "lane '{0}': wt/{1} has diverged from origin/{2}; run mesh sync to reset".format(
                    lane.name, lane.workspace_id, config.default_branch
                )
            )

    if errors:
        for error in errors:
            emit("ERROR: {0}".format(error))
        for hint in adapter_install_hints_from_errors(errors):
            emit("TIP: {0}".format(hint))
        return 1
    emit("OK: Agent Mesh state is valid.")
    return 0


def handle_lane_list(_: argparse.Namespace) -> int:
    from agent_mesh.config import load_project_config
    from agent_mesh.state.storage import resolve_repo_root
    from agent_mesh.topology import inspect_lane_status

    repo_root = resolve_repo_root(Path.cwd())
    config = load_project_config(repo_root)
    lanes = config.coordination.lanes
    if not lanes:
        emit("No lanes provisioned. Run: mesh init --lanes N")
        return 0
    emit("workspace_id\tstatus\tbranch\tworktree_path")
    for lane in lanes:
        status = inspect_lane_status(repo_root, lane, config.coordination.worktree_root)
        emit("{0}\t{1}\t{2}\t{3}".format(
            status.workspace_id,
            status.status,
            status.current_branch or status.base_branch,
            status.worktree_path,
        ))
    return 0


def handle_lane_add(args: argparse.Namespace) -> int:
    from agent_mesh.config import LaneEntry, load_project_config, save_project_config
    from agent_mesh.state.storage import resolve_repo_root
    from agent_mesh.topology import (
        get_user_slug, lane_name_conflicts, next_lane_name,
        provision_lane, resolve_lane_worktree_path,
    )

    repo_root = resolve_repo_root(Path.cwd())
    config = load_project_config(repo_root)

    if args.name:
        name = args.name
        conflict = lane_name_conflicts(repo_root, config, name)
        if conflict:
            emit("ERROR: {0}".format(conflict))
            return 1
    else:
        user_slug = get_user_slug(repo_root)
        existing_names = {lane.name for lane in config.coordination.lanes}
        name = next_lane_name(existing_names, user_slug)

    if config.coordination.worktree_policy != "off" and git_head_available(repo_root):
        try:
            path = provision_lane(repo_root, config, name)
        except RuntimeError as error:
            emit("ERROR: {0}".format(error))
            return 1
    else:
        path = resolve_lane_worktree_path(repo_root, name, config.coordination.worktree_root)

    config.coordination.lanes.append(LaneEntry(name=name, workspace_id=name))
    save_project_config(repo_root, config)
    emit("Lane: {0} @ {1}".format(name, path))
    return 0


def handle_status(args: argparse.Namespace) -> int:
    from agent_mesh.config import load_project_config
    from agent_mesh.state.storage import list_claims, list_effective_work_items, list_reviews, resolve_coordination_root, resolve_repo_root
    from agent_mesh.topology import inspect_coordination_worktree

    repo_root = resolve_repo_root(Path.cwd())
    coordination_root = resolve_coordination_root(repo_root)
    config = load_project_config(repo_root)
    work_items = list_effective_work_items(repo_root, coordination_root)
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
    from agent_mesh.config import load_project_config, save_project_config
    from agent_mesh.scaffold import install_adapters
    from agent_mesh.state.storage import resolve_repo_root

    repo_root = resolve_repo_root(Path.cwd())
    adapters = parse_csv(args.adapters)
    result = install_adapters(repo_root, adapters, force=args.force)
    config = load_project_config(repo_root)
    for adapter in adapters:
        if adapter not in config.adapters:
            config.adapters.append(adapter)
    save_project_config(repo_root, config)
    emit("Installed adapter artifacts: {0}".format(len(result.created)))
    emit("Skipped adapter artifacts: {0}".format(len(result.skipped)))
    return 0


def maybe_emit_runtime_adapter_tip(args: argparse.Namespace) -> None:
    if getattr(args, "command", None) in {None, "version", "init"}:
        return
    if getattr(args, "command", None) == "adapter" and getattr(args, "adapter_command", None) == "install":
        return

    try:
        from agent_mesh.config import load_project_config
        from agent_mesh.state.storage import resolve_repo_root

        repo_root = resolve_repo_root(Path.cwd())
        if not (repo_root / PROJECT_FILE).exists():
            return
        config = load_project_config(repo_root)
    except Exception:
        return

    adapter = detect_runtime_adapter(args)
    if not adapter or adapter == "generic":
        return
    if adapter_artifacts_installed(repo_root, adapter):
        return

    if adapter in config.adapters:
        emit(
            "TIP: configured {0} adapter files are missing locally. Run: mesh adapter install {0}".format(adapter)
        )
        return
    emit(
        "TIP: detected {0} runtime. To enable Mesh wrappers for this repo, run: mesh adapter install {0}".format(
            adapter
        )
    )


def detect_runtime_adapter(args: argparse.Namespace) -> Optional[str]:
    for value in [
        getattr(args, "agent", None),
        os.environ.get("MESH_AGENT_RUNTIME"),
        os.environ.get("AGENT_MESH_RUNTIME"),
    ]:
        adapter = normalize_runtime_adapter(value)
        if adapter:
            return adapter
    return None


def normalize_runtime_adapter(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return RUNTIME_ADAPTER_ALIASES.get(str(value).strip().lower())


def adapter_artifacts_installed(repo_root: Path, adapter: str) -> bool:
    if adapter == "claude":
        return (repo_root / ".claude/skills/claim/SKILL.md").exists() and (repo_root / "CLAUDE.md").exists()
    if adapter == "codex":
        return (repo_root / ".agents/skills/claim/SKILL.md").exists()
    if adapter == "pi":
        return (repo_root / ".agents/skills/claim/SKILL.md").exists() and (repo_root / ".pi/prompts/claim.md").exists()
    if adapter == "cursor":
        return (repo_root / ".cursor/rules/agent-mesh.mdc").exists()
    if adapter == "opencode":
        return (repo_root / "OPENCODE.md").exists() and skill_install_status(repo_root, "opencode", "claim") == "installed"
    if adapter == "windsurf":
        return (repo_root / ".windsurfrules").exists()
    return True


def adapter_install_hints_from_errors(errors: Iterable[str]) -> List[str]:
    hints: List[str] = []
    seen: set[str] = set()
    for error in errors:
        for adapter in SUPPORTED_ADAPTERS:
            if adapter == "generic":
                continue
            marker = "for {0}:".format(adapter)
            if marker in error and adapter not in seen:
                hints.append("Run: mesh adapter install {0}".format(adapter))
                seen.add(adapter)
    return hints


def handle_task_add(args: argparse.Namespace) -> int:
    from agent_mesh.config import load_project_config
    from agent_mesh.state.models import ProviderRef, WorkItem
    from agent_mesh.state.storage import create_work_item_with_unique_id, resolve_repo_root

    repo_root = resolve_repo_root(Path.cwd())
    config = load_project_config(repo_root)
    description = args.description or args.title
    acceptance = args.acceptance or ["Define task-specific acceptance criteria."]

    def build_work_item(work_id: str) -> WorkItem:
        now = utc_now()
        return WorkItem(
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

    work_item, _ = create_work_item_with_unique_id(repo_root, config.project_key, build_work_item)
    emit("Created task {0}".format(work_item.id))
    return 0


def handle_task_list(_: argparse.Namespace) -> int:
    from agent_mesh.state.storage import list_effective_work_items, resolve_coordination_root, resolve_repo_root

    repo_root = resolve_repo_root(Path.cwd())
    coordination_root = resolve_coordination_root(repo_root)
    for work_item in list_effective_work_items(repo_root, coordination_root):
        emit("{0}\t{1}\t{2}".format(work_item.id, work_item.status, work_item.title))
    return 0


def handle_task_show(args: argparse.Namespace) -> int:
    from agent_mesh.state.models import WorkItem
    from agent_mesh.state.storage import load_model, resolve_coordination_root, resolve_repo_root

    repo_root = resolve_repo_root(Path.cwd())
    coordination_root = resolve_coordination_root(repo_root)
    work_item = load_model(resolve_current_work_item_path(repo_root, coordination_root, args.work_id), WorkItem)
    emit(work_item.model_dump_json(indent=2))
    return 0


def handle_bootstrap_tasks(args: argparse.Namespace) -> int:
    from agent_mesh.config import load_project_config
    from agent_mesh.state.models import ProviderRef, WorkItem
    from agent_mesh.state.storage import resolve_coordination_root, resolve_repo_root, save_model_json

    repo_root = resolve_repo_root(Path.cwd())
    coordination_root = resolve_coordination_root(repo_root)
    config = load_project_config(repo_root)

    try:
        payload = _load_bootstrap_task_payload(args.input)
    except ValueError as error:
        emit("ERROR: {0}".format(error))
        return 1

    task_inputs = _extract_bootstrap_task_inputs(payload)
    if not task_inputs:
        emit("ERROR: bootstrap payload did not contain any tasks.")
        return 1

    work_dir = repo_root / ".agentic/work"
    existing_ids = {path.stem for path in work_dir.glob("*.json")}
    assigned_ids = set(existing_ids)
    created = 0
    updated = 0

    for task_input in task_inputs:
        if not isinstance(task_input, dict):
            emit("ERROR: each bootstrap task must be a JSON object.")
            return 1
        try:
            work_item, work_id, existed = _normalize_bootstrap_task(
                task_input=task_input,
                config=config,
                repo_root=repo_root,
                coordination_root=coordination_root,
                assigned_ids=assigned_ids,
            )
        except ValueError as error:
            emit("ERROR: {0}".format(error))
            return 1
        assigned_ids.add(work_id)
        save_model_json(work_dir / "{0}.json".format(work_id), work_item)
        if existed:
            updated += 1
        else:
            created += 1

    emit(
        "Bootstrapped {0} tasks ({1} created, {2} updated).".format(
            len(task_inputs), created, updated
        )
    )
    if config.dashboard.enabled:
        build_dashboard(repo_root, coordination_root)
    return 0


def handle_claim(args: argparse.Namespace) -> int:
    from agent_mesh.config import load_project_config
    from agent_mesh.state.models import Claim, ClaimEvent, WorkItem
    from agent_mesh.state.storage import load_model, resolve_coordination_root, resolve_repo_root

    repo_root = resolve_repo_root(Path.cwd())
    coordination_root = resolve_coordination_root(repo_root)
    config = load_project_config(repo_root)
    work_path = resolve_current_work_item_path(repo_root, coordination_root, args.work_id)
    if not work_path.exists():
        emit("ERROR: work item {0} not found".format(args.work_id))
        return 1
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
    try:
        selected_lane = select_claim_lane(repo_root, config, args.lane, args.workspace_id)
        if selected_lane is not None:
            workspace_id = selected_lane.workspace_id
            worktree = prepare_lane_claim_workspace(
                repo_root,
                config,
                branch,
                selected_lane,
                args.worktree,
            )
        else:
            workspace_id = args.workspace_id or derive_workspace_id(args.agent, args.machine)
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
    work_item.status = "in_progress"
    work_item.updated_at = now
    work_path = materialize_live_work_item(repo_root, coordination_root, args.work_id)
    try:
        persist_new_claim_state(
            repo_root,
            coordination_root,
            config,
            work_item,
            work_path,
            claim,
            existing_claim_path,
            no_push=args.no_push,
        )
    except RuntimeError as error:
        emit("ERROR: {0}".format(error))
        return 1
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
    work_path = resolve_current_work_item_path(repo_root, coordination_root, args.work_id)
    work_item = load_model(work_path, WorkItem)
    claim = load_model(coordination_root / ".agentic/claims" / "{0}.json".format(args.work_id), Claim)

    if claim.worktree:
        worktree_path = Path(claim.worktree)
        if not worktree_path.exists():
            emit("WARNING: claimed worktree no longer exists at {0} — proceeding from current directory".format(claim.worktree))
        else:
            current_path = Path.cwd().resolve()
            target_worktree = worktree_path.resolve()
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
    save_model_json(materialize_live_work_item(repo_root, coordination_root, args.work_id), work_item)

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
    work_item = load_model(resolve_current_work_item_path(repo_root, coordination_root, args.work_id), WorkItem)
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
    work_item = load_model(resolve_current_work_item_path(repo_root, coordination_root, review_packet.work_id), WorkItem)

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


def build_dashboard(
    repo_root: Path,
    coordination_root: Optional[Path] = None,
    *,
    public: bool = False,
    output_dir: Optional[str] = None,
) -> None:
    from agent_mesh.config import load_project_config
    from agent_mesh.dashboard import build_dashboard_payload, render_dashboard_html
    from agent_mesh.state.storage import list_claims, list_effective_work_items, list_reviews, resolve_coordination_root

    if coordination_root is None:
        coordination_root = resolve_coordination_root(repo_root)
    config = load_project_config(repo_root)
    target_dir = output_dir or ("dist/public-dashboard" if public else config.dashboard.output_dir)
    output_path = repo_root / target_dir / "index.html"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    work_items = list_effective_work_items(repo_root, coordination_root)
    claims = list_claims(coordination_root)
    reviews = list_reviews(coordination_root)
    payload = build_dashboard_payload(config, work_items, claims, reviews, public=public)
    output_path.write_text(render_dashboard_html(payload), encoding="utf-8")
    if public:
        data_path = output_path.parent / "dashboard-data.json"
        data_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        emit("Built public dashboard at {0}".format(output_path))
        emit("Wrote public data snapshot at {0}".format(data_path))
        return
    emit("Built dashboard at {0}".format(output_path))


def handle_dashboard_build(args: argparse.Namespace) -> int:
    from agent_mesh.state.storage import resolve_coordination_root, resolve_repo_root

    repo_root = resolve_repo_root(Path.cwd())
    build_dashboard(
        repo_root,
        resolve_coordination_root(repo_root),
        public=bool(args.public),
        output_dir=args.output_dir,
    )
    return 0


def handle_merge(args: argparse.Namespace) -> int:
    import shutil

    from agent_mesh.config import load_project_config
    from agent_mesh.state.models import Claim, ReviewPacket, WorkItem
    from agent_mesh.state.storage import load_model, resolve_coordination_root, resolve_repo_root, save_model_json
    from agent_mesh.topology import resolve_coordination_worktree_path

    repo_root = resolve_repo_root(Path.cwd())
    coordination_root = resolve_coordination_root(repo_root)
    config = load_project_config(repo_root)
    warnings_fired = False
    lane = None

    work_path = resolve_current_work_item_path(repo_root, coordination_root, args.work_id)
    if not work_path.exists():
        emit("ERROR: work item {0} not found".format(args.work_id))
        return 1
    work_item = load_model(work_path, WorkItem)

    claim_path = coordination_root / ".agentic/claims" / "{0}.json".format(args.work_id)
    if not claim_path.exists():
        emit("ERROR: no active claim for {0}".format(args.work_id))
        return 1
    claim = load_model(claim_path, Claim)
    if claim.workspace_id:
        for configured_lane in config.coordination.lanes:
            if configured_lane.workspace_id == claim.workspace_id:
                lane = configured_lane
                break

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

    # Return lane worktrees to idle; remove legacy task worktrees.
    if config.coordination.worktree_policy != "off" and claim.worktree:
        worktree_path = Path(claim.worktree).resolve()
        if worktree_path == coordination_worktree.resolve():
            emit("ERROR: claim worktree matches the coordination worktree — refusing to modify it")
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
                clean_result = run_git(worktree_path, ["clean", "-fd"])
                if clean_result.returncode != 0:
                    emit("WARNING: could not clean untracked files in worktree {0}: {1}".format(
                        worktree_path,
                        (clean_result.stderr or clean_result.stdout).strip(),
                    ))
                    warnings_fired = True
            if lane is not None:
                base_branch = "wt/{0}".format(lane.workspace_id)
                current_branch = run_git(worktree_path, ["branch", "--show-current"])
                ensure_git_ok(current_branch, "failed to inspect lane worktree branch during merge")
                active_branch = current_branch.stdout.strip()
                if active_branch != base_branch:
                    switch_result = run_git(worktree_path, ["switch", base_branch])
                    if switch_result.returncode == 0:
                        emit("Returned lane to base branch: {0}".format(base_branch))
                    else:
                        emit("WARNING: could not switch lane worktree {0} to {1}: {2}".format(
                            worktree_path,
                            base_branch,
                            (switch_result.stderr or switch_result.stdout).strip(),
                        ))
                        warnings_fired = True
                reset_target = "origin/{0}".format(config.default_branch)
                if not ref_exists(repo_root, "refs/remotes/{0}".format(reset_target)):
                    reset_target = config.default_branch
                reset_result = run_git(worktree_path, ["reset", "--hard", reset_target])
                if reset_result.returncode == 0:
                    emit("Reset lane worktree to {0}: {1}".format(reset_target, worktree_path))
                else:
                    emit("WARNING: could not reset lane worktree {0} to {1}: {2}".format(
                        worktree_path,
                        reset_target,
                        (reset_result.stderr or reset_result.stdout).strip(),
                    ))
                    warnings_fired = True
            else:
                result = run_git(repo_root, ["worktree", "remove", "--force", str(worktree_path)])
                if result.returncode == 0:
                    emit("Removed worktree: {0}".format(worktree_path))
                else:
                    emit("WARNING: could not remove worktree {0}: {1}".format(
                        worktree_path, (result.stderr or result.stdout).strip()
                    ))
                    warnings_fired = True
        else:
            if lane is not None:
                emit("WARNING: lane worktree missing during merge: {0}".format(claim.worktree))
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
    review_packet_path = resolve_review_packet_path(coordination_root, args.work_id)
    review = None
    if review_packet_path is not None:
        review = load_model(review_packet_path, ReviewPacket)
        review.status = "merged"
        emit("Marked review packet merged: {0}".format(review.id))
    else:
        emit("WARNING: no review packet found for {0} — dashboard may show stale review state".format(args.work_id))
        warnings_fired = True

    # Mark work item done first — safer order: if archive fails, work item is
    # already done and the live claim can be retried
    now = utc_now()
    work_item.status = "done"
    work_item.updated_at = now
    work_path = materialize_live_work_item(repo_root, coordination_root, args.work_id)
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

    repaired_reviews = reconcile_completed_review_packets(repo_root, coordination_root, args.work_id)
    if review_packet_path is None and repaired_reviews:
        for review_id in repaired_reviews:
            emit("Reconciled review packet to merged: {0}".format(review_id))

    review_packet_path = resolve_review_packet_path(coordination_root, args.work_id)
    if review_packet_path is not None:
        review = load_model(review_packet_path, ReviewPacket)
        review.status = "merged"

    persist_completed_work_state(
        coordination_root,
        config,
        work_id=args.work_id,
        work_item=work_item,
        work_path=work_path,
        claim=claim,
        claim_path=claim_path,
        archive_path=archive_path,
        review_packet_path=review_packet_path,
        review=review,
        no_push=args.no_push,
    )

    active_claim_exists = (coordination_root / ".agentic/claims" / "{0}.json".format(args.work_id)).exists()
    if active_claim_exists:
        emit("WARNING: active claim still present for {0} after merge".format(args.work_id))
        warnings_fired = True

    review_packet_path = resolve_review_packet_path(coordination_root, args.work_id)
    if review_packet_path is not None:
        review = load_model(review_packet_path, ReviewPacket)
        if review.status != "merged":
            emit("WARNING: review packet still pending after merge: {0}".format(review.id))
            warnings_fired = True

    if lane is not None and claim.worktree:
        lane_path = Path(claim.worktree).resolve()
        if lane_path.exists() and (lane_path / ".git").exists():
            current_branch = run_git(lane_path, ["branch", "--show-current"])
            if current_branch.returncode != 0 or current_branch.stdout.strip() != "wt/{0}".format(lane.workspace_id):
                emit("WARNING: lane {0} did not return to idle base branch".format(lane.workspace_id))
                warnings_fired = True

    if config.dashboard.enabled and not warnings_fired:
        build_dashboard(repo_root, coordination_root)
    elif config.dashboard.enabled:
        emit("Skipped dashboard rebuild due to warnings — run mesh sync to rebuild")

    return 2 if warnings_fired else 0


def handle_sync(_: argparse.Namespace) -> int:
    from agent_mesh.config import load_project_config
    from agent_mesh.state.storage import resolve_coordination_root, resolve_repo_root
    from agent_mesh.topology import ensure_coordination_worktree, resolve_coordination_worktree_path

    repo_root = resolve_repo_root(Path.cwd())
    coordination_root = resolve_coordination_root(repo_root)
    config = load_project_config(repo_root)
    if config.coordination.worktree_policy != "off" and git_head_available(repo_root):
        expected_coordination_root = resolve_coordination_worktree_path(repo_root, config)
        if _finalize_pending_coordination_scaffold(expected_coordination_root):
            coordination_root = expected_coordination_root
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

    repaired_reviews = reconcile_completed_review_packets(repo_root, coordination_root)
    for review_id in repaired_reviews:
        emit("Reconciled review packet to merged: {0}".format(review_id))

    if config.dashboard.enabled:
        build_dashboard(repo_root, coordination_root)
    return handle_doctor(argparse.Namespace())


def derive_project_key(project_name: str) -> str:
    tokens = [token for token in re.split(r"[^A-Za-z0-9]+", project_name) if token]
    weak_tokens = {"agent", "app", "service", "tool", "repo", "project"}

    preferred_tokens = [
        token for token in tokens
        if "".join(char for char in token if char.isalnum()) and token.lower() not in weak_tokens
    ]
    candidates = preferred_tokens or tokens
    candidates = sorted(
        candidates,
        key=lambda token: (-len("".join(char for char in token if char.isalnum())), tokens.index(token)),
    )

    for token in candidates:
        letters = [char for char in token.upper() if char.isalnum()]
        if letters:
            return "".join(letters[:4])

    letters = [char for char in project_name.upper() if char.isalnum()]
    return "".join(letters[:4]) or "APP"


def parse_csv(raw: str) -> List[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def _load_bootstrap_task_payload(input_path: Optional[str]) -> object:
    if input_path:
        raw = Path(input_path).read_text(encoding="utf-8")
    else:
        if sys.stdin.isatty():
            raise ValueError(
                "bootstrap-tasks expects JSON on stdin or via --input PATH."
            )
        raw = sys.stdin.read()
    if not raw.strip():
        raise ValueError("bootstrap-tasks received empty input.")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError("bootstrap-tasks input is not valid JSON: {0}".format(error)) from error


def _extract_bootstrap_task_inputs(payload: object) -> list[dict]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        tasks = payload.get("tasks")
        if isinstance(tasks, list):
            return tasks
    raise ValueError("bootstrap-tasks input must be a JSON array or an object with a `tasks` array.")


def _normalize_bootstrap_task(
    *,
    task_input: dict,
    config,
    repo_root: Path,
    coordination_root: Path,
    assigned_ids: set[str],
):
    from agent_mesh.state.models import ProviderRef, WorkItem
    from agent_mesh.state.storage import next_work_item_id

    title = str(task_input.get("title", "")).strip()
    if not title:
        raise ValueError("bootstrap task is missing required field `title`.")

    requested_id = str(task_input.get("id", "")).strip() or None
    if requested_id:
        work_id = requested_id
    else:
        work_id = next_work_item_id(repo_root, config.project_key)
        while work_id in assigned_ids:
            suffix = int(work_id.split("-")[-1]) + 1
            work_id = "{0}-{1}".format(config.project_key, suffix)

    now = utc_now()
    target_path = repo_root / ".agentic/work" / "{0}.json".format(work_id)
    existed = target_path.exists()
    created_at = now
    if existed:
        try:
            existing_item = load_work_item(target_path)
            created_at = existing_item.created_at
        except Exception:
            created_at = now

    planning_input = task_input.get("planning") if isinstance(task_input.get("planning"), dict) else {}
    provider = str(planning_input.get("provider") or config.planning.provider)
    planning = ProviderRef(
        provider=provider,
        url=planning_input.get("url"),
        external_id=planning_input.get("external_id"),
    )
    acceptance = task_input.get("acceptance_criteria") or task_input.get("acceptance") or []
    if not isinstance(acceptance, list):
        raise ValueError("bootstrap task `{0}` has non-list acceptance criteria.".format(title))
    dependencies = task_input.get("dependencies") or []
    if not isinstance(dependencies, list):
        raise ValueError("bootstrap task `{0}` has non-list dependencies.".format(title))

    work_item = WorkItem(
        id=work_id,
        title=title,
        description=str(task_input.get("description") or title),
        kind=str(task_input.get("kind") or "feature"),
        status=str(task_input.get("status") or "needs_triage"),
        execution=str(task_input.get("execution") or "afk_safe"),
        module=task_input.get("module"),
        planning=planning,
        prd=task_input.get("prd"),
        acceptance_criteria=[str(item) for item in acceptance],
        dependencies=[str(item) for item in dependencies],
        risk=str(task_input.get("risk") or "medium"),
        created_at=created_at,
        updated_at=now,
    )
    return work_item, work_id, existed


def git_head_available(repo_root: Path) -> bool:
    result = run_git(repo_root, ["rev-parse", "--verify", "HEAD"])
    return result.returncode == 0


def git_identity_configured(repo_root: Path) -> bool:
    for key in ["user.name", "user.email"]:
        result = run_git(repo_root, ["config", key])
        if result.returncode != 0 or not result.stdout.strip():
            return False
    return True


def resolve_review_packet_path(coordination_root: Path, target: str) -> Optional[Path]:
    candidates = [
        coordination_root / ".agentic/reviews" / "{0}.json".format(target),
        coordination_root / ".agentic/reviews" / "PR-{0}.json".format(target),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    from agent_mesh.state.models import ReviewPacket
    from agent_mesh.state.storage import iter_json_files, load_model

    reviews_dir = coordination_root / ".agentic/reviews"
    aliases = {target, "PR-{0}".format(target)}
    for candidate in iter_json_files(reviews_dir):
        try:
            review = load_model(candidate, ReviewPacket)
        except Exception:
            continue
        if review.id in aliases or review.work_id == target:
            return candidate
    return None


def load_work_item(path: Path):
    from agent_mesh.state.models import WorkItem
    from agent_mesh.state.storage import load_model

    return load_model(path, WorkItem)


def resolve_current_work_item_path(repo_root: Path, coordination_root: Path, work_id: str) -> Path:
    from agent_mesh.state.storage import resolve_live_work_item_path, resolve_shared_work_item_path

    live_path = resolve_live_work_item_path(coordination_root, work_id)
    if live_path.exists():
        return live_path
    return resolve_shared_work_item_path(repo_root, work_id)


def materialize_live_work_item(repo_root: Path, coordination_root: Path, work_id: str) -> Path:
    from agent_mesh.state.storage import resolve_live_work_item_path, resolve_shared_work_item_path, save_model_json

    live_path = resolve_live_work_item_path(coordination_root, work_id)
    if live_path.exists() or coordination_root == repo_root:
        return live_path

    shared_path = resolve_shared_work_item_path(repo_root, work_id)
    if not shared_path.exists():
        raise FileNotFoundError("work item {0} not found".format(work_id))
    work_item = load_work_item(shared_path)
    save_model_json(live_path, work_item)
    return live_path


def reconcile_completed_review_packets(repo_root: Path, coordination_root: Path, work_id: Optional[str] = None) -> list[str]:
    from agent_mesh.state.models import ReviewPacket, WorkItem
    from agent_mesh.state.storage import iter_json_files, list_effective_work_items, load_model, save_model_json

    reviews_dir = coordination_root / ".agentic/reviews"
    if not reviews_dir.exists():
        return []

    work_items = {item.id: item for item in list_effective_work_items(repo_root, coordination_root)}

    repaired: list[str] = []
    for path in iter_json_files(reviews_dir):
        try:
            review = load_model(path, ReviewPacket)
        except Exception:
            continue
        if work_id is not None and review.work_id != work_id:
            continue
        if review.status == "merged":
            continue

        work_item = work_items.get(review.work_id)
        if work_item is None or work_item.status != "done":
            continue

        active_claim_path = coordination_root / review.context.claim
        archived_claim_path = coordination_root / ".agentic/claims/archive" / "{0}.json".format(review.work_id)
        if active_claim_path.exists() and not archived_claim_path.exists():
            continue

        review.status = "merged"
        save_model_json(path, review)
        repaired.append(review.id)

    return repaired


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
            save_model_json(materialize_live_work_item(repo_root, coordination_root, work_item.id), work_item)
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
            save_model_json(materialize_live_work_item(repo_root, coordination_root, work_item.id), work_item)
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


def ref_exists(repo_root: Path, ref: str) -> bool:
    result = run_git(repo_root, ["show-ref", "--verify", "--quiet", ref])
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


def _assert_lane_available(repo_root: Path, config, lane) -> None:
    from agent_mesh.topology import inspect_lane_status

    status = inspect_lane_status(repo_root, lane, config.coordination.worktree_root)
    if status.status == "active":
        raise RuntimeError(
            "lane '{0}' is active on branch {1}; choose an idle lane or omit --lane".format(
                lane.name, status.current_branch or "<unknown>"
            )
        )


def select_claim_lane(repo_root: Path, config, requested_lane: Optional[str], requested_workspace_id: Optional[str]):
    from agent_mesh.topology import inspect_lane_status

    lanes = config.coordination.lanes
    if not lanes:
        return None

    lane_map = {}
    for lane in lanes:
        lane_map[lane.name] = lane
        lane_map[lane.workspace_id] = lane

    if requested_lane:
        lane = lane_map.get(requested_lane)
        if lane is None:
            raise RuntimeError("lane '{0}' is not registered".format(requested_lane))
        _assert_lane_available(repo_root, config, lane)
        return lane

    if requested_workspace_id:
        lane = lane_map.get(requested_workspace_id)
        if lane is not None:
            _assert_lane_available(repo_root, config, lane)
        return lane

    for lane in lanes:
        status = inspect_lane_status(repo_root, lane, config.coordination.worktree_root)
        if status.status == "idle":
            return lane
    for lane in lanes:
        status = inspect_lane_status(repo_root, lane, config.coordination.worktree_root)
        if status.status == "missing":
            return lane
    raise RuntimeError("no idle lanes available; run mesh lane list or specify --lane")


def prepare_lane_claim_workspace(
    repo_root: Path,
    config,
    branch: str,
    lane,
    requested_worktree: Optional[str],
) -> str:
    from agent_mesh.topology import provision_lane, resolve_lane_entry_path

    lane_path = resolve_lane_entry_path(repo_root, lane, config.coordination.worktree_root).expanduser().resolve()
    if requested_worktree:
        requested_path = Path(requested_worktree).expanduser()
        requested_path = (repo_root / requested_path).resolve() if not requested_path.is_absolute() else requested_path.resolve()
        if requested_path != lane_path:
            raise RuntimeError(
                "lane '{0}' is bound to worktree {1}; requested {2}".format(
                    lane.name, lane_path, requested_path
                )
            )

    if config.coordination.worktree_policy == "off":
        return str(lane_path)

    if lane_path.exists() and not (lane_path / ".git").exists():
        raise RuntimeError("lane worktree path already exists and is not a git worktree: {0}".format(lane_path))

    if not lane_path.exists():
        lane_path = provision_lane(repo_root, config, lane.workspace_id).resolve()

    ensure_lane_worktree_ready(repo_root, lane_path, config.default_branch, lane.workspace_id, branch)
    return str(lane_path)


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


def ensure_lane_worktree_ready(
    repo_root: Path,
    worktree_path: Path,
    default_branch: str,
    workspace_id: str,
    branch: str,
) -> None:
    base_branch = "wt/{0}".format(workspace_id)
    current_branch = run_git(worktree_path, ["branch", "--show-current"])
    ensure_git_ok(current_branch, "failed to inspect lane worktree branch")
    active_branch = current_branch.stdout.strip()

    dirty = run_git(worktree_path, ["status", "--porcelain"])
    ensure_git_ok(dirty, "failed to inspect lane worktree status")
    if dirty.stdout.strip():
        raise RuntimeError(
            "lane worktree is dirty on branch {0}; clean it before claiming new work".format(
                active_branch or "<detached>"
            )
        )

    if active_branch and active_branch != base_branch:
        raise RuntimeError(
            "lane '{0}' is active on branch {1}; return it to {2} before claiming new work".format(
                workspace_id, active_branch, base_branch
            )
        )

    if active_branch != base_branch:
        switch_result = run_git(worktree_path, ["switch", base_branch])
        ensure_git_ok(switch_result, "failed to reset lane to its base branch")

    reset_target = "origin/{0}".format(default_branch)
    if not ref_exists(repo_root, "refs/remotes/{0}".format(reset_target)):
        reset_target = default_branch
    reset_result = run_git(worktree_path, ["reset", "--hard", reset_target])
    ensure_git_ok(reset_result, "failed to sync lane base branch")

    if branch_exists(repo_root, branch):
        switch_result = run_git(worktree_path, ["switch", branch])
        ensure_git_ok(switch_result, "failed to switch lane worktree to existing task branch")
        return

    switch_result = run_git(worktree_path, ["switch", "-c", branch, base_branch])
    ensure_git_ok(switch_result, "failed to create task branch from lane base branch")


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


def coordination_remote_exists(coordination_root: Path) -> bool:
    result = run_git(coordination_root, ["remote", "get-url", "origin"])
    return result.returncode == 0


def coordination_push_conflict(detail: str) -> bool:
    lowered = detail.lower()
    return "non-fast-forward" in lowered or "fetch first" in lowered or "rejected" in lowered


def commit_coordination_state(coordination_root: Path, paths: Sequence[Path], message: str) -> None:
    relative_paths = [str(path.relative_to(coordination_root)) for path in paths]
    ensure_git_ok(run_git(coordination_root, ["add", *relative_paths]), "failed to stage coordination state")
    pending = run_git(coordination_root, ["status", "--porcelain", "--", *relative_paths])
    ensure_git_ok(pending, "failed to inspect coordination state changes")
    if not pending.stdout.strip():
        return
    commit = run_git(coordination_root, ["commit", "-m", message])
    ensure_git_ok(commit, "failed to commit coordination state")


def push_coordination_state(coordination_root: Path, branch: str) -> subprocess.CompletedProcess[str]:
    return run_git(coordination_root, ["push", "origin", "HEAD:{0}".format(branch)])


def sync_coordination_state_from_remote(coordination_root: Path, branch: str) -> None:
    fetch = run_git(coordination_root, ["fetch", "origin", branch])
    ensure_git_ok(fetch, "failed to fetch latest coordination state")
    reset = run_git(coordination_root, ["reset", "--hard", "origin/{0}".format(branch)])
    ensure_git_ok(reset, "failed to reset coordination state after push conflict")


def completed_work_state_persisted(
    coordination_root: Path,
    work_id: str,
    *,
    review_packet_path: Optional[Path],
) -> bool:
    from agent_mesh.state.models import ReviewPacket, WorkItem
    from agent_mesh.state.storage import load_model

    work_path = coordination_root / ".agentic/work" / "{0}.json".format(work_id)
    archive_path = coordination_root / ".agentic/claims/archive" / "{0}.json".format(work_id)
    active_claim_path = coordination_root / ".agentic/claims" / "{0}.json".format(work_id)

    if not work_path.exists() or active_claim_path.exists() or not archive_path.exists():
        return False

    work_item = load_model(work_path, WorkItem)
    if work_item.status != "done":
        return False

    if review_packet_path is None or not review_packet_path.exists():
        return True

    review = load_model(review_packet_path, ReviewPacket)
    return review.status == "merged"


def persist_completed_work_state(
    coordination_root: Path,
    config,
    *,
    work_id: str,
    work_item,
    work_path: Path,
    claim,
    claim_path: Path,
    archive_path: Path,
    review_packet_path: Optional[Path],
    review,
    no_push: bool,
    max_attempts: int = 2,
) -> None:
    from agent_mesh.state.storage import save_model_json

    attempts = 0
    commit_paths = [work_path, claim_path, archive_path]
    if review_packet_path is not None:
        commit_paths.append(review_packet_path)

    review_suffix = ""
    if review is not None and getattr(review.pr, "number", None):
        review_suffix = " (PR #{0})".format(review.pr.number)

    while True:
        attempts += 1
        save_model_json(work_path, work_item)
        save_model_json(archive_path, claim)
        if claim_path.exists():
            claim_path.unlink()
        if review_packet_path is not None and review is not None:
            save_model_json(review_packet_path, review)

        if not git_head_available(coordination_root):
            return

        commit_coordination_state(
            coordination_root,
            commit_paths,
            "Close {0}; archive claim, mark merged{1}".format(work_id, review_suffix),
        )

        if no_push or not coordination_remote_exists(coordination_root):
            return

        push_result = push_coordination_state(coordination_root, config.coordination.branch)
        if push_result.returncode == 0:
            return

        detail = (push_result.stderr or push_result.stdout).strip() or "unknown git error"
        if attempts >= max_attempts or not coordination_push_conflict(detail):
            raise RuntimeError("failed to push completed work state: {0}".format(detail))

        sync_coordination_state_from_remote(coordination_root, config.coordination.branch)
        if completed_work_state_persisted(
            coordination_root,
            work_id,
            review_packet_path=review_packet_path,
        ):
            return


def persist_new_claim_state(
    repo_root: Path,
    coordination_root: Path,
    config,
    work_item,
    work_path: Path,
    claim,
    claim_path: Path,
    *,
    no_push: bool,
    max_attempts: int = 2,
) -> None:
    from agent_mesh.state.models import Claim, WorkItem
    from agent_mesh.state.storage import load_model, save_model_json

    attempts = 0
    while True:
        attempts += 1
        save_model_json(claim_path, claim)
        save_model_json(work_path, work_item)

        if not git_head_available(coordination_root):
            return

        commit_coordination_state(
            coordination_root,
            [claim_path, work_path],
            "Claim {0} via {1}".format(claim.work_id, claim.workspace_id or "workspace"),
        )

        if no_push or not coordination_remote_exists(coordination_root):
            return

        push_result = push_coordination_state(coordination_root, config.coordination.branch)
        if push_result.returncode == 0:
            return

        detail = (push_result.stderr or push_result.stdout).strip() or "unknown git error"
        if attempts >= max_attempts or not coordination_push_conflict(detail):
            raise RuntimeError("failed to push claim state: {0}".format(detail))

        sync_coordination_state_from_remote(coordination_root, config.coordination.branch)
        if claim_path.exists():
            live_claim = load_model(claim_path, Claim)
            raise RuntimeError(
                "claim lost push race for {0}; it is now owned by {1}".format(
                    claim.work_id, live_claim.claimed_by
                )
            )
        refreshed_work = load_model(work_path, WorkItem)
        if refreshed_work.status not in ["ready", "in_progress"]:
            raise RuntimeError(
                "claim lost push race for {0}; work item is now {1}".format(
                    claim.work_id, refreshed_work.status
                )
            )


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
    from agent_mesh.dashboard import build_dashboard_payload, render_dashboard_html as _render_dashboard_html

    return _render_dashboard_html(build_dashboard_payload(config, work_items, claims, reviews))


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
