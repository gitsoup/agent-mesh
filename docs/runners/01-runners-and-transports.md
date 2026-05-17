# Runners and Transports

## 1. Key distinction

Coordination and execution are separate.

- A **transport** delivers messages or events.
- A **runner** executes an agent or workflow.

A reviewer agent cannot wake up unless some compute is available.

## 2. Runner types

### local_manual

The user manually starts agent sessions. Agent Mesh generates review packets and commands but does not spawn agents.

### local_watch

A local daemon watches `.agentic/inbox`, GitHub, or another transport and starts configured commands.

Example future command:

```bash
mesh watch --role reviewer --agent codex
```

### github_actions

A generated workflow runs on PR events and performs automated review or status aggregation.

Use this primarily for review, lint, tests, and status generation, not heavy implementation.

### self_hosted

A machine controlled by the team runs agents from queue messages.

### codespaces

Future backend that starts cloud dev environments for agent work.

### cloud_vm

Future backend for container/VM agent execution.

### aweb

Future backend or transport adapter for agent-to-agent coordination.

## 3. Transport types

### git_files

Commit files under `.agentic/` to communicate state.

### local_inbox

Write request files under `.agentic/inbox/<role>/`.

### github

Use PR comments, labels, assignments, checks, and workflow dispatch.

### aweb

Use aweb mail/tasks/chat/roles/presence/locks when configured.

### cloudflare

Future control plane using Workers, Queues, Workflows, Durable Objects, and Pages.

Cloudflare should route, queue, and track jobs. It should not be the default place to run full coding agents.

## 4. Review delegation flow

Local-first v0.1/v0.2 flow:

```text
/implement
  ↓
/pr --review
  ↓
create review packet
  ↓
write .agentic/reviews/PR-12.json
  ↓
optionally write .agentic/inbox/reviewer/PR-12.json
  ↓
reviewer agent runs /review PR-12 manually or via mesh watch
```

Future GitHub flow:

```text
PR opened
  ↓
GitHub Actions workflow
  ↓
checkout repo
  ↓
run mesh review-packet / agent review command
  ↓
comment on PR
```

Future aweb flow:

```text
/pr --review
  ↓
mesh delegate review --transport aweb
  ↓
aweb task/mail to reviewer role
  ↓
reviewer agent receives message
  ↓
reviewer comments on PR
```
