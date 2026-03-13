from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM
    anthropic_api_key: str = Field(default="", description="Anthropic API key")
    openai_api_key: str = Field(default="", description="OpenAI API key")

    # Database
    database_url: str = Field(
        default="postgresql://finsight:finsight@localhost:5432/finsight",
        description="PostgreSQL connection URL",
    )

    # Redis
    redis_url: str = Field(default="redis://localhost:6379", description="Redis URL")

    # MinIO / S3
    minio_endpoint: str = Field(default="localhost:9000", description="MinIO endpoint")
    minio_access_key: str = Field(default="minio", description="MinIO access key")
    minio_secret_key: str = Field(default="minio123", description="MinIO secret key")
    minio_bucket: str = Field(default="finsight", description="MinIO bucket name")
    minio_use_ssl: bool = Field(default=False, description="Use SSL for MinIO")

    # API
    api_port: int = Field(default=8000, description="API server port")
    api_env: str = Field(default="development", description="Environment name")

    # Rate limiting
    rate_limit_agent_rpm: int = Field(default=10, description="Agent queries per minute per tenant")

    # LLM models
    agent_model: str = Field(default="claude-sonnet-4-6", description="Claude model for agent")
    embedding_model: str = Field(
        default="text-embedding-3-small", description="OpenAI embedding model"
    )
    embedding_dimensions: int = Field(default=1536, description="Embedding vector dimensions")

    # Pipeline
    chunk_max_tokens: int = Field(default=400, description="Max tokens per chunk")
    chunk_overlap_tokens: int = Field(default=50, description="Overlap tokens between chunks")
    chunk_min_tokens: int = Field(default=50, description="Minimum chunk size")
    embedding_batch_size: int = Field(default=20, description="Chunks per embedding batch")
    agent_max_iterations: int = Field(default=8, description="Max ReAct loop iterations")

    # Airflow
    airflow_api_url: str = Field(
        default="http://localhost:8080/api/v1",
        description="Airflow REST API base URL",
    )
    airflow_api_user: str = Field(default="airflow", description="Airflow basic-auth username")
    airflow_api_password: str = Field(default="airflow", description="Airflow basic-auth password")

    # EDGAR
    edgar_user_agent: str = Field(
        default="FinSight research@example.com",
        description="User-Agent for EDGAR API requests",
    )
    edgar_rate_limit_rps: float = Field(
        default=8.0, description="Max requests/second to EDGAR"
    )


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
