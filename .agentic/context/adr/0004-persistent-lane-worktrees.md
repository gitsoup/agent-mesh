# ADR 0004: Persistent Lane Worktrees and Worker Pool Claim Model

## Status

Accepted

## Context

ADR 0002 defined task worktrees as ephemeral — created at claim time and
removed at merge time. Dogfooding revealed that this model is the direct cause
of agent drift: every claim forces the agent to `cd` into a newly-created
directory, and every merge destroys the workspace. Agents repeatedly worked
from the shared root instead of the worktree because the switch was advisory
and easily missed (MESH-18 was created specifically to address this symptom).

Three additional problems emerged from the ephemeral model:

1. `workspace_id` is documented as a "reusable agent lane" identity, but the
   implementation creates a new directory per task — contradicting the concept.
2. Build caches, tool state, and IDE integrations are lost between tasks.
3. The per-task `git worktree add` / `git worktree remove` cycle introduces
   failure modes at both ends of every task (MESH-15 was a worktree-removal
   crash).

Separately, the `mesh review` command was routing reviewers into the
implementer's worktree. This is wrong: reviewers do not need the implementer's
workspace. They need the branch and the PR, both of which are globally
accessible.

Finally, a worker pool model was aligned as the target UX: the user provisions
N lanes once, agents self-assign to free lanes when work is requested, and the
coordination layer tracks lane occupancy so parallel agents don't collide.

## Decision

### 1. Lane worktrees are permanent

A lane worktree is created once per agent lane and persists for the lifetime of
that lane. It is not created per task and not removed at merge.

A lane has two states:
- **idle**: checked out on `wt/{workspace_id}`, tracking `origin/main`
- **active**: checked out on a task branch (`feat/...`, `fix/...`, etc.)

`mesh merge` returns the lane to idle state — checkout `wt/{workspace_id}`,
sync to `origin/main` — instead of removing the worktree.

### 2. Lane names are auto-generated and machine-scoped

Lane names are generated at `mesh init` time as `{user-slug}-{n}`, where
`user-slug` is derived from `git config user.name` (slugified) and `n` is the
slot index (1, 2, ...). Additional lanes can be added with `mesh lane add`.

This scheme is globally unique by construction: two machines with different
users cannot produce the same lane name. The lane name becomes the
`workspace_id` recorded in claims.

The user controls parallelism by specifying how many lanes to provision at
init time (default: 1). Each lane is a permanent worktree directory.

### 3. The worktree path is machine-local; the branch is the global primitive

The `worktree` field on a claim is informational for the lane owner and
meaningless to agents or humans on other machines. Other machines coordinate
via the branch name and task ID.

`mesh review` and `mesh merge` on a non-owning machine operate on the branch,
not the worktree path.

### 4. Reviewers do not need a worktree

Review requires the diff and the task contract — both available from the PR
URL and the work item. The `mesh review` worktree routing guard is removed.
`mesh review` works from the shared root, any lane worktree, or any machine.

The asymmetry is intentional:
- Implementers: must be in their lane (workspace guard on `mesh pr` is correct)
- Reviewers: work from anywhere

### 5. Worker pool claim model

When an agent requests work (`mesh claim` or `/implement`):

1. Read available tasks (ready, no active claim) from coordination state.
2. Read available lanes (idle) from coordination state.
3. Atomically write: claim = `{task_id, workspace_id, branch, machine, timestamp}`.
4. On write conflict (another agent claimed first): retry from step 1.
5. On success: reset lane worktree to main, create task branch, begin work.

The atomic write is a git commit + push to the `mesh/state` branch. A push
conflict is the conflict signal — pull, re-read, retry. No separate lock file
is needed; git's own push rejection handles the race.

This model requires MESH-9 (route coordination through `mesh/state`) and
MESH-10 (write safety for shared coordination state) as prerequisites.

## Consequences

### Benefits

- Agents have a stable, permanent workspace path — no `cd` context switch per
  task.
- Build caches, tool state, and IDE integrations survive between tasks.
- `mesh merge` has no worktree removal step — one class of crash eliminated.
- `workspace_id` now correctly identifies a persistent lane, matching its
  documented intent.
- Lane occupancy is visible in coordination state — `mesh lane list` shows
  free and busy lanes at a glance.
- Reviewers can work from any machine without needing the implementer's path.
- Parallelism is controlled by provisioning lanes at init time, not by
  per-task worktree creation.

### Costs

- `mesh init` now creates worktree directories — slightly heavier first-run.
- Abandoned lanes accumulate if not cleaned up. `mesh doctor` should surface
  idle lanes with no recent activity.
- `mesh merge` must sync the lane to main rather than removing it — slightly
  more complex than `git worktree remove`.
- The `wt/{workspace_id}` base branch convention must be established and kept
  in sync with `origin/main` before each task.

### Supersedes

This ADR supersedes the "task worktree is ephemeral" clause in ADR 0002.
The rest of ADR 0002 (topology naming, coordination worktree permanence,
`mesh/state` branch) remains in effect.

## Follow-up tasks

- MESH-19: `mesh lane` command — provision, list, and auto-name lanes at init
- MESH-20: Update `mesh claim` for persistent lane reuse and auto-selection
- MESH-21: Update `mesh merge` to return lane to idle instead of removing it
- MESH-22: Remove `mesh review` worktree routing; review works from anywhere
