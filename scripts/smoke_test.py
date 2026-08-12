#!/usr/bin/env python3
"""Smoke test — checks all service health endpoints are responding."""

import subprocess
import sys
import requests

SERVICES = {
    "Command API": "http://localhost:8000/health",
    "State Engine": "http://localhost:8002/health",
    "AI Service": "http://localhost:8003/health",
    "Robot Simulator": "http://localhost:8004/health",
    "Web Control": "http://localhost:8005/health",
}


def _ingestion_url() -> str:
    """Telemetry Ingestion publishes on a host port allocated from a range, so
    that replicas can be scaled. Ask compose which port it actually got."""
    try:
        out = subprocess.run(
            ["docker", "compose", "port", "telemetry-ingestion", "8001"],
            capture_output=True,
            text=True,
            timeout=15,
        ).stdout.strip()
        port = out.rsplit(":", 1)[-1]
        if port.isdigit():
            return f"http://localhost:{port}/health"
    except Exception:
        pass
    return ""


# Grafana is published on 3001, not its container port 3000, because a native
# Grafana install already holds 3000 on the development machine.
GRAFANA = "http://localhost:3001/api/health"
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


def _with_ingestion(services: dict) -> dict:
    url = _ingestion_url()
    if url:
        services = {**services, "Telemetry Ingestion": url}
    return services


def main() -> int:
    print("\nSmartClean Twin — Smoke Test")
    print("=" * 40)
    failures = 0

    for name, url in _with_ingestion(SERVICES).items():
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
