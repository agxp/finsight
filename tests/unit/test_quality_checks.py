from __future__ import annotations

import uuid

import pytest

from finsight.domain.errors import QualityGateError
from finsight.domain.types import PipelineStage
from finsight.quality.checks import (
    check_embedding,
    check_ingestion,
    check_transform,
    enforce_quality_gate,
)


def make_id():
    return uuid.uuid4()


class TestIngestionChecks:
    def test_passes_when_accessible_and_large_enough(self):
        report = check_ingestion(make_id(), content_bytes=50_000, http_status=200)
        assert report.passed
        assert report.stage == PipelineStage.INGESTION

    def test_fails_on_http_error(self):
        report = check_ingestion(make_id(), content_bytes=50_000, http_status=404)
        assert not report.passed
        failed = [c for c in report.checks if not c.passed]
        assert any(c.name == "filing_accessible" for c in failed)

    def test_fails_on_small_content(self):
        report = check_ingestion(make_id(), content_bytes=5_000, http_status=200)
        assert not report.passed
        failed = [c for c in report.checks if not c.passed]
        assert any(c.name == "min_content_bytes" for c in failed)


class TestTransformChecks:
    def test_passes_with_good_sections(self):
        sections = {"risk_factors", "mda", "financials", "business"}
        report = check_transform(make_id(), sections_found=sections, chunk_count=50)
        assert report.passed

    def test_fails_without_mda(self):
        sections = {"risk_factors", "financials", "business"}
        report = check_transform(make_id(), sections_found=sections, chunk_count=50)
        assert not report.passed
        failed_names = [c.name for c in report.checks if not c.passed]
        assert "mda_present" in failed_names

    def test_fails_with_too_few_chunks(self):
        sections = {"risk_factors", "mda", "financials"}
        report = check_transform(make_id(), sections_found=sections, chunk_count=5)
        assert not report.passed
        failed_names = [c.name for c in report.checks if not c.passed]
        assert "min_total_chunks" in failed_names

    def test_fails_with_too_few_sections(self):
        sections = {"mda"}
        report = check_transform(make_id(), sections_found=sections, chunk_count=50)
        assert not report.passed


class TestEmbeddingChecks:
    def test_passes_when_all_good(self):
        report = check_embedding(
            make_id(),
            parquet_count=100,
            pgvector_count=100,
            zero_vectors=0,
            embedding_dim=1536,
        )
        assert report.passed

    def test_fails_on_count_mismatch(self):
        report = check_embedding(
            make_id(),
            parquet_count=100,
            pgvector_count=95,
            zero_vectors=0,
            embedding_dim=1536,
        )
        assert not report.passed
        failed_names = [c.name for c in report.checks if not c.passed]
        assert "chunk_count_matches" in failed_names

    def test_fails_on_wrong_dimension(self):
        report = check_embedding(
            make_id(),
            parquet_count=100,
            pgvector_count=100,
            zero_vectors=0,
            embedding_dim=768,
        )
        assert not report.passed

    def test_fails_on_zero_vectors(self):
        report = check_embedding(
            make_id(),
            parquet_count=100,
            pgvector_count=100,
            zero_vectors=3,
            embedding_dim=1536,
        )
        assert not report.passed


class TestEnforceQualityGate:
    def test_raises_on_failed_report(self):
        report = check_ingestion(make_id(), content_bytes=100, http_status=404)
        with pytest.raises(QualityGateError) as exc_info:
            enforce_quality_gate(report)
        assert "filing_accessible" in str(exc_info.value)

    def test_no_raise_on_passing_report(self):
        report = check_ingestion(make_id(), content_bytes=50_000, http_status=200)
        enforce_quality_gate(report)  # Should not raise
