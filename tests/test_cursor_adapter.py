from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest

from test_advance_command import (
    PROJECT_ROOT,
    agentflow,
    create_profiled_run,
)


PLAN = {
    "files_to_modify": ["README.md"],
    "risks": [],
    "steps": [
        {
            "description": "Document the health endpoint",
            "id": "P1",
            "verification": "The authoritative checks pass",
        }
    ],
    "summary": "Add a health endpoint",
}


def base_environment() -> dict[str, str]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("AGENTFLOW_CURSOR")
    }
    environment["PYTHONPATH"] = str(PROJECT_ROOT / "src")
    return environment


def write_stub(path: Path, source: str) -> None:
    path.write_text(source, encoding="utf-8")
    path.chmod(0o755)


def read_events(data_dir: Path, run_id: str) -> list[dict]:
    return [
        json.loads(line)
        for line in (data_dir / "runs" / run_id / "events.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]


class CursorAdapterTests(unittest.TestCase):
    def test_planner_is_read_only_and_records_validated_stream_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            fake_cursor = temp_path / "agent"
            write_stub(
                fake_cursor,
                f"""#!/usr/bin/env python3
import json
import sys

arguments = sys.argv[1:]


def value(flag):
    return arguments[arguments.index(flag) + 1]


assert "--print" in arguments
assert value("--output-format") == "stream-json"
assert value("--mode") == "ask"
assert value("--model") == "cursor-test-model"
assert "--trust" in arguments
assert "--force" not in arguments
assert "JSON Schema" in arguments[-1]
print(json.dumps({{"type": "system", "subtype": "init"}}))
print(json.dumps({{
    "type": "result",
    "subtype": "success",
    "result": "Progress update that Cursor may retain.\\n" + json.dumps({PLAN!r})
}}))
""",
            )
            environment = base_environment()
            environment["AGENTFLOW_CURSOR"] = str(fake_cursor)
            environment["AGENTFLOW_CURSOR_PLANNER_MODEL"] = "cursor-test-model"
            _, data_dir, run_id = create_profiled_run(temp_path, environment)

            planned = agentflow(
                "advance",
                run_id,
                "--adapter",
                "cursor",
                "--data-dir",
                str(data_dir),
                cwd=temp_path,
                environment=environment,
            )

            self.assertEqual(planned.returncode, 0, planned.stderr)
            self.assertEqual(json.loads(planned.stdout)["state"], "planned")
            run_dir = data_dir / "runs" / run_id
            self.assertEqual(
                json.loads((run_dir / "plan.json").read_text(encoding="utf-8")),
                PLAN,
            )
            transcript = run_dir / "planner-transcript.jsonl"
            self.assertTrue(transcript.is_file())
            self.assertIn("agentflow_adapter_attempt", transcript.read_text())
            plan_ready = next(
                event
                for event in read_events(data_dir, run_id)
                if event["type"] == "plan_ready"
            )
            self.assertEqual(plan_ready["adapter"], "cursor")
            self.assertEqual(plan_ready["model"], "cursor-test-model")
            self.assertEqual(
                Path(plan_ready["transcript"]).resolve(), transcript.resolve()
            )

    def test_invalid_output_is_retried_once_then_validated(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            fake_cursor = temp_path / "agent"
            counter = temp_path / "attempts"
            write_stub(
                fake_cursor,
                f"""#!/usr/bin/env python3
import json
import os
from pathlib import Path

counter = Path(os.environ["CURSOR_STUB_COUNTER"])
attempt = int(counter.read_text()) + 1 if counter.exists() else 1
counter.write_text(str(attempt))
result = "not JSON" if attempt == 1 else json.dumps({PLAN!r})
print(json.dumps({{
    "type": "result",
    "subtype": "success",
    "result": result
}}))
""",
            )
            environment = base_environment()
            environment["AGENTFLOW_CURSOR"] = str(fake_cursor)
            environment["CURSOR_STUB_COUNTER"] = str(counter)
            _, data_dir, run_id = create_profiled_run(temp_path, environment)

            planned = agentflow(
                "advance",
                run_id,
                "--adapter",
                "cursor",
                "--model",
                "cursor-test-model",
                "--data-dir",
                str(data_dir),
                cwd=temp_path,
                environment=environment,
            )

            self.assertEqual(planned.returncode, 0, planned.stderr)
            self.assertEqual(counter.read_text(), "2")
            transcript = (
                data_dir / "runs" / run_id / "planner-transcript.jsonl"
            ).read_text(encoding="utf-8")
            self.assertEqual(transcript.count("agentflow_adapter_attempt"), 2)

    def test_builder_uses_force_with_sandbox_and_commits_validated_changes(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            environment = base_environment()
            _, data_dir, run_id = create_profiled_run(temp_path, environment)
            fixture = temp_path / "adapter-fixture.json"
            fixture.write_text(json.dumps({"planner": PLAN}), encoding="utf-8")
            planned = agentflow(
                "advance",
                run_id,
                "--adapter",
                "fake",
                "--adapter-fixture",
                str(fixture),
                "--data-dir",
                str(data_dir),
                cwd=temp_path,
                environment=environment,
            )
            self.assertEqual(planned.returncode, 0, planned.stderr)
            fake_cursor = temp_path / "agent"
            write_stub(
                fake_cursor,
                """#!/usr/bin/env python3
import json
from pathlib import Path
import sys

arguments = sys.argv[1:]


def value(flag):
    return arguments[arguments.index(flag) + 1]


assert "--force" in arguments
assert value("--sandbox") == "enabled"
assert "--mode" not in arguments
Path("README.md").write_text(
    "# Target\\n\\nHealth endpoint documented.\\n", encoding="utf-8"
)
print(json.dumps({
    "type": "result",
    "subtype": "success",
    "result": json.dumps({
        "commands_run": [],
        "files_changed": ["README.md"],
        "steps_completed": ["P1"],
        "unresolved_issues": []
    })
}))
""",
            )
            environment["AGENTFLOW_CURSOR"] = str(fake_cursor)

            built = agentflow(
                "advance",
                run_id,
                "--adapter",
                "cursor",
                "--model",
                "cursor-test-model",
                "--data-dir",
                str(data_dir),
                cwd=temp_path,
                environment=environment,
            )

            self.assertEqual(built.returncode, 0, built.stderr)
            self.assertEqual(json.loads(built.stdout)["state"], "built")

    def test_failure_envelope_surfaces_cursor_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            fake_cursor = temp_path / "agent"
            write_stub(
                fake_cursor,
                """#!/usr/bin/env python3
import json

print(json.dumps({
    "type": "result",
    "subtype": "error_during_execution",
    "duration_ms": 321,
    "session_id": "session-1",
    "result": "provider failed"
}))
""",
            )
            environment = base_environment()
            environment["AGENTFLOW_CURSOR"] = str(fake_cursor)
            _, data_dir, run_id = create_profiled_run(temp_path, environment)

            planned = agentflow(
                "advance",
                run_id,
                "--adapter",
                "cursor",
                "--model",
                "cursor-test-model",
                "--data-dir",
                str(data_dir),
                cwd=temp_path,
                environment=environment,
            )

            self.assertNotEqual(planned.returncode, 0)
            self.assertIn("error_during_execution", planned.stderr)
            self.assertIn("session-1", planned.stderr)
            self.assertIn("321", planned.stderr)
            status = agentflow(
                "status",
                run_id,
                "--data-dir",
                str(data_dir),
                cwd=temp_path,
                environment=environment,
            )
            self.assertEqual(json.loads(status.stdout)["state"], "ready")

    def test_cursor_adapter_preserves_stderr_on_nonzero_exit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            fake_cursor = temp_path / "agent"
            write_stub(
                fake_cursor,
                """#!/usr/bin/env python3
import sys

print("cursor stderr detail", file=sys.stderr)
raise SystemExit(3)
""",
            )
            environment = base_environment()
            environment["AGENTFLOW_CURSOR"] = str(fake_cursor)
            _, data_dir, run_id = create_profiled_run(temp_path, environment)

            planned = agentflow(
                "advance",
                run_id,
                "--adapter",
                "cursor",
                "--model",
                "cursor-test-model",
                "--data-dir",
                str(data_dir),
                cwd=temp_path,
                environment=environment,
            )

            self.assertNotEqual(planned.returncode, 0)
            self.assertIn("exit 3", planned.stderr)
            self.assertIn("cursor stderr detail", planned.stderr)

    def test_cursor_adapter_reports_missing_result_event(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            fake_cursor = temp_path / "agent"
            write_stub(
                fake_cursor,
                """#!/usr/bin/env python3
import json

print(json.dumps({"type": "system", "subtype": "init"}))
""",
            )
            environment = base_environment()
            environment["AGENTFLOW_CURSOR"] = str(fake_cursor)
            _, data_dir, run_id = create_profiled_run(temp_path, environment)

            planned = agentflow(
                "advance",
                run_id,
                "--adapter",
                "cursor",
                "--model",
                "cursor-test-model",
                "--data-dir",
                str(data_dir),
                cwd=temp_path,
                environment=environment,
            )

            self.assertNotEqual(planned.returncode, 0)
            self.assertIn("no result event", planned.stderr)


if __name__ == "__main__":
    unittest.main()
