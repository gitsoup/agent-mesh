# /pr

Prepare a pull request and review packet.

## Steps

1. Validate the branch and claim status.
2. Confirm the current checkout matches the claimed workspace.
3. Check `git status` and `git diff` for unintended or accidental changes.
4. Refuse PR creation until verification evidence exists and the workspace is in
   a deliberate reviewable state.
5. Check verification status and summarize the recorded evidence.
6. Generate the PR body.
7. Create a review packet.
8. Open the PR only when not in dry-run mode.
