# Agent Mesh

Agent Mesh is a git-native coordination toolkit for running multiple AI coding
agents and humans safely in one repository.

The repository is still in early implementation. The current focus is the v0.1
local-first scaffold described in [AGENTS.md](./AGENTS.md) and the planning docs
under [docs/](./docs).

## Current status

The project now includes:

- a Python package scaffold
- a `mesh` CLI entrypoint
- initial Pydantic config/state models
- baseline tests for installability and config/state validation

## Development

Create a virtualenv, install the package in editable mode, and run tests:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
pytest
```
