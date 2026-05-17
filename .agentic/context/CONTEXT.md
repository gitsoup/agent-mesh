# Context

Agent Mesh is a git-native coordination toolkit for parallel human and AI coding
agents working in one repository.

## Core concepts

- `work item`: a planned unit of work stored as repo-local state
- `claim`: a repo-visible ownership record for a work item
- `review packet`: the handoff artifact from implementation to review
- `adapter`: tool-specific instructions generated from canonical workflows
- `coordination state`: the human-readable files under `.agentic/`

## Product modes

- `greenfield`: empty or near-empty repo; the system should help establish the
  product, context, PRD, and initial work items
- `brownfield adoption`: existing repo with code/docs/conventions, but without
  agent coordination; the system should help derive context and normalize
  existing artifacts into Mesh-compatible state
- `ongoing coordination`: repo already uses Agent Mesh; agents should inspect
  current work, claims, reviews, and continue within the protocol

## Current dogfooding notes

- This repository is using Agent Mesh to build Agent Mesh
- Brownfield adoption should be treated as a first-class workflow, not as a
  side effect of `mesh init`
- The current runtime surfaced a real concurrency issue in `mesh task add`
  when multiple tasks are created in parallel without locking
