# FinSight — Financial Research Data Pipeline + RAG Agent

Ingests SEC EDGAR filings (10-K, 10-Q) through a multi-stage pipeline and exposes a ReAct agent that answers financial research questions with citations.

## What this demonstrates

| Skill | Implementation |
|-------|---------------|
| **Batch pipelines + idempotency** | `ON CONFLICT (accession_number) DO NOTHING` — re-running backfills is always safe |
| **Lakehouse / Parquet** | PyArrow + DuckDB, partitioned by `ticker/year/quarter/` on MinIO |
| **Orchestration** | Airflow DAGs with `catchup=True`, SLA alerts, exponential backoff retries |
| **Data quality gates** | Per-stage `QualityReport` → `QualityGateError` → Airflow task failure |
| **Semantic retrieval** | pgvector cosine search over 1536-dim embeddings with metadata filters |
| **ReAct agent** | Claude claude-sonnet-4-6 tool use loop, stateless, full audit log |
| **Guardrails** | Deterministic regex (no second LLM) — injection detection + ticker hallucination check |
| **Streaming** | FastAPI `StreamingResponse` + SSE with `event: tool_call` / `event: done` |

## Architecture

```
SEC EDGAR ──► FilingDownloader ──► MinIO (raw HTML)
                                      │
                                   html_parser + chunker
                                      │
                                   Parquet (MinIO, DuckDB-queryable)
                                      │
                                   OpenAI embedder
                                      │
                                   pgvector (filing_chunks)
                                      │
                              FastAPI /v1/query
                                      │
                              ReAct agent (Claude)
                                   ┌──┴──┐
                              search_filings  get_financial_metrics  compare_periods
```

## Stack

- **Language:** Python 3.11
- **API:** FastAPI + uvicorn
- **LLM (agent):** Anthropic Claude claude-sonnet-4-6 (tool use)
- **Embeddings:** OpenAI text-embedding-3-small (1536 dim)
- **Vector DB:** PostgreSQL 16 + pgvector
- **Object storage:** MinIO (S3-compatible)
- **Orchestration:** Apache Airflow 2.9
- **Rate limiting:** Redis 7 sliding window
- **Testing:** pytest + pytest-asyncio + respx

## Quick start

```bash
# Start all services
docker-compose up -d

# Apply migrations + seed dev tenant
cp .env.example .env   # add ANTHROPIC_API_KEY and OPENAI_API_KEY
source .env
make migrate && make seed   # prints API key

# Run API
make run-api   # http://localhost:8000

# Trigger backfill for AAPL (via Airflow or directly)
airflow dags trigger edgar_backfill \
  --conf '{"tickers": ["AAPL"], "date_from": "2023-01-01", "date_to": "2024-12-31"}'

# Query the agent
curl -X POST http://localhost:8000/v1/query \
  -H "Authorization: Bearer fs_YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query": "What were the main risk factors Apple cited in their most recent 10-K?"}'

# Run tests
make test-unit
```

## API

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/v1/query` | Agent query (supports `"stream": true` for SSE) |
| `GET` | `/v1/filings` | List filings with filters |
| `GET` | `/v1/filings/{id}` | Get single filing |
| `POST` | `/v1/filings/ingest` | Trigger ingestion for a ticker + date range |
| `GET` | `/health` | Health check |
| `GET` | `/ready` | Readiness check (DB + Redis) |

## Pipeline stages

1. **Ingestion** — EDGAR API → raw HTML → MinIO. Quality: HTTP 200, ≥10KB
2. **Transform** — HTML → sections (Items 1–9) → chunks (≤400 tokens, 50-token overlap) → Parquet
3. **Embedding** — Parquet → OpenAI batched → pgvector upsert. Quality: count match, dim=1536, no zero vectors
4. **Agent** — Semantic search → ReAct loop → cited answer

## Key design decisions

**pgvector over Pinecone:** native joins between vector results and relational metadata, one fewer managed service, sufficient at filing corpus scale.

**DuckDB over Spark:** in-process Parquet queries with SQL. No cluster needed at this scale.

**`ON CONFLICT DO NOTHING` as idempotency primitive:** multiple workers can process concurrently; re-running backfills is always safe. Mirrors DocPulse's `FOR UPDATE SKIP LOCKED` pattern.

**Deterministic guardrails:** input/output validation via regex and content-matching rather than a second LLM call. Faster, more predictable, easier to audit — important in a financial context.
