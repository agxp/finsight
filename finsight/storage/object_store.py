from __future__ import annotations

from typing import Protocol, runtime_checkable

import boto3
from botocore.client import Config

from finsight.config import get_settings
from finsight.domain.errors import StorageError


@runtime_checkable
class ObjectStore(Protocol):
    async def put(
        self, key: str, data: bytes, content_type: str = "application/octet-stream"
    ) -> None: ...
    async def get(self, key: str) -> bytes: ...
    async def exists(self, key: str) -> bool: ...
    async def delete(self, key: str) -> None: ...


class MinIOStore:
    """S3-compatible object store backed by MinIO."""

    def __init__(self) -> None:
        settings = get_settings()
        self._bucket = settings.minio_bucket
        protocol = "https" if settings.minio_use_ssl else "http"
        self._client = boto3.client(
            "s3",
            endpoint_url=f"{protocol}://{settings.minio_endpoint}",
            aws_access_key_id=settings.minio_access_key,
            aws_secret_access_key=settings.minio_secret_key,
            config=Config(signature_version="s3v4"),
            region_name="us-east-1",
        )
        self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except Exception:
            try:
                self._client.create_bucket(Bucket=self._bucket)
            except Exception as e:
                raise StorageError(f"Failed to create bucket '{self._bucket}'") from e

    async def put(
        self, key: str, data: bytes, content_type: str = "application/octet-stream"
    ) -> None:
        try:
            self._client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
            )
        except Exception as e:
            raise StorageError(f"Failed to put object '{key}'") from e

    async def get(self, key: str) -> bytes:
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
            return response["Body"].read()
        except Exception as e:
            raise StorageError(f"Failed to get object '{key}'") from e

    async def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except Exception:
            return False

    async def delete(self, key: str) -> None:
        try:
            self._client.delete_object(Bucket=self._bucket, Key=key)
        except Exception as e:
            raise StorageError(f"Failed to delete object '{key}'") from e
