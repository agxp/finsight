from __future__ import annotations

import structlog

from finsight.domain.types import QualityReport

log = structlog.get_logger(__name__)


def log_report(report: QualityReport) -> None:
    """Log a quality report with structured fields."""
    failed = [c for c in report.checks if not c.passed]
    log.info(
        "quality_report",
        filing_id=str(report.filing_id),
        stage=report.stage.value,
        passed=report.passed,
        total_checks=len(report.checks),
        failed_checks=len(failed),
        failures=[c.name for c in failed],
    )
