from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from agentflow.contracts import ContractError, validate_work_graph  # noqa: E402
from agentflow.work_graph import (  # noqa: E402
    compute_ready_work,
    work_item_content_hash,
)


def _item(item_id: str, depends_on: list[str] | None = None) -> dict:
    return {
        "id": item_id,
        "summary": f"Work {item_id}",
        "acceptance_criteria": [],
        "depends_on": depends_on or [],
    }


def run_agentflow(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "agentflow", *args],
        cwd=cwd,
        env={**os.environ, "PYTHONPATH": str(PROJECT_ROOT / "src")},
        text=True,
        capture_output=True,
        check=False,
    )


class WorkGraphContractTests(unittest.TestCase):
    def test_valid_graph_normalizes_defaults(self) -> None:
        graph = validate_work_graph(
            [{"id": "a", "summary": "A"}, {"id": "b", "summary": "B", "depends_on": ["a"]}]
        )
        self.assertEqual(graph[0]["depends_on"], [])
        self.assertEqual(graph[0]["acceptance_criteria"], [])
        self.assertEqual(graph[1]["depends_on"], ["a"])

    def test_duplicate_ids_rejected(self) -> None:
        with self.assertRaises(ContractError):
            validate_work_graph([_item("a"), _item("a")])

    def test_unknown_dependency_rejected(self) -> None:
        with self.assertRaises(ContractError):
            validate_work_graph([_item("a", ["ghost"])])

    def test_self_dependency_rejected(self) -> None:
        with self.assertRaises(ContractError):
            validate_work_graph([_item("a", ["a"])])

    def test_dependency_cycle_rejected(self) -> None:
        with self.assertRaises(ContractError):
            validate_work_graph([_item("a", ["b"]), _item("b", ["a"])])

    def test_unknown_field_rejected(self) -> None:
        with self.assertRaises(ContractError):
            validate_work_graph([{"id": "a", "summary": "A", "status": "done"}])


class ReadyWorkTests(unittest.TestCase):
    def test_ready_excludes_completed_and_blocked(self) -> None:
        graph = validate_work_graph(
            [_item("a"), _item("b", ["a"]), _item("c", ["b"])]
        )
        # Nothing done: only the dependency-free item is ready.
        self.assertEqual(
            [item["id"] for item in compute_ready_work(graph, set())], ["a"]
        )
        # a done: b unblocks; c still blocked by b.
        self.assertEqual(
            [item["id"] for item in compute_ready_work(graph, {"a"})], ["b"]
        )
        # a and b done: c ready, a/b excluded as completed.
        self.assertEqual(
            [item["id"] for item in compute_ready_work(graph, {"a", "b"})], ["c"]
        )

    def test_content_hash_is_stable_and_sensitive(self) -> None:
        item = _item("a")
        self.assertEqual(
            work_item_content_hash(item), work_item_content_hash(_item("a"))
        )
        self.assertNotEqual(
            work_item_content_hash(item),
            work_item_content_hash({**item, "summary": "changed"}),
        )


class WorkCommandTests(unittest.TestCase):
    def test_work_list_and_ready_reflect_completed_runs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            repository = temp_path / "repo"
            data_dir = temp_path / "home"
            work_dir = repository / ".agentflow" / "work"
            work_dir.mkdir(parents=True)
            (work_dir / "graph.jsonl").write_text(
                "\n".join(
                    json.dumps(item)
                    for item in [_item("a"), _item("b", ["a"])]
                )
                + "\n",
                encoding="utf-8",
            )

            listed = run_agentflow(
                "work", "list", "--repository", str(repository), cwd=temp_path
            )
            self.assertEqual(listed.returncode, 0, listed.stderr)
            self.assertEqual(
                [item["id"] for item in json.loads(listed.stdout)], ["a", "b"]
            )

            ready = run_agentflow(
                "work",
                "ready",
                "--repository",
                str(repository),
                "--data-dir",
                str(data_dir),
                cwd=temp_path,
            )
            self.assertEqual(ready.returncode, 0, ready.stderr)
            self.assertEqual(
                [item["id"] for item in json.loads(ready.stdout)], ["a"]
            )

            # Record a human_approved Run that captured work item "a", so "a"
            # counts as completed and "b" becomes ready.
            content_hash = work_item_content_hash(_item("a"))
            run_id = "run-a"
            run_dir = data_dir / "runs" / run_id
            run_dir.mkdir(parents=True)
            (run_dir / "task.json").write_text(
                json.dumps(
                    {
                        "summary": "deliver a",
                        "acceptance_criteria": [],
                        "source": {
                            "provider": "work-graph",
                            "work_item_id": "a",
                            "captured_at": "2026-07-16T00:00:00+00:00",
                            "content_hash": content_hash,
                        },
                    }
                ),
                encoding="utf-8",
            )
            (run_dir / "events.jsonl").write_text(
                "".join(
                    json.dumps(event) + "\n"
                    for event in [
                        {"run_id": run_id, "sequence": 1, "type": "run_created"},
                        {
                            "approved_by": "d",
                            "approved_sha": "0" * 40,
                            "candidate_sha": "0" * 40,
                            "sequence": 2,
                            "type": "human_approved",
                        },
                    ]
                ),
                encoding="utf-8",
            )

            ready_after = run_agentflow(
                "work",
                "ready",
                "--repository",
                str(repository),
                "--data-dir",
                str(data_dir),
                cwd=temp_path,
            )
            self.assertEqual(ready_after.returncode, 0, ready_after.stderr)
            self.assertEqual(
                [item["id"] for item in json.loads(ready_after.stdout)], ["b"]
            )


if __name__ == "__main__":
    unittest.main()
