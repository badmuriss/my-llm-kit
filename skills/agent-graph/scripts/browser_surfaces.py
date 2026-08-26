"""Bounded browser-surface contracts shared by Agent Graph drivers.

Requests express intended presentation. Receipts preserve the independent observed
visibility, focus and paint state, including unavailable outcomes. Browser
contents remain provider-owned and never cross this contract.
"""

from __future__ import annotations

import copy
import re
from typing import Any, Mapping
from urllib.parse import parse_qsl, urlparse


class BrowserSurfaceError(ValueError):
    """Reports an invalid or unsafe browser-surface lifecycle transition."""


REQUEST_FIELDS = frozenset({"schema_version", "request_id", "task_id", "attempt_id", "idempotency_key", "mode", "retention", "execution_host_id", "workspace_key", "page_binding", "binding", "viewport", "source_revision"})
RECEIPT_FIELDS = frozenset({"schema_version", "receipt_id", "request_id", "task_id", "attempt_id", "operation", "status", "idempotency_key", "surface", "observation", "capture", "unavailability"})
FORBIDDEN_KEYS = frozenset({"accessibility_tree", "authorization", "authorization_data", "cookie", "cookies", "dom", "frame", "frames", "html", "live_frame", "screenshot", "screenshot_bytes", "storage"})
SENSITIVE_QUERY_NAMES = frozenset({"access_token", "api_key", "authorization", "cookie", "key", "session", "sig", "signature", "token"})
OPERATIONS = frozenset({"reserve", "bind", "capture", "release"})
STATUSES = frozenset({"reserved", "bound", "captured", "released", "retained", "unsupported", "unavailable", "outcome_unknown", "unverifiable"})
OBSERVED_VISIBILITIES = frozenset({"visible", "offscreen", "hidden", "old-peer", "remote-unreachable", "unsupported", "unavailable"})
UNAVAILABILITY_CODES = frozenset({"native-capability-unavailable", "old-peer", "remote-unreachable", "unsupported", "outcome-unknown", "unverifiable"})
SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


