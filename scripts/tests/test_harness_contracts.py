import json
import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[2]
GRAPH = ROOT / "skills" / "agent-graph" / "scripts" / "agent_graph.py"


class PortableGraphDocumentationBehavior(unittest.TestCase):
    def read(self, relative: str) -> str:
        return (ROOT / relative).read_text(encoding="utf-8")

    def test_spec_requires_and_validates_every_graph_field(self) -> None:
        sources = self.read("skills/spec/SKILL.md") + self.read("commands/spec.md")

        for field in ("Depends:", "Paths:", "Mode:", "Isolation:", "Acceptance:", "Check:"):
            self.assertIn(field, sources)
        self.assertIn("agent_graph.py validate", sources)
        self.assertIn("never starts workers", sources)

    def test_impl_owns_the_fresh_coordinator_and_graph_commands(self) -> None:
        sources = self.read("skills/impl/SKILL.md") + self.read("commands/impl.md")

        for command in (
            "bootstrap", "claim-coordinator", "resume", "ready", "dispatch", "sync",
            "record-result", "reply", "run-check", "grade", "record-repair",
            "cleanup-register", "cleanup-finish", "status --watch", "takeover", "digest", "complete",
        ):
            self.assertIn(command, sources)
        self.assertIn("fresh top-level session", sources)
        self.assertIn("Never create an Orca Task or Dispatch for the coordinator", sources)
        self.assertIn("generated capsule", sources)
        self.assertIn("tracked-terminal", sources)
        self.assertIn("Maestri", sources)

    def test_research_keeps_collectors_read_only_and_adjudication_local(self) -> None:
        source = self.read("skills/research/SKILL.md")

        self.assertIn("Mode: read", source)
        self.assertIn("agent_graph.py validate", source)
        self.assertIn("dispatch", source)
        self.assertIn("record-result", source)
        self.assertIn("main researcher", source)

    def test_harness_contracts_keep_routing_decomposition_and_portability_explicit(self) -> None:
        sources = "\n".join(
            self.read(relative)
            for relative in (
                "skills/agent-graph/SKILL.md",
                "skills/agent-graph/references/task-graph.md",
                "skills/impl/SKILL.md",
                "skills/impl/references/model-routing.md",
                "skills/spec/SKILL.md",
                "commands/impl.md",
                "commands/spec.md",
                "README.md",
            )
        )
        for phrase in (
            "immutable control runtime",
            "strong",
            "xhigh",
            "cheapest sufficient",
            "smallest useful",
            "one heavy worker",
            "dynamic delegation",
            "Host path",
            "never dispatches",
            "Mode: read",
            "process exit",
        ):
            self.assertIn(phrase, sources)
        self.assertNotIn("uses Luna", sources)
        self.assertNotIn("uses Terra", sources)
        self.assertNotIn("uses Sol", sources)

    def test_routes_every_entry_through_the_minimum_process_before_graph_bootstrap(self) -> None:
        sources = "\n".join(
            self.read(relative)
            for relative in (
                "commands/spec.md",
                "commands/impl.md",
                "skills/spec/SKILL.md",
                "skills/impl/SKILL.md",
                "skills/agent-graph/SKILL.md",
            )
        )

        self.assertIn("agent_graph.py intake", sources)
        for mode in ("`direct`", "`verified_single`", "`light_spec`", "`graph`"):
            self.assertIn(mode, sources)
        self.assertIn("OpenSpec remains optional", sources)
        self.assertIn("Graph mode alone", sources)
        self.assertIn("Never use a provider, model, Canvas", sources)
        self.assertIn("Never invoke `$grill-me` unless the user explicitly asks", sources)
        self.assertNotIn("requests `strong` lane with `xhigh` effort", sources)

    def test_runs_non_graph_modes_without_openspec_or_orca_and_bootstraps_only_graph_mode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            subprocess.run(["git", "init", "-q", str(repository)], check=True)
            subprocess.run(
                ["git", "-C", str(repository), "config", "user.email", "test@example.com"],
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(repository), "config", "user.name", "Test"],
                check=True,
            )

            def intake(signals: dict) -> dict:
                completed = subprocess.run(
                    [
                        sys.executable,
                        str(GRAPH),
                        "intake",
                        "--repo",
                        str(repository),
                        "--request",
                        "Apply the bounded change.",
                        "--check",
                        f'"{sys.executable}" -c "raise SystemExit(0)"',
                        "--signals-json",
                        json.dumps(signals),
                        "--json",
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                    env={"PATH": str(Path(sys.executable).parent), "ORCA_CLI_COMMAND": "missing-orca"},
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)
                return json.loads(completed.stdout)["result"]

            direct = intake({"small_change": True, "known_scope": True})
            verified = intake(
                {
                    "small_change": False,
                    "known_scope": True,
                    "needs_iteration": True,
                    "context_pressure": "medium",
                }
            )
            light = intake(
                {"known_scope": False, "architecture_uncertainty": "material"}
            )

            self.assertEqual(direct["decision"]["mode"], "direct")
            self.assertEqual(verified["decision"]["mode"], "verified_single")
            self.assertEqual(light["decision"]["mode"], "light_spec")
            self.assertFalse((repository / "openspec").exists())

            check = {
                "command": f'"{sys.executable}" -c "raise SystemExit(0)"',
                "oracle": "The task exits successfully.",
            }
            graph = intake(
                {
                    "known_scope": True,
                    "graph_requested": True,
                    "cohesion": "independent",
                    "independent_packets": [
                        {"packet_id": "packet-a", "paths": ["src/a.py"], "check": check},
                        {"packet_id": "packet-b", "paths": ["src/b.py"], "check": check},
                    ],
                    "integrator": "coordinator",
                    "permission_observed": True,
                    "budget_limits": [
                        {
                            "resource": "workers",
                            "value": 2,
                            "unit": "workers",
                            "rationale": "Two packets have disjoint ownership.",
                        }
                    ],
                    "cleanup_plan": "Verify that every owned process is gone.",
                }
            )
            self.assertEqual(graph["decision"]["mode"], "graph")
            self.assertFalse((repository / "openspec").exists())

            change = repository / "openspec/changes/portable"
            change.mkdir(parents=True)
            (change / "proposal.md").write_text("# Proposal\n", encoding="utf-8")
            (change / "design.md").write_text("# Design\n", encoding="utf-8")
            (change / "tasks.md").write_text(
                f"""# Tasks

- [ ] packet-a Apply the first graph change
  Depends: []
  Paths: [src/a.py]
  Mode: write
  Isolation: auto
  Acceptance: The first bounded change is verified.
  Check: "{sys.executable}" -c "raise SystemExit(0)"

- [ ] packet-b Apply the second graph change
  Depends: []
  Paths: [src/b.py]
  Mode: write
  Isolation: auto
  Acceptance: The second bounded change is verified.
  Check: "{sys.executable}" -c "raise SystemExit(0)"
""",
                encoding="utf-8",
            )
            (change / "process-decision.json").write_text(
                json.dumps(graph), encoding="utf-8"
            )
            subprocess.run(["git", "-C", str(repository), "add", "."], check=True)
            subprocess.run(
                ["git", "-C", str(repository), "commit", "-qm", "test fixture"],
                check=True,
            )
            bootstrap = subprocess.run(
                [
                    sys.executable,
                    str(GRAPH),
                    "bootstrap",
                    "--repo",
                    str(repository),
                    "--change",
                    "portable",
                    "--run-id",
                    "run-1",
                    "--bootstrap-id",
                    "bootstrap-1",
                    "--driver",
                    "host",
                    "--json",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(bootstrap.returncode, 0, bootstrap.stderr)
            result = json.loads(bootstrap.stdout)["result"]
            self.assertTrue((repository / result["capsule_path"]).is_file())
            self.assertTrue(
                (repository / "openspec/runs/portable/run-1/artifacts/workspace-bootstrap-receipt-v1.json").is_file()
            )

    def test_learning_snapshot_drops_transcript_bearing_source_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            state_path = repository / "openspec/runs/change/run-1/state.json"
            state_path.parent.mkdir(parents=True)
            state_path.write_text(
                json.dumps(
                    {
                        "status": "complete",
                        "change": "change",
                        "run_id": "run-1",
                        "outcome": "pass",
                        "prompt": "do not copy this",
                        "reports": [{"body": "do not copy this"}],
                        "tasks": {
                            "B-02": {
                                "grade": "pass",
                                "check": {"attempts": 1, "status": "passed", "command": "check"},
                                "contract": {"visual": [], "visual_scope": []},
                                "hypotheses": [],
                                "evidence_refs": [],
                            },
                            "A-01": {
                                "grade": "pass",
                                "check": {"attempts": 1, "status": "passed", "command": "check"},
                                "contract": {"visual": [], "visual_scope": []},
                                "hypotheses": [],
                                "evidence_refs": [],
                                "terminal_output": "do not copy this",
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )
            source_state = state_path.read_bytes()
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "skills/impl/scripts/learning.py"),
                    "--repo",
                    str(repository),
                    "snapshot",
                    "--change",
                    "change",
                    "--run-id",
                    "run-1",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            evidence = repository / "openspec/impl-learning/evidence/run-1.state.json"
            evidence_text = evidence.read_text(encoding="utf-8")
            self.assertNotIn("do not copy this", evidence_text)
            self.assertEqual([task["task_id"] for task in json.loads(evidence_text)["tasks"]], ["A-01", "B-02"])
            self.assertEqual(state_path.read_bytes(), source_state)
            record = json.loads((repository / "openspec/impl-learning/runs/run-1.json").read_text())
            telemetry = record["process_telemetry"]
            self.assertEqual(telemetry["policy"], "shadow_only")
            self.assertEqual(telemetry["provider_usage"]["status"], "unavailable")
            self.assertEqual(telemetry["provider_cache"]["status"], "unavailable")
            self.assertEqual(telemetry["time"]["status"], "unavailable")
            self.assertIsNone(record["facts"][0]["check_total_duration_ms"])

    def test_learning_snapshot_preserves_bounded_routing_and_lifecycle_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            state_path = repository / "openspec/runs/change/run-1/state.json"
            state_path.parent.mkdir(parents=True)
            artifacts = state_path.parent / "artifacts"
            artifacts.mkdir()
            (artifacts / "attempt.json").write_bytes(b"attempt receipt")
            (artifacts / "cleanup.json").write_bytes(b"cleanup receipt")
            (artifacts / "delegation.json").write_bytes(b"delegation receipt")
            (artifacts / "route.json").write_bytes(b"route receipt")
            state_path.write_text(
                json.dumps(
                    {
                        "status": "complete",
                        "change": "change",
                        "run_id": "run-1",
                        "outcome": "partial",
                        "prompt": "secret prompt body",
                        "tasks": {
                            "TASK-01": {
                                "grade": "pass",
                                "check": {
                                    "attempts": 1,
                                    "status": "passed",
                                    "command": "python3 check.py",
                                    "exit_code": 0,
                                    "duration_ms": 4,
                                    "total_duration_ms": 4,
                                },
                                "contract": {
                                    "visual": ["home | populated | mobile | 390x664 | populated"],
                                    "visual_scope": ["home | populated | mobile | The bounded mobile contract is reviewed."],
                                },
                                "hypotheses": [],
                                "evidence_refs": ["file:artifacts/check.json"],
                            }
                        },
                        "attempts": {
                            "attempt-1": {
                                "task_id": "TASK-01",
                                "attempt_id": "attempt-1",
                                "status": "reported",
                                "receipt_id": "receipt-attempt-1",
                                "receipt_path": "openspec/runs/change/run-1/artifacts/attempt.json",
                                "routing_summary": {
                                    "role": "implementation",
                                    "risk": "material",
                                    "requested": {"lane": "strong", "agent": "codex", "model": "requested-model", "effort": "high"},
                                    "resolved": {"agent": "codex", "model": "resolved-model", "effort": "medium"},
                                    "fallback_reason": "requested effort unavailable",
                                    "risk_rationale": {"risk": "material", "required_tools": ["shell"]},
                                    "cost_rank": 2,
                                },
                                "routing_decision": {"outcome": "resolved", "blocked_reason": None},
                                "routing_decision_ref": {
                                    "receipt_id": "receipt-route-1",
                                    "receipt_path": "openspec/runs/change/run-1/artifacts/route.json",
                                    "sha256": "sha256:" + hashlib.sha256(b"route receipt").hexdigest(),
                                    "authority": {"kind": "coordinator", "generation": 1},
                                },
                                "execution_profile": {
                                    "role": "implementation",
                                    "requested": {"lane": "strong", "agent": "codex", "model": "requested-model", "effort": "high"},
                                    "resolved": {"agent": "codex", "model": "resolved-model", "effort": "medium"},
                                    "fallback_reason": "requested effort unavailable",
                                },
                                "provider_telemetry": {
                                    "usage": {"input_units": 12, "output_units": 7},
                                    "cache": {"read_units": 3},
                                },
                            }
                        },
                        "cleanup": {"cleanup-1": {"owner": "attempt-1", "status": "verified", "receipt": "openspec/runs/change/run-1/artifacts/cleanup.json"}},
                        "delegations": {
                            "delegation-1": {
                                "parent_task_id": "TASK-01",
                                "child_attempt_id": "attempt-child",
                                "status": "released",
                                "lifecycle_receipts": {
                                    "released": {
                                        "receipt_id": "receipt-delegation-1",
                                        "receipt_path": "openspec/runs/change/run-1/artifacts/delegation.json",
                                        "sha256": "sha256:" + hashlib.sha256(b"delegation receipt").hexdigest(),
                                        "byte_length": len(b"delegation receipt"),
                                    }
                                },
                            }
                        },
                        "report": "secret report body",
                        "terminal_output": "secret terminal body",
                        "note_body": "secret note body",
                    }
                ),
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "skills/impl/scripts/learning.py"),
                    "--repo",
                    str(repository),
                    "snapshot",
                    "--change",
                    "change",
                    "--run-id",
                    "run-1",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            record = json.loads((repository / "openspec/impl-learning/runs/run-1.json").read_text())
            fact = record["facts"][0]
            self.assertEqual(fact["routing_decisions"][0]["fallback_reason"], "requested effort unavailable")
            self.assertEqual(fact["routing_decisions"][0]["requested"]["model"], "requested-model")
            self.assertEqual(fact["routing_decisions"][0]["reference"]["receipt_id"], "receipt-route-1")
            self.assertEqual(record["process_telemetry"]["provider_usage"]["status"], "observed")
            self.assertEqual(record["process_telemetry"]["provider_cache"]["status"], "observed")
            self.assertEqual(record["process_telemetry"]["profiles"]["status"], "observed")
            self.assertEqual(
                {item["kind"] for item in fact["lifecycle_receipts"] if item["receipt_path"]},
                {"attempt", "cleanup", "delegation"},
            )
            for item in fact["lifecycle_receipts"]:
                if item["receipt_path"]:
                    self.assertTrue(item["sha256"].startswith("sha256:"))
                    self.assertGreater(item["byte_length"], 0)
            self.assertEqual(
                {item["receipt_id"] for item in fact["lifecycle_receipts"] if item["receipt_id"]},
                {"receipt-attempt-1", "receipt-delegation-1"},
            )
            self.assertNotIn("secret", json.dumps(record).casefold())
            import jsonschema

            schema = json.loads((ROOT / "skills/impl/references/learning-run.schema.json").read_text())
            jsonschema.Draft202012Validator.check_schema(schema)
            jsonschema.validate(record, schema)

    def test_learning_snapshot_normalizes_real_receipt_producer_shapes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            state_path = repository / "openspec/runs/change/run-1/state.json"
            artifacts = state_path.parent / "artifacts"
            artifacts.mkdir(parents=True)
            receipts = {
                "host.json": b"host receipt",
                "unverifiable.json": b"unverifiable receipt",
                "route.json": b"routing receipt",
                "delegation.json": b"delegation receipt",
            }
            for name, body in receipts.items():
                (artifacts / name).write_bytes(body)
            route_hash = "sha256:" + hashlib.sha256(receipts["route.json"]).hexdigest()
            delegation_hash = "sha256:" + hashlib.sha256(receipts["delegation.json"]).hexdigest()
            state_path.write_text(
                json.dumps(
                    {
                        "status": "complete",
                        "change": "change",
                        "run_id": "run-1",
                        "outcome": "pass",
                        "tasks": {
                            "TASK-01": {
                                "grade": "pass",
                                "check": {"attempts": 1, "status": "passed", "command": "check"},
                                "contract": {"visual": [], "visual_scope": []},
                                "hypotheses": [],
                                "evidence_refs": [],
                            }
                        },
                        "attempts": {
                            "attempt-host": {
                                "task_id": "TASK-01",
                                "status": "reported",
                                "receipt_id": "receipt-host",
                                "receipt_path": "openspec/runs/change/run-1/artifacts/host.json",
                                "routing_summary": {
                                    "role": "implementation",
                                    "requested": {"lane": "standard", "agent": "codex", "model": "model", "effort": "medium"},
                                    "resolved": {"lane": "standard", "agent": "codex", "model": "model", "effort": "medium"},
                                },
                                "routing_decision_ref": {
                                    "receipt_id": "receipt-route",
                                    "receipt_path": "openspec/runs/change/run-1/artifacts/route.json",
                                    "sha256": route_hash,
                                    "authority": {"kind": "coordinator", "generation": 1},
                                },
                                "execution_profile": {},
                            }
                        },
                        "cleanup": {
                            "cleanup-typed": {
                                "owner": {
                                    "execution_host_id": "host-provider-01",
                                    "workspace_key": "workspace-provider-01",
                                    "attempt_id": "attempt-host",
                                    "terminal_id": None,
                                    "incarnation_id": None,
                                    "process_root": None,
                                    "provenance": "orca-supervised:runtime-provider-01:worktree-provider-01:run-provider-01:dispatch-provider-01",
                                },
                                "status": "verified",
                                "receipt": {
                                    "kind": "provider-dispatch",
                                    "owner": {
                                        "execution_host_id": "host-provider-01",
                                        "workspace_key": "workspace-provider-01",
                                        "attempt_id": "attempt-host",
                                        "terminal_id": None,
                                        "incarnation_id": None,
                                        "process_root": None,
                                        "provenance": "orca-supervised:runtime-provider-01:worktree-provider-01:run-provider-01:dispatch-provider-01",
                                    },
                                    "dispatch_id": "dispatch-provider-01",
                                    "runtime_id": "runtime-provider-01",
                                    "worktree_id": "worktree-provider-01",
                                    "run_id": "run-provider-01",
                                    "status": "already_released",
                                },
                            },
                            "cleanup-unverifiable": {
                                "owner": "attempt-host",
                                "status": "unverifiable",
                                "receipt": {
                                    "receipt_id": "receipt-cleanup",
                                    "receipt_path": "openspec/runs/change/run-1/artifacts/unverifiable.json",
                                    "driver": "host",
                                },
                            },
                        },
                        "delegations": {
                            "delegation-1": {
                                "parent_task_id": "TASK-01",
                                "child_attempt_id": "attempt-child",
                                "status": "released",
                                "lifecycle_receipts": {
                                    "released": {
                                        "receipt_id": "receipt-delegation",
                                        "receipt_path": "openspec/runs/change/run-1/artifacts/delegation.json",
                                        "sha256": delegation_hash,
                                        "byte_length": len(receipts["delegation.json"]),
                                    }
                                },
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "skills/impl/scripts/learning.py"),
                    "--repo",
                    str(repository),
                    "snapshot",
                    "--change",
                    "change",
                    "--run-id",
                    "run-1",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            record = json.loads((repository / "openspec/impl-learning/runs/run-1.json").read_text())
            lifecycle = record["facts"][0]["lifecycle_receipts"]
            typed = next(item for item in lifecycle if item["entity_id"] == "cleanup-typed")
            self.assertEqual(typed["kind"], "cleanup")
            self.assertEqual(typed["status"], "verified")
            self.assertEqual(
                {typed[field] for field in ("receipt_id", "receipt_path", "sha256", "byte_length")},
                {None},
            )
            unverifiable = next(item for item in lifecycle if item["entity_id"] == "cleanup-unverifiable")
            self.assertEqual(unverifiable["receipt_id"], "receipt-cleanup")
            self.assertEqual(unverifiable["sha256"], "sha256:" + hashlib.sha256(receipts["unverifiable.json"]).hexdigest())
            self.assertEqual(unverifiable["byte_length"], len(receipts["unverifiable.json"]))
            delegation = next(item for item in lifecycle if item["kind"] == "delegation")
            self.assertEqual(delegation["sha256"], delegation_hash)
            self.assertEqual(delegation["byte_length"], len(receipts["delegation.json"]))
            routing = record["facts"][0]["routing_decisions"][0]
            self.assertEqual(routing["reference"], {
                "receipt_id": "receipt-route",
                "receipt_path": "openspec/runs/change/run-1/artifacts/route.json",
                "sha256": route_hash,
            })
            projected = json.dumps(record)
            for provider_value in (
                "dispatch-provider-01",
                "runtime-provider-01",
                "worktree-provider-01",
                "run-provider-01",
                "host-provider-01",
                "workspace-provider-01",
                "orca",
                "already_released",
            ):
                self.assertNotIn(provider_value, projected)
            import jsonschema

            schema = json.loads((ROOT / "skills/impl/references/learning-run.schema.json").read_text())
            jsonschema.Draft202012Validator.check_schema(schema)
            jsonschema.validate(record, schema)

    def test_learning_snapshot_rejects_unbounded_checks_and_invalid_visual_scopes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            state_path = repository / "openspec/runs/change/run-1/state.json"
            state_path.parent.mkdir(parents=True)
            state = {
                "status": "complete",
                "change": "change",
                "run_id": "run-1",
                "outcome": "pass",
                "tasks": {
                    "TASK-01": {
                        "grade": "pass",
                        "check": {"attempts": 1, "status": "passed", "command": "x" * 513},
                        "contract": {"visual": [], "visual_scope": []},
                        "hypotheses": [],
                        "evidence_refs": [],
                    }
                },
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")
            command_result = subprocess.run(
                [sys.executable, str(ROOT / "skills/impl/scripts/learning.py"), "--repo", str(repository), "snapshot", "--change", "change", "--run-id", "run-1"],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(command_result.returncode, 0)
            self.assertFalse((repository / "openspec/impl-learning/runs/run-1.json").exists())

            state["tasks"]["TASK-01"]["check"]["command"] = "check"
            state["tasks"]["TASK-01"]["contract"]["visual_scope"] = ["home | populated | mobile | too short"]
            state_path.write_text(json.dumps(state), encoding="utf-8")
            visual_result = subprocess.run(
                [sys.executable, str(ROOT / "skills/impl/scripts/learning.py"), "--repo", str(repository), "snapshot", "--change", "change", "--run-id", "run-1"],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(visual_result.returncode, 0)

    def test_learning_snapshot_rejects_signed_receipt_metadata_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            state_path = repository / "openspec/runs/change/run-1/state.json"
            artifacts = state_path.parent / "artifacts"
            artifacts.mkdir(parents=True)
            receipt_path = "openspec/runs/change/run-1/artifacts/delegation.json"
            (artifacts / "delegation.json").write_bytes(b"actual receipt bytes")
            state_path.write_text(
                json.dumps(
                    {
                        "status": "complete",
                        "change": "change",
                        "run_id": "run-1",
                        "outcome": "pass",
                        "tasks": {
                            "TASK-01": {
                                "grade": "pass",
                                "check": {"attempts": 1, "status": "passed", "command": "check"},
                                "contract": {"visual": [], "visual_scope": []},
                                "hypotheses": [],
                                "evidence_refs": [],
                            }
                        },
                        "attempts": {},
                        "cleanup": {},
                        "delegations": {
                            "delegation-1": {
                                "parent_task_id": "TASK-01",
                                "status": "released",
                                "lifecycle_receipts": {
                                    "released": {
                                        "receipt_id": "receipt-1",
                                        "receipt_path": receipt_path,
                                        "sha256": "sha256:" + "0" * 64,
                                        "byte_length": 1,
                                    }
                                },
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(ROOT / "skills/impl/scripts/learning.py"), "--repo", str(repository), "snapshot", "--change", "change", "--run-id", "run-1"],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((repository / "openspec/impl-learning/runs/run-1.json").exists())

    def test_active_harness_docs_do_not_reference_the_flat_runtime(self) -> None:
        paths = [ROOT / "README.md", *sorted((ROOT / "commands").glob("*.md"))]
        paths.extend(
            ROOT / relative
            for relative in (
                "skills/spec/SKILL.md",
                "skills/impl/SKILL.md",
                "skills/research/SKILL.md",
                "skills/frontend-visual-validation/SKILL.md",
            )
        )
        forbidden = "impl" + "_state.py"
        legacy_directory = "openspec/" + "impl-state"

        for path in paths:
            with self.subTest(path=path.relative_to(ROOT)):
                content = path.read_text(encoding="utf-8")
                self.assertNotIn(forbidden, content)
                self.assertNotIn(legacy_directory, content)

    def test_portability_docs_and_shipped_local_references_are_current(self) -> None:
        sources = "\n".join(
            self.read(relative)
            for relative in ("README.md", "skills/agent-graph/SKILL.md", "skills/impl/SKILL.md")
        )
        for phrase in (
            "portable core",
            "OpenSpec is optional",
            "Host is the baseline",
            "Orca is the current rich adapter",
            "future adapter",
            "unavailable",
            "never zero or estimated",
            "shadow learning",
        ):
            self.assertIn(phrase.casefold(), sources.casefold())

        for relative in (
            "commands/spec.md",
            "commands/impl.md",
            "skills/spec/SKILL.md",
            "skills/impl/SKILL.md",
            "skills/agent-graph/SKILL.md",
            "skills/agent-graph/scripts/agent_graph.py",
            "skills/impl/scripts/learning.py",
        ):
            with self.subTest(reference=relative):
                self.assertTrue((ROOT / relative).is_file())

    def test_the_shipped_change_validates_without_starting_workers(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(GRAPH),
                "validate",
                "--repo",
                str(ROOT),
                "--change",
                "portable-agent-graph-orchestration",
                "--json",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"task_count": 8', result.stdout)


if __name__ == "__main__":
    unittest.main()
