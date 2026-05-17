# Context

Agent Mesh is a git-native coordination toolkit for parallel human and AI coding
agents working in one repository.

## Core concepts

- `work item`: a planned unit of work stored as repo-local state
- `claim`: a repo-visible ownership record for a work item
- `review packet`: the handoff artifact from implementation to review
- `adapter`: tool-specific instructions generated from canonical workflows
- `coordination state`: the human-readable files under `.agentic/`
- `shared root`: the primary human entrypoint checkout for the repo; it should
  stay on `main` and be used for coordination, not task implementation
- `coordination worktree`: a dedicated checkout for the `mesh/state` branch that
  owns live coordination state
- `task worktree`: a dedicated checkout for one agent workspace and one task
  branch

## Product modes

- `greenfield`: empty or near-empty repo; the system should help establish the
  product, context, PRD, and initial work items
- `brownfield adoption`: existing repo with code/docs/conventions, but without
  agent coordination; the system should help derive context and normalize
  existing artifacts into Mesh-compatible state
- `ongoing coordination`: repo already uses Agent Mesh; agents should inspect
  current work, claims, reviews, and continue within the protocol

## Startup routing

- Agents should detect repo mode before selecting a workflow
- Startup inspection order is `AGENTS.md`, `CONTEXT.md`, `CONTEXT-MAP.md`,
  `.agentic/project.json`, then current coordination state
- When `.agentic/` already exists, default to `ongoing coordination` and inspect
  active state before proposing `/setup`
- Brownfield adoption is for repos with existing code/docs but missing or
  incomplete Mesh state
- Greenfield is for repos that are still establishing the product and initial
  work graph
- Parallel implementation should default to one claimed task per dedicated
  worktree and branch
- Claims are recoverable ownership records; stale claims should be resumed or
  explicitly taken over instead of manually deleted
- `workspace_id` identifies the reusable agent lane or workspace, while the
  branch name identifies the task

## Coordination state model

- Durable repo contract belongs on `main`
- Live coordination state must be visible before merge from a shared
  coordination location
- `main` should hold durable artifacts such as `AGENTS.md`,
  `.agentic/context/`, ADRs, canonical workflows, adapter templates, and stable
  work definitions
- Live coordination state should hold active claims, review packets, handoffs,
  claim freshness, workspace routing, and runtime task status such as
  `in_progress` and `pr_open`
- Agent Mesh should use a dedicated `mesh/state` branch checked out in a
  coordination worktree for live coordination state
- Task worktrees should hold code branches only; they should read and write
  shared coordination state through Mesh commands rather than by owning the
  authoritative live state files themselves
- Safe takeover means reusing the task branch while allocating a new
  `workspace_id` and worktree by default; committed branch history carries
  forward, uncommitted workspace state does not

## Alignment notes

- The phrase `main repo` was ambiguous because it mixed the durable `main`
  branch with the human entry checkout; use `shared root` for the human entry
  checkout and `main` for the durable branch
- The current branch-local `.agentic` model is not sufficient for a true
  coordination layer because a shared root on `main` cannot see branch-local
  live state before merge
- Future implementation work should prioritize the `mesh/state` coordination
  model before adding more coordination features on top of branch-local state

## Current dogfooding notes

- This repository is using Agent Mesh to build Agent Mesh
- Brownfield adoption should be treated as a first-class workflow, not as a
  side effect of `mesh init`
- The current runtime surfaced a real concurrency issue in `mesh task add`
  when multiple tasks are created in parallel without locking
