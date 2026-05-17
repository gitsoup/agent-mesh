# ADR 0001: Coordination State Model

## Status

Accepted

## Context

Agent Mesh needs two properties at the same time:

1. Task code should be isolated in dedicated worktrees and feature branches.
2. Live coordination state should be visible from the shared root before merge.

The current branch-local `.agentic` model does not satisfy both requirements.
If claims, review packets, and runtime task status live only on a feature
branch, a shared root on `main` cannot see them before merge. That weakens the
core product promise that Agent Mesh is a coordination layer.

The repo also needs stable terminology:

- `shared root`: the human entry checkout on `main`
- `coordination worktree`: the dedicated checkout for live coordination state
- `task worktree`: a dedicated checkout for one agent workspace and one task
  branch

## Decision

Agent Mesh will split state into two layers:

### Durable state on `main`

These files belong on `main` because they remain meaningful even after active
sessions end:

- `AGENTS.md`
- `.agentic/context/CONTEXT.md`
- `.agentic/context/CONTEXT-MAP.md`
- `.agentic/context/adr/*`
- canonical workflows and adapter templates
- stable work definitions and planning artifacts

### Live state on `mesh/state`

These files belong to a dedicated coordination branch checked out in a
coordination worktree because they answer "what is happening right now?":

- active claims
- review packets
- handoffs
- claim freshness and recovery events
- workspace routing
- runtime task status such as `in_progress` and `pr_open`

The `shared root` should remain on `main`. The `mesh/state` branch should be
checked out in a dedicated coordination worktree. Task worktrees should hold
code branches only.

Mesh commands, not ad hoc manual edits, should be the supported way to read and
write live coordination state. Worktrees should treat the coordination worktree
as the authoritative source for live state.

## Consequences

### Benefits

- Shared-root sessions can inspect live coordination state before merge.
- Task code remains isolated in dedicated worktrees.
- Claims, reviews, and handoffs become globally visible without forcing task
  branches into the shared root.
- The model stays git-visible and auditable.

### Costs

- The implementation becomes a multi-worktree design by default.
- Commands must learn how to resolve and write state in the coordination
  worktree.
- Migration is required from the current branch-local `.agentic` runtime model.

### Follow-up implications

- `mesh init` should scaffold or explain the coordination worktree topology.
- `mesh claim`, `mesh pr`, `mesh review`, `mesh sync`, and future merge flows
  should resolve live state through the coordination worktree.
- Runtime task status should stop relying on branch-local work item files as the
  sole source of truth.
