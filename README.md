# Agent Mesh

Agent Mesh is a git-native coordination toolkit for running multiple AI coding
agents and humans safely in one repository.

The repository is still in early implementation. The current focus is the v0.1
local-first scaffold described in [AGENTS.md](./AGENTS.md) and the planning docs
under [docs/](./docs).

## Repo Model

Agent Mesh is repo-native.

- The repository carries the durable Mesh contract: `AGENTS.md`, `.agentic/project.json`,
  context, workflows, and canonical skills.
- Each teammate installs the `mesh` CLI locally on their own machine.
- Agent-specific adapter files are installed only when a given runtime needs them.

That means a fork or fresh clone already contains the coordination contract.
If a teammate or agent session does not have the `mesh` CLI yet, the first step
is to install it locally and run `mesh doctor`.

## Current status

The project now includes:

- a Python package scaffold
- a `mesh` CLI entrypoint
- initial Pydantic config/state models
- explicit shared-root, task-worktree, and `mesh/state` coordination-topology metadata
- baseline tests for installability and config/state validation

## Development

Use `uv` for local development and agent execution:

```bash
uv sync --extra dev
uv run pytest
```

Fallback if `uv` is unavailable:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
pytest
```

## Dashboard Publishing

Agent Mesh can build two kinds of static dashboard artifacts:

- `mesh dashboard build`
  Writes the internal operator dashboard to `dist/mesh-dashboard/index.html`.
- `mesh dashboard build --public --output-dir dist/public-dashboard`
  Writes a stakeholder-safe static export to `dist/public-dashboard/` with:
  - `index.html`
  - `dashboard-data.json`

The public export is designed for static hosting such as Cloudflare Pages. It
keeps task progress and review state visible while redacting coordination-only
fields such as worktree paths, workspace IDs, machine names, and branch names.

## Adapter Activation

`mesh init` establishes the shared repo contract. It does not require every
agent-specific wrapper to be installed up front.

Install adapter files only when a runtime needs them:

```bash
mesh adapter install codex
mesh adapter install claude
mesh adapter install opencode
```

When Mesh can infer a likely runtime, commands such as `mesh doctor`,
`mesh status`, or `mesh claim` will print an install tip if the corresponding
adapter files are missing.
