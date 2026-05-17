# Implementation Plan for Codex

## Phase 0: Project scaffold

Create:

```text
pyproject.toml
README.md
agent_mesh/
tests/
```

Add dependencies:

- typer
- rich
- textual optional
- pydantic
- pyyaml optional
- pytest
- ruff

Expose CLI entrypoint:

```toml
[project.scripts]
mesh = "agent_mesh.cli:app"
```

## Phase 1: Schemas and storage

Implement Pydantic models for:

- ProjectConfig
- PlanningConfig
- CoordinationConfig
- WorkItem
- Claim
- Evidence
- ReviewPacket
- AdapterConfig

Implement storage helpers:

- atomic write JSON
- load JSON
- validate state tree
- list work items
- list claims
- resolve repo root

## Phase 2: Template rendering and scaffold

Implement `mesh init`.

Requirements:

- Should not overwrite existing files unless `--force`.
- Should support non-interactive flags.
- Should create `.agentic/` folders.
- Should create `AGENTS.md`.
- Should create context files.
- Should create canonical workflows and skills.
- Should install selected adapters.

## Phase 3: CLI commands

Implement:

```text
mesh doctor
mesh status
mesh skill list
mesh adapter list
mesh adapter install
mesh task add
mesh task list
mesh task show
mesh claim
mesh pr --dry-run
mesh review-packet
mesh dashboard build
mesh sync
```

## Phase 4: Adapters

Implement adapters:

- generic
- claude
- codex
- cursor
- opencode
- pi
- windsurf

Do not overfit unknown tool-specific config. It is okay for early adapters to generate AGENTS.md plus pointers to canonical workflows.

## Phase 5: Dashboard

Implement static dashboard generation from `.agentic/work`, `.agentic/claims`, `.agentic/reviews`.

Output:

```text
.agentic/dashboard/index.html
```

Also generate GitHub Actions status workflow template.

## Phase 6: Tests

Add tests for:

- schema validation
- scaffold output
- adapter output
- task add/list/show
- claim creation
- PR dry-run body generation
- dashboard generation
- doctor validation

## Phase 7: Documentation

Write README with:

- what Agent Mesh is
- local-first quick start
- supported agents
- command reference
- generated repo structure
- roadmap

## v0.1 acceptance test

In a temp directory:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
mkdir /tmp/demo-agent-mesh && cd /tmp/demo-agent-mesh
git init
mesh init --project-name demo --project-key APP --provider local --adapters generic,codex,claude --yes
mesh doctor
mesh task add "Implement auth endpoint" --module api
mesh task list
mesh claim APP-1 --agent codex --role implementer --no-push
mesh status
mesh pr --dry-run --work-id APP-1
mesh dashboard build
```

All commands should complete successfully.
