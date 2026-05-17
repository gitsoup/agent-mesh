# /claim

Claim a ready work item and prepare implementation context.

## Steps

1. Confirm the repo is in `ongoing coordination` mode, or finish setup/adoption
   work first.
2. Inspect current status, claims, reviews, and handoffs.
3. Validate the work item.
4. Check for an existing claim.
5. Create or verify a dedicated worktree and task branch unless worktree
   isolation is explicitly disabled by project config.
6. Create the claim file.
7. Output the next implementation steps, including the worktree path to enter.

## Recovery

- If a claim already exists and you are continuing the same task, use
  `mesh claim <WORK-ID> --resume`.
- If a claim is stale, use `mesh claim <WORK-ID> --takeover`.
- Safe takeover should keep the existing branch but allocate a new workspace by
  default.
- `workspace_id` should represent a reusable lane or workspace, not the task
  itself.
- Do not delete claim files as a normal recovery path.
