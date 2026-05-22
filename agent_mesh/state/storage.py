"""Storage helpers for Agent Mesh state."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Callable, Iterable, List, Type, TypeVar

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


def atomic_create_json(path: Path, payload: Any) -> None:
    """Create a JSON file exactly once, failing if the path already exists."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        handle = os.fdopen(fd, "w", encoding="utf-8")
        fd = -1
        with handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
    except Exception:
        if fd != -1:
            os.close(fd)
        Path(path).unlink(missing_ok=True)
        raise


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


def list_effective_work_items(repo_root: Path, coordination_root: Path | None = None) -> List[WorkItem]:
    items: dict[str, WorkItem] = {item.id: item for item in list_work_items(repo_root)}
    if coordination_root is not None and coordination_root != repo_root:
        for path in iter_json_files(coordination_root / ".agentic/work"):
            try:
                item = load_model(path, WorkItem)
            except Exception:
                continue
            items[item.id] = item
    return sorted(items.values(), key=lambda item: item.id)


def resolve_shared_work_item_path(repo_root: Path, work_id: str) -> Path:
    return repo_root / ".agentic/work" / "{0}.json".format(work_id)


def resolve_live_work_item_path(coordination_root: Path, work_id: str) -> Path:
    return coordination_root / ".agentic/work" / "{0}.json".format(work_id)


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
    prefix = f"{project_key}-"
    numbers = []
    for work_item in list_work_items(repo_root):
        if work_item.id.startswith(prefix):
            try:
                numbers.append(int(work_item.id.split("-")[-1]))
            except ValueError:
                continue
    return f"{project_key}-{max(numbers, default=0) + 1}"


def create_work_item_with_unique_id(
    repo_root: Path,
    project_key: str,
    build_item: Callable[[str], T],
    *,
    max_attempts: int = 1000,
) -> tuple[T, Path]:
    """Allocate a sequential work ID by exclusive file creation and retry.

    This keeps `mesh task add` safe under concurrent writers on local POSIX
    filesystems without requiring a separate long-lived lock file. `build_item`
    may be called multiple times if ID collisions occur, so it must remain
    side-effect-free.
    """
    for _ in range(max_attempts):
        work_id = next_work_item_id(repo_root, project_key)
        work_item = build_item(work_id)
        path = repo_root / ".agentic/work" / f"{work_id}.json"
        try:
            atomic_create_json(path, work_item.model_dump())
        except FileExistsError:
            continue
        return work_item, path
    raise RuntimeError("failed to allocate a unique work item ID after repeated retries")
