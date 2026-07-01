#!/usr/bin/env python3
"""Smoke test — checks all service health endpoints are responding."""

import sys
import time
import requests

SERVICES = {
    "Command API":          "http://localhost:8000/health",
    "Telemetry Ingestion":  "http://localhost:8001/health",
    "State Engine":         "http://localhost:8002/health",
    "AI Service":           "http://localhost:8003/health",
    "Robot Simulator":      "http://localhost:8004/health",
}

GRAFANA = "http://localhost:3000/api/health"
INFLUXDB = "http://localhost:8086/health"


def check(name: str, url: str, timeout: int = 5) -> bool:
    try:
        r = requests.get(url, timeout=timeout)
        if r.status_code == 200:
            print(f"  [OK] {name}")
            return True
        print(f"  [FAIL] {name} — HTTP {r.status_code}")
        return False
    except Exception as exc:
        print(f"  [FAIL] {name} — {exc}")
        return False


def main() -> int:
    print("\nSmartClean Twin — Smoke Test")
    print("=" * 40)
    failures = 0

    for name, url in SERVICES.items():
        if not check(name, url):
            failures += 1

    check("InfluxDB", INFLUXDB)
    check("Grafana", GRAFANA)

    print("\n" + "=" * 40)
    if failures == 0:
        print("All core services healthy.")
        return 0
    else:
        print(f"{failures} service(s) failed health check.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
