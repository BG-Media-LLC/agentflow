"""Adversarial confinement probes for the read-only web UI.

The base suite pins run-directory escape via a symlink out of ``runs/`` and
evidence/transcript escape via a symlink to a target *outside* the Agentflow
Home entirely, plus circular symlinks at the ``build_projection`` /
``iter_run_stream`` function level. These strengthen the acceptance criterion
"refuse evidence or transcript symlinks that escape the run directory; treat
circular/self-referential ... symlinks as confinement failures (skip that path,
never raise so /api/projection and SSE continue for sibling in-bounds runs)"
along two axes the base suite leaves open:

* a symlink that escapes the *run* directory while staying *inside* ``runs/``
  (a sibling-run escape) — refusing this needs the containment boundary to be
  the run directory, not merely ``runs/``; and
* the confinement guarantees exercised through the live HTTP surface, where a
  raise would surface as a 500 / broken stream rather than a skipped path.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import threading
import tempfile
import unittest
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


PROJECT_ROOT = Path(__file__).parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from agentflow.projection import (  # noqa: E402
    build_projection,
    confined_file,
)
from agentflow.web_ui import (  # noqa: E402
    create_web_server,
    iter_run_stream,
)
from agentflow.work_graph import save_work_graph  # noqa: E402


def _write_run(
    run_dir: Path,
    *,
    events: list[dict],
    summary: str = "A run",
) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "events.jsonl").write_text(
        "".join(json.dumps(event) + "\n" for event in events),
        encoding="utf-8",
    )
    (run_dir / "task.json").write_text(
        json.dumps({"summary": summary}), encoding="utf-8"
    )
    (run_dir / "repository.json").write_text(
        json.dumps({"repository": "/target", "base_sha": "base"}),
        encoding="utf-8",
    )


def _snapshot(root: Path) -> dict[Path, bytes]:
    return {
        path.relative_to(root): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def _sse_sources(frames: list[str]) -> set[str]:
    sources: set[str] = set()
    for frame in frames:
        for line in frame.splitlines():
            if line.startswith("data:"):
                sources.add(json.loads(line[len("data:"):].strip())["source"])
    return sources


class _Served:
    def __init__(self, *, data_dir: Path, repository: Path) -> None:
        self.server = create_web_server(
            data_dir=data_dir, repository=repository, host="127.0.0.1", port=0
        )
        host, port = self.server.server_address[:2]
        self.base_url = f"http://{host}:{port}"
        self._thread = threading.Thread(
            target=self.server.serve_forever, daemon=True
        )

    def __enter__(self) -> "_Served":
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.server.shutdown()
        self.server.server_close()
        self._thread.join(timeout=5)

    def get(self, path: str) -> tuple[int, bytes]:
        try:
            with urlopen(self.base_url + path, timeout=8) as response:
                return response.status, response.read()
        except HTTPError as error:
            return error.code, error.read()


class SiblingRunEscapeTests(unittest.TestCase):
    """A symlink escaping the run directory into a sibling run must be refused."""

    def test_evidence_symlink_into_sibling_run_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            data_dir = temp_path / "home"
            repository = temp_path / "target"
            repository.mkdir()
            save_work_graph([], repository)

            runs = data_dir / "runs"
            _write_run(
                runs / "run-ok",
                events=[
                    {"run_id": "run-ok", "sequence": 1, "type": "run_created"}
                ],
            )
            # run-x has no real events of its own; its events.jsonl is a symlink
            # to a SIBLING run's events file. That escapes run-x's directory even
            # though it stays inside runs/, so it must be refused (read as absent)
            # and run-x must not appear — least of all wearing run-ok's evidence.
            run_x = runs / "run-x"
            run_x.mkdir(parents=True)
            os.symlink(runs / "run-ok" / "events.jsonl", run_x / "events.jsonl")

            self.assertIsNone(confined_file(run_x, "events.jsonl"))
            projection = build_projection(
                data_dir=data_dir, repository=repository
            )
            run_ids = {entry["run_id"] for entry in projection["runs"]}
            self.assertEqual(run_ids, {"run-ok"})

    def test_transcript_symlink_into_sibling_run_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            runs = temp_path / "runs"
            _write_run(
                runs / "run-a",
                events=[
                    {"run_id": "run-a", "sequence": 1, "type": "run_created"}
                ],
            )
            (runs / "run-a" / "builder-1-transcript.jsonl").write_text(
                json.dumps({"text": "in-bounds"}) + "\n", encoding="utf-8"
            )
            _write_run(
                runs / "run-b",
                events=[
                    {"run_id": "run-b", "sequence": 1, "type": "run_created"}
                ],
            )
            secret = runs / "run-b" / "builder-1-transcript.jsonl"
            secret.write_text(
                json.dumps({"text": "sibling-secret"}) + "\n", encoding="utf-8"
            )
            # run-a exposes run-b's transcript via a symlink; escaping the run
            # directory must refuse it even though the target lives in runs/.
            os.symlink(secret, runs / "run-a" / "reviewer-1-transcript.jsonl")

            self.assertIsNone(
                confined_file(runs / "run-a", "reviewer-1-transcript.jsonl")
            )
            frames = list(iter_run_stream(runs / "run-a", follow=False))
            sources = _sse_sources(frames)
            self.assertIn("builder-1-transcript.jsonl", sources)
            self.assertNotIn("reviewer-1-transcript.jsonl", sources)
            body = "".join(frames)
            self.assertNotIn("sibling-secret", body)


class EvidenceStreamConfinementTests(unittest.TestCase):
    """The stream confines events.jsonl the same way it confines transcripts."""

    def test_escaping_events_symlink_is_skipped_but_transcript_streams(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            run_dir = temp_path / "runs" / "run-a"
            run_dir.mkdir(parents=True)
            # events.jsonl escapes the run directory entirely.
            outside = temp_path / "outside-events.jsonl"
            outside.write_text(
                json.dumps(
                    {"run_id": "run-a", "sequence": 1, "type": "human_approved"}
                )
                + "\n",
                encoding="utf-8",
            )
            os.symlink(outside, run_dir / "events.jsonl")
            (run_dir / "builder-1-transcript.jsonl").write_text(
                json.dumps({"text": "in-bounds"}) + "\n", encoding="utf-8"
            )

            self.assertIsNone(confined_file(run_dir, "events.jsonl"))
            frames = list(iter_run_stream(run_dir, follow=False))
            sources = _sse_sources(frames)
            # The escaping events file is skipped; the in-bounds transcript is
            # still streamed and no smuggled event content appears.
            self.assertNotIn("events.jsonl", sources)
            self.assertIn("builder-1-transcript.jsonl", sources)
            self.assertNotIn("human_approved", "".join(frames))


class HttpConfinementTests(unittest.TestCase):
    """Confinement guarantees observed through the live HTTP surface."""

    def test_stream_404_for_symlinked_run_dir_escaping_runs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            data_dir = temp_path / "home"
            repository = temp_path / "target"
            repository.mkdir()
            save_work_graph([], repository)
            (data_dir / "runs").mkdir(parents=True)
            # A fully-formed run directory outside runs/, reachable only via a
            # symlink placed inside runs/. The stream route must 404, not serve.
            outside = data_dir / "outside-run"
            _write_run(
                outside,
                events=[
                    {"run_id": "escape", "sequence": 1, "type": "run_created"}
                ],
            )
            os.symlink(outside, data_dir / "runs" / "escape")

            with _Served(data_dir=data_dir, repository=repository) as served:
                status, _ = served.get("/api/runs/escape/stream?follow=0")
            self.assertEqual(status, 404)

    def test_projection_http_serves_sibling_past_circular_evidence(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            data_dir = temp_path / "home"
            repository = temp_path / "target"
            repository.mkdir()
            save_work_graph([], repository)
            _write_run(
                data_dir / "runs" / "run-ok",
                events=[
                    {"run_id": "run-ok", "sequence": 1, "type": "run_created"}
                ],
            )
            loop = data_dir / "runs" / "run-loop"
            loop.mkdir(parents=True)
            os.symlink(loop / "events.jsonl", loop / "events.jsonl")

            before = _snapshot(temp_path)
            with _Served(data_dir=data_dir, repository=repository) as served:
                status, body = served.get("/api/projection")
            # A confinement failure on one run must not 500 the endpoint; the
            # in-bounds sibling is still served, and nothing was written.
            self.assertEqual(status, 200)
            run_ids = {
                entry["run_id"] for entry in json.loads(body)["runs"]
            }
            self.assertEqual(run_ids, {"run-ok"})
            self.assertEqual(_snapshot(temp_path), before)

    def test_http_sse_skips_circular_transcript_and_still_serves_events(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            data_dir = temp_path / "home"
            repository = temp_path / "target"
            repository.mkdir()
            save_work_graph([], repository)
            run_dir = data_dir / "runs" / "run-a"
            _write_run(
                run_dir,
                events=[
                    {"run_id": "run-a", "sequence": 1, "type": "run_created"}
                ],
            )
            (run_dir / "builder-1-transcript.jsonl").write_text(
                json.dumps({"text": "in-bounds"}) + "\n", encoding="utf-8"
            )
            circular = run_dir / "reviewer-1-transcript.jsonl"
            os.symlink(circular, circular)

            with _Served(data_dir=data_dir, repository=repository) as served:
                try:
                    status, body = served.get(
                        "/api/runs/run-a/stream?follow=0"
                    )
                except URLError as error:  # pragma: no cover - failure signal
                    self.fail(f"SSE stream errored on a circular symlink: {error}")
            self.assertEqual(status, 200)
            sources = _sse_sources(body.decode("utf-8").split("\n\n"))
            self.assertIn("events.jsonl", sources)
            self.assertIn("builder-1-transcript.jsonl", sources)
            self.assertNotIn("reviewer-1-transcript.jsonl", sources)


if __name__ == "__main__":
    unittest.main()
