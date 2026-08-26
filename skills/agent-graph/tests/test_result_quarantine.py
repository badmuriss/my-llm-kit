import argparse
import hashlib
import importlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "agent_graph.py"
sys.path.insert(0, str(SCRIPT.parent))

import adaptive_intake  # noqa: E402
import agent_graph as runtime  # noqa: E402


TASKS = """# Tasks

- [ ] ROOT-01 Quarantine malformed worker result candidates
  Depends: []
  Paths: [src/result.py]
  Mode: write
  Isolation: auto
  Acceptance: A fresh worker attempt can report after malformed predecessors are quarantined.
  Check: python3 -c \"raise SystemExit(0)\"

- [ ] AUX-02 Preserve graph-mode fixture eligibility
  Depends: []
  Paths: [src/aux.py]
  Mode: read
  Isolation: auto
  Acceptance: The independent fixture remains available.
  Check: python3 -c \"raise SystemExit(0)\"
"""


class ResultQuarantineBehavior(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.repository = Path(self.temporary_directory.name)
        change = self.repository / "openspec/changes/quarantine"
        change.mkdir(parents=True)
        for name, body in {
            "proposal.md": "# Proposal\n",
            "design.md": "# Design\n",
            "tasks.md": TASKS,
        }.items():
            (change / name).write_text(body, encoding="utf-8")
        graph = runtime.parse_task_graph(change / "tasks.md")
        decision = adaptive_intake.decide_process(
            self.repository,
            request="Quarantine malformed local worker results.",
            check_command=graph.tasks[0].check,
            signals={
                "known_scope": True,
                "graph_requested": True,
                "cohesion": "independent",
                "independent_packets": [
                    {
                        "packet_id": task.id,
                        "paths": list(task.paths),
                        "check": {"command": task.check, "oracle": f"{task.id} passes."},
                    }
                    for task in graph.tasks
                ],
                "integrator": "coordinator-1",
                "permission_observed": True,
                "budget_limits": [{"resource": "workers", "value": 2, "unit": "workers", "rationale": "Two independent fixture tasks."}],
                "cleanup_plan": "Release local attempts before retrying.",
            },
        )
        (change / "process-decision.json").write_text(json.dumps(decision), encoding="utf-8")
        for command in (
            ["git", "init", "-q", str(self.repository)],
            ["git", "-C", str(self.repository), "config", "user.email", "test@example.com"],
            ["git", "-C", str(self.repository), "config", "user.name", "Test"],
            ["git", "-C", str(self.repository), "add", "."],
            ["git", "-C", str(self.repository), "commit", "-qm", "fixture"],
        ):
            subprocess.run(command, check=True)
        bootstrap = self.run_cli(
            "bootstrap", "--change", "quarantine", "--run-id", "run-1",
            "--bootstrap-id", "bootstrap-1", "--driver", "host",
        )
        capsule = self.result(bootstrap)["capsule_path"]
        self.run_cli("claim-coordinator", "--capsule", capsule, "--coordinator-id", "coordinator-1")
        self.directory = self.repository / "openspec/runs/quarantine/run-1"

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def run_cli(self, command: str, *arguments: str) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), command, "--repo", str(self.repository), "--json", *arguments],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return completed

    def result(self, completed: subprocess.CompletedProcess[str]) -> dict[str, object]:
        return json.loads(completed.stdout)["result"]

    def arguments(self) -> tuple[str, ...]:
        return ("--change", "quarantine", "--run-id", "run-1", "--generation", "2")

    def dispatch(self, attempt_id: str) -> str:
        result = self.result(self.run_cli(
            "dispatch", *self.arguments(), "--task", "ROOT-01", "--attempt-id", attempt_id, "--local",
        ))
        return str(result["attempt_id"])

    def quarantine(self, attempt_id: str, key: str, raw: bytes) -> dict[str, object]:
        candidate = self.directory / "results" / f"{attempt_id}.json"
        candidate.write_bytes(raw)
        return self.result(self.run_cli(
            "quarantine-result", *self.arguments(), "--task", "ROOT-01", "--attempt", attempt_id,
            "--candidate", f"openspec/runs/quarantine/run-1/results/{attempt_id}.json",
            "--idempotency-key", key,
        ))

    def raw_quarantine(
        self,
        attempt_id: str,
        key: str,
        *,
        candidate: str | None = None,
        generation: int = 2,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable, str(SCRIPT), "quarantine-result", "--repo", str(self.repository), "--json",
                "--change", "quarantine", "--run-id", "run-1", "--generation", str(generation),
                "--task", "ROOT-01", "--attempt", attempt_id,
                "--candidate", candidate or f"openspec/runs/quarantine/run-1/results/{attempt_id}.json",
                "--idempotency-key", key,
            ],
            check=False,
            capture_output=True,
            text=True,
        )

    def assert_failure_keeps_state(
        self,
        attempt_id: str,
        key: str,
        code: str,
        *,
        candidate: str | None = None,
        generation: int = 2,
    ) -> None:
        before = {
            name: (self.directory / name).read_bytes()
            for name in ("events.jsonl", "state.json")
        }
        completed = self.raw_quarantine(
            attempt_id, key, candidate=candidate, generation=generation
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(json.loads(completed.stderr)["error"]["code"], code)
        self.assertEqual(
            {name: (self.directory / name).read_bytes() for name in before}, before
        )

    def test_quarantines_two_malformed_candidates_before_a_fresh_valid_attempt(self) -> None:
        first = self.dispatch("attempt-one")
        first_raw = b"\xffquarantine-first-invalid"
        first_receipt = self.quarantine(first, "quarantine-one", first_raw)["receipt"]
        self.assertFalse((self.directory / "results" / f"{first}.json").exists())
        self.assertEqual(first_receipt["validation_error_code"], "invalid_encoding")
        self.assertEqual(
            (self.directory / "artifacts/result-quarantine/sha256" / f"{first_receipt['sha256'][7:]}.json").read_bytes(),
            first_raw,
        )
        self.run_cli("abandon-attempt", *self.arguments(), "--attempt", first, "--reason", "transport failure")

        second = self.dispatch("attempt-two")
        second_raw = b'{"unique_invalid_result_quarantine_two":true}'
        second_receipt = self.quarantine(second, "quarantine-two", second_raw)["receipt"]
        self.assertEqual(second_receipt["validation_error_code"], "invalid_worker_result")
        self.run_cli("abandon-attempt", *self.arguments(), "--attempt", second, "--reason", "transport failure")

        fresh = self.dispatch("attempt-three")
        report = {
            "task_id": "ROOT-01",
            "attempt_id": fresh,
            "outcome": "reported",
            "summary": "A fresh worker reported valid evidence.",
            "files_changed": ["src/result.py"],
            "checks_run": ["python3 -c \"raise SystemExit(0)\""],
            "evidence_refs": [],
            "questions": [],
            "external_refs": {},
        }
        reported = self.result(self.run_cli(
            "record-result", *self.arguments(), "--attempt", fresh, "--result-json", json.dumps(report),
        ))
        state = json.loads((self.directory / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["attempts"][fresh]["status"], "reported")
        self.assertEqual(state["tasks"]["ROOT-01"]["hypotheses"], [])
        self.assertIsNone(state["tasks"]["ROOT-01"]["grade"])
        journal = (self.directory / "events.jsonl").read_bytes()
        self.assertNotIn(first_raw, journal)
        self.assertNotIn(second_raw, journal)

    def test_record_result_quarantines_a_malformed_canonical_candidate_before_returning(self) -> None:
        attempt = self.dispatch("attempt-record-malformed")
        candidate = self.directory / "results" / f"{attempt}.json"
        raw = b"\xffrecord-result-malformed"
        candidate.write_bytes(raw)

        quarantined = self.result(self.run_cli(
            "record-result", *self.arguments(), "--attempt", attempt,
            "--result", f"openspec/runs/quarantine/run-1/results/{attempt}.json",
        ))

        self.assertTrue(quarantined["quarantined"])
        receipt = quarantined["receipt"]
        self.assertEqual(receipt["validation_error_code"], "invalid_encoding")
        self.assertFalse(candidate.exists())
        self.assertEqual(
            (self.directory / "artifacts/result-quarantine/sha256" / f"{receipt['sha256'][7:]}.json").read_bytes(),
            raw,
        )
        blocked = subprocess.run(
            [
                sys.executable, str(SCRIPT), "record-result", "--repo", str(self.repository), "--json",
                *self.arguments(), "--attempt", attempt,
                "--result-json", json.dumps({
                    "task_id": "ROOT-01",
                    "attempt_id": attempt,
                    "outcome": "reported",
                    "summary": "Must not revive a quarantined attempt.",
                    "files_changed": ["src/result.py"],
                    "checks_run": ["python3 -c \"raise SystemExit(0)\""],
                    "evidence_refs": [],
                    "questions": [],
                    "external_refs": {},
                }),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(blocked.returncode, 0)
        error = json.loads(blocked.stderr)["error"]
        self.assertEqual(error["code"], "result_slot_quarantined")
        self.assertEqual(error["receipt"], receipt)

    def test_rejects_and_preserves_post_report_overwrite_until_the_exact_bytes_are_restored(self) -> None:
        attempt = self.dispatch("attempt-post-report-overwrite")
        report = {
            "task_id": "ROOT-01",
            "attempt_id": attempt,
            "outcome": "reported",
            "summary": "The canonical result is accepted once.",
            "files_changed": ["src/result.py"],
            "checks_run": ["python3 -c \"raise SystemExit(0)\""],
            "evidence_refs": [],
            "questions": [],
            "external_refs": {},
        }
        self.result(self.run_cli(
            "record-result", *self.arguments(), "--attempt", attempt,
            "--result-json", json.dumps(report),
        ))
        candidate = self.directory / "results" / f"{attempt}.json"
        accepted = candidate.read_bytes()
        overwritten = json.dumps({**report, "summary": "A divergent overwrite."}).encode("utf-8")
        candidate.write_bytes(overwritten)

        rejected = subprocess.run(
            [
                sys.executable, str(SCRIPT), "record-result", "--repo", str(self.repository), "--json",
                *self.arguments(), "--attempt", attempt, "--result-json", json.dumps(report),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(rejected.returncode, 0)
        error = json.loads(rejected.stderr)["error"]
        self.assertEqual(error["code"], "result_slot_integrity")
        self.assertEqual(error["observed_digest"], "sha256:" + hashlib.sha256(overwritten).hexdigest())
        self.assertTrue(error["accepted_receipt"])
        self.assertEqual(
            (self.directory / "artifacts/result-quarantine/sha256" / f"{error['observed_digest'][7:]}.json").read_bytes(),
            overwritten,
        )

        candidate.write_bytes(accepted)
        replayed = self.result(self.run_cli(
            "record-result", *self.arguments(), "--attempt", attempt,
            "--result-json", json.dumps(report),
        ))
        self.assertTrue(replayed["idempotent"])
        events = [json.loads(line) for line in (self.directory / "events.jsonl").read_text().splitlines()]
        self.assertEqual([event["type"] for event in events].count("worker_reported"), 1)

    def test_rejects_changed_replay_bytes_without_a_second_event(self) -> None:
        attempt = self.dispatch("attempt-replay")
        self.quarantine(attempt, "quarantine-replay", b"{")
        before = {
            name: (self.directory / name).read_bytes()
            for name in ("events.jsonl", "state.json")
        }
        candidate = self.directory / "results" / f"{attempt}.json"
        candidate.write_bytes(b"[not the same candidate]")
        completed = subprocess.run(
            [
                sys.executable, str(SCRIPT), "quarantine-result", "--repo", str(self.repository), "--json",
                *self.arguments(), "--task", "ROOT-01", "--attempt", attempt,
                "--candidate", f"openspec/runs/quarantine/run-1/results/{attempt}.json",
                "--idempotency-key", "quarantine-replay",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(json.loads(completed.stderr)["error"]["code"], "quarantine_collision")
        self.assertEqual(
            {name: (self.directory / name).read_bytes() for name in before}, before
        )

    def test_replays_the_same_key_and_digest_without_rewriting_the_journal(self) -> None:
        attempt = self.dispatch("attempt-idempotent")
        raw = b"\xffsame-key-same-digest"
        first = self.quarantine(attempt, "quarantine-idempotent", raw)
        before = {
            name: (self.directory / name).read_bytes()
            for name in ("events.jsonl", "state.json")
        }
        replay = self.quarantine(attempt, "quarantine-idempotent", raw)
        self.assertTrue(replay["idempotent"])
        self.assertEqual(replay["receipt"], first["receipt"])
        self.assertEqual(
            {name: (self.directory / name).read_bytes() for name in before}, before
        )
        receipt = json.dumps(first["receipt"], sort_keys=True).encode("utf-8")
        self.assertNotIn(raw, receipt)
        self.assertNotIn(raw, (self.directory / "events.jsonl").read_bytes())

    def test_preserves_a_recreated_candidate_when_quarantine_evidence_is_missing_or_tampered(self) -> None:
        attempt = self.dispatch("attempt-evidence-integrity")
        raw = b"\xffrecreated-candidate-evidence-integrity"
        receipt = self.quarantine(attempt, "quarantine-evidence-integrity", raw)["receipt"]
        candidate = self.directory / "results" / f"{attempt}.json"
        evidence = self.directory / "artifacts/result-quarantine/sha256" / f"{receipt['sha256'][7:]}.json"
        candidate.write_bytes(raw)
        evidence.unlink()
        self.assert_failure_keeps_state(
            attempt,
            "quarantine-evidence-integrity",
            "quarantine_evidence_missing",
        )
        self.assertEqual(candidate.read_bytes(), raw)
        evidence.write_bytes(raw)
        evidence.write_bytes(b"tampered quarantine evidence")
        self.assert_failure_keeps_state(
            attempt,
            "quarantine-evidence-integrity",
            "quarantine_collision",
        )
        self.assertEqual(candidate.read_bytes(), raw)

    def test_rejects_a_stale_generation_without_mutating_the_run(self) -> None:
        attempt = self.dispatch("attempt-stale")
        (self.directory / "results" / f"{attempt}.json").write_bytes(b"{")
        self.assert_failure_keeps_state(
            attempt, "quarantine-stale", "stale_coordinator", generation=1
        )

    def test_rejects_a_task_attempt_mismatch_without_mutating_the_run(self) -> None:
        attempt = self.dispatch("attempt-task-mismatch")
        (self.directory / "results" / f"{attempt}.json").write_bytes(b"{")
        before = {
            name: (self.directory / name).read_bytes()
            for name in ("events.jsonl", "state.json")
        }
        completed = subprocess.run(
            [
                sys.executable, str(SCRIPT), "quarantine-result", "--repo", str(self.repository), "--json",
                *self.arguments(), "--task", "AUX-02", "--attempt", attempt,
                "--candidate", f"openspec/runs/quarantine/run-1/results/{attempt}.json",
                "--idempotency-key", "quarantine-task-mismatch",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(json.loads(completed.stderr)["error"]["code"], "attempt_task_mismatch")
        self.assertEqual(
            {name: (self.directory / name).read_bytes() for name in before}, before
        )

    def test_rejects_a_missing_candidate_without_mutating_the_run(self) -> None:
        attempt = self.dispatch("attempt-missing")
        self.assert_failure_keeps_state(attempt, "quarantine-missing", "candidate_missing")

    def test_rejects_symlink_escape_and_noncanonical_candidates_without_mutating_the_run(self) -> None:
        attempt = self.dispatch("attempt-unsafe-path")
        candidate = self.directory / "results" / f"{attempt}.json"
        outside = self.repository / "outside-result.json"
        outside.write_bytes(b"{")
        candidate.symlink_to(outside)
        before = {
            name: (self.directory / name).read_bytes()
            for name in ("events.jsonl", "state.json")
        }
        symlink = self.raw_quarantine(attempt, "quarantine-symlink")
        self.assertNotEqual(symlink.returncode, 0)
        self.assertIn(
            json.loads(symlink.stderr)["error"]["code"],
            {"candidate_symlink", "quarantine_path_escape"},
        )
        self.assertEqual(
            {name: (self.directory / name).read_bytes() for name in before}, before
        )
        candidate.unlink()
        candidate.write_bytes(b"{")
        self.assert_failure_keeps_state(
            attempt,
            "quarantine-escape",
            "candidate_path_mismatch",
            candidate="openspec/runs/quarantine/run-1/results/../outside-result.json",
        )
        self.assert_failure_keeps_state(
            attempt,
            "quarantine-noncanonical",
            "candidate_path_mismatch",
            candidate=f"openspec/runs/quarantine/run-1/results/not-{attempt}.json",
        )

    def test_rejects_a_receipt_collision_before_relocation(self) -> None:
        attempt = self.dispatch("attempt-receipt-collision")
        candidate = self.directory / "results" / f"{attempt}.json"
        raw = b"\xffreceipt-collision"
        candidate.write_bytes(raw)
        receipt = self.directory / "artifacts/result-quarantine/receipts/quarantine-collision.json"
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_text("{}", encoding="utf-8")
        self.assert_failure_keeps_state(
            attempt, "quarantine-collision", "receipt_collision"
        )
        self.assertEqual(candidate.read_bytes(), raw)

    def test_preserves_a_quarantine_when_a_separate_terminal_cleanup_is_pending(self) -> None:
        attempt = self.dispatch("attempt-terminal-cleanup")
        raw = b"\xffpending-terminal-cleanup"
        self.quarantine(attempt, "quarantine-terminal-cleanup", raw)
        state = json.loads((self.directory / "state.json").read_text(encoding="utf-8"))
        workspace = state["workspace_scope"]["execution_workspace"]
        terminal_cleanup = "cleanup-terminal-separate"
        owner = {
            "execution_host_id": workspace["execution_host_id"],
            "workspace_key": workspace["workspace_key"],
            "attempt_id": attempt,
            "terminal_id": "terminal-separate",
            "incarnation_id": "incarnation-separate",
            "process_root": None,
            "provenance": "manual terminal cleanup",
        }
        journal = runtime.EventJournal(
            self.directory / "events.jsonl", self.directory / "state.json"
        )
        journal.append(
            "cleanup_registered",
            {
                "cleanup_id": terminal_cleanup,
                "kind": "terminal",
                "target": "terminal-separate",
                "owner": owner,
                "identity_version": 1,
            },
            coordinator_generation=2,
        )

        synced = subprocess.run(
            [
                sys.executable, str(SCRIPT), "sync", "--repo", str(self.repository), "--json",
                *self.arguments(),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        state = json.loads((self.directory / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["attempts"][attempt]["status"], "running")
        self.assertNotEqual(synced.returncode, 0)
        sync_error = json.loads(synced.stderr)["error"]
        self.assertEqual(sync_error["code"], "result_slot_quarantined")
        self.assertEqual(sync_error["receipt"], state["attempts"][attempt]["result_quarantine"])
        events = [
            json.loads(line)
            for line in (self.directory / "events.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        self.assertNotIn("attempt_abandoned", [event["type"] for event in events])

        for command, expected_code in (("recover-attempt", "result_slot_quarantined"), ("abandon-attempt", "cleanup_pending")):
            arguments = [command, *self.arguments(), "--attempt", attempt]
            if command == "abandon-attempt":
                arguments.extend(["--reason", "terminal cleanup pending"])
            pending = subprocess.run(
                [
                    sys.executable, str(SCRIPT), command, "--repo", str(self.repository),
                    "--json", *arguments[1:],
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(pending.returncode, 0)
            self.assertEqual(json.loads(pending.stderr)["error"]["code"], expected_code)

        self.run_cli(
            "cleanup-retain", *self.arguments(), "--cleanup-id", terminal_cleanup,
            "--receipt", json.dumps({"kind": "terminal", "status": "retained"}),
        )
        self.run_cli(
            "abandon-attempt", *self.arguments(), "--attempt", attempt,
            "--reason", "terminal cleanup retained",
        )
        fresh = self.dispatch("attempt-after-terminal-cleanup")
        self.run_cli(
            "record-result", *self.arguments(), "--attempt", fresh,
            "--result-json", json.dumps({
                "task_id": "ROOT-01",
                "attempt_id": fresh,
                "outcome": "reported",
                "summary": "Fresh attempt reported after terminal cleanup retention.",
                "files_changed": ["src/result.py"],
                "checks_run": ["python3 -c \"raise SystemExit(0)\""],
                "evidence_refs": [],
                "questions": [],
                "external_refs": {},
            }),
        )

    def test_recovers_a_durable_receipt_that_precedes_its_journal_event(self) -> None:
        attempt = self.dispatch("attempt-crash-recovery")
        raw = b"\xffdurable-receipt-before-event"
        candidate = self.directory / "results" / f"{attempt}.json"
        candidate.write_bytes(raw)
        state = json.loads((self.directory / "state.json").read_text(encoding="utf-8"))
        digest = hashlib.sha256(raw).hexdigest()
        quarantine = self.directory / "artifacts/result-quarantine/sha256" / f"{digest}.json"
        receipt_path = self.directory / "artifacts/result-quarantine/receipts/quarantine-crash.json"
        quarantine.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        candidate.replace(quarantine)
        receipt = {
            "task_id": "ROOT-01",
            "attempt_id": attempt,
            "idempotency_key": "quarantine-crash",
            "original_path": f"openspec/runs/quarantine/run-1/results/{attempt}.json",
            "quarantine_path": f"openspec/runs/quarantine/run-1/artifacts/result-quarantine/sha256/{digest}.json",
            "sha256": f"sha256:{digest}",
            "byte_length": len(raw),
            "validation_error_code": "invalid_encoding",
            "generation": 2,
            "revision": state["last_sequence"] + 1,
            "receipt_path": "openspec/runs/quarantine/run-1/artifacts/result-quarantine/receipts/quarantine-crash.json",
        }
        runtime.atomic_write_json(receipt_path, receipt)
        recovered = self.result(self.run_cli(
            "quarantine-result", *self.arguments(), "--task", "ROOT-01", "--attempt", attempt,
            "--candidate", f"openspec/runs/quarantine/run-1/results/{attempt}.json",
            "--idempotency-key", "quarantine-crash",
        ))
        self.assertTrue(recovered["idempotent"])
        self.assertTrue(recovered["recovered"])
        state = json.loads((self.directory / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["attempts"][attempt]["result_quarantine"], receipt)

    def test_recovers_an_older_receipt_after_an_intervening_journal_event(self) -> None:
        attempt = self.dispatch("attempt-intervening-recovery")
        raw = b"\xffdurable-receipt-before-intervening-event"
        candidate = self.directory / "results" / f"{attempt}.json"
        candidate.write_bytes(raw)
        state = json.loads((self.directory / "state.json").read_text(encoding="utf-8"))
        digest = hashlib.sha256(raw).hexdigest()
        quarantine = self.directory / "artifacts/result-quarantine/sha256" / f"{digest}.json"
        receipt_path = self.directory / "artifacts/result-quarantine/receipts/quarantine-intervening.json"
        quarantine.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        candidate.replace(quarantine)
        receipt = {
            "task_id": "ROOT-01",
            "attempt_id": attempt,
            "idempotency_key": "quarantine-intervening",
            "original_path": f"openspec/runs/quarantine/run-1/results/{attempt}.json",
            "quarantine_path": f"openspec/runs/quarantine/run-1/artifacts/result-quarantine/sha256/{digest}.json",
            "sha256": f"sha256:{digest}",
            "byte_length": len(raw),
            "validation_error_code": "invalid_encoding",
            "generation": 2,
            "revision": state["last_sequence"] + 1,
            "receipt_path": "openspec/runs/quarantine/run-1/artifacts/result-quarantine/receipts/quarantine-intervening.json",
        }
        runtime.atomic_write_json(receipt_path, receipt)
        journal = runtime.EventJournal(
            self.directory / "events.jsonl", self.directory / "state.json"
        )
        journal.append(
            "journal_repaired",
            {"artifact": "intervening-repair", "discarded_bytes": 0},
            coordinator_generation=2,
        )
        receipt_bytes = receipt_path.read_bytes()
        takeover = self.result(self.run_cli(
            "takeover", *self.arguments(), "--coordinator-id", "coordinator-2",
        ))
        self.assertEqual(takeover["coordinator_generation"], 3)
        recovered = self.result(self.run_cli(
            "quarantine-result", "--change", "quarantine", "--run-id", "run-1", "--generation", "3",
            "--task", "ROOT-01", "--attempt", attempt,
            "--candidate", f"openspec/runs/quarantine/run-1/results/{attempt}.json",
            "--idempotency-key", "quarantine-intervening",
        ))
        self.assertTrue(recovered["idempotent"])
        self.assertTrue(recovered["recovered"])
        self.assertEqual(recovered["receipt"], receipt)
        self.assertEqual(receipt_path.read_bytes(), receipt_bytes)
        recovered_state = json.loads((self.directory / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(recovered_state["attempts"][attempt]["result_quarantine"], receipt)

    def _seed_orca_sync_attempt(
        self,
        run_id: str,
        attempt_id: str,
        *,
        external_task_id: str,
        dispatch_id: str,
        message_id: str = "message-r38",
        delivery_id: str = "delivery-r38",
        checks_run: list[str] | None = None,
    ) -> tuple[Path, runtime.EventJournal, object, argparse.Namespace]:
        directory = runtime._new_run_directory(self.repository, "quarantine", run_id)
        journal = runtime._journal(directory)
        graph = runtime.parse_task_graph(self.repository / "openspec/changes/quarantine/tasks.md")
        task = graph.tasks[0]
        scope = runtime._persist_workspace_scope(
            self.repository,
            directory,
            runtime._automatic_host_workspace_receipt(self.repository, run_id),
            run_id=run_id,
            coordinator_generation=1,
        )
        profile = runtime._execution_profile_for_task(task, scope)
        workspace = scope["execution_workspace"]
        refs = {
            "tier": "supervised",
            "runtime_id": "runtime-r38",
            "worktree_id": "worktree-r38",
            "run_id": "run-r38",
            "task_id": external_task_id,
            "dispatch_id": dispatch_id,
        }
        owner = {
            "execution_host_id": workspace["execution_host_id"],
            "workspace_key": workspace["workspace_key"],
            "attempt_id": attempt_id,
            "terminal_id": None,
            "incarnation_id": None,
            "process_root": None,
            "provenance": f"orca-supervised:runtime-r38:worktree-r38:run-r38:{dispatch_id}",
        }
        projection = journal.append(
            "run_started",
            {
                "change": "quarantine",
                "run_id": run_id,
                "coordinator_id": "coordinator-1",
                "coordinator_generation": 1,
                "base_commit": runtime._current_commit(self.repository),
                "dirty_paths": [],
                "workspace_scope": scope,
                "tasks": [contract.to_dict() for contract in graph.tasks],
            },
            coordinator_generation=1,
        )
        projection = journal.append("driver_selected", {"driver": "orca"}, coordinator_generation=1)
        projection = journal.append("task_ready", {"task_id": task.id}, coordinator_generation=1)
        projection = journal.append(
            "attempt_reserved",
            {
                "task_id": task.id,
                "attempt_id": attempt_id,
                "driver": "orca",
                "workspace_scope": scope,
                "execution_profile": profile,
                "resolved_placement": profile["resolved_placement"],
                "external_refs": {},
            },
            coordinator_generation=1,
        )
        effective_scope = projection["attempts"][attempt_id]["effective_scope"]
        projection = journal.append(
            "attempt_scope_frozen",
            {"attempt_id": attempt_id, "effective_scope": effective_scope},
            coordinator_generation=1,
        )
        journal.append(
            "attempt_started",
            {
                "task_id": task.id,
                "attempt_id": attempt_id,
                "driver": "orca",
                "tier": "supervised",
                "external_refs": refs,
                "cleanup_id": f"cleanup-{attempt_id}",
                "workspace_scope": scope,
                "execution_profile": profile,
                "effective_scope": effective_scope,
                "resource_owner": owner,
                "cleanup_registration": {
                    "cleanup_id": f"cleanup-{attempt_id}",
                    "kind": "other",
                    "target": dispatch_id,
                    "owner": owner,
                    "external_refs": refs,
                },
            },
            coordinator_generation=1,
        )

        class FakeOrca(runtime.OrcaDriver):
            def __init__(self) -> None:
                self.run_id = "run-r38"
                self.runtime_id = "runtime-r38"
                self.worktree_id = "worktree-r38"
                self.acks: list[str] = []
                self.releases: list[str] = []
                self.delivery_id = delivery_id
                self.message_id = message_id
                self.external_task_id = external_task_id
                self.dispatch_id = dispatch_id
                self.checks_run = checks_run

            def poll(self, _attempt, *, cursor=None, include_delivery=True):
                return runtime.DriverReceipt(
                    "poll", "observed", external_refs={"cursor": cursor or "cursor-r38"}, raw={}
                )

            def check_delivery(self, _run_id):
                payload = {
                    "taskId": self.external_task_id,
                    "dispatchId": self.dispatch_id,
                    "outcome": "succeeded",
                    "filesModified": ["src/result.py"],
                }
                if self.checks_run is not None:
                    payload["checksRun"] = self.checks_run
                message = {
                    "id": self.message_id,
                    "type": "worker_done",
                    "subject": "r38 completion",
                    "body": "The worker completed the r38 task.",
                    "payload": json.dumps(payload),
                }
                return {"ok": True, "result": {"deliveryId": self.delivery_id, "messages": [message]}}

            def ack_delivery(self, _run_id, acknowledged_delivery_id):
                self.acks.append(acknowledged_delivery_id)
                return {"ok": True, "result": {"deliveryId": acknowledged_delivery_id}}

            def release(self, attempt):
                self.releases.append(attempt["attempt_id"])
                return runtime.DriverReceipt(
                    "release",
                    "released",
                    external_refs={"tier": "supervised", "dispatch_id": attempt["dispatch_id"]},
                    raw={"state": "released"},
                )

        arguments = argparse.Namespace(
            repo=self.repository,
            change="quarantine",
            run_id=run_id,
            generation=1,
        )
        return directory, journal, FakeOrca(), arguments

    def _sync_with_orca(self, fake, arguments: argparse.Namespace) -> dict[str, object]:
        driver_factory = runtime._driver_for_state
        runtime._driver_for_state = lambda *_arguments: fake
        try:
            return runtime.command_sync(arguments)
        finally:
            runtime._driver_for_state = driver_factory

    def test_sync_quarantines_the_r38_completion_without_checks_run(self) -> None:
        directory, _journal, fake, arguments = self._seed_orca_sync_attempt(
            "orca-r38-missing-checks", "attempt-r38", external_task_id="orca-task-r38", dispatch_id="ctx-r38"
        )

        synced = self._sync_with_orca(fake, arguments)

        observation = next(item for item in synced["observed"] if "quarantine_required" in item)
        quarantine = observation["quarantine_required"]
        candidate = self.repository / quarantine["candidate_path"]
        receipt = observation["quarantine"]
        evidence = self.repository / receipt["quarantine_path"]
        expected = {
            "task_id": "ROOT-01",
            "attempt_id": "attempt-r38",
            "outcome": "reported",
            "summary": "The worker completed the r38 task.",
            "files_changed": ["src/result.py"],
            "checks_run": [],
            "evidence_refs": [],
            "questions": [],
            "external_refs": {
                "provider": "orca",
                "message_id": "message-r38",
                "task_id": "orca-task-r38",
                "dispatch_id": "ctx-r38",
                "provider_outcome": "succeeded",
                "delivery_id": "delivery-r38",
            },
        }
        raw = evidence.read_bytes()
        self.assertEqual(raw, runtime._canonical_worker_result_bytes(expected))
        self.assertEqual(quarantine["sha256"], f"sha256:{hashlib.sha256(raw).hexdigest()}")
        self.assertEqual(quarantine["byte_length"], len(raw))
        self.assertEqual(quarantine["validation_error_code"], "invalid_worker_result")
        self.assertFalse(candidate.exists())
        self.assertEqual(fake.acks, [])
        state = runtime._projection(directory)
        self.assertEqual(state["attempts"]["attempt-r38"]["status"], "running")
        self.assertEqual(state["attempts"]["attempt-r38"]["result_quarantine"]["sha256"], quarantine["sha256"])
        event_types = [json.loads(line)["type"] for line in (directory / "events.jsonl").read_text().splitlines()]
        self.assertNotIn("worker_reported", event_types)
        self.assertIn("attempt_result_quarantined", event_types)

    def test_sync_replays_identical_r38_candidate_after_runtime_restart(self) -> None:
        global runtime
        directory, _journal, fake, arguments = self._seed_orca_sync_attempt(
            "orca-r38-replay", "attempt-r38-replay", external_task_id="orca-task-replay", dispatch_id="ctx-replay"
        )
        first = self._sync_with_orca(fake, arguments)
        first_observation = next(item for item in first["observed"] if "quarantine_required" in item)
        first_quarantine = first_observation["quarantine_required"]
        evidence = self.repository / first_observation["quarantine"]["quarantine_path"]
        first_raw = evidence.read_bytes()

        runtime = importlib.reload(runtime)
        restarted_fake = type(fake)()
        replay = self._sync_with_orca(restarted_fake, arguments)

        self.assertNotIn("quarantine_required", json.dumps(replay))
        self.assertEqual(evidence.read_bytes(), first_raw)
        self.assertEqual(restarted_fake.acks, ["delivery-r38"])
        state = runtime._projection(directory)
        self.assertEqual(state["attempts"]["attempt-r38-replay"]["status"], "running")
        self.assertEqual(
            state["attempts"]["attempt-r38-replay"]["result_quarantine"]["sha256"],
            first_quarantine["sha256"],
        )

    def test_sync_rejects_a_changed_or_mismatched_delivery_after_preserving_r38(self) -> None:
        directory, _journal, fake, arguments = self._seed_orca_sync_attempt(
            "orca-r38-identities", "attempt-r38-identities", external_task_id="orca-task-identities", dispatch_id="ctx-identities"
        )
        synced = self._sync_with_orca(fake, arguments)
        observed_item = next(item for item in synced["observed"] if "quarantine_required" in item)
        observation = observed_item["quarantine_required"]
        evidence = self.repository / observed_item["quarantine"]["quarantine_path"]
        before = evidence.read_bytes()

        fake.delivery_id = "delivery-changed"
        with self.assertRaisesRegex(runtime.AgentGraphCliError, "identity does not match") as changed:
            self._sync_with_orca(fake, arguments)
        self.assertEqual(changed.exception.code, "provider_delivery_identity_mismatch")
        self.assertEqual(evidence.read_bytes(), before)

        fake.delivery_id = "delivery-r38"
        fake.dispatch_id = "ctx-wrong"
        with self.assertRaisesRegex(runtime.AgentGraphCliError, "resolved 0 local attempts") as mismatched:
            self._sync_with_orca(fake, arguments)
        self.assertEqual(mismatched.exception.code, "provider_identity_ambiguous")
        self.assertEqual(evidence.read_bytes(), before)

    def test_sync_acks_a_quarantined_delivery_then_accepts_a_corrected_fresh_attempt(self) -> None:
        directory, journal, fake, arguments = self._seed_orca_sync_attempt(
            "orca-r38-corrected", "attempt-r38-invalid", external_task_id="orca-task-invalid", dispatch_id="ctx-invalid"
        )
        quarantined = self._sync_with_orca(fake, arguments)
        observed_item = next(item for item in quarantined["observed"] if "quarantine_required" in item)
        observation = observed_item["quarantine_required"]
        candidate = self.repository / observation["candidate_path"]
        receipt = observed_item["quarantine"]
        evidence = self.repository / receipt["quarantine_path"]
        original = evidence.read_bytes()
        self.assertFalse(candidate.exists())

        acknowledged = self._sync_with_orca(fake, arguments)
        self.assertEqual(fake.acks, ["delivery-r38"])
        self.assertNotIn("quarantine_required", json.dumps(acknowledged))
        self.assertNotIn(original.decode("utf-8"), json.dumps(acknowledged))

        runtime.command_cleanup_retain(
            argparse.Namespace(
                **vars(arguments),
                cleanup_id="cleanup-attempt-r38-invalid",
                receipt=json.dumps({"kind": "other", "status": "retained"}),
                reason=None,
                replacement_cleanup_id=None,
            )
        )
        driver_factory = runtime._driver_for_state
        runtime._driver_for_state = lambda *_arguments: fake
        try:
            runtime.command_abandon_attempt(
                argparse.Namespace(
                    **vars(arguments),
                    attempt="attempt-r38-invalid",
                    reason="malformed provider delivery",
                )
            )
        finally:
            runtime._driver_for_state = driver_factory
        self.assertEqual(evidence.read_bytes(), original)

        journal = runtime._journal(directory)
        projection = runtime._projection(directory)
        task = runtime._task_from_state(projection, "ROOT-01")
        scope = projection["workspace_scope"]
        profile = runtime._execution_profile_for_task(task, scope)
        workspace = scope["execution_workspace"]
        fresh = "attempt-r38-corrected"
        refs = {
            "tier": "supervised", "runtime_id": "runtime-r38", "worktree_id": "worktree-r38",
            "run_id": "run-r38", "task_id": "orca-task-corrected", "dispatch_id": "ctx-corrected",
        }
        owner = {
            "execution_host_id": workspace["execution_host_id"], "workspace_key": workspace["workspace_key"],
            "attempt_id": fresh, "terminal_id": None, "incarnation_id": None, "process_root": None,
            "provenance": "orca-supervised:runtime-r38:worktree-r38:run-r38:ctx-corrected",
        }
        projection = journal.append("task_ready", {"task_id": "ROOT-01"}, coordinator_generation=1)
        projection = journal.append(
            "attempt_reserved",
            {"task_id": "ROOT-01", "attempt_id": fresh, "driver": "orca", "workspace_scope": scope,
             "execution_profile": profile, "resolved_placement": profile["resolved_placement"], "external_refs": {}},
            coordinator_generation=1,
        )
        effective_scope = projection["attempts"][fresh]["effective_scope"]
        journal.append("attempt_scope_frozen", {"attempt_id": fresh, "effective_scope": effective_scope}, coordinator_generation=1)
        journal.append(
            "attempt_started",
            {"task_id": "ROOT-01", "attempt_id": fresh, "driver": "orca", "tier": "supervised",
             "external_refs": refs, "cleanup_id": f"cleanup-{fresh}", "workspace_scope": scope,
             "execution_profile": profile, "effective_scope": effective_scope, "resource_owner": owner,
             "cleanup_registration": {"cleanup_id": f"cleanup-{fresh}", "kind": "other", "target": "ctx-corrected",
                                      "owner": owner, "external_refs": refs}},
            coordinator_generation=1,
        )
        corrected_fake = type(fake)()
        corrected_fake.external_task_id = "orca-task-corrected"
        corrected_fake.dispatch_id = "ctx-corrected"
        corrected_fake.message_id = "message-corrected"
        corrected_fake.delivery_id = "delivery-corrected"
        corrected_fake.checks_run = ["python3 -c \"raise SystemExit(0)\""]

        self._sync_with_orca(corrected_fake, arguments)

        state = runtime._projection(directory)
        self.assertEqual(state["attempts"][fresh]["status"], "reported")
        self.assertEqual(corrected_fake.acks, ["delivery-corrected"])
        self.assertEqual(evidence.read_bytes(), original)

        # The prior delivery was explicitly acknowledged before its attempt
        # was abandoned. Replaying it cannot poison the corrected successor.
        self._sync_with_orca(fake, arguments)
        state = runtime._projection(directory)
        self.assertEqual(state["attempts"][fresh]["status"], "reported")
        self.assertEqual(fake.acks, ["delivery-r38", "delivery-r38"])


if __name__ == "__main__":
    unittest.main()
