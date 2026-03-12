CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS filing_chunks (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    filing_id        UUID NOT NULL REFERENCES filings(id) ON DELETE CASCADE,
    chunk_index      INT NOT NULL,
    section          TEXT NOT NULL,
    content          TEXT NOT NULL,
    token_count      INT NOT NULL,
    embedding        vector(1536),
    ticker           TEXT NOT NULL,
    form_type        TEXT NOT NULL,
    period_of_report DATE NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(filing_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_chunks_ticker ON filing_chunks(ticker);
CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON filing_chunks
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
