# Agent Adapter Requirements

## 1. Goal

The core workflows must be agent-agnostic. Adapters translate canonical skills and instructions into tool-specific formats.

## 2. Canonical source

The canonical source is:

```text
.agentic/workflows/*.md
.agentic/skills/*/SKILL.md
AGENTS.md
```

Do not hand-author divergent versions for each tool. Generate them from templates and shared metadata.
Adapter entrypoints should point agents to `AGENTS.md` first so repo-mode
detection happens before a tool-specific skill or workflow is chosen.

Adapters should be lazy-activated.
The repo-level Mesh contract should exist after `mesh init`, while tool-specific
wrapper files should be installed only when the active runtime actually needs
them. Mesh commands may suggest `mesh adapter install <name>` when they detect a
likely runtime and the corresponding wrapper files are missing.

## 3. Required adapters for v0.1

### generic

Outputs:

```text
AGENTS.md
.agentic/workflows/*.md
```

### claude

Outputs:

```text
.claude/skills/<skill-name>/SKILL.md
CLAUDE.md
```

Each skill may be a concise wrapper that points to `.agentic/workflows/<skill>.md`.

### codex / open Agent Skills

Outputs:

```text
.agents/skills/<skill-name>/SKILL.md
AGENTS.md
```

### cursor

Outputs:

```text
.cursor/rules/agent-mesh.mdc
AGENTS.md
```

The rule file should point Cursor to `AGENTS.md` and `.agentic/workflows/`.

### opencode

Outputs:

```text
AGENTS.md
```

Optionally generate an `opencode.json` only if a minimal, stable config is known. Avoid overfitting.

### pi

Outputs:

```text
.agents/skills/<skill-name>/SKILL.md
AGENTS.md
.pi/prompts/<skill-name>.md optional
```

### windsurf

Outputs:

```text
AGENTS.md
.windsurfrules optional
```

## 4. Adapter interface

Implement something like:

```python
class Adapter(Protocol):
    name: str
    description: str

    def detect(self, repo: Path) -> DetectionResult: ...
    def install(self, repo: Path, skills: SkillCatalog, force: bool = False) -> AdapterInstallResult: ...
    def render_project_instructions(self, context: RenderContext) -> dict[Path, str]: ...
    def render_skills(self, context: RenderContext) -> dict[Path, str]: ...
```

Detection should remain best-effort and safe. Missing adapter wrappers should
produce actionable hints, not block core Mesh coordination commands by default.

## 5. Skill frontmatter

Use a simple portable format:

```yaml
---
name: claim
description: Claim a ready work item using Agent Mesh coordination state, create or verify the branch/worktree, and prepare implementation context.
---
```

## 6. Aliases

Support friendly aliases in metadata:

```yaml
aliases:
  - create-pr
  - open-pr
```

Canonical command names should remain short.
