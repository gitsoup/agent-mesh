"""Storage helpers for Agent Mesh state."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Iterable, List, Type, TypeVar

from pydantic import BaseModel

from agent_mesh.state.models import Claim, ReviewPacket, WorkItem

T = TypeVar("T", bound=BaseModel)


def resolve_repo_root(start: Path) -> Path:
    current = start.resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            common_dir = subprocess.run(
                ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                cwd=candidate,
                check=False,
                capture_output=True,
                text=True,
            )
            if common_dir.returncode == 0:
                common_dir_path = Path(common_dir.stdout.strip())
                if common_dir_path.name == ".git":
                    return common_dir_path.parent
            return candidate
    raise FileNotFoundError("Could not find a git repository root from the given path.")


def resolve_coordination_root(repo_root: Path) -> Path:
    """Return the path whose .agentic/ subtree holds live coordination state.

    Uses the ADR 0002 sibling naming convention: <repo>-mesh-state next to the
    shared root. Falls back to repo_root when the coordination worktree has not
    been set up yet (degraded / bootstrap mode).
    """
    candidate = repo_root.parent / "{0}-mesh-state".format(repo_root.name)
    if candidate.exists() and (candidate / ".agentic").exists():
        return candidate
    return repo_root


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
        temp_path = Path(handle.name)
    temp_path.replace(path)


def save_model_json(path: Path, model: BaseModel) -> None:
    atomic_write_json(path, model.model_dump())


def load_model(path: Path, model_type: Type[T]) -> T:
    return model_type.model_validate(load_json(path))


def iter_json_files(path: Path) -> Iterable[Path]:
    if not path.exists():
        return []
    return sorted(item for item in path.iterdir() if item.suffix == ".json")


def list_work_items(repo_root: Path) -> List[WorkItem]:
    return [load_model(path, WorkItem) for path in iter_json_files(repo_root / ".agentic/work")]


def list_claims(repo_root: Path) -> List[Claim]:
    return [load_model(path, Claim) for path in iter_json_files(repo_root / ".agentic/claims")]


def list_reviews(repo_root: Path) -> List[ReviewPacket]:
    return [load_model(path, ReviewPacket) for path in iter_json_files(repo_root / ".agentic/reviews")]


def refresh_claim_last_seen(repo_root: Path, cwd: Path) -> None:
    """Bump last_seen on any in-progress claim whose worktree matches cwd."""
    coordination_root = resolve_coordination_root(repo_root)
    claims_dir = coordination_root / ".agentic/claims"
    if not claims_dir.exists():
        return
    cwd_resolved = cwd.resolve()
    for path in iter_json_files(claims_dir):
        try:
            claim = load_model(path, Claim)
        except Exception:
            continue
        if claim.status != "in_progress" or not claim.worktree:
            continue
        if Path(claim.worktree).resolve() != cwd_resolved:
            continue
        try:
            now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
            claim.last_seen = now
            save_model_json(path, claim)
        except Exception:
            pass


def next_work_item_id(repo_root: Path, project_key: str) -> str:
    prefix = "{0}-".format(project_key)
    numbers = []
    for work_item in list_work_items(repo_root):
        if work_item.id.startswith(prefix):
            try:
                numbers.append(int(work_item.id.split("-")[-1]))
            except ValueError:
                continue
    return "{0}-{1}".format(project_key, max(numbers, default=0) + 1)
