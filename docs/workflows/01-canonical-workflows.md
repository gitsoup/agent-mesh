# Canonical Workflow Specifications

These workflows should be rendered into `.agentic/workflows/*.md` during `mesh init`.

## Startup routing

Before invoking a workflow, agents should inspect `AGENTS.md`,
`.agentic/context/CONTEXT.md`, `.agentic/context/CONTEXT-MAP.md`,
`.agentic/project.json` when present, and current coordination state.

Repo mode should be classified as:

- `greenfield`: no durable product/code context and no usable Mesh state
- `brownfield adoption`: meaningful repo context exists, but Mesh state is
  missing or incomplete
- `ongoing coordination`: `.agentic/` exists with work, claim, review, or
  handoff state that should be continued

Prefer the most coordinated mode already supported by repo state.

## /setup

Input: repo root and current repo state.

Steps:

1. Detect repo mode before making changes.
2. Read `AGENTS.md`, `CONTEXT.md`, and `CONTEXT-MAP.md`.
3. If `.agentic/` already exists, inspect current work, claims, reviews, and handoffs first.
4. If the repo is `greenfield`, scaffold Agent Mesh state and route into `/align`, `/to-prd`, and `/to-tasks`.
5. If the repo is `brownfield adoption`, derive durable context from existing code, docs, and conventions before normalizing them into `.agentic/` state.
6. Install or refresh adapters only after deciding setup or adoption work is needed.
7. Do not overwrite existing coordination state without explicit confirmation.

## /align

Input: idea, plan, feature, bug, PRD draft, or architecture proposal.

Steps:

1. Determine affected context from `CONTEXT-MAP.md`.
2. Read relevant `CONTEXT.md` files.
3. Read relevant ADRs if present.
4. Identify ambiguous or conflicting terms.
5. Challenge the plan against existing code and constraints.
6. Ask decision-shaping questions only when needed.
7. Recommend defaults.
8. Update context files if terminology is clarified.
9. Create ADR only for durable decisions.
10. Output alignment summary.

## /to-prd

Input: alignment summary or conversation context.

Steps:

1. Summarize problem.
2. Define goals and non-goals.
3. Define user flows or technical flows.
4. Define acceptance criteria.
5. Define risks and open questions.
6. Save PRD.

## /to-tasks

Input: PRD/spec.

Steps:

1. Identify vertical slices.
2. Create tasks with acceptance criteria.
3. Mark execution mode: `afk_safe`, `hitl`, `human_only`.
4. Add dependencies.
5. Write `.agentic/work/*.json`.

## /triage

Input: work items.

Steps:

1. Check clarity.
2. Check dependencies.
3. Check testability.
4. Check risk.
5. Set status.

## /claim

Input: work item ID.

Steps:

1. Confirm the repo is in `ongoing coordination` mode, or finish setup/adoption work first.
2. Inspect current status, claims, reviews, and handoffs.
3. Validate work item.
4. Check existing claim.
5. Create/check a dedicated worktree and task branch unless worktree isolation is disabled by project config.
6. Create claim file.
7. Commit/push claim if remote exists.
8. Output next steps, including the worktree path to enter.

Recovery:

- If the claim already exists and the work is being continued by a new session, use `mesh claim <ID> --resume`.
- If the claim is stale, use `mesh claim <ID> --takeover`.
- Safe takeover should reuse the branch but allocate a new workspace by default.
- Workspace identity should be lane-oriented and reusable across tasks; branch identity should stay task-oriented.
- Prefer explicit recovery over deleting claim files manually.

## /implement

Input: current claim.

Steps:

1. Read work item and claim.
2. Read PRD/context/ADRs.
3. Plan smallest vertical slice.
4. Add or update tests.
5. Implement.
6. Run verification.
7. Record evidence.
8. Stop before opening PR.

## /pr

Input: current claim/branch.

Steps:

1. Validate branch and status.
2. Check uncommitted changes.
3. Run configured verification or summarize missing verification.
4. Generate PR body.
5. Create review packet.
6. If not dry-run, create PR using configured provider.
7. Update work item status.

## /review

Input: PR number or review packet.

Steps:

1. Resolve the review packet to its claim, branch, and claimed workspace.
2. If the current path does not match the claimed workspace, switch to the resolved worktree first.
3. Read review packet.
4. Read task, PRD, context, ADRs.
5. Inspect diff.
6. Check acceptance criteria.
7. Check tests, risks, security, maintainability.
8. Produce structured review.

## /address

Input: review comments.

Steps:

1. Group feedback.
2. Fix blockers.
3. Re-run verification.
4. Update evidence.
5. Reply with changes.

## /merge

Input: PR number.

Steps:

1. Verify approval and checks.
2. Merge according to configured strategy.
3. Mark work done.
4. Archive claim.
5. Sync status/dashboard.

## /handoff

Input: current task/session.

Steps:

1. Reference durable artifacts.
2. Summarize current state.
3. List next action.
4. List risks/open questions.
5. Save handoff.
