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

## Next product areas

- onboarding and first-run TUI
- brownfield adoption and migration workflows
- stronger coordination semantics for concurrent agent work
