"""CLI entrypoint for Agent Mesh."""

from __future__ import annotations

import argparse
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

from agent_mesh import __version__
from agent_mesh.skills.catalog import SKILLS
from agent_mesh.utils.slug import slugify

try:
    from rich.console import Console
except ModuleNotFoundError:  # pragma: no cover - exercised only in thin envs
    Console = None

console = Console() if Console is not None else None
SUPPORTED_ADAPTERS = ["generic", "claude", "codex", "cursor", "opencode", "pi", "windsurf"]


def emit(message: str) -> None:
    if console is not None:
        console.print(message)
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
    claim_parser.add_argument("--worktree")
    claim_parser.add_argument("--branch")
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
    from agent_mesh.scaffold import init_repo
    from agent_mesh.state.storage import resolve_repo_root

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
    )
    emit("Initialized Agent Mesh in {0}".format(repo_root))
    emit("Created {0} files.".format(len(result.created)))
    emit("Skipped {0} existing files.".format(len(result.skipped)))
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

    repo_root = resolve_repo_root(Path.cwd())
    config = load_project_config(repo_root)
    work_items = list_work_items(repo_root)
    claims = list_claims(repo_root)
    reviews = list_reviews(repo_root)

    emit("Project: {0} ({1})".format(config.project_name, config.project_key))
    emit("Tasks: {0}".format(len(work_items)))
    for line in summarize_work_items(work_items):
        emit(line)
    emit("Claims: {0}".format(len(claims)))
    for line in summarize_claims(claims):
        emit(line)
    emit("Reviews: {0}".format(len(reviews)))
    for line in summarize_reviews(reviews):
        emit(line)
    return 0


def handle_skill_list(_: argparse.Namespace) -> int:
    for skill in SKILLS:
        emit("{0}\t{1}".format(skill.name, skill.summary))
    return 0


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
    from agent_mesh.state.models import Claim, WorkItem
    from agent_mesh.state.storage import load_model, resolve_repo_root, save_model_json

    repo_root = resolve_repo_root(Path.cwd())
    work_path = repo_root / ".agentic/work" / "{0}.json".format(args.work_id)
    work_item = load_model(work_path, WorkItem)

    existing_claim_path = repo_root / ".agentic/claims" / "{0}.json".format(args.work_id)
    if existing_claim_path.exists():
        emit("ERROR: claim already exists for {0}".format(args.work_id))
        return 1
    if work_item.status not in ["ready", "in_progress"]:
        emit("ERROR: work item {0} is not ready to claim".format(args.work_id))
        return 1

    now = utc_now()
    branch = args.branch or "feat/{0}-{1}".format(args.work_id, slugify(work_item.title))
    claim = Claim(
        work_id=args.work_id,
        status="in_progress",
        claimed_by="agent:{0}:{1}".format(args.agent, args.machine),
        agent_runtime=args.agent,
        role=args.role,
        machine=args.machine,
        worktree=args.worktree,
        branch=branch,
        claimed_at=now,
        last_seen=now,
    )
    save_model_json(existing_claim_path, claim)

    work_item.status = "in_progress"
    work_item.updated_at = now
    save_model_json(work_path, work_item)
    emit("Claimed {0} on branch {1}".format(args.work_id, branch))
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
    save_model_json(repo_root / ".agentic/reviews" / "{0}.json".format(review_packet.id), review_packet)

    work_item.status = "pr_open"
    work_item.updated_at = utc_now()
    save_model_json(repo_root / ".agentic/work" / "{0}.json".format(args.work_id), work_item)

    if args.dry_run:
        emit("Dry-run: review packet written to .agentic/reviews/{0}.json".format(review_packet.id))
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
    save_model_json(repo_root / ".agentic/reviews" / "{0}.json".format(review_packet.id), review_packet)
    emit("Wrote review packet {0}".format(review_packet.id))
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

    repo_root = resolve_repo_root(Path.cwd())
    config = load_project_config(repo_root)
    if config.dashboard.enabled:
        handle_dashboard_build(argparse.Namespace())
    return handle_doctor(argparse.Namespace())


def derive_project_key(project_name: str) -> str:
    letters = [char for char in project_name.upper() if char.isalnum()]
    return "".join(letters[:4]) or "APP"


def parse_csv(raw: str) -> List[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


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


def summarize_claims(claims: Iterable[object]) -> List[str]:
    return [
        "  - {0}: {1} on {2}".format(claim.work_id, claim.agent_runtime, claim.branch)
        for claim in list(claims)[:5]
    ]


def summarize_reviews(reviews: Iterable[object]) -> List[str]:
    return ["  - {0}: {1}".format(review.id, review.status) for review in list(reviews)[:5]]
