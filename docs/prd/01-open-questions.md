# Open Questions

These should not block v0.1 unless the implementer needs a product decision.

## Naming

Current assumption:

- Product: Agent Mesh
- Package: agent-mesh
- CLI: mesh

Alternates:

- Branchmesh
- Fractal
- Mesh

The implementation should centralize names so renaming is easy.

## Python vs TypeScript

Assumption: Python, because the existing uploaded repo used Python/Typer-style scaffolding.

## Cloud execution

Assumption: defer. Build interfaces and docs only.

## Provider support

Assumption: local provider in v0.1; GitHub and Linear in v0.2.

## TUI depth

Assumption: minimal TUI is acceptable in v0.1. CLI must be complete first.

## Adapter certainty

Some agent runtimes evolve quickly. Adapters should be conservative and generate `AGENTS.md` + canonical workflow pointers when exact config is uncertain.
