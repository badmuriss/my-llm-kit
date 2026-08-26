#!/usr/bin/env python3
"""Keep coding-agent workloads from exhausting the desktop session."""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence


DENIED_EXIT_CODE = 75
DEFAULT_MAX_AGENTS = 20
DEFAULT_MAX_HEAVY_COMMANDS = 4
DEFAULT_MIN_AVAILABLE_MEMORY_PERCENT = 20.0
DEFAULT_MAX_MANAGED_MEMORY_PERCENT = 65.0
DEFAULT_EMERGENCY_MAX_MANAGED_MEMORY_PERCENT = 72.0
DEFAULT_EMERGENCY_MIN_AVAILABLE_MEMORY_PERCENT = 12.0
DEFAULT_STALE_AFTER_SECONDS = 300
DEFAULT_IDLE_AGENT_AFTER_SECONDS = 1800
DEFAULT_TERMINATION_GRACE_SECONDS = 3.0

AGENT_EXECUTABLES = frozenset(
    {
        "claude",
        "codex",
        "copilot",
        "cursor-agent",
        "gemini",
        "opencode",
    }
)
OWNER_ENVIRONMENT_KEYS = (
    "CODEX_THREAD_ID",
    "CLAUDE_CODE_SESSION_ID",
    "OPENCODE_SESSION_ID",
    "GEMINI_SESSION_ID",
    "ORCA_TERMINAL_HANDLE",
)
MANAGED_WORKLOAD_EXECUTABLES = frozenset(
    {
        "bash",
        "bun",
        "chrome",
        "chrome-headless-shell",
        "chromium",
        "codex-code-mode",
        "deno",
        "esbuild",
        "node",
        "npm",
        "npx",
        "pnpm",
        "playwright",
        "pytest",
        "python",
        "python3",
        "sh",
        "vite",
        "workerd",
        "wrangler",
        "yarn",
    }
)
MANAGED_COMMAND_MARKERS = (
    "node_modules/",
    "npm run ",
    "npm exec ",
    "npx ",
    "playwright",
    "pytest",
    "vite",
    "workerd",
    "wrangler",
    "codex-code-mode",
)
HEAVY_COMMAND_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\b(?:npm|pnpm|yarn|bun)\s+(?:run\s+)?(?:build|typecheck|test|lint|dev|start)\b",
        r"\b(?:npm|pnpm|yarn|bun)\s+exec\b",
        r"\b(?:playwright|pytest|vitest|jest)\b",
        r"\b(?:next|vite)\s+(?:build|dev)\b",
        r"\bwrangler\s+dev\b",
        r"\b(?:cargo|go)\s+test\b",
    )
)
THREAD_ID_PATTERN = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ProcessRecord:
    pid: int
    parent_pid: int
    age_seconds: float
    resident_bytes: int
    executable: str
    arguments: tuple[str, ...]
    environment: Mapping[str, str]
    cgroups: tuple[str, ...] = ()
    cpu_ticks: int = 0

    @property
    def command(self) -> str:
        return " ".join(self.arguments)


@dataclass(frozen=True)
class ResourcePolicy:
    max_agents: int = DEFAULT_MAX_AGENTS
    max_heavy_commands: int = DEFAULT_MAX_HEAVY_COMMANDS
    min_available_memory_percent: float = DEFAULT_MIN_AVAILABLE_MEMORY_PERCENT
    max_managed_memory_percent: float = DEFAULT_MAX_MANAGED_MEMORY_PERCENT


@dataclass(frozen=True)
class ResourceState:
    active_agents: int
    heavy_commands: int
    stale_processes: int
    available_memory_percent: float
    managed_memory_percent: float
    managed_memory_bytes: int
    total_memory_bytes: int


@dataclass(frozen=True)
class SessionActivity:
    key: str
    cpu_ticks: int
    last_active_epoch: float
    has_heavy_command: bool


