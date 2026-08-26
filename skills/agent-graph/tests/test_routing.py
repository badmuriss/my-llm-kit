import importlib.util
import json
import sys
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "routing.py"
SPEC = importlib.util.spec_from_file_location("routing", SCRIPT)
assert SPEC and SPEC.loader
routing = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = routing
SPEC.loader.exec_module(routing)


CATALOG = {
    "profiles": [
        {
            "agent": "builder-b",
            "model": "runtime-fast-b",
            "lane": "fast",
            "efforts": ["low", "medium", "high"],
            "tools": ["files", "shell"],
            "max_context_tokens": 32_000,
            "cost_rank": 2,
        },
        {
            "agent": "builder-a",
            "model": "runtime-fast-a",
            "lane": "fast",
            "efforts": ["low", "medium", "high"],
            "tools": ["files", "shell"],
            "max_context_tokens": 32_000,
            "cost_rank": 1,
        },
        {
            "agent": "builder-a",
            "model": "runtime-balanced",
            "lane": "balanced",
            "efforts": ["medium", "high", "xhigh"],
            "tools": ["browser", "files", "shell"],
            "max_context_tokens": 128_000,
            "cost_rank": 1,
        },
        {
            "agent": "builder-a",
            "model": "runtime-strong",
            "lane": "strong",
            "efforts": ["low", "high", "xhigh"],
            "tools": ["browser", "files", "shell"],
            "max_context_tokens": 256_000,
            "cost_rank": 1,
        },
    ]
}


