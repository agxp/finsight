#!/usr/bin/env python3
from __future__ import annotations

import os
import sys

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

endpoint = os.environ["MINIO_ENDPOINT"]
bucket = os.environ["MINIO_BUCKET"]
use_ssl = os.environ.get("MINIO_USE_SSL", "false").lower() == "true"
protocol = "https" if use_ssl else "http"

client = boto3.client(
    "s3",
    endpoint_url=f"{protocol}://{endpoint}",
    aws_access_key_id=os.environ["MINIO_ACCESS_KEY"],
    aws_secret_access_key=os.environ["MINIO_SECRET_KEY"],
    config=Config(signature_version="s3v4"),
    region_name="us-east-1",
)

try:
    client.head_bucket(Bucket=bucket)
    print(f"Bucket '{bucket}' already exists.")
except ClientError as e:
    if e.response["Error"]["Code"] in ("404", "NoSuchBucket"):
        client.create_bucket(Bucket=bucket)
        print(f"Bucket '{bucket}' created.")
    else:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
