from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "skills/agent-graph/scripts"
sys.path.insert(0, str(SCRIPTS))

import agent_graph as runtime  # noqa: E402
from run_progress import build_run_progress_summary, validate_run_progress_summary  # noqa: E402


FIXTURES = ROOT / "skills/agent-graph/fixtures/maestro-protocol-v1"
REFERENCES = ROOT / "skills/agent-graph/references"


def _contract(task_id: str, title: str) -> dict:
    return {"id": task_id, "title": title, "depends": [], "paths": ["src/"], "mode": "write", "isolation": "auto", "acceptance": "Focused", "check": "python3 -c pass", "context": "", "visual": [], "visual_scope": [], "checked": False, "source_line": 1}


def _projection() -> dict:
    return {
        "change": "change",
        "run_id": "run-01",
        "status": "active",
        "outcome": None,
        "coordinator": {"id": "coordinator-01", "generation": 1},
        "driver": "host",
        "last_sequence": 12,
        "tasks": {
            "MLK-01": {"status": "running", "grade": None, "attempt_ids": ["attempt-mlk-01"], "contract": _contract("MLK-01", "Run")},
            "MLK-02": {"status": "pending", "grade": None, "attempt_ids": [], "contract": _contract("MLK-02", "Next")},
        },
        "attempts": {"attempt-mlk-01": {"task_id": "MLK-01", "status": "running"}},
        "questions": {},
        "cleanup": {},
        "degradations": [],
    }


LAST_EVENT = {"sequence": 12, "timestamp": "2026-08-22T09:04:01Z", "type": "attempt_started"}


class _WatchJournal:
    def __init__(self, projection: dict, events: list[dict], *, full_events: list[dict] | None = None) -> None:
        self.projection = projection
        self.events = events
        self.full_events = full_events or events

    def watch_snapshot(self, _limit: int) -> tuple[list[dict], dict]:
        return self.events[-_limit:], self.projection

    def replay_snapshot(self) -> tuple[list[dict], dict]:
        return self.full_events, self.projection


