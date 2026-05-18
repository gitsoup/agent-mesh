"""Canonical skill metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class SkillDefinition:
    name: str
    summary: str


SKILLS: List[SkillDefinition] = [
    SkillDefinition("setup", "Configure a repository for Agent Mesh."),
    SkillDefinition("align", "Align a plan with repo context and decisions."),
    SkillDefinition("to-prd", "Convert aligned context into a concise PRD."),
    SkillDefinition("to-tasks", "Turn a PRD into provider-independent work items."),
    SkillDefinition("triage", "Classify raw work and determine readiness."),
    SkillDefinition("claim", "Claim a ready work item and prepare implementation context."),
    SkillDefinition("implement", "Implement the claimed task safely."),
    SkillDefinition("diagnose", "Debug using a disciplined diagnosis loop."),
    SkillDefinition("prototype", "Build a throwaway prototype to answer a design question."),
    SkillDefinition("pr", "Prepare a pull request and review packet."),
    SkillDefinition("review", "Review a PR or review packet against the task contract."),
    SkillDefinition("address", "Address review feedback and refresh evidence."),
    SkillDefinition("merge", "Merge approved work and update repo coordination state."),
    SkillDefinition("refactor", "Improve structure while preserving behavior."),
    SkillDefinition("handoff", "Create compact continuation context for another session."),
    SkillDefinition("sync", "Sync repo, claims, and dashboard state."),
    SkillDefinition("ongoing", "Inspect and continue work in a repo that already uses Agent Mesh."),
]
