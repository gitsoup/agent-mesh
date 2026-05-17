# Product Requirements Document: Agent Mesh

## 1. Name and identity

Working name: **Agent Mesh**

Package name: `agent-mesh`

CLI command: `mesh`

Possible future aliases or alternate branding:

- Mesh
- Branchmesh
- Fractal

For v0.1, use **agent-mesh** for the package and **mesh** for the command.

## 2. One-line pitch

Agent Mesh is a git-native coordination toolkit for running multiple AI coding agents and humans safely in one repository.

## 3. Problem

AI coding agents are increasingly capable of implementing, reviewing, debugging, and refactoring code. Developers already run several agent sessions locally: one agent implements, another reviews, another diagnoses failures. However, current workflows rely on humans to coordinate the sessions manually.

Common pain points:

- Agents pick the same task.
- Agents overwrite each other's work.
- Agents do not know which branch, worktree, or issue belongs to whom.
- Humans manually copy PR links between sessions.
- Agent handoffs lose context.
- Review agents lack acceptance criteria and test evidence.
- Issue trackers are optional and inconsistent across teams.
- Claude Code, Codex, Cursor, OpenCode, Pi, and other agents all use slightly different instruction mechanisms.
- Teams want local-first workflows now, but may want CI/cloud execution later.

## 4. Product thesis

The durable source of coordination should be the repository itself.

Agent Mesh treats git, branches, PRs, and human-readable repo files as the coordination fabric. Agent runtimes become interchangeable adapters.

Agent Mesh is not:

- a coding agent
- a replacement for GitHub, Linear, Jira, or CI
- a hosted autonomous agent platform
- a database-backed task queue
- a Claude-only toolkit

Agent Mesh is:

- a repo operating layer
- a coordination protocol
- a skill/workflow pack
- a local-first CLI/TUI
- an adapter generator for agent runtimes
- a pathway toward optional automated review/delegation

## 5. Goals

### v0.1 goals

1. Provide a CLI and minimal TUI for initializing an agent-ready repo.
2. Scaffold `.agentic/` state folders and canonical workflows.
3. Scaffold `AGENTS.md` and context files.
4. Provide canonical skill definitions for core workflows.
5. Generate adapter-specific files for Claude Code, Codex/open Agent Skills, Cursor, OpenCode, Pi, Windsurf, and generic agents.
6. Provide local-only task creation, task claiming, status, review packet generation, and PR dry-run support.
7. Provide GitHub-compatible PR and status workflow templates.
8. Provide a simple static dashboard generator.
9. Provide schema validation and `mesh doctor`.
10. Keep all v0.1 functionality local-first and human-reviewable.

### v0.2 goals

1. Add GitHub Issues provider.
2. Add Linear provider.
3. Add `mesh watch --role reviewer` for local reviewer automation.
4. Add `mesh pr --review` to create a review packet and queue review work.
5. Add GitHub Actions runner template for automated PR review.
6. Add provider import/export flows.

### Future goals

1. Add Jira provider.
2. Add Cloudflare control-plane template for webhooks, queues, workflows, presence, and dashboard APIs.
3. Add aweb transport adapter.
4. Add cloud runner backends: GitHub Actions, self-hosted runner, Codespaces, container/VM.
5. Add richer role routing: implementer, reviewer, architect, release, product.

## 6. Non-goals for v0.1

- No hosted service.
- No cloud compute orchestration.
- No long-running remote agent execution.
- No proprietary server dependency.
- No hard dependency on Linear.
- No hard dependency on Claude Code.
- No mandatory GitHub repository; local git should work.
- No automatic merge without explicit user command.

## 7. User personas

### Solo developer running many agents locally

Runs Claude Code in one terminal, Codex/OpenCode/Qwen in another, and wants structured coordination without copying context manually.

### Small team using GitHub Issues or Linear

Wants agents to claim tasks, open PRs with evidence, and avoid collisions.

### Maintainer preparing an open-source repo for agents

Wants `AGENTS.md`, skills, and workflows that let external contributors or agents operate consistently.

### Advanced team exploring cloud agents

Wants a clean local-first protocol today and pluggable runners later.

## 8. Core concepts

### Work item

A unit of planned work. It may originate from local JSON, GitHub Issues, Linear, Jira, or a markdown PRD.

### Claim

A git-visible record that a human or agent has taken ownership of a work item.

### Context

The repo's shared domain language and durable decisions. Implemented through `CONTEXT.md`, `CONTEXT-MAP.md`, and ADRs.

### Skill

A reusable workflow instruction bundle. Canonical skills live in `.agentic/skills/` and are adapted into tool-specific folders.

### Adapter

A generator that translates canonical instructions into tool-specific instruction files.

### Provider

A planning source such as local files, GitHub Issues, Linear, or Jira.

### Runner

A place where an agent executes: local terminal, GitHub Actions, self-hosted runner, Codespaces, container/VM, or aweb-connected agent.

### Transport

A mechanism for sending coordination events: git files, GitHub PR comments/labels, local inbox, aweb messages, Cloudflare queues.

## 9. Core workflow

```text
idea
  ↓ /align
prd
  ↓ /to-prd
work items
  ↓ /to-tasks
triaged tasks
  ↓ /triage
claimed work
  ↓ /claim
implementation
  ↓ /implement
pull request
  ↓ /pr
review
  ↓ /review
requested changes
  ↓ /address
merge
  ↓ /merge
done
```

## 10. Required v0.1 commands

- `mesh init`
- `mesh doctor`
- `mesh status`
- `mesh skill list`
- `mesh adapter list`
- `mesh adapter install`
- `mesh task add`
- `mesh task list`
- `mesh task show`
- `mesh claim`
- `mesh pr --dry-run`
- `mesh review-packet`
- `mesh dashboard build`
- `mesh sync`

## 11. Desired future commands

- `mesh watch --role reviewer`
- `mesh delegate review --pr 12`
- `mesh inbox`
- `mesh runner setup github-actions`
- `mesh provider import github`
- `mesh provider import linear`
- `mesh transport add aweb`

## 12. Acceptance criteria

A v0.1 implementation is successful when:

1. A new empty repo can be initialized with `mesh init`.
2. The user can choose local-only provider and at least one agent adapter.
3. The generated repo has clear `AGENTS.md` and `.agentic/` structure.
4. The user can create a local task with `mesh task add`.
5. The user can claim a task with `mesh claim` and see claim files created.
6. `mesh status` summarizes tasks, claims, branches, and pending reviews.
7. `mesh pr --dry-run` generates a PR body and review packet without requiring GitHub.
8. `mesh doctor` validates config and state schemas.
9. Adapter output exists for at least generic AGENTS.md, Claude Code, Codex/open Agent Skills, Cursor, OpenCode, Pi, and Windsurf.
10. Tests cover schema validation, scaffold generation, command behavior, and adapter generation.
