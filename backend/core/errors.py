"""Domain errors and their mapping to HTTP responses.

Services raise these. `main.py` installs a single handler that translates them,
so route code never builds error responses by hand.
"""

from typing import Any


class DomainError(Exception):
    """Base class for errors with a deliberate HTTP mapping."""

    status_code: int = 400
    code: str = "domain_error"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_payload(self) -> dict[str, Any]:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


class NotFoundError(DomainError):
    status_code = 404
    code = "not_found"


class ValidationError(DomainError):
    """The request was well-formed HTTP but semantically invalid."""

    status_code = 422
    code = "validation_error"


class UpstreamError(DomainError):
    """An external provider (LLM, etc.) failed. Usually retryable upstream."""

    status_code = 502
    code = "upstream_error"


class RateLimitedError(DomainError):
    status_code = 429
    code = "rate_limited"


__all__ = [
    "DomainError",
    "NotFoundError",
    "RateLimitedError",
    "UpstreamError",
    "ValidationError",
]
