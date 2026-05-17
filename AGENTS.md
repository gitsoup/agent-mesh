# AGENTS.md - Build Instructions for Agent Mesh

You are building **agent-mesh**, a git-native coordination toolkit for parallel AI coding agents.

## Product summary

Agent Mesh turns a normal git repository into a coordinated workspace for humans and AI coding agents. It does not replace coding agents, issue trackers, or CI. It provides the repo protocol, CLI/TUI, workflow skills, adapters, and local automation needed for many agents to work safely in one repo.

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
pip install -e .
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
