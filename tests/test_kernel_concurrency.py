from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest


PROJECT_ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from agentflow.run_kernel import (  # noqa: E402
    acquire_claim,
    append_event,
    approve_run,
    list_runs,
    read_run_status,
)


def _init_workspace(workspace: Path) -> str:
    workspace.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=workspace, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "agentflow@example.test"],
        cwd=workspace,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Agentflow Test"],
        cwd=workspace,
        check=True,
    )
    (workspace / "README.md").write_text("# Candidate\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=workspace, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Candidate"],
        cwd=workspace,
        check=True,
        capture_output=True,
    )
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=workspace,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()


def _write_events(run_dir: Path, events: list[dict]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "events.jsonl").write_text(
        "".join(json.dumps(event, sort_keys=True) + "\n" for event in events),
        encoding="utf-8",
    )


def _awaiting_human_run(data_dir: Path, workspace: Path, run_id: str) -> str:
    candidate_sha = _init_workspace(workspace)
    _write_events(
        data_dir / "runs" / run_id,
        [
            {"run_id": run_id, "sequence": 1, "type": "run_created"},
            {"sequence": 2, "type": "workspace_ready", "worktree": str(workspace)},
            {
                "candidate_sha": candidate_sha,
                "sequence": 3,
                "type": "awaiting_human",
            },
        ],
    )
    return candidate_sha


def _events(data_dir: Path, run_id: str) -> list[dict]:
    return [
        json.loads(line)
        for line in (data_dir / "runs" / run_id / "events.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]


class KernelConcurrencyTests(unittest.TestCase):
    def test_concurrent_appends_keep_sequences_contiguous_and_replayable(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "home"
            run_id = "run-append-race"
            _write_events(
                data_dir / "runs" / run_id,
                [{"run_id": run_id, "sequence": 1, "type": "run_created"}],
            )

            writer_count = 16
            barrier = threading.Barrier(writer_count)

            def writer(index: int) -> None:
                barrier.wait()
                append_event(
                    data_dir=data_dir,
                    run_id=run_id,
                    event_type="probe",
                    writer=index,
                )

            threads = [
                threading.Thread(target=writer, args=(i,))
                for i in range(writer_count)
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

            events = _events(data_dir, run_id)
            sequences = [event["sequence"] for event in events]
            self.assertEqual(sequences, list(range(1, writer_count + 2)))
            # The whole point: the log stays replayable rather than raising an
            # integrity error forever.
            status = read_run_status(run_id=run_id, data_dir=data_dir)
            self.assertEqual(status.run_id, run_id)

    def test_approve_refused_while_stage_is_claimed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            data_dir = temp_path / "home"
            _awaiting_human_run(data_dir, temp_path / "workspace", "run-claimed")

            acquire_claim(
                data_dir=data_dir, run_id="run-claimed", holder="other-process"
            )

            with self.assertRaises(Exception):
                approve_run(
                    run_id="run-claimed",
                    approved_by="daveonthegit",
                    data_dir=data_dir,
                )

            events = _events(data_dir, "run-claimed")
            self.assertFalse(
                any(event["type"] == "human_approved" for event in events)
            )

    def test_approve_refused_when_candidate_moved(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            data_dir = temp_path / "home"
            workspace = temp_path / "workspace"
            _awaiting_human_run(data_dir, workspace, "run-moved")

            # A rebase or any commit moves HEAD off the verified candidate.
            (workspace / "EXTRA.md").write_text("drift\n", encoding="utf-8")
            subprocess.run(["git", "add", "EXTRA.md"], cwd=workspace, check=True)
            subprocess.run(
                ["git", "commit", "-m", "drift"],
                cwd=workspace,
                check=True,
                capture_output=True,
            )

            with self.assertRaises(Exception):
                approve_run(
                    run_id="run-moved",
                    approved_by="daveonthegit",
                    data_dir=data_dir,
                )

            events = _events(data_dir, "run-moved")
            self.assertFalse(
                any(event["type"] == "human_approved" for event in events)
            )

    def test_list_runs_isolates_a_corrupt_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "home"
            # A healthy, readable run.
            _write_events(
                data_dir / "runs" / "run-healthy",
                [{"run_id": "run-healthy", "sequence": 1, "type": "run_created"}],
            )
            # A run whose sequence integrity is broken (duplicate sequence 1).
            _write_events(
                data_dir / "runs" / "run-corrupt",
                [
                    {"run_id": "run-corrupt", "sequence": 1, "type": "run_created"},
                    {"sequence": 1, "type": "probe"},
                ],
            )

            runs = list_runs(data_dir=data_dir)
            ids = {status.run_id for status in runs}
            self.assertIn("run-healthy", ids)
            # The corrupt run must not hide the healthy one by raising.
            self.assertIn("run-corrupt", ids)


if __name__ == "__main__":
    unittest.main()
