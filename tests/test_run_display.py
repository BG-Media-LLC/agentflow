from __future__ import annotations

import unittest

from agentflow.run_kernel import (
    RunStatus,
    format_run_choice,
    short_run_id,
    truncate_summary,
)


class RunDisplayTests(unittest.TestCase):
    def test_short_run_id_is_the_first_eight_characters(self) -> None:
        run_id = "abcdef0123456789deadbeef"
        self.assertEqual(short_run_id(run_id), "abcdef01")

    def test_truncate_summary_keeps_short_text(self) -> None:
        self.assertEqual(truncate_summary("Add health endpoint"), "Add health endpoint")

    def test_truncate_summary_ellipsizes_long_text(self) -> None:
        long = "x" * 80
        truncated = truncate_summary(long, max_length=60)
        self.assertEqual(len(truncated), 60)
        self.assertTrue(truncated.endswith("…"))
        self.assertEqual(truncated[:-1], "x" * 59)

    def test_format_run_choice_uses_state_summary_and_short_id(self) -> None:
        status = RunStatus(
            run_id="abcdef0123456789deadbeef",
            state="awaiting_human",
            summary="Add a health endpoint for readiness probes",
            repository="/tmp/target",
            base_sha="a" * 40,
            worktree="/tmp/worktree",
            repository_profile_path=None,
            candidate_sha="b" * 40,
            approved_sha=None,
        )
        self.assertEqual(
            format_run_choice(status),
            "awaiting_human  Add a health endpoint for readiness probes  abcdef01",
        )


if __name__ == "__main__":
    unittest.main()
