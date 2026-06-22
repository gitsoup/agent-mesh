# Agent Mesh

Agent Mesh is a git-native coordination toolkit for running multiple AI coding
agents and humans safely in one repository.

The repository is still in early implementation. The current focus is the v0.1
local-first scaffold described in [AGENTS.md](./AGENTS.md) and the planning docs
under [docs/](./docs).

## Installing the `mesh` CLI

Install `mesh` globally so any terminal, agent session, or tool can invoke it
directly without path prefixes or environment variables.

**Recommended — `uv tool` (global install):**

```bash
git clone <this-repo>
cd agent-mesh
uv tool install .
mesh doctor
```

**Upgrading after pulling new changes:**

```bash
cd agent-mesh
uv cache clean agent-mesh
uv tool install . --force
```

**Fallback — pip (if `uv` is unavailable):**

```bash
pip install -e .
mesh doctor
```

> Do NOT use `PYTHONPATH=... /path/to/.venv/bin/mesh` — that approach is
> fragile, session-scoped, and invisible to other agents. A global install via
> `uv tool` or `pip install -e .` puts `mesh` on `PATH` so every agent and
> tool can call it directly.

Once installed, verify with:

```bash
mesh --help
mesh doctor
```

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

## Task Bootstrap

`mesh init` creates the coordination contract, but it does not invent work on
its own. Agents should inspect the repo and any available planning sources,
derive an initial task list, then persist it through Mesh:

```bash
cp .agentic/examples/bootstrap-tasks.json bootstrap-tasks.json
# edit bootstrap-tasks.json for this repo
mesh bootstrap-tasks < bootstrap-tasks.json
mesh sync
```

`mesh bootstrap-tasks` accepts either a JSON array of task objects or an object
with a top-level `tasks` array. Missing task IDs are assigned automatically
using the repo project key. `mesh init` scaffolds a sample task file at
`.agentic/examples/bootstrap-tasks.json`.

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

## Brownfield Adoption

In an existing repo, start with a read-only adoption report:

```bash
mesh adoption report
```

The report classifies the repo as greenfield, brownfield adoption, or ongoing
coordination; lists existing instruction files, planning/task sources, and
product/context artifacts; and prints the safest next commands.

`mesh init` preserves a user-authored root `AGENTS.md`. It does not
automatically rewrite that file to insert Mesh startup routing.

Instead, brownfield adoption works in two steps:

- `mesh init` scaffolds Mesh state and writes `.agentic/AGENTS-BOOTSTRAP.md`
- `mesh doctor` reports adoption as incomplete until the Mesh bootstrap block is
  merged into the root `AGENTS.md`

This keeps repo-specific instructions intact while making missing Mesh startup
control explicit and actionable. Existing Linear/GitHub/TODO work should be
reviewed and normalized through `mesh bootstrap-tasks`; Mesh does not import
or claim external tasks automatically during init.

By default, `mesh init` uses required worktree isolation, creates a local
`mesh/state` coordination branch and sibling coordination worktree, and
publishes that branch when `origin` exists:

```bash
mesh init
```

Use `--no-push` only when you intentionally want local-only coordination. Other
developers cannot discover shared Mesh state from a fresh clone until
`mesh/state` is available on the remote. If no `origin` remote is configured,
`mesh init` leaves the branch local and prints the push command to run after the
remote is wired. Once `mesh/state` is published, a new developer can clone the
repo and run:

```bash
mesh sync
mesh status
```

`mesh sync` creates their local sibling coordination worktree from
`origin/mesh/state`; they should not run `mesh init` again unless repairing an
incomplete adoption.
