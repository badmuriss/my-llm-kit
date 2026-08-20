"""Shared types for portable Agent Graph drivers."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Protocol, Sequence


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


class Driver(Protocol):
    """Seven-operation transport boundary owned by Agent Graph."""

    def detect(self) -> DriverReceipt: ...

    def start_run(self, objective: str, tasks: Sequence[Mapping[str, Any]]) -> DriverReceipt: ...

    def start_attempt(self, attempt: Mapping[str, Any]) -> DriverReceipt: ...

    def poll(self, attempt: Mapping[str, Any], *, cursor: str | None = None) -> DriverReceipt: ...

    def send(self, attempt: Mapping[str, Any], message: Mapping[str, Any]) -> DriverReceipt: ...

    def release(self, attempt: Mapping[str, Any]) -> DriverReceipt: ...

    def reconcile(self, attempts: Sequence[Mapping[str, Any]]) -> DriverReceipt: ...
