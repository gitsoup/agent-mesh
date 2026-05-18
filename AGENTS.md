# AGENTS.md - Build Instructions for Agent Mesh

You are building **agent-mesh**, a git-native coordination toolkit for parallel AI coding agents.

## Product summary

Agent Mesh turns a normal git repository into a coordinated workspace for humans and AI coding agents. It does not replace coding agents, issue trackers, or CI. It provides the repo protocol, CLI/TUI, workflow skills, adapters, and local automation needed for many agents to work safely in one repo.

## Startup behavior

Every fresh Claude or Codex session should determine repo mode before choosing a workflow.

Inspect these signals first, in order:

1. `AGENTS.md`
2. `.agentic/context/CONTEXT.md`
3. `.agentic/context/CONTEXT-MAP.md`
4. `.agentic/project.json` if present
5. Current coordination state via `mesh status` when the CLI is available, otherwise inspect `.agentic/work/`, `.agentic/claims/`, `.agentic/reviews/`, and `.agentic/handoffs/`

Route into one of these modes:

- `greenfield`: no meaningful product code/docs yet, and no established coordination state. Start with `/align`, then `/to-prd`, then `/to-tasks`. Use `/setup` only when Agent Mesh has not been initialized yet.
- `brownfield adoption`: repo has meaningful code/docs/conventions but lacks usable Mesh coordination state. Start with `/setup`, derive durable context from existing artifacts, normalize that context into Mesh state, then continue with `/align`, `/to-prd`, `/to-tasks`, and `/triage` as needed.
- `ongoing coordination`: `.agentic/` already exists with active or historical work state. Follow `/ongoing` for the full inspection sequence, claim rules, and continuation protocol.

Guardrails:

- Do not overwrite existing `.agentic/` state just because `/setup` exists.
- Do not claim work until you have checked for active claims and reviewed the current coordination state.
- Prefer the most coordinated mode already supported by repo state. If `.agentic/` is present, treat the repo as ongoing coordination unless the state is clearly incomplete and the user wants adoption repair.
- In `ongoing coordination` mode, ambiguous execution requests such as `implement`, `continue`, `what next`, `work on this`, or `pick the next task` must be resolved against Agent Mesh coordination state first, not the most recent conversational subtopic.
- For those ambiguous execution requests, inspect `.agentic/work/`, `.agentic/claims/`, `.agentic/reviews/`, and `.agentic/handoffs/` before proposing or starting work unless the user explicitly names a narrower scope.
- Claims should use a dedicated worktree and task branch unless the project explicitly disables worktree isolation.
- Worktree names should follow reusable workspace or lane identity; branch names should remain task-oriented.
- If a claim already exists, resume it explicitly or take it over when it is stale; do not delete claim files as a normal recovery mechanism.
- Safe takeover means: keep the task branch, allocate a new workspace by default, and only carry committed branch history into the new worktree.
- Do not implement claimed work from the shared repo checkout when worktree isolation is enabled.

## Primary docs to read

Read these first, in order:

1. `docs/prd/00-product-requirements.md`
2. `docs/architecture/01-system-architecture.md`
3. `docs/skills/02-skill-catalog.md`
4. `docs/implementation/00-implementation-plan.md`
5. `docs/schemas/01-agentic-state-schemas.md`

## Core principles

- Keep the core agent-agnostic.
- Use git as the durable coordination substrate.
- Use `AGENTS.md` as the universal project contract.
- Generate tool-specific adapters from canonical workflow definitions.
- Keep implementation local-first; cloud execution is optional and future-facing.
- Do not hard-code Linear, Claude Code, or Cloudflare as mandatory dependencies.
- Prefer deterministic scripts for validation, state updates, and scaffolding.
- Keep all generated files human-readable and reviewable.
- Avoid hidden hosted services in v0.1.

## Technology assumptions

Use Python for the CLI/TUI unless the existing repo already strongly prefers another stack.

Recommended stack:

- Python 3.11+
- uv for environment and command execution
- Typer for CLI commands
- Rich for terminal output
- Textual for optional TUI screens
- Pydantic for schemas
- PyYAML/TOML as needed for config
- pytest for tests
- ruff for linting/formatting

## Expected package layout

Implement the project roughly as:

```text
agent_mesh/
  __init__.py
  cli.py
  tui.py
  config.py
  scaffold.py
  state/
  skills/
  adapters/
  providers/
  runners/
  transports/
  dashboard/
  templates/
  utils/
tests/
docs/
pyproject.toml
README.md
```

## Definition of done for v0.1

A user should be able to run:

```bash
uv sync
mesh init
mesh doctor
mesh skill list
mesh task add "Implement auth endpoint" --module api
mesh claim APP-1
mesh status
mesh pr --dry-run
```

The tool should scaffold a target repo with:

```text
.agentic/
AGENTS.md
.agentic/context/CONTEXT.md
.agentic/context/CONTEXT-MAP.md
.agentic/work/
.agentic/claims/
.agentic/reviews/
.agentic/handoffs/
.agentic/workflows/
.agentic/skills/
.github/workflows/agent-mesh-status.yml
```

Do not implement risky autonomous cloud execution in v0.1. Provide interfaces and documentation for future runner backends.