def _read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except (FileNotFoundError, PermissionError, ProcessLookupError, OSError):
        return b""


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (FileNotFoundError, PermissionError, ProcessLookupError, OSError):
        return ""


def _read_environment(path: Path) -> dict[str, str]:
    environment: dict[str, str] = {}
    for entry in _read_bytes(path).split(b"\0"):
        key, separator, value = entry.partition(b"=")
        if not separator:
            continue
        decoded_key = key.decode("utf-8", errors="replace")
        if decoded_key not in OWNER_ENVIRONMENT_KEYS and decoded_key not in {
            "CODEX_CI",
            "TERM_PROGRAM",
        }:
            continue
        environment[decoded_key] = value.decode("utf-8", errors="replace")
    return environment


def _read_process(process_path: Path, uptime_seconds: float) -> ProcessRecord | None:
    stat = _read_text(process_path / "stat")
    closing_parenthesis = stat.rfind(")")
    if closing_parenthesis < 0:
        return None

    fields = stat[closing_parenthesis + 2 :].split()
    if len(fields) <= 21:
        return None

    try:
        parent_pid = int(fields[1])
        cpu_ticks = int(fields[11]) + int(fields[12])
        start_ticks = int(fields[19])
        clock_ticks = os.sysconf("SC_CLK_TCK")
        statm = _read_text(process_path / "statm").split()
        resident_pages = int(statm[1]) if len(statm) > 1 else 0
        resident_bytes = resident_pages * os.sysconf("SC_PAGE_SIZE")
    except (ValueError, OSError):
        return None

    arguments = tuple(
        argument.decode("utf-8", errors="replace")
        for argument in _read_bytes(process_path / "cmdline").split(b"\0")
        if argument
    )
    executable = _read_text(process_path / "comm").strip()
    if not arguments and not executable:
        return None

    cgroups = tuple(
        line.partition("::")[2]
        for line in _read_text(process_path / "cgroup").splitlines()
        if "::" in line
    )
    return ProcessRecord(
        pid=int(process_path.name),
        parent_pid=parent_pid,
        age_seconds=max(0.0, uptime_seconds - (start_ticks / clock_ticks)),
        resident_bytes=resident_bytes,
        executable=executable,
        arguments=arguments,
        environment=_read_environment(process_path / "environ"),
        cgroups=cgroups,
        cpu_ticks=cpu_ticks,
    )


def read_processes(proc_root: Path = Path("/proc")) -> list[ProcessRecord]:
    uptime_text = _read_text(proc_root / "uptime").split()
    uptime_seconds = float(uptime_text[0]) if uptime_text else 0.0
    processes: list[ProcessRecord] = []
    for process_path in proc_root.iterdir():
        if not process_path.name.isdigit():
            continue
        process = _read_process(process_path, uptime_seconds)
        if process is not None:
            processes.append(process)
    return processes


def _argument_executable(process: ProcessRecord) -> str:
    if not process.arguments:
        return process.executable
    return Path(process.arguments[0]).name


def is_agent_process(process: ProcessRecord) -> bool:
    executable = _argument_executable(process)
    if process.executable in AGENT_EXECUTABLES or executable in AGENT_EXECUTABLES:
        return True
    if executable not in {"node", "bun"}:
        return False
    return any(
        Path(argument).name in AGENT_EXECUTABLES
        for argument in process.arguments[1:3]
    )


def process_owner(process: ProcessRecord) -> str | None:
    for key in OWNER_ENVIRONMENT_KEYS[:-1]:
        value = process.environment.get(key)
        if value:
            return f"{key}={value}"

    if is_agent_process(process):
        thread_ids = THREAD_ID_PATTERN.findall(process.command)
        if thread_ids:
            return f"CODEX_THREAD_ID={thread_ids[-1]}"

    terminal_handle = process.environment.get("ORCA_TERMINAL_HANDLE")
    if terminal_handle:
        return f"ORCA_TERMINAL_HANDLE={terminal_handle}"
    if is_agent_process(process):
        return f"pid={process.pid}"
    return None


