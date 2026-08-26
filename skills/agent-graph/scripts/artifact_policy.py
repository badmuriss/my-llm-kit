"""Default artifact budget shared by Host capsules and Orca task prompts."""

from __future__ import annotations

from typing import Any


ARTIFACT_POLICY_NAME = "minimal-by-default-v1"


def artifact_policy() -> dict[str, Any]:
    """Return the bounded worker policy that prevents speculative artifacts."""

    return {
        "name": ARTIFACT_POLICY_NAME,
        "new_tests": "on-demand",
        "new_markdown": "on-demand",
        "max_new_regression_tests_per_defect": 1,
        "prefer_existing": True,
        "required_when": [
            "reproducible regression",
            "security or data-integrity invariant",
            "public contract",
            "task acceptance explicitly names the artifact",
        ],
        "do_not_create_for": [
            "constants or configuration-only changes",
            "trivial passthroughs or type-system guarantees",
            "implementation-detail coverage",
            "behavior explicitly removed or out of scope",
            "status logs, duplicate plans, or narrative check reports",
        ],
        "validation": "run the task's declared Check first; use a broader suite only for broad or high-risk changes",
    }


def artifact_policy_prompt() -> str:
    """Return a short prompt safe to include in an external task capsule."""

    return (
        "Artifact policy (minimal-by-default-v1): create no new test suite or "
        "supplemental Markdown by default. Reuse or extend an existing artifact. "
        "Add at most one focused regression test per reproducible defect, and only "
        "when the task acceptance, a security/data-integrity invariant, or a public "
        "contract requires it. Do not add tests for constants, trivial passthroughs, "
        "type guarantees, implementation details, or behavior explicitly removed "
        "from scope. Do not create status logs, "
        "duplicate plans, or narrative check reports. Run the declared Check first; "
        "run a broader suite only for broad or high-risk changes."
    )


__all__ = ["ARTIFACT_POLICY_NAME", "artifact_policy", "artifact_policy_prompt"]
