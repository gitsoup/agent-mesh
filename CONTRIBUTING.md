# Contributing to Agent Mesh

## Request and approval flow

GitHub Issues are the public queue for bugs and feature requests. Start with an
issue form; do not begin an implementation branch for an untriaged request.

Maintainers move requests through these labels:

1. `needs-triage` — newly submitted and awaiting assessment.
2. `needs-info` — a decision or detail is missing.
3. `approved` — maintainers have accepted the request.
4. `ready-for-development` — the scope and acceptance criteria are sufficient
   for implementation. `agent-safe` additionally means an agent may work on it
   without an interactive product decision.

Only maintainers apply `approved` and `ready-for-development`. Contributors and
agents must work only from issues that have both labels. Use `blocked` whenever
an approved request cannot currently proceed.

## Pull requests

Every pull request must include a closing reference such as `Closes #123` for
an issue carrying both approval labels. The required **Approved issue gate**
check verifies this. Pull requests also need a maintainer review and passing CI
before they can merge into `main`.

For Agent Mesh work, use the GitHub issue as the planning source and the Mesh
claim as the execution lease: the claim records the active agent, branch, and
worktree, but never substitutes for issue approval.
