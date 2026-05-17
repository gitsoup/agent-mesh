# Canonical Workflow Specifications

These workflows should be rendered into `.agentic/workflows/*.md` during `mesh init`.

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

1. Validate work item.
2. Check existing claim.
3. Create claim file.
4. Create branch name.
5. Create/check worktree if configured.
6. Commit/push claim if remote exists.
7. Output next steps.

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

1. Read review packet.
2. Read task, PRD, context, ADRs.
3. Inspect diff.
4. Check acceptance criteria.
5. Check tests, risks, security, maintainability.
6. Produce structured review.

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
