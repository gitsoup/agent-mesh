# ADR 0002: Coordination Worktree Topology

## Status

Accepted

## Context

ADR 0001 established that live coordination state should move to a dedicated
`mesh/state` branch checked out in a coordination worktree. The repo still
needed a concrete topology contract that answers three questions:

1. How does any session locate the expected coordination worktree?
2. When should Agent Mesh create or repair it?
3. What should agents do while the live-state migration is still in progress?

Without a concrete answer, different agents can invent different worktree
layouts or fall back to writing runtime state from the shared root.

## Decision

Agent Mesh will model coordination topology explicitly in
`.agentic/project.json`.

The coordination config now includes:

- `branch`: the live coordination branch, defaulting to `mesh/state`
- `coordination_worktree`: an optional explicit path to the coordination
  worktree
- `worktree_root`: an optional root for generated worktrees

Path resolution rules:

1. If `coordination_worktree` is set, use it.
2. Otherwise, if `worktree_root` is set, the expected coordination worktree is
   `<worktree_root>/<repo>-mesh-state`.
3. Otherwise, the expected coordination worktree is a sibling checkout named
   `<repo>-mesh-state`.

Health rules:

- A missing coordination worktree is a recoverable bootstrap state.
- A present coordination worktree must be a git worktree checked out on
  `mesh/state`.
- A dirty coordination worktree should be surfaced to the user as unhealthy and
  repaired before authoritative live-state writes run through it.

Creation and recovery rules:

- `mesh init` records the coordination topology contract and should create the
  coordination worktree automatically for real git repos with worktrees
  enabled.
- `mesh sync` is the recovery path when the coordination worktree is missing or
  on the wrong branch.
- Until full live-state routing lands, `mesh status` and `mesh doctor` should
  surface the expected topology and obvious misconfiguration.

## Consequences

### Benefits

- Every session can derive the same expected coordination worktree location from
  repo config.
- Shared-root and task-worktree roles remain explicit.
- Later live-state work can reuse a stable topology contract instead of
  re-deciding naming and discovery rules.

### Costs

- The repo now carries topology metadata before the full live-state migration is
  complete.
- `mesh status` and `mesh doctor` can only report topology health today; they do
  not yet route claims, reviews, or handoffs through `mesh/state`.

### Follow-up implications

- `MESH-8` should split durable work definitions from live runtime state using
  this topology.
- `MESH-9` should route claim, PR, review, and sync flows through the
  coordination worktree as the authoritative live-state location.
- `MESH-10` should add write-safety and migration handling for shared live
  state.
