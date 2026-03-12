from __future__ import annotations


class FinSightError(Exception):
    """Base exception for all FinSight errors."""


class QualityGateError(FinSightError):
    """Raised when a quality check fails — Airflow marks task as failed."""

    def __init__(self, stage: str, check: str, detail: str) -> None:
        self.stage = stage
        self.check = check
        self.detail = detail
        super().__init__(f"Quality gate failed [{stage}:{check}]: {detail}")


class IdempotencyError(FinSightError):
    """Raised when an operation would violate idempotency constraints."""


class TenantAuthError(FinSightError):
    """Raised when tenant authentication fails."""


class TickerNotInUniverseError(FinSightError):
    """Raised when a ticker is not in the tenant's allowed universe."""

    def __init__(self, ticker: str) -> None:
        self.ticker = ticker
        super().__init__(f"Ticker '{ticker}' is not in your authorized universe")


class GuardrailViolationError(FinSightError):
    """Raised when input or output fails guardrail validation."""

    def __init__(self, violation_type: str, detail: str) -> None:
        self.violation_type = violation_type
        self.detail = detail
        super().__init__(f"Guardrail violation [{violation_type}]: {detail}")


class EDGARError(FinSightError):
    """Raised when EDGAR API calls fail."""


class EmbeddingError(FinSightError):
    """Raised when embedding generation fails."""


class StorageError(FinSightError):
    """Raised when object storage operations fail."""
