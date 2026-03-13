FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        postgresql-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml .
COPY finsight/ ./finsight/
COPY scripts/ ./scripts/
COPY frontend/ ./frontend/
RUN pip install --no-cache-dir -e "." && chmod +x /app/scripts/docker-init.sh

CMD ["uvicorn", "finsight.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
