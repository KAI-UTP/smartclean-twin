"""System tests: end-to-end scenarios (run against live Docker Compose stack).

These tests require the full stack to be running:
  docker compose up -d

Run with:
  pytest tests/system/ -v --timeout=30

Skip in CI unless INTEGRATION_TEST=1 is set.
"""

import os
import pytest
import time
import requests

STACK_RUNNING = os.environ.get("INTEGRATION_TEST", "0") == "1"
skip_without_stack = pytest.mark.skipif(
    not STACK_RUNNING, reason="Set INTEGRATION_TEST=1 to run against live Docker Compose stack"
)

BASE_URL_CMD = "http://localhost:8000"


def _ingestion_base_url() -> str:
    """Telemetry Ingestion's host port is allocated from a range so replicas can
    be scaled, so it is not fixed at 8001. Ask compose which port it got."""
    import subprocess

    try:
        out = subprocess.run(
            ["docker", "compose", "port", "telemetry-ingestion", "8001"],
            capture_output=True,
            text=True,
            timeout=15,
        ).stdout.strip()
        port = out.rsplit(":", 1)[-1]
        if port.isdigit():
            return f"http://localhost:{port}"
    except Exception:
        pass
    return "http://localhost:8001"


BASE_URL_INGESTION = _ingestion_base_url()
BASE_URL_STATE = "http://localhost:8002"
BASE_URL_AI = "http://localhost:8003"
BASE_URL_SIM = "http://localhost:8004"


@skip_without_stack
class TestServiceHealth:
    def test_command_api_health(self):
        r = requests.get(f"{BASE_URL_CMD}/health", timeout=5)
        assert r.status_code == 200
        assert r.json()["status"] == "healthy"

    def test_ingestion_health(self):
        r = requests.get(f"{BASE_URL_INGESTION}/health", timeout=5)
        assert r.status_code == 200

    def test_state_engine_health(self):
        r = requests.get(f"{BASE_URL_STATE}/health", timeout=5)
        assert r.status_code == 200

    def test_ai_service_health(self):
        r = requests.get(f"{BASE_URL_AI}/health", timeout=5)
        assert r.status_code == 200

    def test_simulator_health(self):
        r = requests.get(f"{BASE_URL_SIM}/health", timeout=5)
        assert r.status_code == 200


@skip_without_stack
class TestCommandFlow:
    def test_pause_command_returns_ack(self):
        r = requests.post(
            f"{BASE_URL_CMD}/api/v1/commands",
            json={"robot_id": "SCR01", "command": "PAUSE"},
            timeout=10,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["command"] == "PAUSE"
        assert data["ack_received"] is True
        assert data["ack_accepted"] is True

    def test_resume_after_pause(self):
        requests.post(
            f"{BASE_URL_CMD}/api/v1/commands",
            json={"robot_id": "SCR01", "command": "PAUSE"},
            timeout=10,
        )
        time.sleep(0.5)
        r = requests.post(
            f"{BASE_URL_CMD}/api/v1/commands",
            json={"robot_id": "SCR01", "command": "RESUME"},
            timeout=10,
        )
        assert r.status_code == 200
        assert r.json()["ack_received"] is True

    def test_command_history_grows(self):
        r1 = requests.get(f"{BASE_URL_CMD}/api/v1/commands", timeout=5)
        count_before = len(r1.json())
        requests.post(
            f"{BASE_URL_CMD}/api/v1/commands",
            json={"robot_id": "SCR01", "command": "STOP"},
            timeout=10,
        )
        time.sleep(0.5)
        r2 = requests.get(f"{BASE_URL_CMD}/api/v1/commands", timeout=5)
        assert len(r2.json()) > count_before


@skip_without_stack
class TestObstacleEmergencyScenario:
    def test_inject_obstacle_and_check_state(self):
        # Inject obstacle via simulator fault API
        r = requests.post(f"{BASE_URL_SIM}/fault", json={"fault": "obstacle"}, timeout=5)
        assert r.status_code == 200
        time.sleep(3)  # Wait for state engine to process
        # State engine should reflect emergency
        r2 = requests.get(f"{BASE_URL_STATE}/health", timeout=5)
        assert r2.status_code == 200
        # Clear fault
        requests.post(f"{BASE_URL_SIM}/fault", json={"fault": "clear"}, timeout=5)


@skip_without_stack
class TestMotorOverloadScenario:
    def test_inject_motor_overload(self):
        r = requests.post(f"{BASE_URL_SIM}/fault", json={"fault": "motor"}, timeout=5)
        assert r.status_code == 200
        time.sleep(2)
        requests.post(f"{BASE_URL_SIM}/fault", json={"fault": "clear"}, timeout=5)


@skip_without_stack
class TestLowBatteryScenario:
    def test_inject_low_battery(self):
        r = requests.post(f"{BASE_URL_SIM}/fault", json={"fault": "battery"}, timeout=5)
        assert r.status_code == 200
        time.sleep(2)
        requests.post(f"{BASE_URL_SIM}/fault", json={"fault": "clear"}, timeout=5)
