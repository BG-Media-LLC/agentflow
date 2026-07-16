from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from agentflow.workflow import (  # noqa: E402
    _assert_workspace_guard,
    _capture_workspace_guard,
)


def _init_repo(workspace: Path) -> None:
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


def _hooks_dir(workspace: Path) -> Path:
    raw = subprocess.run(
        ["git", "rev-parse", "--git-path", "hooks"],
        cwd=workspace,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    hooks_dir = Path(raw)
    if not hooks_dir.is_absolute():
        hooks_dir = (workspace / hooks_dir).resolve()
    return hooks_dir


class WorkspaceEnforcementTests(unittest.TestCase):
    def test_no_tampering_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "ws"
            _init_repo(workspace)
            before = _capture_workspace_guard(workspace)
            # A benign tracked edit is not the guard's concern.
            (workspace / "README.md").write_text("# Edited\n", encoding="utf-8")
            _assert_workspace_guard(workspace, before)  # must not raise

    def test_planted_git_hook_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "ws"
            _init_repo(workspace)
            before = _capture_workspace_guard(workspace)

            hooks_dir = _hooks_dir(workspace)
            hooks_dir.mkdir(parents=True, exist_ok=True)
            pre_commit = hooks_dir / "pre-commit"
            pre_commit.write_text("#!/bin/sh\necho pwned\n", encoding="utf-8")
            pre_commit.chmod(0o755)

            with self.assertRaises(Exception):
                _assert_workspace_guard(workspace, before)

    def test_repointed_hooks_path_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "ws"
            _init_repo(workspace)
            before = _capture_workspace_guard(workspace)

            evil = workspace / ".evil-hooks"
            evil.mkdir()
            hook = evil / "pre-commit"
            hook.write_text("#!/bin/sh\necho pwned\n", encoding="utf-8")
            hook.chmod(0o755)
            subprocess.run(
                ["git", "config", "core.hooksPath", str(evil)],
                cwd=workspace,
                check=True,
            )

            with self.assertRaises(Exception):
                _assert_workspace_guard(workspace, before)

    def test_introduced_ignored_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "ws"
            _init_repo(workspace)
            (workspace / ".gitignore").write_text("secret.env\n", encoding="utf-8")
            subprocess.run(["git", "add", ".gitignore"], cwd=workspace, check=True)
            subprocess.run(
                ["git", "commit", "-m", "ignore"],
                cwd=workspace,
                check=True,
                capture_output=True,
            )
            before = _capture_workspace_guard(workspace)

            # An ignored file the role drops would affect checks but never enter
            # the committed candidate.
            (workspace / "secret.env").write_text("TOKEN=1\n", encoding="utf-8")

            with self.assertRaises(Exception):
                _assert_workspace_guard(workspace, before)


if __name__ == "__main__":
    unittest.main()
