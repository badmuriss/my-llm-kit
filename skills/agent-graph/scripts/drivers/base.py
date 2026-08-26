"""Shared types for portable Agent Graph drivers."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Protocol, Sequence

from graph_core import GraphValidationError, validate_execution_profile
from validation import CAPABILITY_NAMES, validate_capability_receipt


class DriverError(RuntimeError):
    """Reports an unavailable driver or unsafe external transition."""

    def __init__(self, message: str, *, code: str = "driver_error", receipt: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.receipt = receipt


@dataclass(frozen=True, slots=True)
class DriverReceipt:
    """Normalized result plus the unmodified provider receipt."""

    operation: str
    status: str
    local_ids: Mapping[str, str] = field(default_factory=dict)
    external_refs: Mapping[str, Any] = field(default_factory=dict)
    raw: Any = None
    degradation: Mapping[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def capability(
    status: str,
    *,
    method: str | None = None,
    evidence: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    """Build one truthful canonical capability declaration."""

    if status == "supported":
        if not method or not evidence or reason is not None:
            raise DriverError(
                "supported capability requires verification and no missing reason",
                code="capability_claim_unproven",
            )
        return {
            "status": status,
            "verification": {"method": method, "evidence": evidence},
            "reason": None,
        }
    if status not in {"unsupported", "unavailable"} or not reason:
        raise DriverError(
            "missing capability requires unsupported or unavailable status and a reason",
            code="capability_claim_invalid",
        )
    verification = (
        {"method": method, "evidence": evidence}
        if method is not None and evidence is not None
        else None
    )
    return {"status": status, "verification": verification, "reason": reason}


def resolve_capability_request(
    capabilities: Mapping[str, Mapping[str, Any]],
    requested: Sequence[str],
    *,
    operation: str,
    compatible_alternative: str | None = None,
) -> dict[str, Any]:
    """Resolve generic requirements without consulting adapter-private identity."""

    requested_names = list(dict.fromkeys(requested))
    unknown = set(requested_names) - CAPABILITY_NAMES
    if unknown:
        raise DriverError(
            f"unknown portable capability: {', '.join(sorted(unknown))}",
            code="capability_unknown",
        )
    if not isinstance(operation, str) or not operation:
        raise DriverError("capability operation must be non-empty", code="capability_request_invalid")
    missing = [
        name
        for name in requested_names
        if not isinstance(capabilities.get(name), Mapping)
        or capabilities[name].get("status") != "supported"
    ]
    if not missing:
        return {
            "outcome": "none",
            "operation": None,
            "missing_capabilities": [],
            "selected_alternative": None,
            "reason": None,
        }
    if compatible_alternative:
        return {
            "outcome": "downgraded",
            "operation": operation,
            "missing_capabilities": missing,
            "selected_alternative": compatible_alternative,
            "reason": "The requested operation uses a declared compatible alternative.",
        }
    return {
        "outcome": "blocked",
        "operation": operation,
        "missing_capabilities": missing,
        "selected_alternative": None,
        "reason": "The requested operation has no declared compatible alternative.",
    }


def build_capability_receipt(
    adapter: str,
    capabilities: Mapping[str, Mapping[str, Any]],
    *,
    requested: Sequence[str] = (),
    operation: str = "discovery",
    compatible_alternative: str | None = None,
    version: str | None = None,
    extensions: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build and validate one complete portable adapter receipt."""

    if set(capabilities) != CAPABILITY_NAMES:
        raise DriverError(
            "adapter must declare the complete canonical capability set",
            code="capability_set_incomplete",
        )
    degradation = resolve_capability_request(
        capabilities,
        requested,
        operation=operation,
        compatible_alternative=compatible_alternative,
    )
    body = {
        "adapter": {"kind": adapter, "version": version},
        "capabilities": {name: dict(capabilities[name]) for name in sorted(CAPABILITY_NAMES)},
        "requested_capabilities": list(dict.fromkeys(requested)),
        "missing_capabilities": sorted(
            name
            for name, declaration in capabilities.items()
            if declaration.get("status") != "supported"
        ),
        "degradation": degradation,
        "extensions": dict(extensions or {}),
    }
    digest = hashlib.sha256(
        json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()
    try:
        return validate_capability_receipt(
            {"schema_version": 1, "receipt_id": f"receipt-{digest}", **body}
        )
    except ValueError as error:
        raise DriverError(str(error), code="capability_receipt_invalid") from error


def execution_profile_from_attempt(attempt: Mapping[str, Any]) -> dict[str, Any]:
    """Return one fully pinned profile without inventing a default worker."""

    profile = attempt.get("execution_profile")
    workspace_scope = attempt.get("workspace_scope")
    if not isinstance(profile, Mapping) or not isinstance(workspace_scope, Mapping):
        raise DriverError(
            "attempt requires execution_profile and workspace_scope",
            code="execution_profile_required",
        )
    try:
        return validate_execution_profile(profile, workspace_scope)
    except GraphValidationError as error:
        raise DriverError(str(error), code="invalid_execution_profile") from error


def persisted_driver_context(attempt: Mapping[str, Any]) -> dict[str, Any]:
    """Return the complete immutable context required for a driver effect.

    Lifecycle operations must use the context recorded with the attempt, rather
    than reconstructing a placement from the active checkout or driver state.
    """

    workspace_scope = attempt.get("workspace_scope")
    execution_profile = attempt.get("execution_profile")
    external_refs = attempt.get("external_refs")
    resolved_placement = attempt.get("resolved_placement")
    if not isinstance(workspace_scope, Mapping):
        raise DriverError("attempt requires a persisted workspace_scope", code="driver_context_missing")
    if not isinstance(execution_profile, Mapping):
        raise DriverError("attempt requires a persisted execution_profile", code="driver_context_missing")
    if not isinstance(external_refs, Mapping):
        raise DriverError("attempt requires persisted external_refs", code="driver_context_missing")
    profile = execution_profile_from_attempt(
        {
            "workspace_scope": workspace_scope,
            "execution_profile": execution_profile,
        }
    )
    persisted_placement = profile["resolved_placement"]
    if not isinstance(resolved_placement, Mapping):
        raise DriverError("attempt requires a persisted resolved_placement", code="driver_context_missing")
    if dict(resolved_placement) != persisted_placement:
        raise DriverError(
            "attempt resolved_placement differs from its execution profile",
            code="driver_context_mismatch",
        )
    return {
        "workspace_scope": json.loads(json.dumps(dict(workspace_scope), sort_keys=True)),
        "execution_profile": json.loads(json.dumps(profile, sort_keys=True)),
        "resolved_placement": json.loads(json.dumps(persisted_placement, sort_keys=True)),
        "external_refs": json.loads(json.dumps(dict(external_refs), sort_keys=True)),
    }


class Driver(Protocol):
    """Seven-operation transport boundary owned by Agent Graph."""

    def detect(self) -> DriverReceipt: ...

    def start_run(self, objective: str, tasks: Sequence[Mapping[str, Any]]) -> DriverReceipt: ...

    def start_attempt(self, attempt: Mapping[str, Any]) -> DriverReceipt: ...

    def poll(self, attempt: Mapping[str, Any], *, cursor: str | None = None) -> DriverReceipt: ...

    def send(self, attempt: Mapping[str, Any], message: Mapping[str, Any]) -> DriverReceipt: ...

    def release(self, attempt: Mapping[str, Any]) -> DriverReceipt: ...

    def reconcile(self, attempts: Sequence[Mapping[str, Any]]) -> DriverReceipt: ...

    def reserve_browser_surface(self, request: Mapping[str, Any]) -> DriverReceipt: ...

    def bind_browser_surface(self, request: Mapping[str, Any]) -> DriverReceipt: ...

    def capture_browser_surface(self, request: Mapping[str, Any]) -> DriverReceipt: ...

    def release_browser_surface(self, request: Mapping[str, Any]) -> DriverReceipt: ...
