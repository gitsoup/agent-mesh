# /claim

Claim a ready work item and prepare implementation context.

## Steps

1. Confirm the repo is in `ongoing coordination` mode, or finish setup/adoption
   work first.
2. Inspect current status, claims, reviews, and handoffs.
3. If the user request is ambiguous, such as `implement`, `continue`, `what
   next`, `work on this`, or `pick the next task`, resolve it against Agent
   Mesh coordination state first instead of the latest conversational topic.
4. When multiple ready tasks exist and the user did not name one, recommend the
   best unclaimed task that most directly unlocks dependent work.
5. Validate the work item.
6. Check for an existing claim.
7. Create or verify a dedicated worktree and task branch unless worktree
   isolation is explicitly disabled by project config.
8. Create the claim file.
9. Output the next implementation steps, including the worktree path to enter.

## Recovery

- If a claim already exists and you are continuing the same task, use
  `mesh claim <WORK-ID> --resume`.
- If a claim is stale, use `mesh claim <WORK-ID> --takeover`.
- Safe takeover should keep the existing branch but allocate a new workspace by
  default.
- `workspace_id` should represent a reusable lane or workspace, not the task
  itself.
- Do not delete claim files as a normal recovery path.
