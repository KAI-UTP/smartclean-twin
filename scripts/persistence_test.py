#!/usr/bin/env python3
"""Persistence test — proves data survives InfluxDB container restart.

Steps:
  1. Query InfluxDB for current telemetry count.
  2. Record the count and a sample value.
  3. Restart the InfluxDB container.
  4. Wait for InfluxDB to come back.
  5. Query again.
  6. Assert data is still present.
"""

import subprocess
import sys
import time
import requests

INFLUXDB_URL = "http://localhost:8086"
TOKEN = "smartclean-super-secret-token"
ORG = "smartclean"
BUCKET = "smartclean_twin"
HEADERS = {"Authorization": f"Token {TOKEN}", "Content-Type": "application/vnd.flux"}

FLUX_QUERY = """
from(bucket: "smartclean_twin")
  |> range(start: -1h)
  |> filter(fn: (r) => r._measurement == "robot_telemetry" and r._field == "battery_soc")
  |> count()
"""


def query_count() -> int:
    r = requests.post(
        f"{INFLUXDB_URL}/api/v2/query?org={ORG}",
        headers=HEADERS,
        data=FLUX_QUERY,
        timeout=10,
    )
    if r.status_code != 200:
        print(f"Query failed: {r.status_code} {r.text[:200]}")
        return -1
    # Parse CSV response
    lines = [l for l in r.text.strip().splitlines() if l and not l.startswith("#")]
    if len(lines) < 2:
        return 0
    # Last column of last data row is the count
    try:
        return int(lines[-1].split(",")[-1])
    except (ValueError, IndexError):
        return 0


def wait_for_influxdb(timeout: int = 60) -> bool:
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        try:
            r = requests.get(f"{INFLUXDB_URL}/health", timeout=3)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(2)
    return False


def main() -> int:
    print("\nSmartClean Twin — Persistence Test")
    print("=" * 40)

    # Step 1: Pre-restart count
    print("Step 1: Querying InfluxDB before restart...")
    count_before = query_count()
    if count_before < 0:
        print("  FAIL: Could not query InfluxDB. Is the stack running?")
        return 1
    print(f"  Records found before restart: {count_before}")

    if count_before == 0:
        print("  WARNING: No data found. Wait for telemetry to accumulate, then re-run.")
        return 1

    # Step 2: Restart InfluxDB container
    print("Step 2: Restarting InfluxDB container...")
    result = subprocess.run(
        ["docker", "compose", "restart", "influxdb"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"  FAIL: docker compose restart failed: {result.stderr}")
        return 1
    print("  Container restarted.")

    # Step 3: Wait for InfluxDB
    print("Step 3: Waiting for InfluxDB to become healthy...")
    if not wait_for_influxdb(timeout=60):
        print("  FAIL: InfluxDB did not come back healthy within 60s")
        return 1
    print("  InfluxDB healthy.")
    time.sleep(3)  # Extra settle time

    # Step 4: Post-restart count
    print("Step 4: Querying InfluxDB after restart...")
    count_after = query_count()
    print(f"  Records found after restart: {count_after}")

    if count_after >= count_before:
        print(f"\n[PASS] Data persisted: {count_before} records → {count_after} records")
        return 0
    else:
        print(f"\n[FAIL] Data loss detected: {count_before} → {count_after}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
