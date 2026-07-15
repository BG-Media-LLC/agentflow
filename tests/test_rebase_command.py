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

from agentflow.run_kernel import acquire_claim  # noqa: E402

try:
    from tests.test_advance_command import (
        agentflow,
        create_built_run,
        create_profiled_run,
        create_verified_run,
    )
except ImportError:  # unittest discover imports test modules without a package
    from test_advance_command import (
        agentflow,
        create_built_run,
        create_profiled_run,
        create_verified_run,
    )


def read_events(data_dir: Path, run_id: str) -> list[dict]:
    return [
        json.loads(line)
        for line in (data_dir / "runs" / run_id / "events.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]


def non_claim_events(events: list[dict]) -> list[dict]:
    claim_types = {"claim_acquired", "claim_released", "claim_expired"}
    return [event for event in events if event["type"] not in claim_types]


def git(*args: str, cwd: Path) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()


def commit_on_main(repository: Path, path: str, content: str, message: str) -> str:
    target = repository / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", path], cwd=repository, check=True)
    subprocess.run(
        ["git", "commit", "-m", message],
        cwd=repository,
        check=True,
        capture_output=True,
    )
    return git("rev-parse", "HEAD", cwd=repository)


def status_json(
    temp_path: Path,
    data_dir: Path,
    run_id: str,
    environment: dict[str, str],
) -> dict:
    status = agentflow(
        "status",
        run_id,
        "--data-dir",
        str(data_dir),
        cwd=temp_path,
        environment=environment,
    )
    if status.returncode != 0:
        raise AssertionError(status.stderr)
    return json.loads(status.stdout)


def rebase(
    temp_path: Path,
    data_dir: Path,
    run_id: str,
    environment: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    return agentflow(
        "rebase",
        run_id,
        "--data-dir",
        str(data_dir),
        cwd=temp_path,
        environment=environment,
    )


class RebaseCommandTests(unittest.TestCase):
    def test_rebase_on_up_to_date_run_appends_no_events(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            environment = {**os.environ, "PYTHONPATH": str(PROJECT_ROOT / "src")}
            data_dir, run_id = create_built_run(temp_path, environment)
            events_path = data_dir / "runs" / run_id / "events.jsonl"
            before = events_path.read_text(encoding="utf-8")

            rebased = rebase(temp_path, data_dir, run_id, environment)

            self.assertEqual(rebased.returncode, 0, rebased.stderr)
            response = json.loads(rebased.stdout)
            self.assertFalse(response["rebased"])
            self.assertEqual(response["state"], "built")
            self.assertEqual(
                events_path.read_text(encoding="utf-8"), before
            )

    def test_rebase_refreshes_candidate_onto_advanced_main(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            environment = {**os.environ, "PYTHONPATH": str(PROJECT_ROOT / "src")}
            data_dir, run_id = create_built_run(temp_path, environment)
            repository = temp_path / "target"
            status_before = status_json(temp_path, data_dir, run_id, environment)
            old_base = status_before["base_sha"]
            old_candidate = status_before["candidate_sha"]
            new_base = commit_on_main(
                repository, "NOTES.md", "extra notes\n", "Add notes on main"
            )
            target_head_before = git("rev-parse", "HEAD", cwd=repository)
            target_branch_before = git(
                "rev-parse", "--abbrev-ref", "HEAD", cwd=repository
            )

            rebased = rebase(temp_path, data_dir, run_id, environment)

            self.assertEqual(rebased.returncode, 0, rebased.stderr)
            response = json.loads(rebased.stdout)
            self.assertTrue(response["rebased"])
            self.assertEqual(response["state"], "built")
            self.assertEqual(response["old_base_sha"], old_base)
            self.assertEqual(response["new_base_sha"], new_base)
            self.assertEqual(response["old_candidate_sha"], old_candidate)
            new_candidate = response["new_candidate_sha"]
            self.assertNotEqual(new_candidate, old_candidate)

            # The Target Repository's primary checkout is untouched.
            self.assertEqual(git("rev-parse", "HEAD", cwd=repository), target_head_before)
            self.assertEqual(
                git("rev-parse", "--abbrev-ref", "HEAD", cwd=repository),
                target_branch_before,
            )

            status_after = status_json(temp_path, data_dir, run_id, environment)
            self.assertEqual(status_after["state"], "built")
            self.assertEqual(status_after["base_sha"], new_base)
            self.assertEqual(status_after["candidate_sha"], new_candidate)

            listing = agentflow(
                "list",
                "--data-dir",
                str(data_dir),
                cwd=temp_path,
                environment=environment,
            )
            self.assertEqual(listing.returncode, 0, listing.stderr)
            entry = next(
                item
                for item in json.loads(listing.stdout)
                if item["run_id"] == run_id
            )
            self.assertEqual(entry["base_sha"], new_base)
            self.assertEqual(entry["candidate_sha"], new_candidate)

            # Re-verify the rebased candidate and approve it.
            verified = agentflow(
                "advance",
                run_id,
                "--data-dir",
                str(data_dir),
                cwd=temp_path,
                environment=environment,
            )
            self.assertEqual(verified.returncode, 0, verified.stderr)
            self.assertEqual(json.loads(verified.stdout)["state"], "verified")
            self.assertEqual(
                json.loads(verified.stdout)["candidate_sha"], new_candidate
            )
            fixture_path = temp_path / "adapter-fixture.json"
            fixture_path.write_text(
                json.dumps({"reviewer": {"disposition": "approve", "findings": []}}),
                encoding="utf-8",
            )
            reviewed = agentflow(
                "advance",
                run_id,
                "--adapter",
                "fake",
                "--adapter-fixture",
                str(fixture_path),
                "--data-dir",
                str(data_dir),
                cwd=temp_path,
                environment=environment,
            )
            self.assertEqual(reviewed.returncode, 0, reviewed.stderr)
            self.assertEqual(json.loads(reviewed.stdout)["state"], "awaiting_human")
            approved = agentflow(
                "approve",
                run_id,
                "--approved-by",
                "integration-test-human",
                "--data-dir",
                str(data_dir),
                cwd=temp_path,
                environment=environment,
            )
            self.assertEqual(approved.returncode, 0, approved.stderr)
            self.assertEqual(json.loads(approved.stdout)["approved_sha"], new_candidate)

    def test_rebase_conflict_leaves_run_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            environment = {**os.environ, "PYTHONPATH": str(PROJECT_ROOT / "src")}
            data_dir, run_id = create_built_run(temp_path, environment)
            repository = temp_path / "target"
            status_before = status_json(temp_path, data_dir, run_id, environment)
            base_before = status_before["base_sha"]
            candidate_before = status_before["candidate_sha"]
            workspace = Path(status_before["worktree"])
            workspace_head_before = git("rev-parse", "HEAD", cwd=workspace)
            events_before = non_claim_events(read_events(data_dir, run_id))
            # Conflict: rewrite the same README.md the builder rewrote.
            commit_on_main(
                repository,
                "README.md",
                "# Completely different heading\n",
                "Rewrite README on main",
            )

            rebased = rebase(temp_path, data_dir, run_id, environment)

            self.assertNotEqual(rebased.returncode, 0)
            self.assertIn("conflict", rebased.stderr)
            status_after = status_json(temp_path, data_dir, run_id, environment)
            self.assertEqual(status_after["state"], "built")
            self.assertEqual(status_after["base_sha"], base_before)
            self.assertEqual(status_after["candidate_sha"], candidate_before)
            self.assertEqual(
                git("rev-parse", "HEAD", cwd=workspace), workspace_head_before
            )
            self.assertFalse(
                git("status", "--porcelain", "--untracked-files=all", cwd=workspace)
            )
            events_after = read_events(data_dir, run_id)
            self.assertEqual(non_claim_events(events_after), events_before)
            self.assertFalse(
                any(e["type"] == "candidate_rebased" for e in events_after)
            )
            # No rebase is left in progress in the Workspace.
            abort_again = subprocess.run(
                ["git", "rebase", "--abort"],
                cwd=workspace,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(abort_again.returncode, 0)

    def test_rebase_fails_on_pre_candidate_ready_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            environment = {**os.environ, "PYTHONPATH": str(PROJECT_ROOT / "src")}
            repository, data_dir, run_id = create_profiled_run(temp_path, environment)
            # Advance main so the up-to-date fast path does not short-circuit.
            commit_on_main(repository, "NOTES.md", "notes\n", "Advance main")
            events_before = read_events(data_dir, run_id)

            rebased = rebase(temp_path, data_dir, run_id, environment)

            self.assertNotEqual(rebased.returncode, 0)
            self.assertIn(
                f"run {run_id} cannot be rebased from state ready", rebased.stderr
            )
            self.assertEqual(
                non_claim_events(read_events(data_dir, run_id)), events_before
            )

    def test_rebase_fails_on_an_abandoned_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            environment = {**os.environ, "PYTHONPATH": str(PROJECT_ROOT / "src")}
            repository, data_dir, run_id = create_profiled_run(temp_path, environment)
            abandoned = agentflow(
                "abandon",
                run_id,
                "--abandoned-by",
                "rebase-test",
                "--data-dir",
                str(data_dir),
                cwd=temp_path,
                environment=environment,
            )
            self.assertEqual(abandoned.returncode, 0, abandoned.stderr)
            commit_on_main(repository, "NOTES.md", "notes\n", "Advance main")

            rebased = rebase(temp_path, data_dir, run_id, environment)

            self.assertNotEqual(rebased.returncode, 0)
            self.assertIn(
                f"run {run_id} cannot be rebased from state abandoned",
                rebased.stderr,
            )

    def test_rebase_fails_on_a_human_approved_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            environment = {**os.environ, "PYTHONPATH": str(PROJECT_ROOT / "src")}
            data_dir, run_id = create_verified_run(temp_path, environment)
            fixture_path = temp_path / "adapter-fixture.json"
            fixture_path.write_text(
                json.dumps({"reviewer": {"disposition": "approve", "findings": []}}),
                encoding="utf-8",
            )
            reviewed = agentflow(
                "advance",
                run_id,
                "--adapter",
                "fake",
                "--adapter-fixture",
                str(fixture_path),
                "--data-dir",
                str(data_dir),
                cwd=temp_path,
                environment=environment,
            )
            self.assertEqual(reviewed.returncode, 0, reviewed.stderr)
            approved = agentflow(
                "approve",
                run_id,
                "--approved-by",
                "integration-test-human",
                "--data-dir",
                str(data_dir),
                cwd=temp_path,
                environment=environment,
            )
            self.assertEqual(approved.returncode, 0, approved.stderr)
            commit_on_main(temp_path / "target", "MORE.md", "more\n", "Advance main")

            rebased = rebase(temp_path, data_dir, run_id, environment)

            self.assertNotEqual(rebased.returncode, 0)
            self.assertIn(
                f"run {run_id} cannot be rebased from state human_approved",
                rebased.stderr,
            )

    def test_rebase_is_rejected_while_a_foreign_claim_is_held(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            environment = {**os.environ, "PYTHONPATH": str(PROJECT_ROOT / "src")}
            data_dir, run_id = create_built_run(temp_path, environment)
            repository = temp_path / "target"
            # Advance main so the fast path does not short-circuit before the claim.
            commit_on_main(repository, "NOTES.md", "notes\n", "Advance main")
            acquire_claim(
                data_dir=data_dir,
                run_id=run_id,
                holder="other-process",
                lease_seconds=100000,
            )
            events_path = data_dir / "runs" / run_id / "events.jsonl"
            events_before = events_path.read_text(encoding="utf-8")

            rebased = rebase(temp_path, data_dir, run_id, environment)

            self.assertNotEqual(rebased.returncode, 0)
            self.assertIn("other-process", rebased.stderr)
            self.assertEqual(events_path.read_text(encoding="utf-8"), events_before)


if __name__ == "__main__":
    unittest.main()
