"""Platform-compatible request correlation without copying request payloads to logs."""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from fastapi import Request

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}$")


def _header(request: Request, name: str) -> str | None:
    value = request.headers.get(name)
    return value if value and _SAFE_ID.fullmatch(value) else None


@dataclass(frozen=True, slots=True)
class OperationContext:
    run_id: str
    correlation_id: str
    trace_id: str
    request_id: str
    causation_id: str | None = None
    idempotency_key: str | None = None

    @classmethod
    def from_request(cls, request: Request) -> "OperationContext":
        request_id = _header(request, "x-request-id") or f"req-{uuid.uuid4()}"
        return cls(
            run_id=_header(request, "x-shadow-run-id") or f"run-{uuid.uuid4()}",
            correlation_id=_header(request, "x-correlation-id") or request_id,
            trace_id=_header(request, "x-shadow-trace-id") or uuid.uuid4().hex,
            request_id=request_id,
            causation_id=_header(request, "x-causation-id"),
            idempotency_key=_header(request, "idempotency-key"),
        )

    def as_dict(self) -> dict[str, str]:
        values = {
            "run_id": self.run_id, "correlation_id": self.correlation_id,
            "trace_id": self.trace_id, "request_id": self.request_id,
        }
        if self.causation_id:
            values["causation_id"] = self.causation_id
        if self.idempotency_key:
            values["idempotency_key"] = self.idempotency_key
        return values

    def headers(self) -> dict[str, str]:
        values = {
            "X-Shadow-Run-Id": self.run_id, "X-Correlation-Id": self.correlation_id,
            "X-Shadow-Trace-Id": self.trace_id, "X-Request-Id": self.request_id,
        }
        if self.causation_id:
            values["X-Causation-Id"] = self.causation_id
        return values