class RoleRoutingBehavior(unittest.TestCase):
    def test_routes_every_supported_role_deterministically(self) -> None:
        expected = {
            "coordinator": ("runtime-balanced", "high"),
            "research": ("runtime-fast-a", "low"),
            "documentation": ("runtime-fast-a", "low"),
            "implementation": ("runtime-fast-a", "medium"),
            "review": ("runtime-balanced", "medium"),
            "verification": ("runtime-fast-a", "low"),
            "integration": ("runtime-balanced", "high"),
        }

        for role, resolved in expected.items():
            with self.subTest(role=role):
                decision = routing.plan_route(CATALOG, role=role)
                reversed_decision = routing.plan_route(
                    {"profiles": list(reversed(CATALOG["profiles"]))},
                    role=role,
                )

                self.assertEqual(decision.outcome, "resolved")
                self.assertEqual(
                    (decision.resolved["model"], decision.resolved["effort"]),
                    resolved,
                )
                self.assertEqual(decision.to_dict(), reversed_decision.to_dict())

    def test_uses_risk_tools_context_and_checks_as_compatibility_inputs(self) -> None:
        material = routing.plan_route(CATALOG, role="implementation", risk="material")
        browser = routing.plan_route(
            CATALOG,
            role="research",
            required_tools=("browser",),
        )
        large_context = routing.plan_route(
            CATALOG,
            role="documentation",
            context_tokens=64_000,
        )
        no_check = routing.plan_route(
            CATALOG,
            role="verification",
            check_strength="none",
        )

        self.assertEqual(material.resolved["model"], "runtime-balanced")
        self.assertEqual(browser.resolved["model"], "runtime-balanced")
        self.assertEqual(large_context.resolved["model"], "runtime-balanced")
        self.assertEqual(no_check.resolved["model"], "runtime-balanced")
        self.assertEqual(no_check.resolved["effort"], "high")

    def test_keeps_model_and_effort_independent(self) -> None:
        decision = routing.plan_route(
            CATALOG,
            role="implementation",
            overrides={"model": "runtime-strong", "effort": "low"},
            escalation_reason="Security review requires the strong lane despite low effort.",
        )

        self.assertEqual(decision.outcome, "blocked")
        self.assertIn("safe minimum medium", decision.blocked_reason)

        low_effort_strong = routing.plan_route(
            CATALOG,
            role="documentation",
            overrides={"model": "runtime-strong", "effort": "low"},
            escalation_reason="Security review requires the strong lane despite low effort.",
        )
        self.assertEqual(
            low_effort_strong.resolved,
            {"agent": "builder-a", "model": "runtime-strong", "effort": "low"},
        )

    def test_does_not_raise_a_routine_worker_to_advertised_xhigh(self) -> None:
        catalog = {
            "profiles": [
                {
                    "agent": "cheap-worker",
                    "model": "runtime-fast",
                    "lane": "fast",
                    "efforts": ["low", "medium", "high", "xhigh"],
                    "tools": ["files"],
                    "cost_rank": 0,
                },
                {
                    "agent": "expensive-worker",
                    "model": "runtime-strong",
                    "lane": "strong",
                    "efforts": ["xhigh"],
                    "tools": ["files"],
                    "cost_rank": 0,
                },
            ]
        }

        decision = routing.plan_route(catalog, role="implementation")

        self.assertEqual(
            decision.resolved,
            {"agent": "cheap-worker", "model": "runtime-fast", "effort": "medium"},
        )
        self.assertIsNone(decision.escalation_reason)

    def test_skips_automatic_xhigh_when_a_safe_compatible_worker_exists(self) -> None:
        catalog = {
            "profiles": [
                {
                    "agent": "fast-worker",
                    "model": "runtime-fast-xhigh",
                    "lane": "fast",
                    "efforts": ["xhigh"],
                    "tools": ["files"],
                },
                {
                    "agent": "balanced-worker",
                    "model": "runtime-balanced-medium",
                    "lane": "balanced",
                    "efforts": ["medium"],
                    "tools": ["files"],
                },
            ]
        }

        decision = routing.plan_route(catalog, role="implementation")

        self.assertEqual(
            decision.resolved,
            {
                "agent": "balanced-worker",
                "model": "runtime-balanced-medium",
                "effort": "medium",
            },
        )

    def test_treats_an_explicit_lane_as_an_exact_override(self) -> None:
        catalog = {
            "profiles": [
                {
                    "agent": "strong-worker",
                    "model": "runtime-strong",
                    "lane": "strong",
                    "efforts": ["medium"],
                    "tools": ["files"],
                }
            ]
        }

        decision = routing.plan_route(
            catalog,
            role="implementation",
            overrides={"lane": "balanced"},
        )

        self.assertEqual(decision.outcome, "blocked")
        self.assertIn("No advertised profile", decision.blocked_reason)

    def test_blocks_fast_xhigh_without_reason_even_when_xhigh_is_the_only_effort(self) -> None:
        catalog = {
            "profiles": [
                {
                    "agent": "fast-only-xhigh",
                    "model": "runtime-fast-xhigh",
                    "lane": "fast",
                    "efforts": ["xhigh"],
                    "tools": ["files"],
                }
            ]
        }

        blocked = routing.plan_route(catalog, role="implementation")
        resolved = routing.plan_route(
            catalog,
            role="implementation",
            escalation_reason="Data-integrity verification requires exceptional effort.",
        )

        self.assertEqual(blocked.outcome, "blocked")
        self.assertIn("explicit exceptional escalation reason", blocked.blocked_reason)
        self.assertEqual(resolved.resolved["effort"], "xhigh")
        self.assertEqual(
            resolved.escalation_reason,
            "Data-integrity verification requires exceptional effort.",
        )

    def test_blocks_strong_high_without_reason_and_persists_explicit_reason(self) -> None:
        overrides = {"lane": "strong", "model": "runtime-strong", "effort": "high"}
        blocked = routing.plan_route(CATALOG, role="implementation", overrides=overrides)
        resolved = routing.plan_route(
            CATALOG,
            role="implementation",
            overrides=overrides,
            escalation_reason="Cross-cutting security review requires the strongest lane.",
        )

        self.assertEqual(blocked.outcome, "blocked")
        self.assertIn("explicit exceptional escalation reason", blocked.blocked_reason)
        self.assertEqual(
            resolved.resolved,
            {"agent": "builder-a", "model": "runtime-strong", "effort": "high"},
        )
        self.assertEqual(
            resolved.escalation_reason,
            "Cross-cutting security review requires the strongest lane.",
        )
        self.assertEqual(
            resolved.to_dict()["requested"],
            {"lane": "strong", "agent": None, "model": "runtime-strong", "effort": "high"},
        )
        self.assertEqual(resolved.to_dict()["cost_rank"], 1)

    def test_blocks_worker_escalation_without_an_exceptional_risk_marker(self) -> None:
        decision = routing.plan_route(
            CATALOG,
            role="implementation",
            overrides={"lane": "strong", "model": "runtime-strong", "effort": "high"},
            escalation_reason="The worker is important and needs more capability.",
        )

        self.assertEqual(decision.outcome, "blocked")
        self.assertIn("explicit exceptional escalation reason", decision.blocked_reason)

    def test_accepts_each_persisted_exceptional_risk_marker(self) -> None:
        for marker in ("security", "lifecycle", "data-integrity", "cross-cutting"):
            with self.subTest(marker=marker):
                reason = f"Exceptional {marker} risk requires escalation."
                decision = routing.plan_route(
                    CATALOG,
                    role="implementation",
                    overrides={"lane": "strong", "model": "runtime-strong", "effort": "high"},
                    escalation_reason=reason,
                )

                self.assertEqual(decision.outcome, "resolved")
                self.assertEqual(decision.escalation_reason, reason)

    def test_blocks_balanced_xhigh_without_reason_and_accepts_explicit_reason(self) -> None:
        overrides = {"lane": "balanced", "model": "runtime-balanced", "effort": "xhigh"}
        blocked = routing.plan_route(CATALOG, role="implementation", overrides=overrides)
        resolved = routing.plan_route(
            CATALOG,
            role="implementation",
            overrides=overrides,
            escalation_reason="Lifecycle migration requires exceptional validation effort.",
        )

        self.assertEqual(blocked.outcome, "blocked")
        self.assertIn("explicit exceptional escalation reason", blocked.blocked_reason)
        self.assertEqual(resolved.resolved["effort"], "xhigh")
        self.assertEqual(
            resolved.escalation_reason,
            "Lifecycle migration requires exceptional validation effort.",
        )


