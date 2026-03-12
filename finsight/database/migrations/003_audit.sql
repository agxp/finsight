CREATE TABLE IF NOT EXISTS agent_queries (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL REFERENCES tenants(id),
    query_text          TEXT NOT NULL,
    tool_calls          JSONB NOT NULL DEFAULT '[]',
    retrieved_chunk_ids UUID[] NOT NULL DEFAULT '{}',
    model_response      TEXT,
    input_tokens        INT,
    output_tokens       INT,
    latency_ms          INT,
    guardrail_flags     JSONB,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_agent_queries_tenant ON agent_queries(tenant_id);
CREATE INDEX IF NOT EXISTS idx_agent_queries_created ON agent_queries(created_at);
