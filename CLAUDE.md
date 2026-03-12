# CLAUDE.md

## What this is

FinSight — Financial Research Data Pipeline + RAG Agent. Ingests SEC EDGAR filings (10-K, 10-Q), processes them through a multi-stage pipeline (download → parse → chunk → embed), stores embeddings in pgvector, and exposes a ReAct agent that answers financial research questions with citations.

Demonstrates: data engineering (batch pipelines, Parquet/lakehouse, orchestration, idempotency, backfills, data quality) + agentic systems (tool use, RAG/semantic retrieval, ReAct planning, guardrails).

## Architecture

Single Python package (`finsight/`) with distinct layers:
- `ingestion/` — EDGAR API client + idempotent downloader
- `transform/` — HTML parser + chunker + Parquet writer
- `quality/` — per-stage quality checks + QualityGateError
- `embedding/` — OpenAI embedder + pgvector upsert pipeline
- `retrieval/` — pgvector cosine search with metadata filters
- `agent/` — ReAct loop (Claude tool use) + guardrails + audit
- `api/` — FastAPI app, streaming SSE, auth, rate limiting
- `dags/` — Airflow DAGs (ingest → transform → embed chain)

## Stack

Python 3.11, FastAPI, PostgreSQL 16 + pgvector, MinIO (S3-compatible), Redis 7, Apache Airflow 2.9, Anthropic Claude claude-sonnet-4-6, OpenAI text-embedding-3-small.

## Key conventions

- All types in `domain/types.py`. Don't scatter type definitions.
- Config is env-var only via `finsight/config.py` (Pydantic Settings).
- Structured logging via structlog everywhere.
- Errors wrap with explicit context: `raise SomeError("doing thing") from e`.
- API keys hashed with SHA-256. Raw key shown once at creation.
- Tenant is resolved from Bearer token in auth middleware.
- All tool calls validate ticker ∈ `tenant.ticker_universe` — hard security boundary.
- Idempotency primitive: `INSERT ... ON CONFLICT (accession_number) DO NOTHING`.

## Common tasks

```bash
docker-compose up -d
source .env
make migrate && make seed
make run-api
```

## Things that are TODO / stubs

- S3Store uses MinIO locally; production would use real AWS S3
- Airflow DAG trigger_dag_run calls use simplified TriggerDagRunOperator
- evaluator.py stubs response quality metrics (no ground truth dataset yet)
- Integration test fixtures (filing_store, chunk_store, etc.) need real DB setup in conftest
