"""Pydantic state models for repo-local coordination data."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ProviderRef(BaseModel):
    provider: str
    url: Optional[str] = None
    external_id: Optional[str] = None


class Evidence(BaseModel):
    kind: str
    command: str
    result: str
    summary: str
    created_at: str


class ClaimEvent(BaseModel):
    action: str
    at: str
    by: str
    note: Optional[str] = None


class WorkItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "0.1"
    id: str
    title: str
    description: str
    kind: str
    status: str
    execution: str
    module: Optional[str] = None
    planning: ProviderRef
    prd: Optional[str] = None
    acceptance_criteria: List[str] = Field(default_factory=list)
    dependencies: List[str] = Field(default_factory=list)
    risk: str
    created_at: str
    updated_at: str


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "0.1"
    work_id: str
    status: str
    claimed_by: str
    agent_runtime: str
    role: str
    machine: str
    workspace_id: Optional[str] = None
    worktree: Optional[str] = None
    branch: str
    claimed_at: str
    last_seen: str
    evidence: List[Evidence] = Field(default_factory=list)
    events: List[ClaimEvent] = Field(default_factory=list)


class PullRequestRef(BaseModel):
    number: Optional[int] = None
    url: Optional[str] = None
    branch: str
    base: str


class ReviewAuthor(BaseModel):
    agent_runtime: str
    role: str


class ReviewContext(BaseModel):
    work_item: str
    claim: str
    prd: Optional[str] = None
    context_files: List[str] = Field(default_factory=list)


class ReviewPacket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "0.1"
    type: str
    id: str
    work_id: str
    pr: PullRequestRef
    author: ReviewAuthor
    requested_role: str
    context: ReviewContext
    evidence: List[Evidence] = Field(default_factory=list)
    status: str
    created_at: str