class RunProgressTests(unittest.TestCase):
    def test_ignores_terminal_presentation_and_provider_liveness(self) -> None:
        projection = _projection()
        baseline = build_run_progress_summary(projection, last_event=LAST_EVENT)
        decorated = copy.deepcopy(projection)
        decorated["terminal_title"] = "working"
        decorated["spinner"] = "rotating"
        decorated["tui_idle"] = True
        decorated["silent_terminal"] = True
        decorated["provider_completed"] = True
        decorated["apparent_process_stall"] = True
        decorated["attempts"]["attempt-mlk-01"].update({"title": "done", "liveness": "idle"})
        self.assertEqual(build_run_progress_summary(decorated, last_event=LAST_EVENT), baseline)

    def test_derives_diagnostic_coordination_durations_from_event_pairs(self) -> None:
        projection = _projection()
        projection["attempts"]["attempt-mlk-01"]["check"] = {"duration_ms": 17}
        events = [
            {"sequence": 1, "timestamp": "2026-08-22T09:00:00Z", "type": "attempt_started", "data": {"attempt_id": "attempt-mlk-01"}},
            {"sequence": 2, "timestamp": "2026-08-22T09:00:03Z", "type": "worker_reported", "data": {"attempt_id": "attempt-mlk-01"}},
            {"sequence": 3, "timestamp": "2026-08-22T09:00:04Z", "type": "check_recorded", "data": {"task_id": "MLK-01", "attempt_id": "attempt-mlk-01"}},
            {"sequence": 4, "timestamp": "2026-08-22T09:00:06Z", "type": "task_graded", "data": {"task_id": "MLK-01"}},
        ]
        coordination = build_run_progress_summary(projection, last_event=events[-1], events=events)["coordination"]
        self.assertEqual(coordination["implementation_wall_time_ms"], 3000)
        self.assertEqual(coordination["coordinator_wait_for_worker_wall_time_ms"], 3000)
        self.assertEqual(coordination["check_wall_time_ms"], 17)
        self.assertEqual(coordination["audit_wall_time_ms"], 2000)

    def test_bounds_refs_and_prevents_false_complete_with_carry_forward(self) -> None:
        projection = _projection()
        projection["status"] = "complete"
        projection["outcome"] = "pass"
        projection["tasks"] = {
            f"MLK-{index:02d}": {"status": "pass", "grade": "pass", "attempt_ids": [], "contract": _contract(f"MLK-{index:02d}", "Pass")}
            for index in range(8)
        }
        projection["attempts"] = {}
        projection["cleanup"] = {
            f"cleanup-{index:02d}": {"status": "pending", "attempt_id": f"attempt-{index:02d}"}
            for index in range(8)
        }
        projection["degradations"] = [
            {"status": "carry_forward", "task_id": "MLK-00", "finding_refs": [f"file:findings/{index}.md" for index in range(8)]}
        ]
        summary = build_run_progress_summary(projection, last_event=LAST_EVENT)
        self.assertEqual(summary["state"], "partial")
        self.assertEqual(summary["progress_percent"], 99)
        self.assertEqual(summary["cleanup"]["pending"], {"count": 8, "ids": [f"cleanup-{index:02d}" for index in range(5)], "truncated": True})
        self.assertLessEqual(len(summary["current_tasks"]), 3)
        self.assertLessEqual(len(summary["next_tasks"]), 3)
        self.assertLessEqual(len(summary["blockers"]), 5)
        self.assertLessEqual(len(summary["material_findings"]), 5)
        self.assertEqual(validate_run_progress_summary(summary), summary)

    def test_watch_reset_and_resume_cursors_keep_the_same_summary(self) -> None:
        projection = _projection()
        projection["last_sequence"] = 70
        retained_events = [
            {"sequence": sequence, "timestamp": "2026-08-22T09:04:01Z", "type": "task_ready"}
            for sequence in range(2, 71)
        ]
        journal = _WatchJournal(
            projection,
            retained_events,
            full_events=[
                {"sequence": 1, "timestamp": "2026-08-22T09:00:00Z", "type": "attempt_started", "data": {"attempt_id": "attempt-mlk-01"}}
            ] + retained_events,
        )
        snapshot, cursor = runtime._watch_updates(journal, None)
        reset, reset_cursor = runtime._watch_updates(journal, cursor + 1)
        resumed, resumed_cursor = runtime._watch_updates(journal, 9)
        expected = build_run_progress_summary(
            projection, last_event=retained_events[-1], events=journal.full_events
        )
        retained_only = build_run_progress_summary(
            projection, last_event=retained_events[-1], events=journal.events[-runtime.WATCH_RETENTION:]
        )
        self.assertEqual(snapshot[0]["state"]["progress"], expected)
        self.assertEqual(reset[0]["progress"], expected)
        self.assertEqual(resumed[0]["progress"], expected)
        self.assertEqual(resumed[0]["cursor"], expected["last_activity"]["sequence"])
        self.assertEqual(resumed[0]["event"], "progress_aggregate")
        self.assertNotEqual(expected["coordination"], retained_only["coordination"])
        unchanged, unchanged_cursor = runtime._watch_updates(journal, cursor)
        self.assertEqual(unchanged, [])
        self.assertEqual(snapshot[0]["cursor"], journal.full_events[-1]["sequence"])
        self.assertEqual((cursor, reset_cursor, resumed_cursor, unchanged_cursor), (70, 70, 70, 70))

    def test_applies_terminal_first_state_precedence(self) -> None:
        projection = _projection()
        projection["status"] = "complete"
        projection["outcome"] = "partial"
        projection["tasks"]["MLK-01"]["grade"] = "blocked"
        projection["tasks"]["MLK-01"]["status"] = "blocked"
        self.assertEqual(build_run_progress_summary(projection, last_event=LAST_EVENT)["state"], "partial")

        projection["outcome"] = "blocked"
        projection["tasks"]["MLK-01"]["grade"] = "fail"
        projection["tasks"]["MLK-01"]["status"] = "fail"
        self.assertEqual(build_run_progress_summary(projection, last_event=LAST_EVENT)["state"], "failed")

        projection["status"] = "active"
        projection["outcome"] = None
        projection["tasks"]["MLK-01"]["grade"] = "unobserved"
        projection["tasks"]["MLK-01"]["status"] = "unobserved"
        self.assertEqual(build_run_progress_summary(projection, last_event=LAST_EVENT)["state"], "outcome_unknown")

    def test_excludes_resolved_audit_rejections_from_material_findings(self) -> None:
        projection = _projection()
        projection["status"] = "complete"
        projection["outcome"] = "pass"
        projection["tasks"] = {
            "MLK-01": {"status": "pass", "grade": "pass", "attempt_ids": ["attempt-old", "attempt-new"], "contract": _contract("MLK-01", "Recovered")}
        }
        projection["attempts"] = {
            "attempt-old": {"task_id": "MLK-01", "status": "audit-rejected", "audit_rejection": {"finding_refs": ["file:findings/repaired.md"]}},
            "attempt-new": {"task_id": "MLK-01", "status": "reported"},
        }
        summary = build_run_progress_summary(projection, last_event=LAST_EVENT)
        self.assertEqual(summary["material_findings"], [])
        self.assertEqual(summary["state"], "complete")

    def test_keeps_retryable_audit_findings_active_and_failed_cleanup_blocked(self) -> None:
        projection = _projection()
        projection["tasks"]["MLK-01"]["status"] = "pending"
        projection["attempts"]["attempt-mlk-01"].update(
            {"status": "audit-rejected", "audit_rejection": {"finding_refs": ["file:findings/retry.md"]}}
        )
        summary = build_run_progress_summary(projection, last_event=LAST_EVENT)
        self.assertEqual(summary["state"], "active")
        self.assertEqual(summary["material_findings"][0]["finding_ref"], "file:findings/retry.md")

        projection["cleanup"] = {"cleanup-01": {"status": "pending", "attempt_id": "attempt-mlk-01"}}
        self.assertEqual(build_run_progress_summary(projection, last_event=LAST_EVENT)["state"], "active")
        projection["cleanup"]["cleanup-01"]["status"] = "failed"
        self.assertEqual(build_run_progress_summary(projection, last_event=LAST_EVENT)["state"], "blocked")

    def test_uses_unverifiable_cleanup_as_canonical_uncertainty(self) -> None:
        projection = _projection()
        projection["cleanup"] = {"cleanup-01": {"status": "unverifiable", "attempt_id": "attempt-mlk-01"}}
        self.assertEqual(build_run_progress_summary(projection, last_event=LAST_EVENT)["state"], "outcome_unknown")

    def test_keeps_runnable_carry_forward_active(self) -> None:
        projection = _projection()
        projection["degradations"] = [{"status": "carry_forward", "task_id": "MLK-01", "finding_refs": ["file:findings/later.md"]}]
        summary = build_run_progress_summary(projection, last_event=LAST_EVENT)
        self.assertEqual(summary["state"], "active")
        self.assertEqual(summary["progress_percent"], 0)

    def test_orders_mixed_owned_and_unowned_references_deterministically(self) -> None:
        projection = _projection()
        projection["tasks"]["MLK-01"]["status"] = "blocked"
        projection["tasks"]["MLK-01"]["grade"] = "blocked"
        projection["attempts"]["attempt-mlk-01"]["audit_exhaustion"] = {
            "finding_refs": ["file:findings/owned.md"]
        }
        projection["cleanup"] = {"cleanup-unowned": {"status": "failed"}}
        projection["degradations"] = [{"status": "carry_forward", "finding_refs": ["file:findings/unowned.md"]}]
        first = build_run_progress_summary(projection, last_event=LAST_EVENT)
        second = build_run_progress_summary(projection, last_event=LAST_EVENT)
        self.assertEqual(first, second)
        for field in ("blockers", "material_findings"):
            refs = first[field]
            identities = {json.dumps(ref, sort_keys=True) for ref in refs}
            self.assertEqual(len(refs), len(identities))
            self.assertEqual({ref["task_id"] for ref in refs}, {None, "MLK-01"})

    def test_validates_the_versioned_fixture(self) -> None:
        schema = json.loads((REFERENCES / "run-progress-summary.schema.json").read_text(encoding="utf-8"))
        fixture = json.loads((FIXTURES / "run-progress-summary.json").read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(fixture)
        self.assertEqual(validate_run_progress_summary(fixture), fixture)

    def test_rejects_boolean_integer_values(self) -> None:
        summary = build_run_progress_summary(_projection(), last_event=LAST_EVENT)
        cases = {
            "schema_version": lambda value: value.__setitem__("schema_version", True),
            "progress_percent": lambda value: value.__setitem__("progress_percent", True),
            "task_count": lambda value: value["task_counts"].__setitem__("running", True),
            "cleanup_count": lambda value: value["cleanup"]["pending"].__setitem__("count", True),
            "activity_sequence": lambda value: value["last_activity"].__setitem__("sequence", True),
        }
        for name, mutate in cases.items():
            with self.subTest(name=name):
                candidate = copy.deepcopy(summary)
                mutate(candidate)
                with self.assertRaises(ValueError):
                    validate_run_progress_summary(candidate)

    def test_settles_done_verified_and_retained_cleanup_without_hiding_open_gates(self) -> None:
        projection = _projection()
        projection["status"] = "complete"
        projection["outcome"] = "pass"
        projection["tasks"] = {
            "MLK-01": {
                "status": "pass",
                "grade": "pass",
                "attempt_ids": [],
                "contract": _contract("MLK-01", "Pass"),
            }
        }
        projection["attempts"] = {}
        projection["cleanup"] = {
            "cleanup-done": {"status": "done"},
            "cleanup-retained": {"status": "retained"},
            "cleanup-verified": {"status": "verified"},
        }
        summary = build_run_progress_summary(projection, last_event=LAST_EVENT)
        self.assertEqual(summary["state"], "complete")
        self.assertEqual(summary["progress_percent"], 100)
        self.assertEqual(summary["cleanup"]["retained"], {"count": 1, "ids": ["cleanup-retained"], "truncated": False})
        self.assertEqual(summary["blockers"], [])

        for cleanup_status, expected_state in {
            "pending": "active",
            "unverifiable": "outcome_unknown",
            "failed": "blocked",
        }.items():
            with self.subTest(cleanup_status=cleanup_status):
                candidate = copy.deepcopy(projection)
                candidate["cleanup"]["cleanup-gate"] = {"status": cleanup_status}
                gated = build_run_progress_summary(candidate, last_event=LAST_EVENT)
                self.assertEqual(gated["state"], expected_state)
                self.assertEqual(gated["progress_percent"], 99)


if __name__ == "__main__":
    unittest.main()
