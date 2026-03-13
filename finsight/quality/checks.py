from __future__ import annotations

from finsight.domain.errors import QualityGateError
from finsight.domain.types import PipelineStage, QualityCheck, QualityReport

MIN_SECTIONS = 3
MIN_CHUNKS = 20
MIN_CONTENT_BYTES = 10_000
EMBEDDING_DIM = 1536


def check_ingestion(
    filing_id,
    *,
    content_bytes: int,
    http_status: int,
) -> QualityReport:
    checks: list[QualityCheck] = [
        QualityCheck(
            name="filing_accessible",
            passed=http_status == 200,
            value=http_status,
            threshold=200,
            message=None if http_status == 200 else f"HTTP {http_status}",
        ),
        QualityCheck(
            name="min_content_bytes",
            passed=content_bytes >= MIN_CONTENT_BYTES,
            value=content_bytes,
            threshold=MIN_CONTENT_BYTES,
            message=None if content_bytes >= MIN_CONTENT_BYTES else f"Only {content_bytes} bytes",
        ),
    ]
    passed = all(c.passed for c in checks)
    return QualityReport(
        filing_id=filing_id,
        stage=PipelineStage.INGESTION,
        passed=passed,
        checks=checks,
    )


def check_transform(
    filing_id,
    *,
    sections_found: set[str],
    chunk_count: int,
) -> QualityReport:
    section_count = len(sections_found)
    # 10-K: mda = item7; 10-Q: item2 maps to "properties" in the section map
    mda_present = bool(sections_found & {"mda", "properties"})

    checks: list[QualityCheck] = [
        QualityCheck(
            name="section_coverage",
            passed=section_count >= MIN_SECTIONS,
            value=section_count,
            threshold=MIN_SECTIONS,
            message=(
                f"Found: {sorted(sections_found)}"
                if section_count >= MIN_SECTIONS
                else f"Only {section_count} sections"
            ),
        ),
        QualityCheck(
            name="min_total_chunks",
            passed=chunk_count >= MIN_CHUNKS,
            value=chunk_count,
            threshold=MIN_CHUNKS,
            message=None if chunk_count >= MIN_CHUNKS else f"Only {chunk_count} chunks",
        ),
        QualityCheck(
            name="mda_present",
            passed=mda_present,
            value=mda_present,
            threshold=True,
            message=None if mda_present else "MDA section missing",
        ),
    ]
    passed = all(c.passed for c in checks)
    return QualityReport(
        filing_id=filing_id,
        stage=PipelineStage.TRANSFORM,
        passed=passed,
        checks=checks,
    )


def check_embedding(
    filing_id,
    *,
    parquet_count: int,
    pgvector_count: int,
    zero_vectors: int,
    embedding_dim: int,
) -> QualityReport:
    counts_match = parquet_count == pgvector_count
    checks: list[QualityCheck] = [
        QualityCheck(
            name="chunk_count_matches",
            passed=counts_match,
            value={"parquet": parquet_count, "pgvector": pgvector_count},
            threshold=True,
            message=(
                None
                if counts_match
                else f"Parquet={parquet_count} vs pgvector={pgvector_count}"
            ),
        ),
        QualityCheck(
            name="embedding_dimension",
            passed=embedding_dim == EMBEDDING_DIM,
            value=embedding_dim,
            threshold=EMBEDDING_DIM,
            message=(
                None
                if embedding_dim == EMBEDDING_DIM
                else f"Got {embedding_dim}, expected {EMBEDDING_DIM}"
            ),
        ),
        QualityCheck(
            name="no_zero_vectors",
            passed=zero_vectors == 0,
            value=zero_vectors,
            threshold=0,
            message=None if zero_vectors == 0 else f"{zero_vectors} zero-vector embeddings",
        ),
    ]
    passed = all(c.passed for c in checks)
    return QualityReport(
        filing_id=filing_id,
        stage=PipelineStage.EMBEDDING,
        passed=passed,
        checks=checks,
    )


def enforce_quality_gate(report: QualityReport) -> None:
    """Raise QualityGateError if any check failed."""
    for check in report.checks:
        if not check.passed:
            raise QualityGateError(
                stage=report.stage.value,
                check=check.name,
                detail=check.message or f"value={check.value} threshold={check.threshold}",
            )
