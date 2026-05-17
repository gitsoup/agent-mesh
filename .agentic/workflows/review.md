# /review

Review a PR or review packet against the task contract.

## Steps

1. Resolve the review packet to its claim, branch, and claimed workspace.
2. If the current path does not match the claimed workspace, switch to the
   resolved worktree first.
3. Read the review packet, task, PRD, context, and ADRs.
4. Inspect the diff and acceptance criteria.
5. Produce structured review findings.
