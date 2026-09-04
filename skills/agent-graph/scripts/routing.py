#!/usr/bin/env python3
"""Resolve portable execution lanes against a runtime capability catalog."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence


LANES = ("fast", "balanced", "strong")
EFFORTS = ("low", "medium", "high", "xhigh", "max")
EXCEPTIONAL_EFFORTS = frozenset({"xhigh", "max"})
ROLES = (
    "coordinator",
    "research",
    "documentation",
    "implementation",
    "review",
    "verification",
    "integration",
)
RISKS = ("routine", "material", "high")
CHECK_STRENGTHS = ("decisive", "partial", "none")

_EXCEPTIONAL_RISK_MARKERS = (
    "security",
    "lifecycle",
    "data-integrity",
    "data integrity",
    "cross-cutting",
    "cross cutting",
)

_LANE_RANK = {lane: rank for rank, lane in enumerate(LANES)}
_EFFORT_RANK = {effort: rank for rank, effort in enumerate(EFFORTS)}
DEFAULT_POLICY_PATH = Path(__file__).parents[2] / "impl" / "references" / "routing-policy.seed.json"


class RoutingError(ValueError):
    """Reports an invalid routing request or capability catalog."""


@dataclass(frozen=True, slots=True)
class RoutingPolicy:
    """Strict, versioned routing data. Provider identities remain catalog data."""

    policy_id: str
    role_defaults: Mapping[str, Mapping[str, str]]
    risk_minimums: Mapping[str, Mapping[str, str]]
    check_minimums: Mapping[str, Mapping[str, str]]
    tool_minimums: Mapping[str, Mapping[str, str]]
    context_bands: tuple[Mapping[str, Any], ...]
    candidate_order: tuple[Mapping[str, str], ...]
    metadata: Mapping[str, Any]

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "RoutingPolicy":
        if not isinstance(value, Mapping) or set(value) != {
            "schema_version", "policy_id", "metadata", "role_defaults", "risk_minimums",
            "check_minimums", "tool_minimums", "context_bands", "candidate_order",
        }:
            raise RoutingError("routing policy has an invalid shape")
        if value["schema_version"] != 1:
            raise RoutingError("routing policy schema_version must be 1")
        policy_id = _nonempty_string(value["policy_id"], "routing policy id")
        metadata = value["metadata"]
        required_refresh_reasons = {
            "provider_removal", "catalog_incompatibility", "known_price_or_quota_change", "route_failure", "owner_request",
        }
        if (
            not isinstance(metadata, Mapping)
            or metadata.get("default_refresh_interval_days") != 14
            or set(metadata.get("early_refresh_reasons", ())) != required_refresh_reasons
        ):
            raise RoutingError("routing policy metadata must set a fourteen-day default refresh interval")

        def requirements(name: str, keys: Sequence[str]) -> dict[str, dict[str, str]]:
            raw = value[name]
            if not isinstance(raw, Mapping) or set(raw) != set(keys):
                raise RoutingError(f"routing policy {name} is incomplete")
            normalized: dict[str, dict[str, str]] = {}
            for key, requirement in raw.items():
                if not isinstance(requirement, Mapping) or set(requirement) != {"lane", "effort"}:
                    raise RoutingError(f"routing policy {name}.{key} must contain lane and effort")
                lane, effort = requirement["lane"], requirement["effort"]
                if lane not in _LANE_RANK or effort not in _EFFORT_RANK:
                    raise RoutingError(f"routing policy {name}.{key} has an unsupported lane or effort")
                normalized[key] = {"lane": lane, "effort": effort}
            return normalized

        role_defaults = requirements("role_defaults", ROLES)
        risk_minimums = requirements("risk_minimums", RISKS)
        check_minimums = requirements("check_minimums", CHECK_STRENGTHS)
        raw_tools = value["tool_minimums"]
        if not isinstance(raw_tools, Mapping):
            raise RoutingError("routing policy tool_minimums must be an object")
        tool_minimums = requirements_from_mapping(raw_tools, "routing policy tool minimum")
        raw_bands = value["context_bands"]
        if not isinstance(raw_bands, Sequence) or isinstance(raw_bands, (str, bytes)) or not raw_bands:
            raise RoutingError("routing policy context_bands must be a non-empty array")
        bands: list[dict[str, Any]] = []
        previous = -1
        for band in raw_bands:
            if not isinstance(band, Mapping) or set(band) != {"min_tokens", "lane", "effort"}:
                raise RoutingError("routing policy context band is invalid")
            minimum, lane, effort = band["min_tokens"], band["lane"], band["effort"]
            if not isinstance(minimum, int) or isinstance(minimum, bool) or minimum < 0 or minimum <= previous:
                raise RoutingError("routing policy context bands must be ascending non-negative token thresholds")
            if lane not in _LANE_RANK or effort not in _EFFORT_RANK:
                raise RoutingError("routing policy context band has an unsupported lane or effort")
            bands.append({"min_tokens": minimum, "lane": lane, "effort": effort})
            previous = minimum
        if bands[0]["min_tokens"] != 0:
            raise RoutingError("routing policy context bands must start at zero")
        raw_candidates = value["candidate_order"]
        if not isinstance(raw_candidates, Sequence) or isinstance(raw_candidates, (str, bytes)):
            raise RoutingError("routing policy candidate_order must be an array")
        candidates: list[dict[str, str]] = []
        for candidate in raw_candidates:
            if not isinstance(candidate, Mapping) or set(candidate) != {"provider", "agent", "model", "effort"}:
                raise RoutingError("routing policy candidate is invalid")
            candidates.append({key: _nonempty_string(candidate[key], f"routing policy candidate {key}") for key in candidate})
        return cls(policy_id, role_defaults, risk_minimums, check_minimums, tool_minimums, tuple(bands), tuple(candidates), dict(metadata))

    def requirements_for(self, request: "RoutingRequest") -> tuple[str, str]:
        context = next(band for band in reversed(self.context_bands) if request.context_tokens >= band["min_tokens"])
        requirements = [
            self.role_defaults[request.role], self.risk_minimums[request.risk],
            self.check_minimums[request.check_strength], context,
            *(self.tool_minimums[tool] for tool in request.required_tools if tool in self.tool_minimums),
        ]
        return _maximum_requirement(*((item["lane"], item["effort"]) for item in requirements))


def requirements_from_mapping(value: Mapping[str, Any], label: str) -> dict[str, dict[str, str]]:
    normalized: dict[str, dict[str, str]] = {}
    for key, requirement in value.items():
        if not isinstance(key, str) or not key or not isinstance(requirement, Mapping) or set(requirement) != {"lane", "effort"}:
            raise RoutingError(f"{label} is invalid")
        lane, effort = requirement["lane"], requirement["effort"]
        if lane not in _LANE_RANK or effort not in _EFFORT_RANK:
            raise RoutingError(f"{label} has an unsupported lane or effort")
        normalized[key] = {"lane": lane, "effort": effort}
    return normalized


def load_routing_policy(path: Path | str = DEFAULT_POLICY_PATH) -> RoutingPolicy:
    """Load the policy artifact instead of compiling route defaults into code."""

    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise RoutingError(f"cannot load routing policy: {error}") from error
    return RoutingPolicy.from_mapping(value)


def _nonempty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RoutingError(f"{label} must be a non-empty string")
    return value.strip()


def _string_tuple(value: Any, label: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise RoutingError(f"{label} must be an array of strings")
    normalized = tuple(_nonempty_string(item, label) for item in value)
    if len(normalized) != len(set(normalized)):
        raise RoutingError(f"{label} must not contain duplicates")
    return normalized


def _maximum_requirement(*requirements: tuple[str, str]) -> tuple[str, str]:
    return (
        max((lane for lane, _ in requirements), key=_LANE_RANK.__getitem__),
        max((effort for _, effort in requirements), key=_EFFORT_RANK.__getitem__),
    )


@dataclass(frozen=True, slots=True)
class ModelCapability:
    """One agent and model combination advertised by a runtime."""

    agent: str
    model: str
    lane: str
    efforts: tuple[str, ...]
    tools: tuple[str, ...] = ()
    max_context_tokens: int | None = None
    cost_rank: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "agent", _nonempty_string(self.agent, "capability agent"))
        object.__setattr__(self, "model", _nonempty_string(self.model, "capability model"))
        lane = _nonempty_string(self.lane, "capability lane")
        if lane not in _LANE_RANK:
            raise RoutingError(f"capability lane must be one of: {', '.join(LANES)}")
        object.__setattr__(self, "lane", lane)
        efforts = _string_tuple(self.efforts, "capability efforts")
        unsupported_efforts = sorted(set(efforts) - set(EFFORTS))
        if unsupported_efforts:
            raise RoutingError(
                f"capability efforts contain unsupported values: {', '.join(unsupported_efforts)}"
            )
        if not efforts:
            raise RoutingError("capability efforts must not be empty")
        object.__setattr__(
            self,
            "efforts",
            tuple(sorted(efforts, key=_EFFORT_RANK.__getitem__)),
        )
        tools = _string_tuple(self.tools, "capability tools")
        object.__setattr__(self, "tools", tuple(sorted(tools)))
        if self.max_context_tokens is not None and (
            not isinstance(self.max_context_tokens, int)
            or isinstance(self.max_context_tokens, bool)
            or self.max_context_tokens < 1
        ):
            raise RoutingError("capability max_context_tokens must be a positive integer or null")
        if (
            not isinstance(self.cost_rank, int)
            or isinstance(self.cost_rank, bool)
            or self.cost_rank < 0
        ):
            raise RoutingError("capability cost_rank must be a non-negative integer")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> ModelCapability:
        if not isinstance(value, Mapping):
            raise RoutingError("each capability profile must be an object")
        required = {"agent", "model", "lane", "efforts"}
        missing = sorted(required - set(value))
        if missing:
            raise RoutingError(f"capability profile is missing fields: {', '.join(missing)}")
        return cls(
            agent=value["agent"],
            model=value["model"],
            lane=value["lane"],
            efforts=value["efforts"],
            tools=value.get("tools", ()),
            max_context_tokens=value.get("max_context_tokens"),
            cost_rank=value.get("cost_rank", 0),
        )


@dataclass(frozen=True, slots=True)
class RuntimeCatalog:
    """Normalized model profiles advertised by one runtime boundary."""

    profiles: tuple[ModelCapability, ...]

    def __post_init__(self) -> None:
        profiles = tuple(self.profiles)
        if not all(isinstance(profile, ModelCapability) for profile in profiles):
            raise RoutingError("catalog profiles must be ModelCapability values")
        identities = [(profile.agent, profile.model) for profile in profiles]
        if len(identities) != len(set(identities)):
            raise RoutingError("catalog profiles must have unique agent and model pairs")
        object.__setattr__(self, "profiles", profiles)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> RuntimeCatalog:
        if not isinstance(value, Mapping):
            raise RoutingError("runtime catalog must be an object")
        raw_profiles = value.get("profiles")
        if isinstance(raw_profiles, (str, bytes)) or not isinstance(raw_profiles, Sequence):
            raise RoutingError("runtime catalog profiles must be an array")
        return cls(tuple(ModelCapability.from_mapping(profile) for profile in raw_profiles))


@dataclass(frozen=True, slots=True)
class RoutingOverrides:
    """User-selected routing values. Unsupported values produce a blocked result."""

    lane: str | None = None
    agent: str | None = None
    model: str | None = None
    effort: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("lane", "agent", "model", "effort"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(
                    self,
                    field_name,
                    _nonempty_string(value, f"routing override {field_name}"),
                )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> RoutingOverrides:
        if not isinstance(value, Mapping):
            raise RoutingError("routing overrides must be an object")
        unknown = sorted(set(value) - {"lane", "agent", "model", "effort"})
        if unknown:
            raise RoutingError(f"routing overrides contain unknown fields: {', '.join(unknown)}")
        return cls(**value)


@dataclass(frozen=True, slots=True)
class RoutingRequest:
    """Task signals used to derive the least costly safe execution profile."""

    role: str
    risk: str = "routine"
    required_tools: tuple[str, ...] = ()
    context_tokens: int = 0
    check_strength: str = "decisive"
    escalation_reason: str | None = None
    overrides: RoutingOverrides = field(default_factory=RoutingOverrides)

    def __post_init__(self) -> None:
        role = _nonempty_string(self.role, "role")
        risk = _nonempty_string(self.risk, "risk")
        check_strength = _nonempty_string(self.check_strength, "check_strength")
        if role not in ROLES:
            raise RoutingError(f"role must be one of: {', '.join(ROLES)}")
        if risk not in RISKS:
            raise RoutingError(f"risk must be one of: {', '.join(RISKS)}")
        if check_strength not in CHECK_STRENGTHS:
            raise RoutingError(
                f"check_strength must be one of: {', '.join(CHECK_STRENGTHS)}"
            )
        object.__setattr__(self, "role", role)
        object.__setattr__(self, "risk", risk)
        object.__setattr__(self, "check_strength", check_strength)
        if self.escalation_reason is not None:
            object.__setattr__(
                self,
                "escalation_reason",
                _nonempty_string(self.escalation_reason, "escalation_reason"),
            )
        tools = _string_tuple(self.required_tools, "required_tools")
        object.__setattr__(self, "required_tools", tuple(sorted(tools)))
        if (
            not isinstance(self.context_tokens, int)
            or isinstance(self.context_tokens, bool)
            or self.context_tokens < 0
        ):
            raise RoutingError("context_tokens must be a non-negative integer")
        if not isinstance(self.overrides, RoutingOverrides):
            raise RoutingError("overrides must be a RoutingOverrides value")


@dataclass(frozen=True, slots=True)
class RoutingDecision:
    """A persistable resolved profile or a persistable blocked result."""

    outcome: str
    role: str
    requested: Mapping[str, str | None]
    resolved: Mapping[str, str] | None
    fallback_reason: str | None
    blocked_reason: str | None
    escalation_reason: str | None = None
    cost_rank: int | None = None

    def __post_init__(self) -> None:
        if self.outcome not in {"resolved", "blocked"}:
            raise RoutingError("routing decision outcome must be resolved or blocked")
        if (self.outcome == "resolved") != (self.resolved is not None):
            raise RoutingError("resolved routing decisions need a resolved profile")
        if (self.outcome == "blocked") != (self.blocked_reason is not None):
            raise RoutingError("blocked routing decisions need a blocked reason")
        if self.cost_rank is not None and (
            not isinstance(self.cost_rank, int)
            or isinstance(self.cost_rank, bool)
            or self.cost_rank < 0
        ):
            raise RoutingError("routing decision cost_rank must be a non-negative integer or null")

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome,
            "role": self.role,
            "requested": dict(self.requested),
            "resolved": dict(self.resolved) if self.resolved is not None else None,
            "fallback_reason": self.fallback_reason,
            "blocked_reason": self.blocked_reason,
            "escalation_reason": self.escalation_reason,
            "cost_rank": self.cost_rank,
        }

    def execution_profile(self) -> dict[str, Any]:
        """Return the routing portion of ExecutionProfile for a resolved decision."""

        if self.resolved is None:
            raise RoutingError("a blocked routing decision has no execution profile")
        return {
            "role": self.role,
            "requested": dict(self.requested),
            "resolved": dict(self.resolved),
            "fallback_reason": self.fallback_reason,
        }


@dataclass(frozen=True, slots=True)
class _Candidate:
    capability: ModelCapability
    effort: str


def _blocked(
    request: RoutingRequest,
    requested: Mapping[str, str | None],
    reason: str,
) -> RoutingDecision:
    return RoutingDecision(
        outcome="blocked",
        role=request.role,
        requested=requested,
        resolved=None,
        fallback_reason=None,
        blocked_reason=reason,
        escalation_reason=request.escalation_reason,
        cost_rank=None,
    )


def _compatible_profiles(
    catalog: RuntimeCatalog,
    request: RoutingRequest,
) -> list[ModelCapability]:
    required_tools = set(request.required_tools)
    return [
        profile
        for profile in catalog.profiles
        if required_tools <= set(profile.tools)
        and (
            profile.max_context_tokens is None
            or profile.max_context_tokens >= request.context_tokens
        )
    ]


def _fallback_reason(requested_lane: str, requested_effort: str, candidate: _Candidate) -> str | None:
    reasons: list[str] = []
    if candidate.capability.lane != requested_lane:
        reasons.append(
            f"Requested lane {requested_lane} resolved to {candidate.capability.lane}."
        )
    if candidate.effort != requested_effort:
        reasons.append(f"Requested effort {requested_effort} resolved to {candidate.effort}.")
    return " ".join(reasons) or None


def _has_exceptional_escalation_reason(reason: str | None) -> bool:
    """Require a persisted reason to name an exceptional risk class."""

    if reason is None:
        return False
    normalized = reason.casefold()
    return any(marker in normalized for marker in _EXCEPTIONAL_RISK_MARKERS)


def _resolved(
    request: RoutingRequest,
    requested: Mapping[str, str | None],
    candidate: _Candidate,
) -> RoutingDecision:
    return RoutingDecision(
        outcome="resolved",
        role=request.role,
        requested=requested,
        resolved={
            "agent": candidate.capability.agent,
            "model": candidate.capability.model,
            "effort": candidate.effort,
        },
        fallback_reason=_fallback_reason(
            str(requested["lane"]),
            str(requested["effort"]),
            candidate,
        ),
        blocked_reason=None,
        escalation_reason=request.escalation_reason,
        cost_rank=candidate.capability.cost_rank,
    )


def route(
    request: RoutingRequest,
    catalog: RuntimeCatalog,
    policy: RoutingPolicy | None = None,
) -> RoutingDecision:
    """Resolve one deterministic profile without making a fan-out decision."""

    if not isinstance(request, RoutingRequest):
        raise RoutingError("request must be a RoutingRequest value")
    if not isinstance(catalog, RuntimeCatalog):
        raise RoutingError("catalog must be a RuntimeCatalog value")

    routing_policy = policy or load_routing_policy()
    policy_lane, policy_effort = routing_policy.requirements_for(request)
    if request.role == "coordinator":
        safe_lane, safe_effort = _maximum_requirement(
            (routing_policy.risk_minimums[request.risk]["lane"], routing_policy.risk_minimums[request.risk]["effort"]),
            (routing_policy.check_minimums[request.check_strength]["lane"], routing_policy.check_minimums[request.check_strength]["effort"]),
        )
    else:
        safe_lane, safe_effort = policy_lane, policy_effort

    overrides = request.overrides
    requested_lane = overrides.lane or policy_lane
    requested_effort = overrides.effort or policy_effort
    requested = {
        "lane": requested_lane,
        "agent": overrides.agent,
        "model": overrides.model,
        "effort": requested_effort,
    }

    if requested_lane not in _LANE_RANK:
        return _blocked(request, requested, f"Requested lane {requested_lane} is not supported.")
    if requested_effort not in _EFFORT_RANK:
        return _blocked(
            request,
            requested,
            f"Requested effort {requested_effort} is not supported.",
        )
    if _LANE_RANK[requested_lane] < _LANE_RANK[safe_lane]:
        return _blocked(
            request,
            requested,
            f"Requested lane {requested_lane} is below the safe minimum {safe_lane}.",
        )
    if _EFFORT_RANK[requested_effort] < _EFFORT_RANK[safe_effort]:
        return _blocked(
            request,
            requested,
            f"Requested effort {requested_effort} is below the safe minimum {safe_effort}.",
        )

    if overrides.agent is not None and not any(
        profile.agent == overrides.agent for profile in catalog.profiles
    ):
        return _blocked(
            request,
            requested,
            f"Requested agent {overrides.agent} is not advertised by the runtime.",
        )
    if overrides.model is not None and not any(
        profile.model == overrides.model
        and (overrides.agent is None or profile.agent == overrides.agent)
        for profile in catalog.profiles
    ):
        return _blocked(
            request,
            requested,
            f"Requested model {overrides.model} is not advertised for the requested agent.",
        )

    profiles = _compatible_profiles(catalog, request)
    if overrides.agent is not None:
        profiles = [profile for profile in profiles if profile.agent == overrides.agent]
    if overrides.model is not None:
        profiles = [profile for profile in profiles if profile.model == overrides.model]

    if overrides.model is not None and any(
        _LANE_RANK[profile.lane] < _LANE_RANK[safe_lane] for profile in profiles
    ):
        safe_profiles = [
            profile
            for profile in profiles
            if _LANE_RANK[profile.lane] >= _LANE_RANK[safe_lane]
        ]
        if not safe_profiles:
            return _blocked(
                request,
                requested,
                f"Requested model {overrides.model} is below the safe lane {safe_lane}.",
            )

    all_candidates: list[_Candidate] = []
    for profile in profiles:
        if overrides.lane is not None and profile.lane != requested_lane:
            continue
        if overrides.lane is None and _LANE_RANK[profile.lane] < _LANE_RANK[requested_lane]:
            continue
        if overrides.effort is not None:
            if requested_effort in profile.efforts:
                all_candidates.append(_Candidate(profile, requested_effort))
            continue
        compatible_efforts = [
            effort
            for effort in profile.efforts
            if _EFFORT_RANK[effort] >= _EFFORT_RANK[requested_effort]
        ]
        if compatible_efforts:
            all_candidates.append(_Candidate(profile, compatible_efforts[0]))

    candidates = all_candidates
    exceptional_escalation = _has_exceptional_escalation_reason(request.escalation_reason)
    if request.role != "coordinator" and not exceptional_escalation:
        candidates = [
            candidate
            for candidate in candidates
            if candidate.capability.lane != "strong"
            and candidate.effort not in EXCEPTIONAL_EFFORTS
        ]

    if candidates:
        selected = min(
            candidates,
            key=lambda candidate: (
                _LANE_RANK[candidate.capability.lane],
                _EFFORT_RANK[candidate.effort],
                candidate.capability.cost_rank,
                candidate.capability.agent,
                candidate.capability.model,
            ),
        )
        return _resolved(request, requested, selected)

    if (
        request.role != "coordinator"
        and not exceptional_escalation
        and any(
            candidate.capability.lane == "strong"
            or candidate.effort in EXCEPTIONAL_EFFORTS
            for candidate in all_candidates
        )
    ):
        return _blocked(
            request,
            requested,
            "Worker strong or exceptional-effort routing requires an explicit exceptional escalation reason.",
        )

    if request.role == "coordinator":
        fallback_candidates: list[_Candidate] = []
        for profile in profiles:
            if _LANE_RANK[profile.lane] < _LANE_RANK[safe_lane]:
                continue
            if overrides.lane is not None and profile.lane != requested_lane:
                continue
            if overrides.effort is not None:
                compatible_efforts = (
                    [requested_effort] if requested_effort in profile.efforts else []
                )
            else:
                compatible_efforts = [
                    effort
                    for effort in profile.efforts
                    if _EFFORT_RANK[effort] >= _EFFORT_RANK[safe_effort]
                ]
            if compatible_efforts:
                fallback_candidates.append(_Candidate(profile, compatible_efforts[-1]))
        if fallback_candidates:
            selected = min(
                fallback_candidates,
                key=lambda candidate: (
                    (
                        _LANE_RANK[candidate.capability.lane]
                        if overrides.lane is not None
                        else -_LANE_RANK[candidate.capability.lane]
                    ),
                    (
                        _EFFORT_RANK[candidate.effort]
                        if overrides.effort is not None
                        else -_EFFORT_RANK[candidate.effort]
                    ),
                    candidate.capability.cost_rank,
                    candidate.capability.agent,
                    candidate.capability.model,
                ),
            )
            return _resolved(request, requested, selected)

    details: list[str] = []
    if request.required_tools:
        details.append(f"tools {', '.join(request.required_tools)}")
    if request.context_tokens:
        details.append(f"context {request.context_tokens} tokens")
    constraints = f" with {' and '.join(details)}" if details else ""
    return _blocked(
        request,
        requested,
        f"No advertised profile can satisfy lane {requested_lane} and effort "
        f"{requested_effort}{constraints}.",
    )


def plan_route(
    catalog: RuntimeCatalog | Mapping[str, Any],
    *,
    policy: RoutingPolicy | Mapping[str, Any] | None = None,
    role: str,
    risk: str = "routine",
    required_tools: Sequence[str] = (),
    context_tokens: int = 0,
    check_strength: str = "decisive",
    escalation_reason: str | None = None,
    overrides: RoutingOverrides | Mapping[str, Any] | None = None,
) -> RoutingDecision:
    """Build and resolve a routing request from JSON-friendly values."""

    normalized_catalog = (
        catalog if isinstance(catalog, RuntimeCatalog) else RuntimeCatalog.from_mapping(catalog)
    )
    if overrides is None:
        normalized_overrides = RoutingOverrides()
    elif isinstance(overrides, RoutingOverrides):
        normalized_overrides = overrides
    else:
        normalized_overrides = RoutingOverrides.from_mapping(overrides)
    normalized_policy = (
        load_routing_policy() if policy is None else
        policy if isinstance(policy, RoutingPolicy) else RoutingPolicy.from_mapping(policy)
    )
    request = RoutingRequest(
        role=role,
        risk=risk,
        required_tools=tuple(required_tools),
        context_tokens=context_tokens,
        check_strength=check_strength,
        escalation_reason=escalation_reason,
        overrides=normalized_overrides,
    )
    return route(request, normalized_catalog, normalized_policy)
