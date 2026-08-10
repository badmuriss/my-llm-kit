from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_resource_guard import (  # noqa: E402
    DENIED_EXIT_CODE,
    ProcessRecord,
    ResourcePolicy,
    ResourceState,
    SessionActivity,
    active_agent_owners,
    active_agent_sessions,
    emergency_session_to_prune,
    heavy_command_roots,
    idle_sessions_to_prune,
    policy_denials,
    prune_excess_idle_agents,
    stale_agent_processes,
)


def process(
    pid: int,
    parent_pid: int,
    executable: str,
    arguments: tuple[str, ...],
    environment: dict[str, str],
    age_seconds: float = 600,
    cpu_ticks: int = 0,
) -> ProcessRecord:
    return ProcessRecord(
        pid=pid,
        parent_pid=parent_pid,
        age_seconds=age_seconds,
        resident_bytes=0,
        executable=executable,
        arguments=arguments,
        environment=environment,
        cpu_ticks=cpu_ticks,
    )


class StaleProcessDetectionBehavior(unittest.TestCase):
    def test_keeps_workloads_owned_by_a_live_agent(self) -> None:
        owner = {"ORCA_TERMINAL_HANDLE": "terminal-live"}
        records = [
            process(10, 1, "codex", ("codex", "resume", "session"), owner),
            process(11, 10, "npm", ("npm", "run", "build"), owner),
        ]

        self.assertEqual(stale_agent_processes(records), [])

    def test_marks_an_old_workload_after_its_agent_exits(self) -> None:
        records = [
            process(
                11,
                1,
                "npm",
                ("npm", "run", "build"),
                {"ORCA_TERMINAL_HANDLE": "terminal-gone"},
            )
        ]

        self.assertEqual([record.pid for record in stale_agent_processes(records)], [11])

    def test_keeps_a_recent_workload_during_the_exit_grace_period(self) -> None:
        records = [
            process(
                11,
                1,
                "npm",
                ("npm", "run", "build"),
                {"ORCA_TERMINAL_HANDLE": "terminal-gone"},
                age_seconds=60,
            )
        ]

        self.assertEqual(stale_agent_processes(records, stale_after_seconds=300), [])

    def test_ignores_manual_workloads_without_an_agent_owner(self) -> None:
        records = [process(11, 1, "npm", ("npm", "run", "dev"), {})]

        self.assertEqual(stale_agent_processes(records), [])

    def test_keeps_the_orca_terminal_shell_after_an_agent_exits(self) -> None:
        records = [
            process(
                11,
                1,
                "bash",
                ("/bin/bash", "--rcfile", "/tmp/orca/rcfile"),
                {"ORCA_TERMINAL_HANDLE": "terminal-gone"},
            )
        ]

        self.assertEqual(stale_agent_processes(records), [])

    def test_uses_a_thread_owner_when_a_terminal_hosts_multiple_sessions(self) -> None:
        terminal = "terminal-shared"
        live_thread = "11111111-1111-1111-1111-111111111111"
        stale_thread = "22222222-2222-2222-2222-222222222222"
        records = [
            process(
                10,
                1,
                "codex",
                ("codex", "resume", live_thread),
                {"ORCA_TERMINAL_HANDLE": terminal},
            ),
            process(
                11,
                1,
                "npm",
                ("npm", "run", "build"),
                {
                    "CODEX_THREAD_ID": stale_thread,
                    "ORCA_TERMINAL_HANDLE": terminal,
                },
            ),
        ]

        self.assertEqual([record.pid for record in stale_agent_processes(records)], [11])


