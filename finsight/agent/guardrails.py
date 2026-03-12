from __future__ import annotations

import re

import structlog

from finsight.domain.errors import GuardrailViolationError
from finsight.domain.types import RetrievedChunk, Tenant

log = structlog.get_logger(__name__)

MAX_QUERY_LENGTH = 2000

INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(previous|all|prior)\s+instructions", re.IGNORECASE),
    re.compile(r"system\s+prompt", re.IGNORECASE),
    re.compile(r"<\s*system\s*>", re.IGNORECASE),
    re.compile(r"<\s*tool\s*>", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+", re.IGNORECASE),
    re.compile(r"act\s+as\s+", re.IGNORECASE),
    re.compile(r"disregard\s+(previous|all|prior)", re.IGNORECASE),
    re.compile(r"forget\s+(previous|all|prior|your)", re.IGNORECASE),
]

TICKER_RE = re.compile(r"\b[A-Z]{2,5}\b")

KNOWN_NON_TICKERS = {
    "THE", "AND", "FOR", "ARE", "BUT", "NOT", "YOU", "ALL",
    "CAN", "HER", "WAS", "ONE", "OUR", "OUT", "DAY", "GET",
    "HAS", "HIM", "HIS", "HOW", "ITS", "MAY", "NEW", "NOW",
    "OLD", "OWN", "SAY", "SHE", "TOO", "USE", "WAY", "WHO",
    "SEC", "MDA", "EPS", "YOY", "YTD", "QOQ", "USD", "GDP",
    "USA", "ETF", "IPO", "CFO", "CEO", "COO", "ESG", "AI",
    "ML", "API", "LLM", "RAG", "SSE",
}


def validate_input(query: str) -> dict | None:
    """
    Validate query input. Returns guardrail_flags dict if issues found, else None.
    Raises GuardrailViolationError on hard violations.
    """
    flags: dict[str, str] = {}

    if len(query) > MAX_QUERY_LENGTH:
        raise GuardrailViolationError(
            "input_too_long",
            f"Query length {len(query)} exceeds max {MAX_QUERY_LENGTH}",
        )

    for pattern in INJECTION_PATTERNS:
        if pattern.search(query):
            flags["injection_pattern"] = pattern.pattern
            log.warning(
                "injection pattern detected",
                pattern=pattern.pattern,
                query_preview=query[:100],
            )
            raise GuardrailViolationError(
                "injection_attempt",
                f"Query contains prohibited pattern: {pattern.pattern}",
            )

    return flags if flags else None


def validate_output(
    response_text: str,
    retrieved_chunks: list[RetrievedChunk],
    tenant: Tenant,
) -> dict | None:
    """
    Validate agent output. Returns guardrail_flags dict if issues found, else None.
    Does NOT raise — output guardrails are advisory.
    """
    flags: dict[str, list] = {}

    response_tickers = TICKER_RE.findall(response_text)
    universe_upper = {t.upper() for t in tenant.ticker_universe}
    hallucinated = [
        t for t in response_tickers
        if t not in universe_upper and t not in KNOWN_NON_TICKERS
    ]
    if hallucinated:
        flags["potential_ticker_hallucinations"] = hallucinated
        log.warning("potential ticker hallucination", tickers=hallucinated)

    source_content = " ".join(c.content for c in retrieved_chunks)
    number_re = re.compile(r"\$[\d,]+(?:\.\d+)?(?:\s*(?:billion|million|thousand))?", re.IGNORECASE)
    response_numbers = number_re.findall(response_text)
    ungrounded = [
        num for num in response_numbers
        if num.replace(",", "").replace("$", "").strip() not in source_content
        and num not in source_content
    ]
    if ungrounded:
        flags["potentially_ungrounded_figures"] = ungrounded
        log.warning("potentially ungrounded financial figures", figures=ungrounded)

    return flags if flags else None
