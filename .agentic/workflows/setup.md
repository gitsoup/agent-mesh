# /setup

Configure a repository for Agent Mesh.

## Steps

1. Detect repo mode before making changes.
2. Read `AGENTS.md`, `CONTEXT.md`, and `CONTEXT-MAP.md`.
3. If `.agentic/` already exists, inspect current work, claims, reviews, and
   handoffs before doing anything else.
4. If the repo is `greenfield`, scaffold Agent Mesh state and route into
   `/align`, `/to-prd`, and `/to-tasks`.
5. If the repo is `brownfield adoption`, derive durable context from existing
   code, docs, and conventions before normalizing them into `.agentic/` state.
6. Install or refresh the configured adapters only after deciding that setup or
   adoption work is actually needed.
7. Do not overwrite existing coordination state without explicit confirmation.
