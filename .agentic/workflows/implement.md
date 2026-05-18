# /implement

Implement the claimed task safely.

In `ongoing coordination` mode, treat `/implement` as task-oriented by default.
If the user says `implement`, `continue`, `what next`, or similar without
naming a narrower topic, resolve the request against current work items,
claims, reviews, and handoffs before proceeding.

## Steps

1. Read the work item, claim, PRD, context, and ADRs.
2. Plan the smallest vertical slice.
3. Add or update tests.
4. Implement and run verification.
5. Inspect `git diff` and `git status` in the claimed workspace.
6. Remove obvious accidental files, debug leftovers, and unrelated edits before
   handing off to `/pr`.
7. Record evidence, including the commands run and their outcomes.
8. Stop only when the task branch is in a deliberate reviewable state, then
   hand off to `/pr` instead of opening a PR directly.
