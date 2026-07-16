from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from agentflow.run_kernel import read_run_status  # noqa: E402


def _write_log(data_dir: Path, run_id: str, events: list[dict]) -> None:
    run_dir = data_dir / "runs" / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "events.jsonl").write_text(
        "".join(json.dumps(event) + "\n" for event in events),
        encoding="utf-8",
    )


class LegacyReplayTests(unittest.TestCase):
    """The cold planner is retired, but Run logs created before its removal
    still contain plan_ready / plan_rejected / plan_amended events. Those must
    keep replaying to the correct state so historical Runs stay readable."""

    def test_legacy_plan_ready_and_amended_replay_to_built(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            run_id = "legacy-built"
            _write_log(
                data_dir,
                run_id,
                [
                    {"run_id": run_id, "sequence": 1, "type": "run_created"},
                    {"sequence": 2, "type": "workspace_ready", "worktree": "/w"},
                    {"sequence": 3, "type": "plan_ready", "adapter": "fake"},
                    {
                        "sequence": 4,
                        "type": "plan_amended",
                        "added_paths": ["tests/x.py"],
                        "amended_by": "d",
                    },
                    {
                        "sequence": 5,
                        "type": "build_ready",
                        "candidate_sha": "0" * 40,
                    },
                ],
            )
            status = read_run_status(run_id=run_id, data_dir=data_dir)
            # plan_ready -> planned, plan_amended leaves state unchanged,
            # build_ready -> built. No crash on the legacy event types.
            self.assertEqual(status.state, "built")
            self.assertEqual(status.candidate_sha, "0" * 40)

    def test_legacy_plan_rejected_replays_to_terminal(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            run_id = "legacy-rejected"
            _write_log(
                data_dir,
                run_id,
                [
                    {"run_id": run_id, "sequence": 1, "type": "run_created"},
                    {"sequence": 2, "type": "plan_ready", "adapter": "fake"},
                    {
                        "sequence": 3,
                        "type": "plan_rejected",
                        "rejected_by": "d",
                    },
                ],
            )
            status = read_run_status(run_id=run_id, data_dir=data_dir)
            self.assertEqual(status.state, "plan_rejected")


if __name__ == "__main__":
    unittest.main()
