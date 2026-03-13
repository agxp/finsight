FROM apache/airflow:2.9.0

COPY pyproject.toml /tmp/pyproject.toml
RUN pip install --no-cache-dir \
    asyncpg>=0.29.0 \
    pgvector>=0.2.5 \
    anthropic>=0.25.0 \
    openai>=1.30.0 \
    pyarrow>=16.0.0 \
    duckdb>=0.10.3 \
    boto3>=1.34.0 \
    aiobotocore>=2.13.0 \
    "beautifulsoup4>=4.12.0" \
    "lxml>=5.2.0" \
    "redis>=5.0.0" \
    "pydantic>=2.7.0" \
    "pydantic-settings>=2.2.0" \
    "tiktoken>=0.7.0" \
    "tenacity>=8.3.0" \
    "structlog>=24.1.0" \
    "httpx>=0.27.0"
