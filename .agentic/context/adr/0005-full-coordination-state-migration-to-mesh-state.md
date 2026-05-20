# ADR 0005: Full Coordination State Migration to `mesh/state`

## Status

Accepted

## Context

ADR 0001 decided that live coordination state should live on a dedicated
`mesh/state` branch. ADR 0002 defined the topology and naming convention.
Neither was implemented: all `.agentic/` state has continued to be committed
to `main` because MESH-9 (the routing task) remained open.

A separate alignment question arose: which `.agentic/` files are "durable" and
belong on `main`, and which are "live" and belong on `mesh/state`?

The proposed split was: work item definitions stay on `main`, claims and
reviews move to `mesh/state`. The problem with this split is that `mesh status`
and any agent checking available work must then read from two different
locations — the shared root for work items and the coordination worktree for
claims and reviews. This creates dual-read complexity and a failure mode: if the
coordination worktree is missing, status breaks even though work definitions are
right there on `main`.

The real user scenarios (confirmed during dogfooding) are exactly two:

1. **New repo**: no `.agentic/` exists yet. `mesh init` creates everything.
2. **Existing repo** (brownfield): has code/docs/conventions, no `.agentic/`.
   `mesh init` creates everything.

Both cases are identical from the coordination layer's perspective. The
"migrate existing `.agentic/` from `main`" scenario only exists because this
repo is dogfooding Agent Mesh while building it. That is a one-time cleanup,
not a product feature.

## Decision

### 1. All `.agentic/` state moves to `mesh/state`

The coordination worktree owns all `.agentic/` state:

- `project.json`, `context/`, `context/adr/` — project contract
- `work/` — task definitions and status
- `claims/`, `reviews/`, `handoffs/` — live coordination artifacts
- `dashboard/`, `workflows/`, `skills/`, `adapters/` — generated artifacts

`main` keeps only:
- All source code
- `AGENTS.md`
- Adapter install directories (`.claude/`, `.agents/`, `.github/`)
- Nothing from `.agentic/`

### 2. `mesh/state` is an orphan branch

`mesh/state` is created as an orphan branch (no shared history with `main`).
It contains fundamentally different content and should never be merged into
`main`. The current implementation creates it branched from `main` — this is
wrong and is corrected here.

### 3. `mesh init` seeds the coordination worktree

`mesh init` (both for new repos and brownfield):

1. Creates the `mesh/state` orphan branch if it does not exist
2. Creates or repairs the coordination worktree at the sibling path
   `<repo>-mesh-state` (from ADR 0002 naming convention)
3. Writes all `.agentic/` scaffolding to the coordination worktree
4. Commits the initial state to `mesh/state`
5. Pushes `mesh/state` to origin so other machines can fetch it
6. Does NOT write `.agentic/` to the shared root or `main`

### 4. All coordination commands route through the coordination worktree

`mesh claim`, `mesh pr`, `mesh review-packet`, `mesh review`, `mesh status`,
`mesh sync`, `mesh merge`, `mesh task` — all read and write `.agentic/` state
from the coordination worktree, resolved via `resolve_coordination_root()`.

`resolve_coordination_root(repo_root, config)` returns:
- The coordination worktree path if it exists and is on `mesh/state`
- Falls back to `repo_root` if not (backward compat / degraded mode)

### 5. New agent bootstrap on a fresh machine

```
git clone <repo>     # gets main — code + AGENTS.md
mesh doctor          # detects mesh/state on origin, no local worktree
mesh sync            # fetches mesh/state, creates coordination worktree
mesh status          # reads from coordination worktree
```

### 6. This repo's dogfood migration is a one-time manual cleanup

After MESH-9 lands, this repo's `.agentic/` will be moved from `main` to
`mesh/state` manually. This is not a product feature and will not be
implemented as a `mesh migrate` command.

## Consequences

### Benefits

- Single read location for all coordination state — no dual-read complexity
- Live coordination state is visible to all machines without checking out
  feature branches
- `main` stays clean — code only, no coordination noise
- Atomicity: push conflict on `mesh/state` is the concurrency primitive for
  claim races (MESH-10)

### Costs

- Coordination worktree must be set up on every machine before any mesh command
  works; `mesh doctor` + `mesh sync` are the bootstrap path
- `mesh init` becomes slightly heavier — must create orphan branch and
  coordination worktree
- This repo requires a one-time manual migration to move `.agentic/` off `main`

### Supersedes

This ADR supersedes the "live state on `mesh/state`" clause in ADR 0001 by
extending it to ALL `.agentic/` content, not just claims and reviews.

## Follow-up

- MESH-10: write safety for concurrent `mesh/state` pushes
- Manual dogfood cleanup: move this repo's `.agentic/` off `main`
