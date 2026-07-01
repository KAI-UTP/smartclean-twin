"""Integration tests: Command API endpoints (no MQTT required — mock MQTT)."""

import importlib
import importlib.util
import os
import sys
import threading
import time

import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

_ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
_CMD_MAIN_PATH = os.path.join(_ROOT, "services", "command-api", "main.py")
_SHARED_PATH = os.path.abspath(os.path.join(_ROOT, "shared"))

if _SHARED_PATH not in sys.path:
    sys.path.insert(0, _SHARED_PATH)


def _load_cmd_main():
    """Load command-api/main.py from explicit path, bypassing sys.path ordering."""
    with patch("paho.mqtt.client.Client") as mock_mqtt_cls, patch("influxdb_client.InfluxDBClient"):
        mock_mqtt = MagicMock()
        mock_mqtt.is_connected.return_value = True
        mock_mqtt_cls.return_value = mock_mqtt

        sys.modules.pop("main", None)
        spec = importlib.util.spec_from_file_location("main", _CMD_MAIN_PATH)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["main"] = mod
        spec.loader.exec_module(mod)

        mod._mqtt_client = mock_mqtt
        return mod, mock_mqtt


@pytest.fixture
def client():
    cmd_main, mock_mqtt = _load_cmd_main()
    with TestClient(cmd_main.app) as tc:
        tc._cmd_main = cmd_main
        yield tc


class TestHealthEndpoint:
    def test_health_returns_200(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert "status" in data
        assert "uptime_s" in data

    def test_health_has_commands_issued(self, client):
        r = client.get("/health")
        assert "commands_issued" in r.json()


class TestListCommands:
    def test_empty_list_initially(self, client):
        r = client.get("/api/v1/commands")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


class TestIssueCommand:
    def test_unknown_robot_id_returns_404(self, client):
        r = client.post("/api/v1/commands", json={"robot_id": "UNKNOWN", "command": "STOP"})
        assert r.status_code == 404

    def test_invalid_command_returns_422(self, client):
        r = client.post("/api/v1/commands", json={"robot_id": "SCR01", "command": "FLY"})
        assert r.status_code == 422

    def test_valid_command_publishes_to_mqtt(self, client):
        cmd_main = client._cmd_main
        mock_mqtt = cmd_main._mqtt_client

        def _fake_ack():
            time.sleep(0.05)
            for cmd_id, event in list(cmd_main._pending_acks.items()):
                cmd_main._ack_results[cmd_id] = {
                    "robot_id": "SCR01",
                    "command_id": cmd_id,
                    "command": "PAUSE",
                    "accepted": True,
                    "timestamp": "2026-07-15T10:30:16+00:00",
                }
                event.set()

        t = threading.Thread(target=_fake_ack, daemon=True)
        t.start()
        r = client.post("/api/v1/commands", json={"robot_id": "SCR01", "command": "PAUSE"})
        assert r.status_code == 200
        data = r.json()
        assert data["command"] == "PAUSE"
        assert data["robot_id"] == "SCR01"
        assert "command_id" in data
        assert mock_mqtt.publish.called

    def test_command_timeout_when_no_ack(self, client):
        cmd_main = client._cmd_main
        original = cmd_main.ACK_TIMEOUT_S
        cmd_main.ACK_TIMEOUT_S = 0.1
        try:
            r = client.post("/api/v1/commands", json={"robot_id": "SCR01", "command": "START"})
            assert r.status_code == 200
            data = r.json()
            assert data["status"] == "timeout"
            assert data["ack_received"] is False
        finally:
            cmd_main.ACK_TIMEOUT_S = original
