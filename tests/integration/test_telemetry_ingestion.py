"""Integration tests: Telemetry ingestion validation pipeline."""

import importlib
import importlib.util
import json
import os
import sys

import pytest
from unittest.mock import MagicMock, patch

_ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
_ING_MAIN_PATH = os.path.join(_ROOT, "services", "telemetry-ingestion", "main.py")
_SHARED_PATH = os.path.abspath(os.path.join(_ROOT, "shared"))

if _SHARED_PATH not in sys.path:
    sys.path.insert(0, _SHARED_PATH)


def _load_ing_main():
    """Load telemetry-ingestion/main.py from explicit path."""
    with patch("paho.mqtt.client.Client"), \
         patch("influxdb_client.InfluxDBClient"), \
         patch("influxdb_client.WriteOptions"):
        sys.modules.pop("main", None)
        spec = importlib.util.spec_from_file_location("main", _ING_MAIN_PATH)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["main"] = mod
        spec.loader.exec_module(mod)
        return mod


def _make_valid_payload() -> dict:
    return {
        "schema_version": "1.0",
        "robot_id": "SCR01",
        "timestamp": "2026-07-15T10:30:15+00:00",
        "sequence": 5,
        "pose": {"x_m": 2.0, "y_m": 1.0, "heading_deg": 0.0, "speed_mps": 0.2},
        "sensors": {
            "obstacle_cm": 80.0, "battery_v": 12.0, "battery_soc": 90.0,
            "battery_a": 1.0, "motor_current_a": 0.8, "motor_temperature_c": 35.0,
            "dirt_score": 0.3, "water_level_pct": 80.0, "bumper_active": False,
        },
        "actuators": {"brush_on": True, "pump_on": False},
        "mission": {"mission_id": "M1", "mode": "CLEANING"},
    }


class TestIngestionMessageHandling:
    """Tests the _on_message callback in isolation from MQTT."""

    def test_valid_payload_increments_valid(self):
        ing_main = _load_ing_main()
        ing_main._stats["received"] = 0
        ing_main._stats["valid"] = 0
        ing_main._stats["invalid"] = 0

        mock_client = MagicMock()
        mock_msg = MagicMock()
        mock_msg.payload = json.dumps(_make_valid_payload()).encode()

        with patch.object(ing_main, "_write_telemetry_to_influx"), \
             patch.object(ing_main, "_write_invalid_to_influx"):
            ing_main._on_message(mock_client, None, mock_msg)

        assert ing_main._stats["valid"] == 1
        assert ing_main._stats["invalid"] == 0
        mock_client.publish.assert_called_once()

    def test_invalid_json_increments_invalid(self):
        ing_main = _load_ing_main()
        ing_main._stats["received"] = 0
        ing_main._stats["valid"] = 0
        ing_main._stats["invalid"] = 0

        mock_client = MagicMock()
        mock_msg = MagicMock()
        mock_msg.payload = b"not valid json{"

        with patch.object(ing_main, "_write_invalid_to_influx"):
            ing_main._on_message(mock_client, None, mock_msg)

        assert ing_main._stats["invalid"] == 1
        mock_client.publish.assert_not_called()

    def test_missing_required_field_increments_invalid(self):
        ing_main = _load_ing_main()
        ing_main._stats["received"] = 0
        ing_main._stats["valid"] = 0
        ing_main._stats["invalid"] = 0

        payload = _make_valid_payload()
        del payload["pose"]

        mock_client = MagicMock()
        mock_msg = MagicMock()
        mock_msg.payload = json.dumps(payload).encode()

        with patch.object(ing_main, "_write_invalid_to_influx"):
            ing_main._on_message(mock_client, None, mock_msg)

        assert ing_main._stats["invalid"] == 1

    def test_health_endpoint_reflects_stats(self):
        from fastapi.testclient import TestClient
        ing_main = _load_ing_main()
        with TestClient(ing_main.app) as tc:
            r = tc.get("/health")
            assert r.status_code == 200
            data = r.json()
            assert "received" in data
            assert "valid" in data
            assert "invalid" in data
