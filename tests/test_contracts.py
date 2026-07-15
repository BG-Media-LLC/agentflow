from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agentflow.contracts import (
    ContractError,
    MIN_PLAN_TEXT_LENGTH,
    validate_plan,
    validate_planned_paths,
)


def valid_plan(**overrides):
    plan = {
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
    plan.update(overrides)
    return plan


class PlanContractTests(unittest.TestCase):
    def test_rejects_empty_files_to_modify(self) -> None:
        with self.assertRaisesRegex(ContractError, "non-empty"):
            validate_plan(valid_plan(files_to_modify=[]))

    def test_rejects_escape_paths(self) -> None:
        with self.assertRaisesRegex(ContractError, "within the Workspace"):
            validate_plan(valid_plan(files_to_modify=["../outside.txt"]))
        with self.assertRaisesRegex(ContractError, "within the Workspace"):
            validate_plan(valid_plan(files_to_modify=["/tmp/outside.txt"]))

    def test_rejects_exact_19_character_substance(self) -> None:
        nineteen = "x" * (MIN_PLAN_TEXT_LENGTH - 1)
        self.assertEqual(len(nineteen), 19)
        with self.assertRaisesRegex(ContractError, "at least 20 characters"):
            validate_plan(valid_plan(summary=nineteen))
        with self.assertRaisesRegex(ContractError, "at least 20 characters"):
            validate_plan(
                valid_plan(
                    steps=[
                        {
                            "description": nineteen,
                            "id": "P1",
                            "verification": "The authoritative checks pass",
                        }
                    ]
                )
            )
        with self.assertRaisesRegex(ContractError, "at least 20 characters"):
            validate_plan(
                valid_plan(
                    steps=[
                        {
                            "description": "Document the health endpoint",
                            "id": "P1",
                            "verification": nineteen,
                        }
                    ]
                )
            )

    def test_accepts_exact_20_character_substance(self) -> None:
        twenty = "y" * MIN_PLAN_TEXT_LENGTH
        self.assertEqual(len(twenty), 20)
        plan = validate_plan(
            valid_plan(
                summary=twenty,
                steps=[
                    {
                        "description": twenty,
                        "id": "P1",
                        "verification": twenty,
                    }
                ],
            )
        )
        self.assertEqual(plan["summary"], twenty)

    def test_rejects_directory_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            (workspace / "docs").mkdir()
            (workspace / "README.md").write_text("# hi\n", encoding="utf-8")
            plan = validate_plan(valid_plan(files_to_modify=["docs"]))
            with self.assertRaisesRegex(ContractError, "regular file"):
                validate_planned_paths(plan=plan, workspace=workspace)

    def test_rejects_missing_parents(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            (workspace / "README.md").write_text("# hi\n", encoding="utf-8")
            plan = validate_plan(
                valid_plan(files_to_modify=["missing-dir/new-file.txt"])
            )
            with self.assertRaisesRegex(ContractError, "parent directory"):
                validate_planned_paths(plan=plan, workspace=workspace)

    def test_accepts_new_file_with_existing_parent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            (workspace / "docs").mkdir()
            (workspace / "README.md").write_text("# hi\n", encoding="utf-8")
            plan = validate_plan(
                valid_plan(files_to_modify=["docs/new-file.txt", "README.md"])
            )
            validate_planned_paths(plan=plan, workspace=workspace)

    def test_validate_plan_skips_filesystem_checks(self) -> None:
        # Adapter-local validation must accept shape-valid paths without a
        # Workspace so Cursor/Claude local validation does not require parents.
        plan = validate_plan(
            valid_plan(files_to_modify=["missing-dir/new-file.txt"])
        )
        self.assertEqual(plan["files_to_modify"], ["missing-dir/new-file.txt"])


if __name__ == "__main__":
    unittest.main()
