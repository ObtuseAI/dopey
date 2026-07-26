from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import subprocess
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]


def run_powershell(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", *args],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def parse_last_json(stdout: str) -> dict[str, object]:
    lines = [line for line in stdout.splitlines() if line.strip()]
    start_index = 0
    for index, line in enumerate(lines):
        if line.lstrip().startswith("{"):
            start_index = index
            break
    return json.loads("\n".join(lines[start_index:]))


class BlunderAutonomyAndTerminalBenchPrepTests(unittest.TestCase):
    def test_approved_inflow_candidates_validate_without_queue_mutation(self) -> None:
        with TemporaryDirectory() as temp_text:
            queue_path = Path(temp_text) / "idle-task-queue.json"
            queue_path.write_text(json.dumps({"version": "1", "tasks": []}), encoding="utf-8")
            report_root = Path(temp_text) / "wiring-report"
            result = run_powershell(
                [
                    "-File",
                    "scripts/obtuse/blunder-wire-approved-inflow-candidates.ps1",
                    "-Mode",
                    "Validate",
                    "-QueuePath",
                    str(queue_path),
                    "-ReportRoot",
                    str(report_root),
                ]
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            report = parse_last_json(result.stdout)
            self.assertEqual(report["status"], "PASS")
            self.assertGreaterEqual(int(report["approvedCandidateCount"]), 1)
            self.assertEqual(int(report["addedTaskCount"]), 0)
            queue = json.loads(queue_path.read_text(encoding="utf-8-sig"))
            self.assertEqual(queue["tasks"], [])

    def test_terminal_bench_minimax_prep_writes_redacted_single_machine_specs(self) -> None:
        with TemporaryDirectory() as temp_text:
            artifact_root = Path(temp_text) / "tb21"
            result = run_powershell(
                [
                    "-File",
                    "scripts/obtuse/terminal-bench-2-1-k1-minimaxm3-blunder.ps1",
                    "-Mode",
                    "Prepare",
                    "-Profile",
                    "TrimmedSingleMachine",
                    "-ArtifactRoot",
                    str(artifact_root),
                ]
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            report = parse_last_json(result.stdout)
            self.assertIn(report["status"], ["PREP_READY", "PREP_NEEDS_REVIEW"])
            self.assertEqual(report["datasetRef"], "terminal-bench/terminal-bench-2-1@1.0.0")
            self.assertEqual(report["modelRoute"], "minimax/minimax-m3")
            self.assertEqual(int(report["k"]), 1)
            self.assertEqual(int(report["nConcurrent"]), 1)
            self.assertEqual(int(report["taskLimit"]), 1)
            preview = " ".join(report["commandPreview"])
            self.assertIn("--env-file <temp-env-file>", preview)
            self.assertNotIn("OPENROUTER_API_KEY=", preview)
            self.assertFalse(bool(report["prepareLaunchedBenchmark"]))


if __name__ == "__main__":
    unittest.main()
