import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


SCRIPTS = Path(__file__).parents[1] / "scripts"
REFERENCES = Path(__file__).parents[1] / "references"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from validation import (
    CAPABILITY_NAMES,
    CliValidationError,
    validate_capability_receipt,
    validate_process_decision,
)
from adaptive_intake import decide_process


AGENT_GRAPH = SCRIPTS / "agent_graph.py"


def check(command: str = "python3 -m unittest skills.agent_graph") -> dict:
    return {"command": command, "oracle": "The bounded behavior check exits successfully."}


def packet(packet_id: str, path: str) -> dict:
    return {"packet_id": packet_id, "paths": [path], "check": check()}


def process_decision(mode: str) -> dict:
    return {
        "schema_version": 1,
        "decision_id": f"decision-{mode.replace('_', '-')}",
        "request_digest": "sha256:" + "0" * 64,
        "repository_scope": ["skills/agent-graph"],
        "initial_mode": mode,
        "mode": mode,
        "revision": 1,
        "observations": {
            "cohesion": "independent" if mode == "graph" else "cohesive",
            "architecture_uncertainty": "material" if mode == "light_spec" else "known",
            "reversibility": "reversible",
            "blast_radius": "multi_surface" if mode == "graph" else "local",
            "oracle_strength": "strong",
            "independent_packets": (
                [packet("packet-a", "src/a.py"), packet("packet-b", "src/b.py")]
                if mode == "graph"
                else []
            ),
            "shared_write_coupling": False,
            "context_pressure": "medium" if mode == "verified_single" else "low",
            "external_effects": "none",
            "unattended_execution": False,
        },
        "assumptions": [
            {
                "assumption_id": "assumption-mvp",
                "statement": "The repository has no declared external compatibility contract.",
                "basis": "repository",
                "evidence_ref": "file:AGENTS.md",
            }
        ],
        "material_questions": [
            {
                "question_id": "question-scope",
                "question": "Does the requested behavior include the public interface?",
                "answer": "No, the repository-local interface is the complete scope.",
                "decision_effects": ["scope", "mode"],
                "provenance": "owner",
                "safe_default_selected": False,
            }
        ],
        "selected_check": check(),
        "budget": {
            "policy": "task_local",
            "limits": [
                {
                    "resource": "attempts",
                    "value": 2,
                    "unit": "attempts",
                    "rationale": "A second attempt is useful only for a distinct verified hypothesis.",
                }
            ],
            "stop_conditions": ["The check passes.", "No new verifiable hypothesis remains."],
        },
        "triggers": {
            "escalate": ["Repository inspection reveals an independent packet."],
            "deescalate": ["The work is proven cohesive."],
            "stop": ["The acceptance oracle is too weak for the observed blast radius."],
        },
        "amendments": [],
    }


def capability(status: str, evidence: str | None = None) -> dict:
    if status == "supported":
        return {
            "status": status,
            "verification": {"method": "probe", "evidence": evidence or "probe:success"},
            "reason": None,
        }
    return {
        "status": status,
        "verification": None,
        "reason": evidence or "The adapter did not expose this optional capability.",
    }


def capability_receipt(adapter: str) -> dict:
    statuses = {
        "local_checks": "supported",
        "user_questions": "supported",
        "process_tree_cleanup": "supported",
        "isolated_workspace": "supported" if adapter == "orca" else "unsupported",
        "visible_worker_dispatch": "supported" if adapter == "orca" else "unsupported",
        "durable_worker_handle": "supported" if adapter == "orca" else "unsupported",
        "browser_surface": "supported" if adapter == "orca" else "unsupported",
        "usage_metrics": "unavailable",
        "cache_metrics": "unavailable",
    }
    missing = [name for name in CAPABILITY_NAMES if statuses[name] != "supported"]
    return {
        "schema_version": 1,
        "receipt_id": f"receipt-{adapter}",
        "adapter": {"kind": adapter, "version": "1"},
        "capabilities": {
            name: capability(statuses[name], f"{adapter}-probe:{name}")
            for name in sorted(CAPABILITY_NAMES)
        },
        "requested_capabilities": ["local_checks"],
        "missing_capabilities": sorted(missing),
        "degradation": {
            "outcome": "none",
            "operation": None,
            "missing_capabilities": [],
            "selected_alternative": None,
            "reason": None,
        },
        "extensions": {
            adapter: {"transport": "manual" if adapter == "host" else "supervised"},
            "future_adapter_field": {"unknown_optional_value": True},
        },
    }


