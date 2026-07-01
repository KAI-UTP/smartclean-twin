"""Unit tests: Digital Twin state engine rules.

Tests are independent of MQTT/InfluxDB — pure logic tests.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "services", "state-engine"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "shared"))

import pytest
from datetime import datetime, timezone
from smartclean_common.models import (
    SafetyState, MotionState, BatteryState, MotorHealth,
    MissionState, DirtLevel, CleaningState,
)
import rules


def _make_telemetry(**sensor_overrides) -> dict:
    """Build a minimal valid telemetry dict."""
    sensors = {
        "obstacle_cm": 100.0,
        "battery_v": 12.0,
        "battery_soc": 80.0,
        "battery_a": 1.2,
        "motor_current_a": 0.8,
        "motor_temperature_c": 35.0,
        "dirt_score": 0.1,
        "water_level_pct": 80.0,
        "bumper_active": False,
    }
    sensors.update(sensor_overrides)
    from smartclean_common.models import TelemetryMessage
    return TelemetryMessage.model_validate({
        "schema_version": "1.0",
        "robot_id": "SCR01",
        "timestamp": "2026-07-15T10:30:15+00:00",
        "sequence": 1,
        "pose": {"x_m": 1.0, "y_m": 1.0, "heading_deg": 0.0, "speed_mps": 0.2},
        "sensors": sensors,
        "actuators": {"brush_on": True, "pump_on": False},
        "mission": {"mission_id": "MISSION-001", "mode": "CLEANING"},
    })


class TestSafetyRules:
    def test_obstacle_under_25_is_emergency(self):
        msg = _make_telemetry(obstacle_cm=20.0)
        state, alarms = rules.evaluate(msg, 50.0, None, 1)
        assert state.safety_state == SafetyState.EMERGENCY
        assert state.motion_state == MotionState.STOPPED
        assert any(a["alarm_type"] == rules.ALARM_OBSTACLE_EMERGENCY for a in alarms)

    def test_obstacle_between_25_and_50_is_warning(self):
        msg = _make_telemetry(obstacle_cm=35.0)
        state, alarms = rules.evaluate(msg, 50.0, None, 1)
        assert state.safety_state == SafetyState.WARNING
        assert state.motion_state == MotionState.AVOIDING

    def test_obstacle_over_50_is_safe(self):
        msg = _make_telemetry(obstacle_cm=100.0)
        state, _ = rules.evaluate(msg, 50.0, None, 1)
        assert state.safety_state == SafetyState.SAFE

    def test_bumper_active_triggers_emergency(self):
        msg = _make_telemetry(obstacle_cm=200.0, bumper_active=True)
        state, alarms = rules.evaluate(msg, 50.0, None, 1)
        assert state.safety_state == SafetyState.EMERGENCY

    def test_obstacle_exactly_25_is_warning(self):
        msg = _make_telemetry(obstacle_cm=25.0)
        state, _ = rules.evaluate(msg, 50.0, None, 1)
        assert state.safety_state == SafetyState.WARNING

    def test_obstacle_exactly_50_is_safe(self):
        msg = _make_telemetry(obstacle_cm=50.0)
        state, _ = rules.evaluate(msg, 50.0, None, 1)
        assert state.safety_state == SafetyState.SAFE


class TestBatteryRules:
    def test_battery_under_10_is_critical(self):
        msg = _make_telemetry(battery_soc=8.0)
        state, alarms = rules.evaluate(msg, 50.0, None, 1)
        assert state.battery_state == BatteryState.CRITICAL
        assert any(a["alarm_type"] == rules.ALARM_BATTERY_CRITICAL for a in alarms)

    def test_battery_under_20_is_low(self):
        msg = _make_telemetry(battery_soc=15.0)
        state, _ = rules.evaluate(msg, 50.0, None, 1)
        assert state.battery_state == BatteryState.LOW

    def test_battery_over_20_is_normal(self):
        msg = _make_telemetry(battery_soc=80.0)
        state, _ = rules.evaluate(msg, 50.0, None, 1)
        assert state.battery_state == BatteryState.NORMAL


class TestMotorRules:
    def test_motor_current_over_25_is_high_load(self):
        msg = _make_telemetry(motor_current_a=3.0)
        state, alarms = rules.evaluate(msg, 50.0, None, 1)
        assert state.motor_health == MotorHealth.HIGH_LOAD
        assert any(a["alarm_type"] == rules.ALARM_MOTOR_HIGH_LOAD for a in alarms)

    def test_motor_temp_over_70_is_overheated(self):
        msg = _make_telemetry(motor_temperature_c=75.0)
        state, alarms = rules.evaluate(msg, 50.0, None, 1)
        assert state.motor_health == MotorHealth.OVERHEATED
        assert any(a["alarm_type"] == rules.ALARM_MOTOR_OVERHEATED for a in alarms)

    def test_normal_motor(self):
        msg = _make_telemetry(motor_current_a=0.8, motor_temperature_c=35.0)
        state, _ = rules.evaluate(msg, 50.0, None, 1)
        assert state.motor_health == MotorHealth.NORMAL


class TestDirtRules:
    def test_dirt_score_07_is_dirty(self):
        msg = _make_telemetry(dirt_score=0.75)
        state, _ = rules.evaluate(msg, 50.0, None, 1)
        assert state.dirt_level == DirtLevel.DIRTY

    def test_dirt_score_05_is_moderate(self):
        msg = _make_telemetry(dirt_score=0.5)
        state, _ = rules.evaluate(msg, 50.0, None, 1)
        assert state.dirt_level == DirtLevel.MODERATE

    def test_dirt_score_01_is_clean(self):
        msg = _make_telemetry(dirt_score=0.1)
        state, _ = rules.evaluate(msg, 50.0, None, 1)
        assert state.dirt_level == DirtLevel.CLEAN


class TestCoverageAndMission:
    def test_coverage_90_completes_mission(self):
        msg = _make_telemetry()
        state, _ = rules.evaluate(msg, 92.0, None, 1)
        assert state.mission_state == MissionState.COMPLETED
        assert state.cleaning_coverage_pct == 92.0

    def test_coverage_50_is_running(self):
        msg = _make_telemetry()
        state, _ = rules.evaluate(msg, 50.0, None, 1)
        assert state.mission_state == MissionState.RUNNING

    def test_zero_coverage_not_started(self):
        from smartclean_common.models import TelemetryMessage
        msg = TelemetryMessage.model_validate({
            "schema_version": "1.0",
            "robot_id": "SCR01",
            "timestamp": "2026-07-15T10:30:15+00:00",
            "sequence": 1,
            "pose": {"x_m": 0.5, "y_m": 0.5, "heading_deg": 0.0, "speed_mps": 0.0},
            "sensors": {
                "obstacle_cm": 100.0, "battery_v": 12.0, "battery_soc": 100.0,
                "battery_a": 0.5, "motor_current_a": 0.3, "motor_temperature_c": 25.0,
                "dirt_score": 0.0, "water_level_pct": 100.0, "bumper_active": False,
            },
            "actuators": {"brush_on": False, "pump_on": False},
            "mission": {"mission_id": "MISSION-001", "mode": "IDLE"},
        })
        state, _ = rules.evaluate(msg, 0.0, None, 1)
        assert state.mission_state == MissionState.NOT_STARTED


class TestConnectionState:
    def test_no_delay_is_synchronized(self):
        msg = _make_telemetry()
        state, _ = rules.evaluate(msg, 50.0, None, 1)
        from smartclean_common.models import ConnectionState, TwinQuality
        assert state.connection_state == ConnectionState.ONLINE
        assert state.twin_quality == TwinQuality.SYNCHRONIZED

    def test_delayed_message(self):
        from datetime import timedelta
        old_time = datetime.now(timezone.utc) - timedelta(seconds=5)
        msg = _make_telemetry()
        state, _ = rules.evaluate(msg, 50.0, old_time, 1)
        from smartclean_common.models import ConnectionState, TwinQuality
        assert state.connection_state == ConnectionState.DELAYED
        assert state.twin_quality == TwinQuality.DELAYED
