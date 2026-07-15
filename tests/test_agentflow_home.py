from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).parents[1]


class AgentflowHomeTests(unittest.TestCase):
    def test_commands_share_the_agentflow_home_environment_override(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            repository = temp_path / "target"
            agentflow_home = temp_path / "external-evidence"
            repository.mkdir()
            subprocess.run(["git", "init"], cwd=repository, check=True, capture_output=True)
            subprocess.run(
                ["git", "config", "user.email", "agentflow@example.test"],
                cwd=repository,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Agentflow Test"],
                cwd=repository,
                check=True,
            )
            (repository / "README.md").write_text("# Target\n", encoding="utf-8")
            subprocess.run(["git", "add", "README.md"], cwd=repository, check=True)
            subprocess.run(
                ["git", "commit", "-m", "Initial commit"],
                cwd=repository,
                check=True,
                capture_output=True,
            )
            environment = {
                **os.environ,
                "AGENTFLOW_HOME": str(agentflow_home),
                "PYTHONPATH": str(PROJECT_ROOT / "src"),
            }

            started = subprocess.run(
                [sys.executable, "-m", "agentflow", "start", "Add health check"],
                cwd=repository,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(started.returncode, 0, started.stderr)
            run_id = json.loads(started.stdout)["run_id"]

            status = subprocess.run(
                [sys.executable, "-m", "agentflow", "status", run_id],
                cwd=repository,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(status.returncode, 0, status.stderr)
            self.assertEqual(json.loads(status.stdout)["state"], "ready")
            self.assertTrue((agentflow_home / "runs" / run_id).is_dir())


if __name__ == "__main__":
    unittest.main()
