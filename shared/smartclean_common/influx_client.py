"""Shared InfluxDB write helper used by all services."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

from influxdb_client import InfluxDBClient
from influxdb_client.client.write_api import SYNCHRONOUS

logger = logging.getLogger(__name__)


def _get_client() -> tuple[InfluxDBClient, str, str]:
    url = os.environ["INFLUXDB_URL"]
    token = os.environ["INFLUXDB_TOKEN"]
    org = os.environ["INFLUXDB_ORG"]
    bucket = os.environ["INFLUXDB_BUCKET"]
    client = InfluxDBClient(url=url, token=token, org=org)
    return client, org, bucket


def write_points(
    measurement: str,
    tags: dict[str, str],
    fields: dict[str, Any],
    timestamp: datetime | None = None,
) -> None:
    """Write a single data point to InfluxDB."""
    client, org, bucket = _get_client()
    write_api = client.write_api(write_options=SYNCHRONOUS)
    ts = timestamp or datetime.now(timezone.utc)
    point = {
        "measurement": measurement,
        "tags": tags,
        "fields": fields,
        "time": ts,
    }
    try:
        write_api.write(bucket=bucket, org=org, record=point)
    except Exception as exc:
        logger.error("InfluxDB write failed: %s", exc)
    finally:
        client.close()