def active_agent_owners(processes: Sequence[ProcessRecord]) -> set[str]:
    owners: set[str] = set()
    for process in processes:
        if not is_agent_process(process):
            continue
        owner = process_owner(process)
        if owner is not None:
            owners.add(owner)
        terminal_handle = process.environment.get("ORCA_TERMINAL_HANDLE")
        if terminal_handle:
            owners.add(f"ORCA_TERMINAL_HANDLE={terminal_handle}")
    return owners


def active_agent_sessions(processes: Sequence[ProcessRecord]) -> set[str]:
    return {
        session
        for process in processes
        if is_agent_process(process)
        for session in (process_session(process),)
        if session is not None
    }


def process_session(process: ProcessRecord) -> str | None:
    terminal_handle = process.environment.get("ORCA_TERMINAL_HANDLE")
    if terminal_handle:
        return f"ORCA_TERMINAL_HANDLE={terminal_handle}"
    return process_owner(process)


def _has_agent_ancestor(
    process: ProcessRecord,
    processes_by_pid: Mapping[int, ProcessRecord],
) -> bool:
    seen: set[int] = set()
    parent_pid = process.parent_pid
    while parent_pid > 1 and parent_pid not in seen:
        seen.add(parent_pid)
        parent = processes_by_pid.get(parent_pid)
        if parent is None:
            return False
        if is_agent_process(parent):
            return True
        parent_pid = parent.parent_pid
    return False


def is_managed_workload(process: ProcessRecord) -> bool:
    executable = _argument_executable(process)
    command = process.command.lower()
    if process.executable in {"bash", "sh"} or executable in {"bash", "sh"}:
        return any(marker in command for marker in MANAGED_COMMAND_MARKERS)
    if process.executable in MANAGED_WORKLOAD_EXECUTABLES:
        return True
    if executable in MANAGED_WORKLOAD_EXECUTABLES:
        return True
    return any(marker in command for marker in MANAGED_COMMAND_MARKERS)


def stale_agent_processes(
    processes: Sequence[ProcessRecord],
    stale_after_seconds: float = DEFAULT_STALE_AFTER_SECONDS,
) -> list[ProcessRecord]:
    live_owners = active_agent_owners(processes)
    processes_by_pid = {process.pid: process for process in processes}
    stale: list[ProcessRecord] = []
    for process in processes:
        if process.pid == os.getpid() or is_agent_process(process):
            continue
        owner = process_owner(process)
        if owner is None or owner in live_owners:
            continue
        if process.age_seconds < stale_after_seconds:
            continue
        if _has_agent_ancestor(process, processes_by_pid):
            continue
        if is_managed_workload(process):
            stale.append(process)
    return stale


def is_heavy_command(process: ProcessRecord) -> bool:
    return any(pattern.search(process.command) for pattern in HEAVY_COMMAND_PATTERNS)


def heavy_command_roots(processes: Sequence[ProcessRecord]) -> list[ProcessRecord]:
    processes_by_pid = {process.pid: process for process in processes}
    heavy = {process.pid: process for process in processes if is_heavy_command(process)}
    roots: list[ProcessRecord] = []
    for process in heavy.values():
        parent_pid = process.parent_pid
        has_heavy_ancestor = False
        seen: set[int] = set()
        while parent_pid > 1 and parent_pid not in seen:
            seen.add(parent_pid)
            if parent_pid in heavy:
                has_heavy_ancestor = True
                break
            parent = processes_by_pid.get(parent_pid)
            if parent is None:
                break
            parent_pid = parent.parent_pid
        if not has_heavy_ancestor:
            roots.append(process)
    return roots


def _memory_totals(proc_root: Path = Path("/proc")) -> tuple[int, int]:
    values: dict[str, int] = {}
    for line in _read_text(proc_root / "meminfo").splitlines():
        key, separator, raw_value = line.partition(":")
        if not separator:
            continue
        number = raw_value.strip().split()[0]
        try:
            values[key] = int(number) * 1024
        except ValueError:
            continue
    return values.get("MemTotal", 0), values.get("MemAvailable", 0)


