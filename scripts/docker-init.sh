#!/usr/bin/env bash
set -euo pipefail

echo "=== [finsight-init] Starting ==="

echo "--- Applying migrations ---"
for f in $(ls /app/finsight/database/migrations/*.sql | sort); do
    echo "  $f"
    psql "$DATABASE_URL" -f "$f"
done

echo "--- Creating MinIO bucket ---"
python /app/scripts/create_minio_bucket.py

echo "--- Seeding dev tenant ---"
python /app/scripts/seed_tenant.py

echo "=== [finsight-init] Done ==="
