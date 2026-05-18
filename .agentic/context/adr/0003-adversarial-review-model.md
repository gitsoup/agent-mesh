# ADR 0003: Adversarial Review Model

## Status

Accepted

## Context

The existing `/review` skill is confirmatory: it verifies that the
implementation meets the acceptance criteria stated in the task. This is
sufficient for low-risk work but insufficient for tasks that touch
security-sensitive surfaces or carry high implementation risk.

A confirmatory reviewer shares the same mental model as the implementer —
both read the same task description and acceptance criteria. An adversarial
reviewer operates from a different premise: assume the implementation is
wrong and find the proof. These two roles catch different failure classes
and are complementary, not alternatives.

Three problems with relying solely on task labels to trigger adversarial review:

1. **Risk field is self-assessed.** If the task creator underestimates
   risk, adversarial review never triggers. Risk level alone is an
   unreliable trigger.
2. **Risk reflects complexity, not blast radius.** A 50-line feature that
   calls `git push --delete` and `shutil.move` can be labeled `risk: low`
   because its implementation scope is small, yet carry high destructive
   potential. These are independent dimensions. MESH-12 (`risk: low`)
   demonstrated this: an adversarial pass found 3 ship-blockers including
   silent deletion of unmerged code that a confirmatory review would have
   passed.
3. **Same model, same blind spots.** An adversarial reviewer sharing
   weights with the implementer has identical blind spots. The closest
   approximation to true independence is a fresh session with no shared
   implementation context.

## Decision

### Task kind taxonomy

The `kind` field on work items is extended to include `security` as a
valid value alongside `bug`, `feature`, and `refactor`. Security surface
is independent of risk level and requires its own trigger.

### Review mode selection

| Task profile | Review passes |
|---|---|
| `kind: security` (any risk) | Adversarial only |
| `risk: high` (any kind except security) | Confirmatory, then adversarial |
| All other tasks | Confirmatory only |

The reviewer agent **must escalate to adversarial** after reading the
diff when it detects any of the following, regardless of task profile:

- Destructive git operations (`push --delete`, `branch -D`, `worktree remove`)
- File deletion or moves (`shutil.move`, `unlink`, `rmdir`, `rm -rf`)
- State mutations without a rollback or recovery path
- Subprocess calls that modify external state
- Error handling that silently swallows failures or maps distinct errors
  to the same output

Escalation is a **must**, not a judgment call, when these patterns are
present in the diff.

### Adversarial review constraints

- The adversarial session receives only the diff and the task definition.
  It must not receive the implementer's reasoning, evidence, or any
  context from the implementation session.
- Adversarial output is a bounded **attack report**: what attack surfaces
  were identified, what was attempted, what survived, what failed.
- Confirmatory pass always runs before adversarial when both are required.
- The review packet records which mode(s) were applied.

### What adversarial review checks

- Inputs or states that violate assumptions the implementation makes
- Missing error paths and unhandled boundary conditions
- Acceptance criteria that are too weak to catch real failures
- What was not changed: missing guards, unhandled callers, silent
  assumptions in surrounding code
- Whether the evidence provided by the implementer actually proves the
  claims made

## Consequences

### Benefits

- High-risk and security-sensitive work gets independently scrutinized
  rather than just confirmed
- Weak acceptance criteria are surfaced at review time rather than at
  incident time
- The two-pass model keeps confirmatory and adversarial findings separate
  and addressable independently

### Costs

- `risk: high` and diff-triggered tasks require two review passes,
  increasing review cost and latency
- Fresh-session constraint means the adversarial reviewer must re-derive
  context from the diff — potentially slower and noisier than a
  context-sharing approach
- Perverse incentive exists to mark tasks `risk: medium` to avoid the
  dual-pass overhead; mitigated by mandatory reviewer-initiated escalation
  on destructive diff patterns — the reviewer cannot be opted out of
  escalation by a low risk label

### Follow-up implications

- `MESH-14` implements the adversarial review mode in the review skill
  and extends the work item schema to accept `kind: security`.