class ResourceAdmissionBehavior(unittest.TestCase):
    def test_counts_each_live_agent_owner_once(self) -> None:
        thread_id = "11111111-1111-1111-1111-111111111111"
        owner = {"ORCA_TERMINAL_HANDLE": "terminal-live"}
        records = [
            process(10, 1, "MainThread", ("node", "/bin/codex", "resume", thread_id), owner),
            process(11, 10, "codex", ("codex", "resume", thread_id), owner),
        ]

        owners = active_agent_owners(records)

        self.assertIn(f"CODEX_THREAD_ID={thread_id}", owners)
        self.assertIn("ORCA_TERMINAL_HANDLE=terminal-live", owners)
        self.assertEqual(
            active_agent_sessions(records),
            {"ORCA_TERMINAL_HANDLE=terminal-live"},
        )

    def test_counts_one_heavy_root_for_a_build_process_tree(self) -> None:
        records = [
            process(20, 1, "npm", ("npm", "run", "build"), {}),
            process(21, 20, "sh", ("sh", "-c", "npm run typecheck"), {}),
            process(22, 21, "npm", ("npm", "run", "typecheck"), {}),
        ]

        self.assertEqual([record.pid for record in heavy_command_roots(records)], [20])

    def test_denies_an_agent_that_exceeds_the_global_limit(self) -> None:
        state = ResourceState(
            active_agents=8,
            heavy_commands=1,
            stale_processes=0,
            available_memory_percent=50,
            managed_memory_percent=30,
            managed_memory_bytes=0,
            total_memory_bytes=0,
        )

        denials = policy_denials(state, ResourcePolicy(), intent="agent", demand=1)

        self.assertTrue(any("active agents" in denial for denial in denials))

    def test_denies_heavy_work_when_memory_is_low(self) -> None:
        state = ResourceState(
            active_agents=2,
            heavy_commands=1,
            stale_processes=0,
            available_memory_percent=10,
            managed_memory_percent=30,
            managed_memory_bytes=0,
            total_memory_bytes=0,
        )

        denials = policy_denials(state, ResourcePolicy(), intent="heavy", demand=1)

        self.assertTrue(any("available memory" in denial for denial in denials))

    def test_uses_a_distinct_exit_code_for_admission_denials(self) -> None:
        self.assertEqual(DENIED_EXIT_CODE, 75)


class IdleAgentCleanupBehavior(unittest.TestCase):
    def test_selects_only_the_oldest_idle_sessions_above_the_limit(self) -> None:
        sessions = [
            SessionActivity("oldest", 0, 100, False),
            SessionActivity("older", 0, 200, False),
            SessionActivity("busy", 0, 50, True),
            SessionActivity("recent", 0, 950, False),
        ]

        selected = idle_sessions_to_prune(
            sessions,
            max_agents=2,
            idle_after_seconds=300,
            now_epoch=1000,
        )

        self.assertEqual(selected, ["oldest", "older"])

    def test_keeps_idle_sessions_when_the_machine_is_within_budget(self) -> None:
        sessions = [SessionActivity("old", 0, 100, False)]

        selected = idle_sessions_to_prune(
            sessions,
            max_agents=2,
            idle_after_seconds=300,
            now_epoch=1000,
        )

        self.assertEqual(selected, [])

    def test_stops_only_the_idle_agent_tree(self) -> None:
        owner = {"ORCA_TERMINAL_HANDLE": "terminal-idle"}
        records = [
            process(5, 1, "bash", ("bash", "--rcfile", "/tmp/rcfile"), owner),
            process(10, 5, "MainThread", ("node", "/bin/codex"), owner, cpu_ticks=10),
            process(11, 10, "codex", ("codex",), owner, cpu_ticks=20),
            process(12, 11, "node", ("node", "worker.js"), owner, cpu_ticks=30),
            process(13, 5, "node", ("node", "manual-server.js"), owner, cpu_ticks=40),
        ]
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            state_path.write_text(
                '{"sessions":{"ORCA_TERMINAL_HANDLE=terminal-idle":'
                '{"cpu_ticks":100,"last_active_epoch":100}}}',
                encoding="utf-8",
            )

            sessions, selected = prune_excess_idle_agents(
                records,
                max_agents=0,
                idle_after_seconds=300,
                grace_seconds=0,
                state_path=state_path,
                dry_run=True,
                now_epoch=1000,
            )

        self.assertEqual(sessions, ["ORCA_TERMINAL_HANDLE=terminal-idle"])
        self.assertEqual({record.pid for record in selected}, {10, 11, 12})


class EmergencyCleanupBehavior(unittest.TestCase):
    def test_selects_the_largest_session_under_critical_pressure(self) -> None:
        state = ResourceState(
            active_agents=3,
            heavy_commands=2,
            stale_processes=0,
            available_memory_percent=8,
            managed_memory_percent=70,
            managed_memory_bytes=0,
            total_memory_bytes=0,
        )

        selected = emergency_session_to_prune(
            state,
            {"small": 100, "large": 500},
            min_available_memory_percent=12,
            max_managed_memory_percent=72,
        )

        self.assertEqual(selected, "large")

    def test_keeps_sessions_when_memory_is_healthy(self) -> None:
        state = ResourceState(
            active_agents=3,
            heavy_commands=2,
            stale_processes=0,
            available_memory_percent=40,
            managed_memory_percent=50,
            managed_memory_bytes=0,
            total_memory_bytes=0,
        )

        selected = emergency_session_to_prune(
            state,
            {"large": 500},
            min_available_memory_percent=12,
            max_managed_memory_percent=72,
        )

        self.assertIsNone(selected)


if __name__ == "__main__":
    unittest.main()
