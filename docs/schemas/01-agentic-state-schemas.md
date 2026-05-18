# Agentic State Schemas

Use Pydantic models in implementation and JSON files in target repos.

## 1. Project config: `.agentic/project.json`

```json
{
  "schema_version": "0.1",
  "project_name": "example-project",
  "project_key": "APP",
  "default_branch": "main",
  "planning": {
    "provider": "local",
    "external_project": null
  },
  "coordination": {
    "strategy": "git_files",
    "branch": "mesh/state",
    "work_dir": ".agentic/work",
    "claims_dir": ".agentic/claims",
    "reviews_dir": ".agentic/reviews",
    "handoffs_dir": ".agentic/handoffs",
    "worktree_policy": "required",
    "worktree_root": null,
    "coordination_worktree": null,
    "claim_stale_after_minutes": 120
  },
  "adapters": ["generic", "codex", "claude"],
  "runner": {
    "default": "local_manual"
  },
  "dashboard": {
    "enabled": true,
    "output_dir": ".agentic/dashboard"
  }
}
```

## 2. Work item: `.agentic/work/APP-1.json`

```json
{
  "schema_version": "0.1",
  "id": "APP-1",
  "title": "Implement auth endpoint",
  "description": "Add an endpoint that lets users request an email sign-in link.",
  "kind": "feature",
  "status": "ready",
  "execution": "afk_safe",
  "module": "api",
  "planning": {
    "provider": "local",
    "url": null,
    "external_id": null
  },
  "prd": null,
  "acceptance_criteria": [
    "Endpoint validates email input",
    "Endpoint returns success response without leaking account existence",
    "Tests cover valid and invalid inputs"
  ],
  "dependencies": [],
  "risk": "medium",
  "created_at": "2026-05-17T00:00:00Z",
  "updated_at": "2026-05-17T00:00:00Z"
}
```

## 3. Claim: `.agentic/claims/APP-1.json`

```json
{
  "schema_version": "0.1",
  "work_id": "APP-1",
  "status": "in_progress",
  "claimed_by": "agent:codex:karthick-laptop",
  "agent_runtime": "codex",
  "role": "implementer",
  "machine": "karthick-laptop",
  "workspace_id": "codex-karthick-laptop",
  "worktree": "../example-project-codex",
  "branch": "feat/APP-1-auth-endpoint",
  "claimed_at": "2026-05-17T00:00:00Z",
  "last_seen": "2026-05-17T00:00:00Z",
  "evidence": [],
  "events": [
    {
      "action": "claimed",
      "at": "2026-05-17T00:00:00Z",
      "by": "agent:codex:karthick-laptop",
      "note": null
    }
  ]
}
```

## 4. Evidence item

```json
{
  "kind": "test",
  "command": "pytest tests/api/test_auth.py",
  "result": "passed",
  "summary": "6 tests passed",
  "created_at": "2026-05-17T00:00:00Z"
}
```

## 5. Review packet: `.agentic/reviews/PR-12.json`

```json
{
  "schema_version": "0.1",
  "type": "review_request",
  "id": "PR-12",
  "work_id": "APP-1",
  "pr": {
    "number": 12,
    "url": "https://github.com/org/repo/pull/12",
    "branch": "feat/APP-1-auth-endpoint",
    "base": "main"
  },
  "author": {
    "agent_runtime": "codex",
    "role": "implementer"
  },
  "requested_role": "reviewer",
  "context": {
    "work_item": ".agentic/work/APP-1.json",
    "claim": ".agentic/claims/APP-1.json",
    "prd": null,
    "context_files": [".agentic/context/CONTEXT.md"]
  },
  "evidence": [],
  "status": "pending_review",
  "created_at": "2026-05-17T00:00:00Z"
}
```

## 6. Status lifecycle

Work item statuses:

```text
needs_triage -> needs_info -> ready -> in_progress -> pr_open -> done
                         \-> blocked
                         \-> human_only
                         \-> wontfix
```

Claim statuses:

```text
in_progress -> stale -> completed -> archived
```

Notes:

- `workspace_id` identifies the reusable agent lane or workspace.
- Safe takeover should normally keep the same branch and assign a new `workspace_id` and worktree.
- Active claims live under `.agentic/claims/`.
- Completed or superseded claims should move to `.agentic/claims/archive/` so
  active status only reflects current ownership.
- The shared root stays on `main`; live coordination state is intended to move
  to the `mesh/state` branch in a dedicated coordination worktree.
- `coordination_worktree` may be set explicitly. If it is unset, the default
  expected path is `<worktree_root>/<repo>-mesh-state` when `worktree_root` is
  configured, otherwise a sibling checkout named `<repo>-mesh-state`.
- A missing coordination worktree is a recoverable bootstrap state. A present
  coordination worktree must be a git worktree checked out on `mesh/state`.

Review statuses:

```text
pending_review -> in_review -> changes_requested -> approved -> resolved
```
