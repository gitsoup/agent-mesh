# Prompt to give Codex

Read `AGENTS.md` first. Then read the PRD and architecture docs under `docs/`.

Build the v0.1 version of Agent Mesh exactly as specified:

1. Python package named `agent-mesh` with CLI command `mesh`.
2. Typer/Rich CLI and minimal optional TUI.
3. Pydantic schemas for project config, work items, claims, evidence, and review packets.
4. `mesh init` that scaffolds `.agentic/`, `AGENTS.md`, canonical workflows, canonical skills, context files, and selected adapters.
5. Required commands: `doctor`, `status`, `skill list`, `adapter list`, `adapter install`, `task add/list/show`, `claim`, `pr --dry-run`, `review-packet`, `dashboard build`, `sync`.
6. Adapters for generic, Claude, Codex, Cursor, OpenCode, Pi, and Windsurf.
7. Static dashboard generator.
8. Tests covering schemas, scaffold, adapters, task commands, claim, PR dry-run, dashboard, and doctor.
9. README with quick start and command reference.

Do not implement cloud execution or hosted services in v0.1. Create clean interfaces for future runner and transport backends.

After implementation, run tests and show a short demo transcript of the v0.1 acceptance test from `docs/implementation/00-implementation-plan.md`.