def _managed_cgroup_memory(
    processes: Sequence[ProcessRecord],
    cgroup_root: Path = Path("/sys/fs/cgroup"),
) -> int:
    cgroups = {
        cgroup
        for process in processes
        if is_agent_process(process)
        for cgroup in process.cgroups
        if cgroup
    }
    memory_bytes = 0
    for cgroup in cgroups:
        value = _read_text(cgroup_root / cgroup.lstrip("/") / "memory.current").strip()
        try:
            memory_bytes += int(value)
        except ValueError:
            continue
    return memory_bytes


def resource_state(
    processes: Sequence[ProcessRecord],
    proc_root: Path = Path("/proc"),
    cgroup_root: Path = Path("/sys/fs/cgroup"),
    stale_after_seconds: float = DEFAULT_STALE_AFTER_SECONDS,
) -> ResourceState:
    total_memory, available_memory = _memory_totals(proc_root)
    managed_memory = _managed_cgroup_memory(processes, cgroup_root)
    available_percent = (
        available_memory * 100 / total_memory if total_memory else 100.0
    )
    managed_percent = managed_memory * 100 / total_memory if total_memory else 0.0
    return ResourceState(
        active_agents=len(active_agent_sessions(processes)),
        heavy_commands=len(heavy_command_roots(processes)),
        stale_processes=len(stale_agent_processes(processes, stale_after_seconds)),
        available_memory_percent=available_percent,
        managed_memory_percent=managed_percent,
        managed_memory_bytes=managed_memory,
        total_memory_bytes=total_memory,
    )


def policy_denials(
    state: ResourceState,
    policy: ResourcePolicy,
    intent: str,
    demand: int,
) -> list[str]:
    requested_agents = demand if intent == "agent" else 0
    requested_heavy_commands = demand if intent == "heavy" else 0
    denials: list[str] = []
    if state.active_agents + requested_agents > policy.max_agents:
        denials.append(
            f"active agents would reach {state.active_agents + requested_agents}; "
            f"limit is {policy.max_agents}"
        )
    if state.heavy_commands + requested_heavy_commands > policy.max_heavy_commands:
        denials.append(
            f"heavy commands would reach {state.heavy_commands + requested_heavy_commands}; "
            f"limit is {policy.max_heavy_commands}"
        )
    if state.available_memory_percent < policy.min_available_memory_percent:
        denials.append(
            f"available memory is {state.available_memory_percent:.1f}%; "
            f"minimum is {policy.min_available_memory_percent:.1f}%"
        )
    if state.managed_memory_percent > policy.max_managed_memory_percent:
        denials.append(
            f"agent cgroups use {state.managed_memory_percent:.1f}% of memory; "
            f"limit is {policy.max_managed_memory_percent:.1f}%"
        )
    return denials


def idle_sessions_to_prune(
    sessions: Sequence[SessionActivity],
    max_agents: int,
    idle_after_seconds: float,
    now_epoch: float,
) -> list[str]:
    excess_sessions = max(0, len(sessions) - max_agents)
    if excess_sessions == 0:
        return []
    eligible = [
        session
        for session in sessions
        if not session.has_heavy_command
        and now_epoch - session.last_active_epoch >= idle_after_seconds
    ]
    eligible.sort(key=lambda session: session.last_active_epoch)
    return [session.key for session in eligible[:excess_sessions]]


def _default_state_path() -> Path:
    state_root = os.environ.get("XDG_STATE_HOME")
    if state_root:
        return Path(state_root) / "my-llm-kit" / "resource-guard.json"
    return Path.home() / ".local" / "state" / "my-llm-kit" / "resource-guard.json"


