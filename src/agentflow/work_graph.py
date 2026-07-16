"""Target-repository Work Graph: git-tracked Work Items and computed ready work.

The Work Graph is owned by the Target Repository and stored as git-tracked JSONL
under ``.agentflow/work/``. Work-intent truth lives here; execution truth lives
in Run Evidence. The two keep only references to each other — a Run records the
``work_item_id`` it captured, and completion is derived from Run Evidence rather
than stored back into the graph. Ready work is computed from dependency
relationships whenever it is needed, never persisted as a mutable value.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .contracts import ContractError, validate_work_graph
from .run_kernel import list_runs

WORK_RELATIVE_DIR = Path(".agentflow/work")


def work_item_content_hash(item: dict) -> str:
    """Stable content hash of a Work Item for Run capture-by-reference.

    A Run records this alongside the ``work_item_id`` so later edits to the Work
    Item are detectable and never silently alter an in-flight Run.
    """
    canonical = json.dumps(item, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_work_graph(repository: Path) -> list[dict]:
    """Load and validate the Work Graph from a Target Repository.

    Reads every ``*.jsonl`` file under ``.agentflow/work/`` in deterministic
    order, one Work Item per non-blank line, and validates the aggregate graph
    (unique ids, resolvable dependencies, no cycles). A missing directory is an
    empty graph.
    """
    work_dir = repository / WORK_RELATIVE_DIR
    if not work_dir.is_dir():
        return []
    items: list[dict] = []
    for path in sorted(work_dir.glob("*.jsonl")):
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not line.strip():
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise ContractError(
                    f"{path.name}:{line_number} is not valid JSON"
                ) from error
    return validate_work_graph(items)


def completed_work_item_ids(data_dir: Path) -> set[str]:
    """Work-item ids a human-approved Run has already delivered.

    Completion is read from Run Evidence: a Work Item is done when a
    ``human_approved`` Run captured it (its Task Spec ``source.work_item_id``
    names the item). Nothing is written back to the Work Graph.
    """
    completed: set[str] = set()
    for run in list_runs(data_dir=data_dir, state="human_approved"):
        source = run.source
        if isinstance(source, dict) and source.get("work_item_id"):
            completed.add(source["work_item_id"])
    return completed


def compute_ready_work(
    graph: list[dict], completed_ids: set[str]
) -> list[dict]:
    """Work Items that are not yet complete and whose dependencies all are.

    Deterministic: the result preserves the graph's order. Ready work is derived
    on demand from the dependency relationships and the completion set; it is
    never stored.
    """
    ready: list[dict] = []
    for item in graph:
        if item["id"] in completed_ids:
            continue
        if all(dep in completed_ids for dep in item["depends_on"]):
            ready.append(item)
    return ready
