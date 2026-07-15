from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import uuid


@dataclass(frozen=True)
class StartedRun:
    run_id: str
    state: str
    worktree: Path


@dataclass(frozen=True)
class RunStatus:
    run_id: str
    state: str
    summary: str | None
    repository: str | None
    base_sha: str | None
    worktree: str | None


@dataclass(frozen=True)
class Approval:
    run_id: str
    state: str
    approved_by: str


def _git(*args: str, cwd: Path) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()


def _write_json(path: Path, value: dict[str, str]) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def start_run(*, summary: str, repository: Path, data_dir: Path) -> StartedRun:
    repository = Path(_git("rev-parse", "--show-toplevel", cwd=repository))
    base_sha = _git("rev-parse", "HEAD", cwd=repository)
    run_id = uuid.uuid4().hex
    run_dir = data_dir / "runs" / run_id
    worktree = data_dir / "worktrees" / run_id
    run_dir.mkdir(parents=True)
    worktree.parent.mkdir(parents=True, exist_ok=True)

    _write_json(run_dir / "task.json", {"summary": summary})
    _write_json(
        run_dir / "repository.json",
        {"base_sha": base_sha, "repository": str(repository)},
    )

    branch = f"agentflow/{run_id}"
    _git(
        "worktree",
        "add",
        "-b",
        branch,
        str(worktree),
        base_sha,
        cwd=repository,
    )
    events = (
        {"run_id": run_id, "sequence": 1, "type": "run_created"},
        {
            "base_sha": base_sha,
            "repository": str(repository),
            "sequence": 2,
            "type": "repository_snapshotted",
        },
        {
            "sequence": 3,
            "type": "workspace_ready",
            "worktree": str(worktree),
        },
    )
    (run_dir / "events.jsonl").write_text(
        "".join(json.dumps(event, sort_keys=True) + "\n" for event in events),
        encoding="utf-8",
    )
    return StartedRun(run_id=run_id, state="ready", worktree=worktree)


def read_run_status(*, run_id: str, data_dir: Path) -> RunStatus:
    run_dir = data_dir / "runs" / run_id
    state = "unknown"
    worktree: str | None = None
    state_by_event = {
        "run_created": "created",
        "workspace_ready": "ready",
        "plan_ready": "planned",
        "checks_passed": "verified",
        "awaiting_human": "awaiting_human",
        "human_approved": "human_approved",
    }
    for line_number, line in enumerate(
        (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        event = json.loads(line)
        sequence = event.get("sequence")
        if sequence is not None and sequence != line_number:
            raise ValueError(
                f"invalid event sequence for run {run_id}: "
                f"expected {line_number}, got {sequence}"
            )
        state = state_by_event.get(event["type"], state)
        if event["type"] == "workspace_ready":
            worktree = event.get("worktree")

    task_path = run_dir / "task.json"
    task = json.loads(task_path.read_text(encoding="utf-8")) if task_path.exists() else {}
    repository_path = run_dir / "repository.json"
    repository = (
        json.loads(repository_path.read_text(encoding="utf-8"))
        if repository_path.exists()
        else {}
    )
    return RunStatus(
        run_id=run_id,
        state=state,
        summary=task.get("summary"),
        repository=repository.get("repository"),
        base_sha=repository.get("base_sha"),
        worktree=worktree,
    )


def approve_run(*, run_id: str, approved_by: str, data_dir: Path) -> Approval:
    status = read_run_status(run_id=run_id, data_dir=data_dir)
    if status.state != "awaiting_human":
        raise ValueError(
            f"run {run_id} cannot be approved from state {status.state}"
        )
    events_path = data_dir / "runs" / run_id / "events.jsonl"
    sequence = len(events_path.read_text(encoding="utf-8").splitlines()) + 1
    event = {
        "approved_by": approved_by,
        "sequence": sequence,
        "type": "human_approved",
    }
    with events_path.open("a", encoding="utf-8") as events_file:
        events_file.write(json.dumps(event, sort_keys=True) + "\n")
    return Approval(
        run_id=run_id,
        state="human_approved",
        approved_by=approved_by,
    )
