# /review

Review a PR or review packet against the task contract.

## Steps

1. Resolve the review packet to its claim, branch, PR URL, and acceptance criteria.
2. Read the review packet, task, PRD, context, and ADRs from any checkout — no
   worktree switch required (ADR 0004 §4: reviewers do not need the implementer's
   worktree; use the PR URL and branch for inspection).
3. Inspect the diff and acceptance criteria.
4. Produce structured review findings.