def _read_session_state(state_path: Path) -> dict[str, dict[str, float | int]]:
    try:
        value = json.loads(state_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    sessions = value.get("sessions") if isinstance(value, dict) else None
    if not isinstance(sessions, dict):
        return {}
    return {
        str(key): session
        for key, session in sessions.items()
        if isinstance(session, dict)
    }


def _write_session_state(
    state_path: Path,
    sessions: Mapping[str, Mapping[str, float | int]],
) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = state_path.with_suffix(".tmp")
    temporary_path.write_text(
        json.dumps({"sessions": sessions}, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(state_path)


def _session_processes(
    processes: Sequence[ProcessRecord],
) -> dict[str, list[ProcessRecord]]:
    sessions = active_agent_sessions(processes)
    grouped = {session: [] for session in sessions}
    for process in processes:
        session = process_session(process)
        if session in grouped:
            grouped[session].append(process)
    return grouped


def _descendants_of(
    root_pids: set[int],
    processes: Sequence[ProcessRecord],
) -> list[ProcessRecord]:
    selected_pids = set(root_pids)
    changed = True
    while changed:
        changed = False
        for process in processes:
            if process.pid in selected_pids or process.parent_pid not in selected_pids:
                continue
            selected_pids.add(process.pid)
            changed = True
    return [process for process in processes if process.pid in selected_pids]


def _processes_for_agent_sessions(
    selected_sessions: Sequence[str],
    grouped: Mapping[str, Sequence[ProcessRecord]],
    processes: Sequence[ProcessRecord],
) -> list[ProcessRecord]:
    root_agent_pids = {
        process.pid
        for key in selected_sessions
        for process in grouped[key]
        if is_agent_process(process)
    }
    return [
        process
        for process in _descendants_of(root_agent_pids, processes)
        if _argument_executable(process) not in {"bash", "sh"}
    ]


def prune_excess_idle_agents(
    processes: Sequence[ProcessRecord],
    max_agents: int,
    idle_after_seconds: float,
    grace_seconds: float,
    state_path: Path,
    dry_run: bool,
    now_epoch: float | None = None,
) -> tuple[list[str], list[ProcessRecord]]:
    now = time.time() if now_epoch is None else now_epoch
    previous_state = _read_session_state(state_path)
    grouped = _session_processes(processes)
    next_state: dict[str, dict[str, float | int]] = {}
    activities: list[SessionActivity] = []
    for key, session_processes in grouped.items():
        cpu_ticks = sum(process.cpu_ticks for process in session_processes)
        previous = previous_state.get(key, {})
        previous_ticks = int(previous.get("cpu_ticks", -1))
        previous_active = float(previous.get("last_active_epoch", now))
        last_active = now if previous_ticks != cpu_ticks else previous_active
        has_heavy_command = any(is_heavy_command(process) for process in session_processes)
        activities.append(
            SessionActivity(
                key=key,
                cpu_ticks=cpu_ticks,
                last_active_epoch=last_active,
                has_heavy_command=has_heavy_command,
            )
        )
        next_state[key] = {
            "cpu_ticks": cpu_ticks,
            "last_active_epoch": last_active,
            "last_seen_epoch": now,
        }

    selected_sessions = idle_sessions_to_prune(
        activities,
        max_agents=max_agents,
        idle_after_seconds=idle_after_seconds,
        now_epoch=now,
    )
    selected_processes = _processes_for_agent_sessions(
        selected_sessions,
        grouped,
        processes,
    )
    if not dry_run:
        _write_session_state(state_path, next_state)
        if selected_processes:
            _signal_processes(selected_processes, signal.SIGTERM)
            deadline = time.monotonic() + grace_seconds
            remaining = selected_processes
            while remaining and time.monotonic() < deadline:
                time.sleep(0.1)
                remaining = [
                    process
                    for process in remaining
                    if Path(f"/proc/{process.pid}").exists()
                ]
            _signal_processes(remaining, signal.SIGKILL)
    return selected_sessions, selected_processes


def emergency_session_to_prune(
    state: ResourceState,
    session_resident_bytes: Mapping[str, int],
    min_available_memory_percent: float,
    max_managed_memory_percent: float,
) -> str | None:
    memory_is_critical = (
        state.available_memory_percent < min_available_memory_percent
        or state.managed_memory_percent > max_managed_memory_percent
    )
    if not memory_is_critical or not session_resident_bytes:
        return None
    return max(session_resident_bytes, key=session_resident_bytes.__getitem__)


def prune_emergency_agent(
    processes: Sequence[ProcessRecord],
    state: ResourceState,
    min_available_memory_percent: float,
    max_managed_memory_percent: float,
    grace_seconds: float,
    dry_run: bool,
) -> tuple[str | None, list[ProcessRecord]]:
    grouped = _session_processes(processes)
    resident_bytes = {
        key: sum(process.resident_bytes for process in session_processes)
        for key, session_processes in grouped.items()
    }
    selected_session = emergency_session_to_prune(
        state,
        resident_bytes,
        min_available_memory_percent=min_available_memory_percent,
        max_managed_memory_percent=max_managed_memory_percent,
    )
    if selected_session is None:
        return None, []
    selected_processes = _processes_for_agent_sessions(
        [selected_session],
        grouped,
        processes,
    )
    if not dry_run and selected_processes:
        _signal_processes(selected_processes, signal.SIGTERM)
        deadline = time.monotonic() + grace_seconds
        remaining = selected_processes
        while remaining and time.monotonic() < deadline:
            time.sleep(0.1)
            remaining = [
                process
                for process in remaining
                if Path(f"/proc/{process.pid}").exists()
            ]
        _signal_processes(remaining, signal.SIGKILL)
    return selected_session, selected_processes


def _signal_processes(processes: Iterable[ProcessRecord], process_signal: signal.Signals) -> None:
    for process in processes:
        try:
            os.kill(process.pid, process_signal)
        except (ProcessLookupError, PermissionError):
            continue


def prune_stale_processes(
    processes: Sequence[ProcessRecord],
    stale_after_seconds: float,
    grace_seconds: float,
    dry_run: bool,
) -> list[ProcessRecord]:
    stale = stale_agent_processes(processes, stale_after_seconds)
    if dry_run or not stale:
        return stale

    _signal_processes(stale, signal.SIGTERM)
    deadline = time.monotonic() + grace_seconds
    remaining = stale
    while remaining and time.monotonic() < deadline:
        time.sleep(0.1)
        remaining = [process for process in remaining if Path(f"/proc/{process.pid}").exists()]
    _signal_processes(remaining, signal.SIGKILL)
    return stale


def _format_bytes(value: int) -> str:
    gibibytes = value / (1024**3)
    return f"{gibibytes:.1f} GiB"


def _print_state(state: ResourceState, as_json: bool) -> None:
    if as_json:
        print(json.dumps(asdict(state), sort_keys=True))
        return
    print(
        "agents={active_agents} heavy={heavy_commands} stale={stale_processes} "
        "available={available_memory_percent:.1f}% managed={managed}".format(
            **asdict(state),
            managed=_format_bytes(state.managed_memory_bytes),
        )
    )


def _positive_integer(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("status", "check", "prune"), nargs="?", default="status")
    parser.add_argument("--intent", choices=("agent", "heavy"), default="heavy")
    parser.add_argument("--demand", type=_positive_integer, default=1)
    parser.add_argument("--max-agents", type=_positive_integer, default=DEFAULT_MAX_AGENTS)
    parser.add_argument(
        "--max-heavy-commands",
        type=_positive_integer,
        default=DEFAULT_MAX_HEAVY_COMMANDS,
    )
    parser.add_argument(
        "--min-available-memory-percent",
        type=float,
        default=DEFAULT_MIN_AVAILABLE_MEMORY_PERCENT,
    )
    parser.add_argument(
        "--max-managed-memory-percent",
        type=float,
        default=DEFAULT_MAX_MANAGED_MEMORY_PERCENT,
    )
    parser.add_argument(
        "--emergency-min-available-memory-percent",
        type=float,
        default=DEFAULT_EMERGENCY_MIN_AVAILABLE_MEMORY_PERCENT,
    )
    parser.add_argument(
        "--emergency-max-managed-memory-percent",
        type=float,
        default=DEFAULT_EMERGENCY_MAX_MANAGED_MEMORY_PERCENT,
    )
    parser.add_argument(
        "--stale-after-seconds",
        type=float,
        default=DEFAULT_STALE_AFTER_SECONDS,
    )
    parser.add_argument(
        "--idle-agent-after-seconds",
        type=float,
        default=DEFAULT_IDLE_AGENT_AFTER_SECONDS,
    )
    parser.add_argument("--state-path", type=Path, default=_default_state_path())
    parser.add_argument(
        "--termination-grace-seconds",
        type=float,
        default=DEFAULT_TERMINATION_GRACE_SECONDS,
    )
    parser.add_argument("--prune", action="store_true", help="remove stale workloads before checking")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    options = build_parser().parse_args(arguments)
    if sys.platform != "linux":
        print(
            "agent-resource-guard is Linux-only; use the host and operating system "
            "process controls on this platform",
            file=sys.stderr,
        )
        return 2
    processes = read_processes()
    pruned: list[ProcessRecord] = []
    pruned_sessions: list[str] = []
    if options.command == "prune" or options.prune:
        pruned = prune_stale_processes(
            processes,
            stale_after_seconds=options.stale_after_seconds,
            grace_seconds=options.termination_grace_seconds,
            dry_run=options.dry_run,
        )
        if pruned:
            action = "would prune" if options.dry_run else "pruned"
            print(f"{action} {len(pruned)} stale agent-owned process(es)")
        pruned_sessions, _pruned_agent_processes = prune_excess_idle_agents(
            processes,
            max_agents=options.max_agents,
            idle_after_seconds=options.idle_agent_after_seconds,
            grace_seconds=options.termination_grace_seconds,
            state_path=options.state_path,
            dry_run=options.dry_run,
        )
        if pruned_sessions:
            action = "would stop" if options.dry_run else "stopped"
            print(f"{action} {len(pruned_sessions)} excess idle agent session(s)")
        processes = read_processes()
        current_state = resource_state(
            processes,
            stale_after_seconds=options.stale_after_seconds,
        )
        emergency_session, _emergency_processes = prune_emergency_agent(
            processes,
            current_state,
            min_available_memory_percent=options.emergency_min_available_memory_percent,
            max_managed_memory_percent=options.emergency_max_managed_memory_percent,
            grace_seconds=options.termination_grace_seconds,
            dry_run=options.dry_run,
        )
        if emergency_session is not None:
            action = "would stop" if options.dry_run else "stopped"
            print(f"{action} largest agent session under critical memory pressure")
        processes = read_processes()

    state = resource_state(
        processes,
        stale_after_seconds=options.stale_after_seconds,
    )
    if options.command == "prune":
        if not options.quiet:
            _print_state(state, options.json)
        return 0
    if options.command == "status":
        _print_state(state, options.json)
        return 0

    policy = ResourcePolicy(
        max_agents=options.max_agents,
        max_heavy_commands=options.max_heavy_commands,
        min_available_memory_percent=options.min_available_memory_percent,
        max_managed_memory_percent=options.max_managed_memory_percent,
    )
    denials = policy_denials(state, policy, options.intent, options.demand)
    if denials:
        if options.json:
            print(json.dumps({"allowed": False, "denials": denials, "state": asdict(state)}))
        elif not options.quiet:
            _print_state(state, False)
            for denial in denials:
                print(f"DENY: {denial}", file=sys.stderr)
        return DENIED_EXIT_CODE

    if options.json:
        print(json.dumps({"allowed": True, "denials": [], "state": asdict(state)}))
    elif not options.quiet:
        _print_state(state, False)
        print("ALLOW")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