class OverrideAndFallbackBehavior(unittest.TestCase):
    def test_honors_supported_user_overrides(self) -> None:
        decision = routing.plan_route(
            CATALOG,
            role="implementation",
            overrides={
                "lane": "balanced",
                "agent": "builder-a",
                "model": "runtime-balanced",
                "effort": "xhigh",
            },
            escalation_reason="Cross-cutting validation requires exceptional effort.",
        )

        self.assertEqual(decision.outcome, "resolved")
        self.assertEqual(
            decision.resolved,
            {"agent": "builder-a", "model": "runtime-balanced", "effort": "xhigh"},
        )
        self.assertIsNone(decision.fallback_reason)

    def test_blocks_unsupported_and_unsafe_overrides(self) -> None:
        cases = (
            ({"agent": "missing-agent"}, "not advertised"),
            ({"model": "missing-model"}, "not advertised"),
            ({"effort": "extreme"}, "not supported"),
            ({"lane": "fast"}, "below the safe minimum balanced"),
        )

        for overrides, message in cases:
            with self.subTest(overrides=overrides):
                decision = routing.plan_route(
                    CATALOG,
                    role="review",
                    overrides=overrides,
                )

                self.assertEqual(decision.outcome, "blocked")
                self.assertIn(message, decision.blocked_reason)
                self.assertIsNone(decision.resolved)

    def test_persists_coordinator_fallbacks(self) -> None:
        catalog = {
            "profiles": [
                {
                    "agent": "portable-agent",
                    "model": "catalog-balanced",
                    "lane": "balanced",
                    "efforts": ["medium", "high"],
                    "tools": [],
                    "cost_rank": 0,
                }
            ]
        }

        decision = routing.plan_route(catalog, role="coordinator")

        self.assertEqual(decision.outcome, "resolved")
        self.assertEqual(
            decision.requested,
            {"lane": "balanced", "agent": None, "model": None, "effort": "high"},
        )
        self.assertEqual(
            decision.resolved,
            {"agent": "portable-agent", "model": "catalog-balanced", "effort": "high"},
        )
        self.assertEqual(
            decision.fallback_reason,
            None,
        )
        self.assertNotIn("fan", decision.to_dict())

    def test_preserves_explicit_coordinator_dimensions_during_fallback(self) -> None:
        decision = routing.plan_route(
            CATALOG,
            role="coordinator",
            overrides={"lane": "strong"},
        )
        effort_override = routing.plan_route(
            {"profiles": [CATALOG["profiles"][2]]},
            role="coordinator",
            overrides={"effort": "high"},
        )

        self.assertEqual(decision.resolved["model"], "runtime-strong")
        self.assertEqual(decision.resolved["effort"], "high")
        self.assertIsNone(decision.fallback_reason)
        self.assertEqual(effort_override.resolved["model"], "runtime-balanced")
        self.assertEqual(effort_override.resolved["effort"], "high")
        self.assertIsNone(effort_override.fallback_reason)

    def test_blocks_a_coordinator_when_an_explicit_lane_is_not_advertised(self) -> None:
        decision = routing.plan_route(
            {
                "profiles": [
                    {
                        "agent": "strong-only",
                        "model": "runtime-strong",
                        "lane": "strong",
                        "efforts": ["high"],
                    }
                ]
            },
            role="coordinator",
            overrides={"lane": "balanced"},
        )

        self.assertEqual(decision.outcome, "blocked")
        self.assertIn("No advertised profile", decision.blocked_reason)

    def test_blocks_a_coordinator_when_no_safe_profile_exists(self) -> None:
        decision = routing.plan_route(
            {"profiles": []},
            role="coordinator",
        )

        self.assertEqual(decision.outcome, "blocked")
        self.assertIn("No advertised profile", decision.blocked_reason)
        with self.assertRaises(routing.RoutingError):
            decision.execution_profile()