def _exact(value: Any, fields: frozenset[str], context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise BrowserSurfaceError(f"{context} must be an object")
    if set(value) != fields:
        missing, unknown = sorted(fields - set(value)), sorted(set(value) - fields)
        details = ", ".join([*(f"missing {item}" for item in missing), *(f"unknown {item}" for item in unknown)])
        raise BrowserSurfaceError(f"{context} has invalid fields: {details}")
    return value


def _identifier(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 256:
        raise BrowserSurfaceError(f"{context} must be a bounded non-empty string")
    if any(ord(character) < 32 for character in value):
        raise BrowserSurfaceError(f"{context} contains control characters")
    return value


def _nullable_identifier(value: Any, context: str) -> str | None:
    return None if value is None else _identifier(value, context)


def _reject_contents(value: Any, context: str = "browser surface") -> None:
    if isinstance(value, Mapping):
        forbidden = sorted(str(key) for key in value if str(key).casefold() in FORBIDDEN_KEYS)
        if forbidden:
            raise BrowserSurfaceError(f"{context} contains browser contents: {', '.join(forbidden)}")
        for key, nested in value.items():
            _reject_contents(nested, f"{context}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _reject_contents(nested, f"{context}[{index}]")


def _page_binding(value: Any, context: str, *, nullable: bool = False) -> dict[str, str] | None:
    if value is None and nullable:
        return None
    binding = _exact(value, frozenset({"browser_page_id", "browser_profile_id"}), context)
    return {field: _identifier(binding[field], f"{context} {field}") for field in ("browser_page_id", "browser_profile_id")}


def _confined_ref(value: Any, context: str) -> str | None:
    reference = _nullable_identifier(value, context)
    if reference is None:
        return None
    if not reference.startswith("artifact:"):
        raise BrowserSurfaceError(f"{context} must use an artifact: reference")
    path = reference.removeprefix("artifact:")
    if not path or path.startswith(("/", "\\")) or "\\" in path or any(part in {"", ".", ".."} for part in path.split("/")):
        raise BrowserSurfaceError(f"{context} must be confined to a relative artifact path")
    return reference


def _binding(value: Any, context: str) -> dict[str, str]:
    binding = _exact(value, frozenset({"kind", "value"}), context)
    if binding["kind"] not in {"initial_url", "artifact_route"}:
        raise BrowserSurfaceError(f"{context} kind is unsupported")
    target = _identifier(binding["value"], f"{context} value")
    if binding["kind"] == "initial_url":
        parsed = urlparse(target)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise BrowserSurfaceError(f"{context} initial_url must be an absolute HTTP(S) URL")
        if parsed.username or parsed.password:
            raise BrowserSurfaceError(f"{context} initial_url cannot include credentials")
        if parsed.fragment:
            raise BrowserSurfaceError(f"{context} initial_url cannot include fragments")
        if {name.casefold() for name, _ in parse_qsl(parsed.query, keep_blank_values=True)} & SENSITIVE_QUERY_NAMES:
            raise BrowserSurfaceError(f"{context} initial_url cannot include authorization-bearing query values")
    else:
        if (
            target.startswith(("/", "\\"))
            or "\\" in target
            or "?" in target
            or "#" in target
            or "//" in target
            or re.match(r"^[A-Za-z]:", target)
            or any(part in {"", ".", ".."} for part in target.split("/"))
        ):
            raise BrowserSurfaceError(
                f"{context} artifact_route must be a confined relative route"
            )
    return {"kind": binding["kind"], "value": target}


def _viewport(value: Any, context: str) -> dict[str, int]:
    viewport = _exact(value, frozenset({"width", "height"}), context)
    result: dict[str, int] = {}
    for field in ("width", "height"):
        dimension = viewport[field]
        if not isinstance(dimension, int) or isinstance(dimension, bool) or not 1 <= dimension <= 8192:
            raise BrowserSurfaceError(f"{context} {field} must be between 1 and 8192")
        result[field] = dimension
    return result


def validate_browser_surface_request(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate one exact idempotent surface request without browser contents."""

    request = _exact(value, REQUEST_FIELDS, "browser surface request")
    if request["schema_version"] != 1 or request["mode"] not in {"visible", "offscreen"} or request["retention"] not in {"release", "retain"}:
        raise BrowserSurfaceError("browser surface request has an unsupported version, mode, or retention")
    result = {
        "schema_version": 1,
        "request_id": _identifier(request["request_id"], "browser surface request request_id"),
        "task_id": _identifier(request["task_id"], "browser surface request task_id"),
        "attempt_id": _identifier(request["attempt_id"], "browser surface request attempt_id"),
        "idempotency_key": _identifier(request["idempotency_key"], "browser surface request idempotency_key"),
        "mode": request["mode"], "retention": request["retention"],
        "execution_host_id": _identifier(request["execution_host_id"], "browser surface request execution_host_id"),
        "workspace_key": _identifier(request["workspace_key"], "browser surface request workspace_key"),
        "page_binding": _page_binding(request["page_binding"], "browser surface request page_binding", nullable=True),
        "binding": _binding(request["binding"], "browser surface request binding"),
        "viewport": _viewport(request["viewport"], "browser surface request viewport"),
        "source_revision": _identifier(request["source_revision"], "browser surface request source_revision"),
    }
    _reject_contents(result)
    return result


def _surface(value: Any, context: str) -> dict[str, Any]:
    surface = _exact(value, frozenset({"surface_id", "execution_host_id", "workspace_key", "page_binding", "binding", "viewport", "source_revision", "harness_owned"}), context)
    if not isinstance(surface["harness_owned"], bool):
        raise BrowserSurfaceError(f"{context} harness_owned must be boolean")
    return {
        "surface_id": _identifier(surface["surface_id"], f"{context} surface_id"),
        "execution_host_id": _identifier(surface["execution_host_id"], f"{context} execution_host_id"),
        "workspace_key": _identifier(surface["workspace_key"], f"{context} workspace_key"),
        "page_binding": _page_binding(surface["page_binding"], f"{context} page_binding", nullable=True),
        "binding": _binding(surface["binding"], f"{context} binding"),
        "viewport": _viewport(surface["viewport"], f"{context} viewport"),
        "source_revision": _identifier(surface["source_revision"], f"{context} source_revision"),
        "harness_owned": surface["harness_owned"],
    }


def _observation(value: Any, context: str) -> dict[str, str | None]:
    observation = _exact(value, frozenset({"visibility", "focus", "paint", "native_pane_ref"}), context)
    if observation["visibility"] not in OBSERVED_VISIBILITIES or observation["focus"] not in {"focused", "unfocused", "unavailable"} or observation["paint"] not in {"painted", "unpainted", "unavailable"}:
        raise BrowserSurfaceError(f"{context} contains an unsupported observation")
    pane = _nullable_identifier(observation["native_pane_ref"], f"{context} native_pane_ref")
    if observation["paint"] == "painted" and (observation["visibility"] != "visible" or pane is None):
        raise BrowserSurfaceError(f"{context} painted state requires an exact visible native-pane reference")
    if observation["paint"] != "painted" and pane is not None:
        raise BrowserSurfaceError(f"{context} native-pane reference requires painted state")
    if observation["visibility"] in {"offscreen", "hidden"} and (observation["focus"] == "focused" or observation["paint"] == "painted"):
        raise BrowserSurfaceError(f"{context} offscreen or hidden surfaces cannot focus or paint")
    return {"visibility": observation["visibility"], "focus": observation["focus"], "paint": observation["paint"], "native_pane_ref": pane}


def _capture(value: Any, context: str) -> dict[str, str | int | float | None]:
    capture = _exact(value, frozenset({"artifact_ref", "artifact_hash", "width", "height", "device_scale", "route_or_component", "state", "theme", "source_revision", "capture_mode", "vision_review_ref", "vision_outcome"}), context)
    result: dict[str, str | int | float | None] = {field: _nullable_identifier(capture[field], f"{context} {field}") for field in ("route_or_component", "state", "theme", "source_revision", "capture_mode", "vision_outcome")}
    result["artifact_ref"] = _confined_ref(capture["artifact_ref"], f"{context} artifact_ref")
    result["vision_review_ref"] = _confined_ref(capture["vision_review_ref"], f"{context} vision_review_ref")
    result["artifact_hash"] = _nullable_identifier(capture["artifact_hash"], f"{context} artifact_hash")
    for field in ("width", "height"):
        dimension = capture[field]
        if dimension is not None and (not isinstance(dimension, int) or isinstance(dimension, bool) or not 1 <= dimension <= 8192):
            raise BrowserSurfaceError(f"{context} {field} must be null or between 1 and 8192")
        result[field] = dimension
    scale = capture["device_scale"]
    if scale is not None and (not isinstance(scale, (int, float)) or isinstance(scale, bool) or not 0 < float(scale) <= 8):
        raise BrowserSurfaceError(f"{context} device_scale must be null or between 0 and 8")
    result["device_scale"] = scale
    if result["artifact_hash"] is not None and not SHA256_PATTERN.fullmatch(str(result["artifact_hash"])):
        raise BrowserSurfaceError(f"{context} artifact_hash must be an exact sha256 reference")
    if result["vision_outcome"] is not None and result["vision_outcome"] not in {"pending", "pass", "fail", "unobserved", "blocked"}:
        raise BrowserSurfaceError(f"{context} vision_outcome is unsupported")
    return result


def _unavailability(value: Any, context: str) -> dict[str, str | None] | None:
    if value is None:
        return None
    unavailable = _exact(value, frozenset({"code", "detail"}), context)
    if unavailable["code"] not in UNAVAILABILITY_CODES:
        raise BrowserSurfaceError(f"{context} code is unsupported")
    return {"code": unavailable["code"], "detail": _nullable_identifier(unavailable["detail"], f"{context} detail")}


def validate_browser_surface_receipt(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a compact provider receipt that cannot transport browser data."""

    receipt = _exact(value, RECEIPT_FIELDS, "browser surface receipt")
    if receipt["schema_version"] != 1 or receipt["operation"] not in OPERATIONS or receipt["status"] not in STATUSES:
        raise BrowserSurfaceError("browser surface receipt has an unsupported version, operation, or status")
    if receipt["operation"] == "capture" and receipt["status"] not in {"captured", "unsupported", "unavailable", "outcome_unknown", "unverifiable"}:
        raise BrowserSurfaceError("browser surface capture receipt must be captured")
    if receipt["operation"] == "release" and receipt["status"] not in {"released", "retained", "unsupported", "unavailable", "outcome_unknown", "unverifiable"}:
        raise BrowserSurfaceError("browser surface release receipt must be released or retained")
    expected_status = {"reserve": "reserved", "bind": "bound", "capture": "captured", "release": None}[receipt["operation"]]
    if expected_status is not None and receipt["status"] not in {expected_status, "unsupported", "unavailable", "outcome_unknown", "unverifiable"}:
        raise BrowserSurfaceError("browser surface receipt status does not match its operation")
    unavailable = _unavailability(receipt["unavailability"], "browser surface receipt unavailability")
    if (receipt["status"] in {"unsupported", "unavailable", "outcome_unknown", "unverifiable"}) != (unavailable is not None):
        raise BrowserSurfaceError("browser surface unavailable status and typed unavailability must agree")
    result = {
        "schema_version": 1, "receipt_id": _identifier(receipt["receipt_id"], "browser surface receipt receipt_id"),
        "request_id": _identifier(receipt["request_id"], "browser surface receipt request_id"), "task_id": _identifier(receipt["task_id"], "browser surface receipt task_id"), "attempt_id": _identifier(receipt["attempt_id"], "browser surface receipt attempt_id"),
        "operation": receipt["operation"], "status": receipt["status"], "idempotency_key": _identifier(receipt["idempotency_key"], "browser surface receipt idempotency_key"),
        "surface": _surface(receipt["surface"], "browser surface receipt surface"), "observation": _observation(receipt["observation"], "browser surface receipt observation"), "capture": _capture(receipt["capture"], "browser surface receipt capture"), "unavailability": unavailable,
    }
    _reject_contents(result)
    return result


def visible_paint_proven(receipt: Mapping[str, Any], request: Mapping[str, Any]) -> bool:
    """Return true only for the exact native-pane proof a visible request needs."""

    observed, requested = validate_browser_surface_receipt(receipt), validate_browser_surface_request(request)
    observation = observed["observation"]
    return bool(requested["mode"] == "visible" and observed["status"] not in {"unsupported", "unavailable", "outcome_unknown", "unverifiable"} and observation["visibility"] == "visible" and observation["focus"] == "focused" and observation["paint"] == "painted" and observation["native_pane_ref"] is not None)


def validate_receipt_for_request(receipt: Mapping[str, Any], request: Mapping[str, Any]) -> dict[str, Any]:
    """Require exact identity, while retaining contrary visibility observations."""

    observed, requested = validate_browser_surface_receipt(receipt), validate_browser_surface_request(request)
    for field in ("request_id", "task_id", "attempt_id", "idempotency_key"):
        if observed[field] != requested[field]:
            raise BrowserSurfaceError(f"browser surface receipt {field} does not match its request")
    for field in ("execution_host_id", "workspace_key", "binding", "viewport", "source_revision"):
        if observed["surface"][field] != requested[field]:
            raise BrowserSurfaceError(f"browser surface receipt {field} does not match its request")
    failed = observed["status"] in {"unsupported", "unavailable", "outcome_unknown", "unverifiable"}
    if requested["page_binding"] is not None and observed["operation"] in {"bind", "capture", "release"} and not failed and observed["surface"]["page_binding"] != requested["page_binding"]:
        raise BrowserSurfaceError("browser surface receipt page_binding does not match adopted page")
    if observed["operation"] == "reserve" and not failed and observed["surface"]["page_binding"] is not None:
        raise BrowserSurfaceError("browser surface reserve cannot claim a page binding")
    if observed["operation"] in {"bind", "capture", "release"} and not failed and observed["surface"]["page_binding"] is None:
        raise BrowserSurfaceError("browser surface bind, capture, and release require an exact page binding")
    if requested["mode"] == "offscreen" and not failed and observed["observation"]["visibility"] != "offscreen":
        raise BrowserSurfaceError("offscreen browser surface must remain observed offscreen")
    if observed["operation"] == "capture" and observed["status"] == "captured":
        required = ("artifact_ref", "artifact_hash", "width", "height", "device_scale", "route_or_component", "state", "theme", "source_revision", "capture_mode", "vision_review_ref", "vision_outcome")
        if any(observed["capture"][field] is None for field in required):
            raise BrowserSurfaceError("browser surface capture requires complete bounded evidence metadata")
        if observed["capture"]["source_revision"] != requested["source_revision"]:
            raise BrowserSurfaceError("browser surface capture source_revision does not match its request")
    return observed


def public_receipt(value: Mapping[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(validate_browser_surface_receipt(value))


def unavailable_receipt(
    request: Mapping[str, Any], *, operation: str, code: str, detail: str | None = None
) -> dict[str, Any]:
    """Build a truthful metadata-only failure receipt without inventing a page."""

    requested = validate_browser_surface_request(request)
    status = "outcome_unknown" if code == "outcome-unknown" else "unverifiable" if code == "unverifiable" else "unsupported" if code in {"unsupported", "old-peer"} else "unavailable"
    return validate_browser_surface_receipt({
        "schema_version": 1,
        "receipt_id": f"browser-surface-{operation}-{requested['request_id']}",
        "request_id": requested["request_id"], "task_id": requested["task_id"], "attempt_id": requested["attempt_id"],
        "operation": operation, "status": status, "idempotency_key": requested["idempotency_key"],
        "surface": {"surface_id": f"surface-{requested['request_id']}", "execution_host_id": requested["execution_host_id"], "workspace_key": requested["workspace_key"], "page_binding": None, "binding": requested["binding"], "viewport": requested["viewport"], "source_revision": requested["source_revision"], "harness_owned": False},
        "observation": {"visibility": "old-peer" if code == "old-peer" else "remote-unreachable" if code == "remote-unreachable" else "unsupported" if code == "unsupported" else "unavailable", "focus": "unavailable", "paint": "unavailable", "native_pane_ref": None},
        "capture": {"artifact_ref": None, "artifact_hash": None, "width": None, "height": None, "device_scale": None, "route_or_component": None, "state": None, "theme": None, "source_revision": None, "capture_mode": None, "vision_review_ref": None, "vision_outcome": None},
        "unavailability": {"code": code, "detail": detail},
    })
