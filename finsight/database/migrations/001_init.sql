CREATE TABLE IF NOT EXISTS tenants (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    api_key_hash    TEXT NOT NULL UNIQUE,
    ticker_universe TEXT[] NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS filings (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    accession_number TEXT NOT NULL UNIQUE,
    ticker           TEXT NOT NULL,
    cik              TEXT NOT NULL,
    form_type        TEXT NOT NULL,
    period_of_report DATE NOT NULL,
    filed_date       DATE NOT NULL,
    raw_s3_key       TEXT,
    parquet_s3_key   TEXT,
    status           TEXT NOT NULL DEFAULT 'pending',
    error_message    TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_filings_ticker ON filings(ticker);
CREATE INDEX IF NOT EXISTS idx_filings_status ON filings(status);
CREATE INDEX IF NOT EXISTS idx_filings_period ON filings(period_of_report);

CREATE TABLE IF NOT EXISTS filing_quality_reports (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    filing_id  UUID NOT NULL REFERENCES filings(id),
    stage      TEXT NOT NULL,
    passed     BOOLEAN NOT NULL,
    checks     JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