class CatalogValidationBehavior(unittest.TestCase):
    def test_uses_an_external_policy_without_scheduler_changes(self) -> None:
        policy = json.loads((SCRIPT.parents[2] / "impl" / "references" / "routing-policy.seed.json").read_text())
        policy["role_defaults"]["implementation"] = {"lane": "balanced", "effort": "medium"}

        decision = routing.plan_route(CATALOG, policy=policy, role="implementation")

        self.assertEqual(decision.resolved["model"], "runtime-balanced")

    def test_execution_profile_stays_within_strict_schema_properties(self) -> None:
        decision = routing.plan_route(
            CATALOG,
            role="implementation",
            overrides={"lane": "balanced", "model": "runtime-balanced", "effort": "xhigh"},
            escalation_reason="Cross-cutting validation requires exceptional effort.",
        )
        schema_path = SCRIPT.parents[1] / "references" / "execution-profile.schema.json"
        schema = json.loads(schema_path.read_text())
        execution_profile = decision.execution_profile()

        self.assertNotIn("escalation_reason", execution_profile)
        self.assertTrue(set(execution_profile) <= set(schema["properties"]))
        self.assertEqual(
            decision.to_dict()["escalation_reason"],
            "Cross-cutting validation requires exceptional effort.",
        )

    def test_rejects_duplicate_profiles_and_invalid_capabilities(self) -> None:
        duplicate = {"profiles": [CATALOG["profiles"][0], CATALOG["profiles"][0]]}
        invalid_effort = {
            "profiles": [
                {
                    "agent": "agent",
                    "model": "model",
                    "lane": "fast",
                    "efforts": ["extreme"],
                }
            ]
        }

        with self.assertRaisesRegex(routing.RoutingError, "unique agent and model"):
            routing.plan_route(duplicate, role="research")
        with self.assertRaisesRegex(routing.RoutingError, "unsupported values"):
            routing.plan_route(invalid_effort, role="research")

    def test_never_invents_a_model_when_constraints_do_not_match(self) -> None:
        decision = routing.plan_route(
            CATALOG,
            role="implementation",
            required_tools=("gpu",),
        )

        self.assertEqual(decision.outcome, "blocked")
        advertised = {profile["model"] for profile in CATALOG["profiles"]}
        self.assertTrue(
            decision.resolved is None
            or decision.resolved["model"] in advertised
        )


if __name__ == "__main__":
    unittest.main()
