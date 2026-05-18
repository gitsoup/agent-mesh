# /ongoing

Inspect and continue work in a repo that already uses Agent Mesh.

This workflow applies whenever `.agentic/` already exists with active or
historical coordination state. Route here from the startup inspection in
`AGENTS.md` when the repo is in `ongoing coordination` mode.

## Startup inspection sequence

When `.agentic/` already exists, inspect in this order before proposing or
starting any work:

1. `.agentic/project.json` — project key, coordination branch, worktree policy.
2. `.agentic/claims/` — active and stale claims; identify who owns what.
3. `.agentic/reviews/` — open review packets awaiting feedback or merge.
4. `.agentic/handoffs/` — continuation notes from previous sessions.
5. `.agentic/work/` — task statuses; identify `ready`, `in_progress`, and `done` items.

Do not propose `/setup` or overwrite existing state unless it is explicitly
incomplete and the user requests adoption repair.

## Claim inspection rules

A claim is **active** when its `last_seen` is within `claim_stale_after_minutes`
(default: 120 minutes) of the current time.

A claim is **stale** when its `last_seen` has exceeded `claim_stale_after_minutes`.

A claim is **orphaned** when its referenced work item does not exist in
`.agentic/work/`.

Resolution:

- Active claim → do not claim the same work item; resume or offer to take over
  with explicit user confirmation.
- Stale claim → use `mesh claim <WORK-ID> --takeover`; keep the existing branch,
  allocate a new `workspace_id`.
- Orphaned claim → surface to the user via `mesh doctor`; do not delete without
  explicit confirmation.

## Priority order when choosing work

When the user does not name a specific task, select the best ready unclaimed
task using this priority:

1. Tasks with no unresolved dependencies that directly unblock other ready tasks.
2. Tasks with `execution: afk_safe` when the agent will run unattended.
3. Tasks with the lowest risk rating.
4. Tasks created earliest.

## Open review handling

When `.agentic/reviews/` contains a packet with `status: pending_review`:

1. Resolve the workspace from the claim linked in the review packet.
2. If you are not already in that workspace, report the path and ask the user to
   switch before continuing.
3. Do not start new implementation work while a review for the same task is
   pending.

## Continuation and handoff expectations

When `.agentic/handoffs/` contains a file:

1. Read the handoff before inspecting tasks or claims.
2. The handoff takes precedence over coordination state for identifying the
   immediate next action.
3. Acknowledge the handoff explicitly to the user before proceeding.
4. Archive the handoff file after confirming the continuation context has been
   consumed.

When ending a session, create a handoff at `.agentic/handoffs/<WORK-ID>.md`
that includes: the work item ID, claim file path, branch, worktree path, last
completed step, next intended action, and any open risks or blockers.

## Steps

1. Inspect `.agentic/project.json`, claims, reviews, handoffs, and work items.
2. Identify active claims, stale claims, open reviews, and pending handoffs.
3. Report a compact summary of current coordination state.
4. If a handoff exists, surface the continuation note first.
5. If an open review exists, resolve the workspace and prompt the user.
6. Otherwise, recommend the best ready task or resume in-progress work.
7. Proceed with `/claim`, `/implement`, `/pr`, `/review`, `/address`, `/merge`,
   or `/handoff` as appropriate.
