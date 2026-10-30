# MESH-26 — GitHub Issue synchronization

- Work item: `.agentic/work/MESH-26.json`
- GitHub Issue: https://github.com/gitsoup/agent-mesh/issues/22
- Claim: `.agentic/claims/MESH-26.json`
- Branch: `feat/MESH-26-synchronize-approved-github-issues-with-agent-mesh-work-items`
- Worktree: `<local-path>`

## Completed setup

- Issue #22 is labelled `approved`, `ready-for-development`, and `agent-safe`.
- MESH-26 is published on `main`, linked to Issue #22, and claimed on `mesh/state`.
- Current provider code is only a local placeholder in `agent_mesh/providers/local.py`.

## Next action

Design and implement a GitHub provider/CLI workflow that imports or links only
approved, ready GitHub Issues as idempotent Mesh work items; add lifecycle
synchronization and tests. Preserve GitHub Issue → MESH work item → PR mapping.

## Risks

- GitHub fine-grained token permissions and CLI auth need to be handled without
  storing tokens in repo state.
- `mesh task add` currently writes directly to `main`, which conflicts with a
  PR-only default-branch policy; MESH-26 should address the protected-branch
  workflow rather than relying on the bootstrap exception used for its setup.
