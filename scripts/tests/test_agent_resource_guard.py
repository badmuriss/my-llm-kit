from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_resource_guard import (  # noqa: E402
    ProcessRecord,
    is_agent_process,
    stale_agent_processes,
)


def process(
    pid: int,
    parent_pid: int,
    executable: str,
    arguments: tuple[str, ...],
    environment: dict[str, str],
    age_seconds: float = 600,
) -> ProcessRecord:
    return ProcessRecord(
        pid=pid,
        parent_pid=parent_pid,
        age_seconds=age_seconds,
        resident_bytes=0,
        executable=executable,
        arguments=arguments,
        environment=environment,
    )


class OmpSessionDetectionBehavior(unittest.TestCase):
    def test_recognizes_an_omp_binary_as_an_agent(self) -> None:
        record = process(
            10,
            1,
            "omp",
            ("/home/user/.bun/bin/omp", "--extension", "status.ts"),
            {},
        )

        self.assertTrue(is_agent_process(record))

    def test_recognizes_a_bun_launched_omp_session_as_an_agent(self) -> None:
        record = process(
            10,
            1,
            "bun",
            ("bun", "/home/user/.bun/bin/omp", "--extension", "status.ts"),
            {},
        )

        self.assertTrue(is_agent_process(record))

    def test_keeps_a_long_running_workload_under_a_live_omp_session(self) -> None:
        owner = {"ORCA_TERMINAL_HANDLE": "terminal-omp"}
        records = [
            process(10, 1, "omp", ("/home/user/.bun/bin/omp",), owner),
            process(11, 10, "python3", ("python3", "-"), owner),
        ]

        self.assertEqual(stale_agent_processes(records), [])

    def test_marks_an_old_bun_workload_that_is_not_an_agent(self) -> None:
        owner = {"ORCA_TERMINAL_HANDLE": "terminal-detached"}
        records = [process(10, 1, "bun", ("bun", "run", "server.ts"), owner)]

        self.assertEqual([record.pid for record in stale_agent_processes(records)], [10])


if __name__ == "__main__":
    unittest.main()
