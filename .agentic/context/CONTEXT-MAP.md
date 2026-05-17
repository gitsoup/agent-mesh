# Context Map

## Durable product context

- `.agentic/context/CONTEXT.md`: domain language, product modes, and durable
  coordination concepts
- `.agentic/context/adr/`: durable architecture decisions, especially for the
  coordination-state model
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
- `.agentic/work/`: stable task definitions on `main`; live runtime task status
  should move to the coordination layer
- `.agentic/claims/`: live claim ownership and workspace routing; should move to
  `mesh/state`
- `.agentic/reviews/`: live review packets; should move to `mesh/state`
- `.agentic/handoffs/`: live continuation context; should move to `mesh/state`
- `.agentic/workflows/setup.md`: first-run routing for greenfield and brownfield
- `.agentic/workflows/claim.md`: transition from inspected coordination state to
  active implementation

## Target workspace topology

- `shared root`: human entry checkout on `main`
- `coordination worktree`: dedicated checkout for the `mesh/state` branch
- `task worktrees`: dedicated checkouts for feature branches and isolated agent
  work

## Next product areas

- onboarding and first-run TUI
- brownfield adoption and migration workflows
- stronger coordination semantics for concurrent agent work
- migration from branch-local live state to a dedicated coordination worktree
