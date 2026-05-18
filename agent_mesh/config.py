"""Configuration models and loaders."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

PROJECT_FILE = Path(".agentic/project.json")


class PlanningConfig(BaseModel):
    provider: str = "local"
    external_project: Optional[str] = None


class CoordinationConfig(BaseModel):
    strategy: str = "git_files"
    branch: str = "mesh/state"
    work_dir: str = ".agentic/work"
    claims_dir: str = ".agentic/claims"
    reviews_dir: str = ".agentic/reviews"
    handoffs_dir: str = ".agentic/handoffs"
    worktree_policy: str = "required"
    worktree_root: Optional[str] = None
    coordination_worktree: Optional[str] = None
    claim_stale_after_minutes: int = 120


class RunnerConfig(BaseModel):
    default: str = "local_manual"


class DashboardConfig(BaseModel):
    enabled: bool = True
    output_dir: str = ".agentic/dashboard"


class ProjectConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "0.1"
    project_name: str
    project_key: str
    default_branch: str = "main"
    planning: PlanningConfig = Field(default_factory=PlanningConfig)
    coordination: CoordinationConfig = Field(default_factory=CoordinationConfig)
    adapters: list[str] = Field(default_factory=lambda: ["generic"])
    runner: RunnerConfig = Field(default_factory=RunnerConfig)
    dashboard: DashboardConfig = Field(default_factory=DashboardConfig)

    def to_json(self) -> str:
        return self.model_dump_json(indent=2) + "\n"


def load_project_config(repo_root: Path) -> ProjectConfig:
    path = repo_root / PROJECT_FILE
    data = json.loads(path.read_text(encoding="utf-8"))
    return ProjectConfig.model_validate(data)
