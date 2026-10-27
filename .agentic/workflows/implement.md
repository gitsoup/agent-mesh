# /implement

Implement the claimed task safely.

In `ongoing coordination` mode, treat `/implement` as task-oriented by default.
If the user says `implement`, `continue`, `what next`, or similar without
naming a narrower topic, resolve the request against current work items,
claims, reviews, and handoffs before proceeding.

## Steps

1. Run `mesh route <WORK-ID> --json` before reading or writing task files.
   Treat its `worktree` value as the execution root for every file operation,
   shell command, test, and git command. If routing fails, stop without writing.
   Do not assume that invoking `/implement` or running `cd` once changes a tool's
   working directory; use the resolved worktree explicitly on every operation.
2. Read the work item, claim, PRD, context, and ADRs from the routed workspace.
3. Plan the smallest vertical slice.
4. Add or update tests.
5. Implement and run verification in the routed workspace.
6. Inspect `git diff` and `git status` in the claimed workspace.
7. Remove obvious accidental files, debug leftovers, and unrelated edits before
   handing off to `/pr`.
8. Record evidence, including the commands run and their outcomes.
9. Stop only when the task branch is in a deliberate reviewable state, then
   hand off to `/pr` instead of opening a PR directly.
10. Commit coordination state to `mesh/state`.
   - In the coordination worktree, stage and commit the updated work item
     (`.agentic/work/TASK-ID.json`) and claim file (`.agentic/claims/TASK-ID.json`).
   - Commit message: `chore(state): {TASK-ID} → {new status} — {short title}`
   - Do this on every status transition: in_progress → done, or in_progress → review.
   - Do NOT skip this step. It is part of the definition of done.
