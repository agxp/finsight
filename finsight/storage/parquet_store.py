from __future__ import annotations

import io

import pyarrow as pa
import pyarrow.parquet as pq

from finsight.domain.types import ParquetChunkRow
from finsight.storage.object_store import MinIOStore

PIPELINE_VERSION = "0.1.0"

PARQUET_SCHEMA = pa.schema(
    [
        pa.field("filing_id", pa.string()),
        pa.field("accession_number", pa.string()),
        pa.field("ticker", pa.string()),
        pa.field("form_type", pa.string()),
        pa.field("period_of_report", pa.string()),
        pa.field("filed_date", pa.string()),
        pa.field("section", pa.string()),
        pa.field("chunk_index", pa.int32()),
        pa.field("content", pa.string()),
        pa.field("token_count", pa.int32()),
        pa.field("char_count", pa.int32()),
        pa.field("has_tables", pa.bool_()),
        pa.field("quality_score", pa.float32()),
        pa.field("pipeline_version", pa.string()),
        pa.field("created_at", pa.string()),
    ]
)


def make_parquet_key(ticker: str, year: int, quarter: int, part_id: str) -> str:
    return f"parquet/chunks/ticker={ticker}/year={year}/quarter={quarter}/part-{part_id}.parquet"


class ParquetStore:
    def __init__(self, store: MinIOStore) -> None:
        self._store = store

    async def write_chunks(self, rows: list[ParquetChunkRow], s3_key: str) -> str:
        """Write chunks as Parquet to MinIO. Returns the S3 key."""
        dicts = [r.model_dump() for r in rows]
        table = pa.Table.from_pylist(dicts, schema=PARQUET_SCHEMA)

        buf = io.BytesIO()
        pq.write_table(table, buf, compression="snappy")
        buf.seek(0)

        await self._store.put(s3_key, buf.read(), content_type="application/octet-stream")
        return s3_key

    async def read_chunks(self, s3_key: str) -> list[ParquetChunkRow]:
        """Read Parquet file from MinIO, return rows."""
        data = await self._store.get(s3_key)
        buf = io.BytesIO(data)
        table = pq.read_table(buf)
        return [ParquetChunkRow(**row) for row in table.to_pylist()]