class AdaptiveContractBehavior(unittest.TestCase):
    def test_accepts_every_process_mode_with_bounded_provenance(self) -> None:
        for mode in ("direct", "verified_single", "light_spec", "graph"):
            with self.subTest(mode=mode):
                self.assertEqual(validate_process_decision(process_decision(mode))["mode"], mode)

    def test_accepts_a_contiguous_evidence_amendment_and_replacement_check(self) -> None:
        decision = process_decision("direct")
        replacement = check("python3 -m unittest scripts.tests.test_harness_contracts")
        decision.update({"mode": "light_spec", "revision": 2, "selected_check": replacement})
        decision["amendments"] = [
            {
                "amendment_id": "amendment-interface",
                "from_revision": 1,
                "to_revision": 2,
                "from_mode": "direct",
                "to_mode": "light_spec",
                "changed_evidence": ["A public interface decision remains unresolved."],
                "reason": "The new evidence changes architecture and acceptance.",
                "replacement_check": replacement,
            }
        ]

        self.assertEqual(validate_process_decision(decision)["revision"], 2)

    def test_accepts_host_and_orca_truth_with_unknown_adapter_extensions(self) -> None:
        host = validate_capability_receipt(capability_receipt("host"))
        orca = validate_capability_receipt(capability_receipt("orca"))

        self.assertEqual(host["capabilities"]["browser_surface"]["status"], "unsupported")
        self.assertEqual(orca["capabilities"]["browser_surface"]["status"], "supported")
        self.assertTrue(host["extensions"]["future_adapter_field"]["unknown_optional_value"])

    def test_accepts_an_explicit_compatible_downgrade_for_missing_optional_capability(self) -> None:
        receipt = capability_receipt("host")
        receipt["requested_capabilities"] = ["local_checks", "visible_worker_dispatch"]
        receipt["degradation"] = {
            "outcome": "downgraded",
            "operation": "worker_dispatch",
            "missing_capabilities": ["visible_worker_dispatch"],
            "selected_alternative": "local_execution",
            "reason": "Host can execute the bounded task locally without a visible worker.",
        }

        self.assertEqual(validate_capability_receipt(receipt)["degradation"]["outcome"], "downgraded")

    def test_rejects_mode_changes_without_a_contiguous_amendment(self) -> None:
        decision = process_decision("direct")
        decision["mode"] = "graph"
        with self.assertRaisesRegex(CliValidationError, "without a matching amendment"):
            validate_process_decision(decision)

        amended = process_decision("direct")
        amended["revision"] = 2
        amended["mode"] = "verified_single"
        amended["amendments"] = [
            {
                "amendment_id": "amendment-gap",
                "from_revision": 2,
                "to_revision": 3,
                "from_mode": "direct",
                "to_mode": "verified_single",
                "changed_evidence": ["A debugging loop emerged."],
                "reason": "One iterative loop is now required.",
                "replacement_check": amended["selected_check"],
            }
        ]
        with self.assertRaisesRegex(CliValidationError, "contiguous revision chain"):
            validate_process_decision(amended)

    def test_rejects_transcript_provider_and_universal_threshold_payloads(self) -> None:
        invalid_values = []
        transcript = process_decision("direct")
        transcript["transcript"] = ["unbounded conversation"]
        invalid_values.append(transcript)
        provider = process_decision("direct")
        provider["provider_assumption"] = {"model": "hidden-default"}
        invalid_values.append(provider)
        universal = process_decision("direct")
        universal["budget"]["policy"] = "universal"
        invalid_values.append(universal)
        threshold = process_decision("direct")
        threshold["score_threshold"] = 7
        invalid_values.append(threshold)

        for value in invalid_values:
            with self.subTest(fields=sorted(value)):
                with self.assertRaises(CliValidationError):
                    validate_process_decision(value)

    def test_rejects_unknown_or_unverified_supported_capability_claims(self) -> None:
        unknown = capability_receipt("host")
        unknown["capabilities"]["telepathy"] = capability("supported")
        unverified = capability_receipt("host")
        unverified["capabilities"]["local_checks"]["verification"] = None

        for value in (unknown, unverified):
            with self.subTest(receipt=value["receipt_id"]):
                with self.assertRaises(CliValidationError):
                    validate_capability_receipt(value)

    def test_rejects_inconsistent_missing_and_degradation_claims(self) -> None:
        missing = capability_receipt("host")
        missing["missing_capabilities"] = []
        with self.assertRaisesRegex(CliValidationError, "missing_capabilities"):
            validate_capability_receipt(missing)

        degraded = capability_receipt("host")
        degraded["requested_capabilities"] = ["visible_worker_dispatch"]
        with self.assertRaisesRegex(CliValidationError, "degradation"):
            validate_capability_receipt(degraded)

    def test_keeps_both_contract_schemas_valid_draft_2020_12(self) -> None:
        for name in ("process-decision.schema.json", "capability-receipt.schema.json"):
            with self.subTest(schema=name):
                schema = json.loads((REFERENCES / name).read_text(encoding="utf-8"))
                Draft202012Validator.check_schema(schema)


