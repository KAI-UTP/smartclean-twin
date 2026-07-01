"""Unit tests: telemetry schema validation."""

import pytest
from pydantic import ValidationError
from smartclean_common.models import TelemetryMessage


def _valid_payload(**overrides) -> dict:
    base = {
        "schema_version": "1.0",
        "robot_id": "SCR01",
        "timestamp": "2026-07-15T10:30:15.250+00:00",
        "sequence": 1,
        "pose": {"x_m": 2.5, "y_m": 1.5, "heading_deg": 90.0, "speed_mps": 0.2},
        "sensors": {
            "obstacle_cm": 62.0,
            "battery_v": 11.7,
            "battery_soc": 72.0,
            "battery_a": 1.4,
            "motor_current_a": 0.8,
            "motor_temperature_c": 41.0,
            "dirt_score": 0.72,
            "water_level_pct": 66.0,
            "bumper_active": False,
        },
        "actuators": {"brush_on": True, "pump_on": False},
        "mission": {"mission_id": "MISSION-001", "mode": "CLEANING"},
    }
    base.update(overrides)
    return base


class TestValidTelemetry:
    def test_valid_message_parses(self):
        msg = TelemetryMessage.model_validate(_valid_payload())
        assert msg.robot_id == "SCR01"
        assert msg.sequence == 1
        assert msg.sensors.battery_soc == 72.0

    def test_valid_boundary_heading_359(self):
        data = _valid_payload()
        data["pose"]["heading_deg"] = 359.9
        msg = TelemetryMessage.model_validate(data)
        assert msg.pose.heading_deg == 359.9

    def test_valid_zero_obstacle(self):
        data = _valid_payload()
        data["sensors"]["obstacle_cm"] = 0.0
        msg = TelemetryMessage.model_validate(data)
        assert msg.sensors.obstacle_cm == 0.0

    def test_valid_brush_off(self):
        data = _valid_payload()
        data["actuators"]["brush_on"] = False
        msg = TelemetryMessage.model_validate(data)
        assert msg.actuators.brush_on is False


class TestMissingFields:
    def test_missing_robot_id(self):
        data = _valid_payload()
        del data["robot_id"]
        with pytest.raises(ValidationError):
            TelemetryMessage.model_validate(data)

    def test_missing_timestamp(self):
        data = _valid_payload()
        del data["timestamp"]
        with pytest.raises(ValidationError):
            TelemetryMessage.model_validate(data)

    def test_missing_pose(self):
        data = _valid_payload()
        del data["pose"]
        with pytest.raises(ValidationError):
            TelemetryMessage.model_validate(data)

    def test_missing_battery_soc(self):
        data = _valid_payload()
        del data["sensors"]["battery_soc"]
        with pytest.raises(ValidationError):
            TelemetryMessage.model_validate(data)

    def test_missing_brush_on(self):
        data = _valid_payload()
        del data["actuators"]["brush_on"]
        with pytest.raises(ValidationError):
            TelemetryMessage.model_validate(data)


class TestInvalidRanges:
    def test_battery_soc_over_100(self):
        data = _valid_payload()
        data["sensors"]["battery_soc"] = 101.0
        with pytest.raises(ValidationError):
            TelemetryMessage.model_validate(data)

    def test_negative_battery_soc(self):
        data = _valid_payload()
        data["sensors"]["battery_soc"] = -1.0
        with pytest.raises(ValidationError):
            TelemetryMessage.model_validate(data)

    def test_heading_360_or_more(self):
        data = _valid_payload()
        data["pose"]["heading_deg"] = 360.0
        with pytest.raises(ValidationError):
            TelemetryMessage.model_validate(data)

    def test_speed_over_max(self):
        data = _valid_payload()
        data["pose"]["speed_mps"] = 3.0
        with pytest.raises(ValidationError):
            TelemetryMessage.model_validate(data)

    def test_dirt_score_over_1(self):
        data = _valid_payload()
        data["sensors"]["dirt_score"] = 1.1
        with pytest.raises(ValidationError):
            TelemetryMessage.model_validate(data)


class TestInvalidTypes:
    def test_sequence_as_string(self):
        data = _valid_payload()
        data["sequence"] = "not_an_int"
        with pytest.raises(ValidationError):
            TelemetryMessage.model_validate(data)

    def test_brush_on_as_string(self):
        data = _valid_payload()
        data["actuators"]["brush_on"] = "yes"
        # Pydantic coerces "yes" → True, which is valid — test that False-like strings fail
        data["actuators"]["brush_on"] = "invalid_bool_string_xyz"
        with pytest.raises(ValidationError):
            TelemetryMessage.model_validate(data)

    def test_invalid_timestamp_format(self):
        data = _valid_payload()
        data["timestamp"] = "not-a-date"
        with pytest.raises(ValidationError):
            TelemetryMessage.model_validate(data)
