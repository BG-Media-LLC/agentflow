from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).parents[1]


def run_agentflow(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "agentflow", *args],
        cwd=cwd,
        env={**os.environ, "PYTHONPATH": str(PROJECT_ROOT / "src")},
        text=True,
        capture_output=True,
        check=False,
    )


def git(*args: str, cwd: Path) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()


class StatusCommandTests(unittest.TestCase):
    def test_status_rebuilds_a_run_in_a_new_process(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            repository = temp_path / "target"
            data_dir = temp_path / "agentflow-home"
            repository.mkdir()
            git("init", cwd=repository)
            git("config", "user.email", "agentflow@example.test", cwd=repository)
            git("config", "user.name", "Agentflow Test", cwd=repository)
            (repository / "README.md").write_text("# Target\n", encoding="utf-8")
            git("add", "README.md", cwd=repository)
            git("commit", "-m", "Initial commit", cwd=repository)
            base_sha = git("rev-parse", "HEAD", cwd=repository)

            started = run_agentflow(
                "start",
                "Add a health endpoint",
                "--data-dir",
                str(data_dir),
                cwd=repository,
            )
            self.assertEqual(started.returncode, 0, started.stderr)
            run_id = json.loads(started.stdout)["run_id"]

            status = run_agentflow(
                "status",
                run_id,
                "--data-dir",
                str(data_dir),
                cwd=repository,
            )

            self.assertEqual(status.returncode, 0, status.stderr)
            self.assertEqual(
                json.loads(status.stdout),
                {
                    "base_sha": base_sha,
                    "repository": str(repository.resolve()),
                    "run_id": run_id,
                    "state": "ready",
                    "summary": "Add a health endpoint",
                    "worktree": str(data_dir.resolve() / "worktrees" / run_id),
                },
            )

    def test_status_includes_the_captured_repository_profile_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            repository = temp_path / "target"
            data_dir = temp_path / "agentflow-home"
            repository.mkdir()
            git("init", cwd=repository)
            git("config", "user.email", "agentflow@example.test", cwd=repository)
            git("config", "user.name", "Agentflow Test", cwd=repository)
            (repository / "README.md").write_text("# Target\n", encoding="utf-8")
            git("add", "README.md", cwd=repository)
            git("commit", "-m", "Initial commit", cwd=repository)

            profiled = run_agentflow(
                "profile",
                "--check",
                "python3 -m unittest discover -s tests -v",
                cwd=repository,
            )
            self.assertEqual(profiled.returncode, 0, profiled.stderr)
            git("add", "-f", ".agentflow/repository-profile.json", cwd=repository)
            git("commit", "-m", "Add repository profile", cwd=repository)

            started = run_agentflow(
                "start",
                "Add a health endpoint",
                "--data-dir",
                str(data_dir),
                cwd=repository,
            )
            self.assertEqual(started.returncode, 0, started.stderr)
            run_id = json.loads(started.stdout)["run_id"]

            status = run_agentflow(
                "status",
                run_id,
                "--data-dir",
                str(data_dir),
                cwd=repository,
            )

            self.assertEqual(status.returncode, 0, status.stderr)
            self.assertEqual(
                json.loads(status.stdout)["repository_profile_path"],
                ".agentflow/repository-profile.json",
            )


if __name__ == "__main__":
    unittest.main()
