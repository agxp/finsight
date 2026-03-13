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
git clone <repo> && cd finsight
cp .env.example .env        # set ANTHROPIC_API_KEY and OPENAI_API_KEY
docker-compose up
```

That's it. On first boot `docker-compose` will:
1. Start Postgres, MinIO, Redis
2. Run DB migrations and create the MinIO bucket (`finsight-init`)
3. Seed a dev tenant and print your API key
4. Start the FastAPI app, Airflow webserver, and scheduler

**Get your API key:**
```bash
docker-compose logs finsight-init | grep "fs_"
```

**Open the UI:** http://localhost:8000 (redirects to `/ui`)

**Ingest filings** — use the Filings tab in the UI, or via curl:
```bash
curl -X POST http://localhost:8000/v1/filings/ingest \
  -H "Authorization: Bearer fs_YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"ticker": "AAPL", "date_from": "2023-01-01", "date_to": "2023-12-31"}'
```

The ingest DAG runs automatically. Watch progress in the Filings tab — filings move through `ingested → transformed → embedded`. Once `embedded`, the agent can answer questions about them.

**Query the agent:**
```bash
curl -X POST http://localhost:8000/v1/query \
  -H "Authorization: Bearer fs_YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query": "What were the main risk factors Apple cited in their most recent 10-K?", "stream": false}'
```

**Other services:**
| Service | URL |
|---------|-----|
| API + UI | http://localhost:8000 |
| Airflow | http://localhost:8081 (admin / admin) |
| MinIO console | http://localhost:9001 (minio / minio123) |

**Re-running is safe** — all init steps are idempotent. If you reset and want a fresh API key:
```bash
docker-compose exec postgres psql -U finsight -d finsight -c "DELETE FROM tenants WHERE name = 'dev-tenant';"
docker-compose restart finsight-init
docker-compose logs finsight-init | grep "fs_"
```

**Run tests:**
```bash
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

**`ON CONFLICT DO NOTHING` as idempotency primitive:** multiple workers can process concurrently; re-running backfills is always safe.

**Deterministic guardrails:** input/output validation via regex and content-matching rather than a second LLM call. Faster, more predictable, easier to audit — important in a financial context.
