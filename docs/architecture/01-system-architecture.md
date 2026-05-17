# System Architecture

## 1. Architecture summary

Agent Mesh is a local-first repo protocol plus CLI/TUI.

It separates the system into four layers:

```text
Planning layer      local / GitHub Issues / Linear / Jira / markdown PRDs
Coordination layer  .agentic files + git branches + claims + PRs
Execution layer     Claude Code / Codex / Cursor / OpenCode / Pi / humans / runners
Visibility layer    CLI status / TUI / static dashboard / PR comments
```

## 2. Design principles

- The repo is the shared source of truth.
- All state is human-readable.
- All state can be versioned in git.
- Coordination should work without a cloud service.
- Agent runtimes should be adapters, not core dependencies.
- Planning providers should import/export work, not own claim state.
- Runners execute work; transports deliver messages.
- Cloudflare can be a control plane later, not the first execution environment.

## 3. Repository structure generated into target projects

```text
.agentic/
  project.json
  config.toml
  context/
    CONTEXT.md
    CONTEXT-MAP.md
    adr/
      README.md
  work/
    README.md
  claims/
    README.md
  reviews/
    README.md
  handoffs/
    README.md
  workflows/
    align.md
    to-prd.md
    to-tasks.md
    triage.md
    claim.md
    implement.md
    diagnose.md
    prototype.md
    pr.md
    review.md
    address.md
    merge.md
    refactor.md
    handoff.md
    sync.md
  skills/
    align/SKILL.md
    to-prd/SKILL.md
    to-tasks/SKILL.md
    triage/SKILL.md
    claim/SKILL.md
    implement/SKILL.md
    diagnose/SKILL.md
    prototype/SKILL.md
    pr/SKILL.md
    review/SKILL.md
    address/SKILL.md
    merge/SKILL.md
    refactor/SKILL.md
    handoff/SKILL.md
    sync/SKILL.md
  adapters/
    README.md
  dashboard/
    index.html
AGENTS.md
.github/
  workflows/
    agent-mesh-status.yml
    agent-mesh-review.yml optional future
```

## 4. Internal package architecture

```text
agent_mesh/
  cli.py                 Typer command entrypoint
  tui.py                 Textual/Rich TUI entrypoint
  config.py              project and user config loading
  scaffold.py            target repo scaffolding
  templates/             packaged templates
  state/
    models.py            Pydantic models for project, work, claims, reviews
    storage.py           read/write state safely
    validate.py          schema validation
  skills/
    catalog.py           canonical skill metadata
    render.py            render SKILL.md and workflow docs
  adapters/
    base.py
    generic.py           AGENTS.md + workflows only
    claude.py            .claude/skills
    codex.py             .agents/skills
    cursor.py            .cursor/rules
    opencode.py          AGENTS.md/OpenCode compatibility
    pi.py                .pi and/or .agents/skills
    windsurf.py          AGENTS.md/.windsurfrules
  providers/
    base.py
    local.py
    github.py            v0.2
    linear.py            v0.2
    jira.py              future
  runners/
    base.py
    local.py             v0.2 watch runner
    github_actions.py    v0.2 template generator
    cloudflare.py        future control plane only
    aweb.py              future transport/runner adapter
  transports/
    base.py
    git.py
    github.py            v0.2 labels/comments
    local_inbox.py       v0.2
    aweb.py              future
  dashboard/
    aggregate.py
    render.py
  utils/
    git.py
    github_cli.py
    paths.py
    slug.py
```

## 5. State ownership model

Planning providers own requested work metadata. Agent Mesh owns coordination metadata.

A provider may create or update work items, but claims are always repo-local and git-visible.

```text
provider issue  -> imported work item
work item       -> claim
claim           -> branch/worktree
branch          -> PR
PR              -> review packet
review packet   -> review comments / follow-up work
```

## 6. Compute model

Agent Mesh must not assume cloud compute.

Supported execution modes:

1. Local manual mode: user starts each agent session.
2. Local watcher mode: `mesh watch` starts agents when inbox items appear.
3. CI runner mode: GitHub Actions runs review/test jobs.
4. Cloud runner mode: future VM/container/Codespaces/aweb runner.

Cloudflare Workers/Queues/Workflows are suitable for future control-plane features such as webhooks, queues, durable orchestration, presence, and dashboard APIs. They should not be the default place to run full coding agents because coding agents usually need file-system-heavy clones, dependency installs, test processes, and long-running subprocesses.

## 7. Adapter model

Canonical workflows and skills are stored in `.agentic/workflows` and `.agentic/skills`.

Adapters generate tool-specific files.

Examples:

```text
Claude Code     .claude/skills/*/SKILL.md
Codex           .agents/skills/*/SKILL.md and AGENTS.md
Cursor          .cursor/rules/agent-mesh.mdc and AGENTS.md
OpenCode        AGENTS.md and compatibility notes
Pi              .agents/skills/*/SKILL.md and optional .pi prompts
Windsurf        AGENTS.md and optional .windsurfrules
Generic         AGENTS.md + .agentic/workflows only
```

## 8. Safety model

- Never auto-merge in v0.1.
- Never run destructive git commands without explicit confirmation.
- Prefer dry-run support for PR, merge, provider sync, and dashboard publish commands.
- Keep cloud execution disabled unless explicitly configured.
- Validate all JSON/TOML state before writing.
- Use atomic writes where possible.
- Avoid writing over existing user files unless `--force` is supplied.
