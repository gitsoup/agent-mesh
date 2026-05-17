# Context Map

## Durable product context

- `.agentic/context/CONTEXT.md`: domain language, product modes, and durable
  coordination concepts
- `docs/prd/00-product-requirements.md`: product goals and non-goals
- `docs/implementation/00-implementation-plan.md`: current implementation
  phases and acceptance flow

## Current implementation areas

- `agent_mesh/cli.py`: command surface and user interaction entrypoints
- `agent_mesh/scaffold.py`: repo initialization and adapter file generation
- `agent_mesh/state/`: persistent models, storage, and validation
- `tests/`: behavior and regression coverage

## Startup artifacts

- `AGENTS.md`: startup contract, mode detection, and repo-wide guardrails
- `.agentic/project.json`: installed adapters and coordination configuration
- `.agentic/work/`: task inventory and readiness state
- `.agentic/claims/`: active task ownership
- claim files also record the assigned task branch and dedicated worktree path
- `.agentic/reviews/`: pending or completed review packets
- `.agentic/handoffs/`: continuation context between sessions
- `.agentic/workflows/setup.md`: first-run routing for greenfield and brownfield
- `.agentic/workflows/claim.md`: transition from inspected coordination state to
  active implementation

## Next product areas

- onboarding and first-run TUI
- brownfield adoption and migration workflows
- stronger coordination semantics for concurrent agent work