class AdaptiveIntakeBehavior(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.repository = Path(self.temporary_directory.name)
        (self.repository / ".git").mkdir()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def select(self, **signals) -> dict:
        return decide_process(
            self.repository,
            request="Apply the bounded repository change.",
            check_command="python3 -m compileall .",
            signals=signals,
        )

    def test_selects_direct_for_small_known_reversible_work_without_a_graph(self) -> None:
        result = self.select(
            small_change=True,
            known_scope=True,
            cohesion="cohesive",
            reversibility="reversible",
            oracle_strength="strong",
        )

        self.assertEqual(result["decision"]["mode"], "direct")
        self.assertFalse(result["graph_artifacts_created"])
        self.assertFalse((self.repository / "openspec" / "runs").exists())

    def test_selects_verified_single_for_one_cohesive_debugging_loop(self) -> None:
        result = self.select(
            small_change=False,
            known_scope=True,
            cohesion="cohesive",
            needs_iteration=True,
            context_pressure="medium",
        )

        self.assertEqual(result["decision"]["mode"], "verified_single")

    def test_selects_light_spec_for_material_interface_uncertainty(self) -> None:
        result = self.select(
            known_scope=False,
            architecture_uncertainty="material",
            blast_radius="multi_surface",
        )

        self.assertEqual(result["decision"]["mode"], "light_spec")

    def test_selects_graph_only_with_complete_independent_packet_contracts(self) -> None:
        common = {
            "graph_requested": True,
            "cohesion": "independent",
            "independent_packets": [
                packet("packet-a", "src/a.py"),
                packet("packet-b", "src/b.py"),
            ],
            "integrator": "coordinator",
            "permission_observed": True,
            "budget_limits": [
                {
                    "resource": "workers",
                    "value": 2,
                    "unit": "workers",
                    "rationale": "The two disjoint packets are independently useful.",
                }
            ],
            "cleanup_plan": "The integrator verifies every owned resource is released.",
        }
        selected = self.select(**common)
        self.assertEqual(selected["decision"]["mode"], "graph")
        self.assertEqual(selected["graph_blockers"], [])

        incomplete = dict(common)
        incomplete.pop("integrator")
        incomplete["independent_packets"] = [packet("packet-a", "src/a.py")]
        rejected = self.select(**incomplete)
        self.assertEqual(rejected["decision"]["mode"], "light_spec")
        self.assertTrue(any("two independently useful" in item for item in rejected["graph_blockers"]))
        self.assertTrue(any("integration owner" in item for item in rejected["graph_blockers"]))

        unverified = dict(common)
        unverified["independent_packets"] = [
            {"packet_id": "packet-a", "paths": ["src/a.py"]},
            packet("packet-b", "src/b.py"),
        ]
        rejected = self.select(**unverified)
        self.assertEqual(rejected["decision"]["mode"], "light_spec")
        self.assertTrue(any("individual check" in item for item in rejected["graph_blockers"]))

    def test_suppresses_a_question_answered_by_repository_instructions(self) -> None:
        (self.repository / "AGENTS.md").write_text(
            "Breaking changes are allowed for this repository.\n", encoding="utf-8"
        )
        ambiguity = {
            "question_id": "compatibility",
            "question": "Must the old interface remain compatible?",
            "decision_effects": ["scope", "mode"],
            "repository_fact": "compatibility",
            "safe_default": "Preserve the old interface.",
        }

        result = self.select(ambiguities=[ambiguity])

        self.assertEqual(result["status"], "selected")
        self.assertEqual(result["questions"], [])
        self.assertEqual(result["decision"]["assumptions"][0]["basis"], "repository")

    def test_emits_one_decision_changing_question_and_honors_its_safe_default(self) -> None:
        ambiguity = {
            "question_id": "public-interface",
            "question": "Is the public interface part of this change?",
            "decision_effects": ["scope", "acceptance", "mode"],
            "safe_default": "Keep the public interface unchanged.",
        }

        pending = self.select(ambiguities=[ambiguity])
        self.assertEqual(pending["status"], "questions")
        self.assertEqual(len(pending["questions"]), 1)
        self.assertIsNone(pending["decision"])

        selected = decide_process(
            self.repository,
            request="Apply the bounded repository change.",
            check_command="python3 -m compileall .",
            signals={"ambiguities": [ambiguity]},
            use_safe_defaults=True,
        )
        question = selected["decision"]["material_questions"][0]
        self.assertEqual(question["provenance"], "safe_default")
        self.assertTrue(question["safe_default_selected"])

    def test_exposes_the_read_only_intake_command_without_provider_or_run_artifacts(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(AGENT_GRAPH),
                "intake",
                "--repo",
                str(self.repository),
                "--request",
                "Make the small reversible edit.",
                "--check",
                "python3 -m compileall .",
                "--signals-json",
                json.dumps({"small_change": True, "known_scope": True}),
                "--json",
            ],
            check=False,
            capture_output=True,
            text=True,
            env={"PATH": str(Path(sys.executable).parent), "MODEL_PROVIDER": "ignored"},
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["result"]["decision"]["mode"], "direct")
        self.assertNotIn("provider", json.dumps(payload["result"]["decision"]).casefold())
        self.assertFalse((self.repository / "openspec" / "runs").exists())


if __name__ == "__main__":
    unittest.main()
