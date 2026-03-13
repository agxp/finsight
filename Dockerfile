FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml .
COPY finsight/ ./finsight/
RUN pip install --no-cache-dir -e "."

CMD ["uvicorn", "finsight.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
