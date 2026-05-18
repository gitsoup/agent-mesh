# Skill Catalog

Agent Mesh exposes short, developer-friendly skills. The skill names should be memorable and intuitive.

Canonical public names:

```text
/setup
/align
/to-prd
/to-tasks
/triage
/claim
/implement
/diagnose
/prototype
/pr
/review
/address
/merge
/refactor
/handoff
/sync
```

## 1. /setup

Configure the target repo for Agent Mesh.

Responsibilities:

- Detect repo mode: `greenfield`, `brownfield adoption`, or `ongoing coordination`.
- Detect repo type and languages where possible.
- Ask for planning provider: local, GitHub, Linear, Jira future, none.
- Ask for agent adapters: generic, Claude, Codex, Cursor, OpenCode, Pi, Windsurf.
- Ask whether worktrees are used.
- Ask whether dashboard should be generated.
- Create `.agentic/` state and context files.
- Generate `AGENTS.md` and adapter files.
- Route greenfield repos into `/align`, `/to-prd`, and `/to-tasks`.
- Route brownfield repos into context derivation and normalization before task creation.
- Refuse to overwrite usable Mesh state without explicit confirmation.

## 2. /align

Align an idea, plan, feature, bug, or architecture proposal with repo context.

This is the improved version of a repo-aware challenge skill.

Responsibilities:

- Read `CONTEXT.md`, `CONTEXT-MAP.md`, and relevant ADRs.
- Detect unclear, overloaded, or conflicting terms.
- Challenge assumptions.
- Ask one decision-shaping question at a time.
- Recommend a default answer with reasoning.
- Update `CONTEXT.md` when shared vocabulary is clarified.
- Create ADRs only for decisions that are hard to reverse, surprising without context, or trade-off-heavy.
- Produce an alignment summary suitable for `/to-prd`.

Do not let `CONTEXT.md` become a spec or scratchpad. It is for domain language and durable concepts.

## 3. /to-prd

Convert aligned context into a concise PRD or implementation brief.

Responsibilities:

- Use the current conversation, alignment summary, and existing context.
- Do not re-interview the user unless critical information is missing.
- Produce a PRD with problem, goals, non-goals, user flows, acceptance criteria, risks, and rollout notes.
- Store generated PRDs under `.agentic/prds/` or `docs/prds/` depending on config.

## 4. /to-tasks

Convert a PRD/spec into provider-independent work items.

Responsibilities:

- Break work into vertical, independently reviewable tasks.
- Mark each task as AFK-safe, HITL, blocked, or needs-info.
- Add dependencies and acceptance criteria.
- Create local `.agentic/work/*.json` items.
- Optionally export to GitHub Issues or Linear in future versions.

## 5. /triage

Classify raw work.

Statuses:

- `needs_triage`
- `needs_info`
- `ready`
- `blocked`
- `human_only`
- `wontfix`

Responsibilities:

- Decide whether work is ready for agents.
- Mark missing information.
- Avoid claiming vague tasks.
- Update local work item files.

## 6. /claim

Claim a ready work item.

Responsibilities:

- Confirm the repo is already in ongoing-coordination mode before claiming work.
- Inspect current status, claims, reviews, and handoffs first.
- Resolve ambiguous execution requests such as `implement`, `continue`, `what next`, or `work on this` against coordination state first unless the user explicitly names a narrower scope.
- When multiple ready tasks exist and no task is named, recommend the best unclaimed task that most directly unlocks dependent work.
- Validate work item exists and is `ready`.
- Check existing claims.
- Create or verify a dedicated worktree and task branch unless explicitly disabled.
- Create a claim file.
- Resume an existing claim when the same task is being continued by a new session.
- Take over a stale claim explicitly instead of deleting it.
- Commit and push claim if git remote is configured.
- Update status to `in_progress`.

## 7. /implement

Implement the claimed task safely.

Responsibilities:

- Treat `/implement` as task-oriented by default in ongoing-coordination mode, not as a continuation of the latest conversational subtopic.
- Read task, claim, PRD, context, and relevant ADRs.
- Use tests and feedback loops.
- Prefer vertical slices.
- Inspect `git diff` and `git status` before handing off.
- Remove obvious accidental files, debug leftovers, and unrelated edits from the claimed workspace.
- Update evidence as tests are run.
- Leave the branch in a deliberate reviewable state before stopping.
- Do not open PR; that belongs to `/pr`.

## 8. /diagnose

Debug using a disciplined diagnosis loop.

Responsibilities:

- Reproduce.
- Minimize.
- Form hypotheses.
- Instrument.
- Fix.
- Add regression tests.
- Clean up debug instrumentation.

Use `/diagnose` instead of vague `/debug` as the canonical name.

## 9. /prototype

Build throwaway code to answer a design, integration, or UX question.

Responsibilities:

- State the question being answered.
- Keep prototype isolated.
- Avoid accidental productionization.
- Summarize findings and recommend whether to discard, refine, or turn into tasks.

## 10. /pr

Create or prepare a pull request for the current claimed task.

Responsibilities:

- Validate claim and branch.
- Confirm the current checkout matches the claimed workspace.
- Check `git status` and `git diff` for unintended or accidental changes.
- Refuse PR creation until the workspace is deliberate and reviewable.
- Confirm tests/evidence.
- Generate PR title and body.
- Include task link, acceptance criteria, implementation summary, evidence, risks, and review checklist.
- Update status to `pr_open` when real PR is created.
- Generate a review packet.
- Optionally delegate review in future versions.

Aliases: `/create-pr`, `/open-pr`.

## 11. /review

Review a PR or review packet.

Responsibilities:

- Resolve the review packet to the claimed workspace before reviewing.
- Warn or redirect when the current checkout does not match the claimed worktree.
- Read PRD/task/claim/context/ADRs.
- Inspect changed files.
- Compare implementation to acceptance criteria.
- Run or request tests where possible.
- Leave structured review findings.
- Distinguish blockers, suggestions, questions, and praise.

## 12. /address

Address review feedback.

Responsibilities:

- Read review comments.
- Group findings.
- Fix blockers first.
- Update tests/evidence.
- Reply with what changed and what was intentionally not changed.

## 13. /merge

Merge completed work and update coordination state.

Responsibilities:

- Verify PR approval and CI.
- Merge using configured strategy.
- Mark task `done`.
- Remove or archive claim.
- Sync worktrees.
- Update dashboard state.

## 14. /refactor

Improve code structure while preserving behavior.

Responsibilities:

- Identify module boundaries and test seams.
- Avoid speculative rewrites.
- Preserve behavior with tests.
- Update context/ADRs if terminology or architecture changes.
- Produce small reviewable PRs.

## 15. /handoff

Create compact continuation context for another agent/session/human.

Responsibilities:

- Reference durable artifacts instead of copying everything.
- Include current state, next action, risks, files touched, commands run, and open questions.
- Store under `.agentic/handoffs/`.

## 16. /sync

Sync repo, worktrees, claims, and dashboard state.

Responsibilities:

- Fetch remotes.
- Detect stale branches and claims.
- Summarize active work.
- Rebuild dashboard.
- Never delete branches without explicit confirmation.
