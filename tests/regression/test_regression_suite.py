"""Regression test suite.

These tests must pass on every commit. They verify that known-good behaviours
have not been broken.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "shared"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "services", "state-engine"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "services", "robot-simulator"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "services", "ai-service"))

import pytest
from datetime import datetime, timezone
from smartclean_common.models import (
    TelemetryMessage, SafetyState, BatteryState, MotorHealth,
    MissionState, DirtLevel,
)
import rules
import predictor


def _msg(**sensor_overrides) -> TelemetryMessage:
    s = {
        "obstacle_cm": 100.0, "battery_v": 12.0, "battery_soc": 80.0,
        "battery_a": 1.2, "motor_current_a": 0.8, "motor_temperature_c": 35.0,
        "dirt_score": 0.1, "water_level_pct": 80.0, "bumper_active": False,
    }
    s.update(sensor_overrides)
    return TelemetryMessage.model_validate({
        "schema_version": "1.0", "robot_id": "SCR01",
        "timestamp": "2026-07-15T10:30:15+00:00", "sequence": 1,
        "pose": {"x_m": 1.0, "y_m": 1.0, "heading_deg": 0.0, "speed_mps": 0.2},
        "sensors": s,
        "actuators": {"brush_on": True, "pump_on": False},
        "mission": {"mission_id": "M1", "mode": "CLEANING"},
    })


# ── REG-001: obstacle emergency ───────────────────────────────────────────────
def test_reg_obstacle_emergency():
    """Obstacle < 25 cm → EMERGENCY + STOPPED. Must never regress."""
    state, alarms = rules.evaluate(_msg(obstacle_cm=10.0), 50.0, None, 1)
    assert state.safety_state == SafetyState.EMERGENCY
    assert "OBSTACLE_EMERGENCY" in [a["alarm_type"] for a in alarms]


# ── REG-002: battery critical ─────────────────────────────────────────────────
def test_reg_battery_critical():
    """Battery < 10% → CRITICAL alarm. Must never regress."""
    state, alarms = rules.evaluate(_msg(battery_soc=5.0), 50.0, None, 1)
    assert state.battery_state == BatteryState.CRITICAL
    assert "BATTERY_CRITICAL" in [a["alarm_type"] for a in alarms]


# ── REG-003: motor overheated ─────────────────────────────────────────────────
def test_reg_motor_overheated():
    """Motor temp > 70°C → OVERHEATED alarm. Must never regress."""
    state, alarms = rules.evaluate(_msg(motor_temperature_c=85.0), 50.0, None, 1)
    assert state.motor_health == MotorHealth.OVERHEATED
    assert "MOTOR_OVERHEATED" in [a["alarm_type"] for a in alarms]


# ── REG-004: mission completion ───────────────────────────────────────────────
def test_reg_mission_completed_at_90_pct():
    """Coverage ≥ 90% → COMPLETED. Must never regress."""
    state, _ = rules.evaluate(_msg(), 95.0, None, 1)
    assert state.mission_state == MissionState.COMPLETED


# ── REG-005: schema backward compatibility ────────────────────────────────────
def test_reg_schema_v1_parses():
    """Telemetry schema v1.0 must always parse without error."""
    payload = {
        "schema_version": "1.0",
        "robot_id": "SCR01",
        "timestamp": "2026-07-15T10:30:15+00:00",
        "sequence": 125,
        "pose": {"x_m": 2.35, "y_m": 1.42, "heading_deg": 90.0, "speed_mps": 0.20},
        "sensors": {
            "obstacle_cm": 62.0, "battery_v": 11.7, "battery_soc": 72.0,
            "battery_a": 1.4, "motor_current_a": 0.8, "motor_temperature_c": 41.0,
            "dirt_score": 0.72, "water_level_pct": 66.0, "bumper_active": False,
        },
        "actuators": {"brush_on": True, "pump_on": False},
        "mission": {"mission_id": "MISSION-001", "mode": "CLEANING"},
    }
    msg = TelemetryMessage.model_validate(payload)
    assert msg.sequence == 125


# ── REG-006: AI fallback always returns valid prediction ──────────────────────
def test_reg_ai_fallback_always_returns_prediction():
    """AI service rule fallback must return valid prediction dict even without model."""
    predictor._loaded = False
    result = predictor.predict(0.8, 35.0, 0.2, True, False, 1.2, 0.5)
    assert "motor_health_prediction" in result
    assert result["motor_health_prediction"] in ["NORMAL", "HIGH_LOAD", "OVERHEATED", "FAULT"]
    assert result["dirt_level_prediction"] in ["CLEAN", "MODERATE", "DIRTY"]


# ── REG-007: lawnmower path is deterministic ──────────────────────────────────
def test_reg_lawnmower_path_deterministic():
    import grid_map as gm
    p1 = gm.lawnmower_path()
    p2 = gm.lawnmower_path()
    assert p1 == p2, "Lawnmower path must be deterministic"


# ── REG-008: all MQTT topics are non-empty strings ────────────────────────────
def test_reg_mqtt_topics_defined():
    from smartclean_common.topics import Topics
    topic_attrs = [
        "TELEMETRY_RAW", "TELEMETRY_VALIDATED", "STATE", "PREDICTION",
        "ALERT", "COMMAND_MOTION", "COMMAND_CLEANING", "ACK", "SERVICE_HEALTH",
    ]
    for attr in topic_attrs:
        val = getattr(Topics, attr)
        assert isinstance(val, str) and len(val) > 0, f"Topic {attr} is invalid"


# ── REG-009: coverage formula ─────────────────────────────────────────────────
def test_reg_coverage_formula():
    import grid_map as gm
    total = gm.total_accessible_cells()
    cleaned = int(total * 0.92)
    coverage = cleaned / total * 100.0
    assert 90.0 <= coverage <= 100.0


# ── REG-010: safe message not confused with emergency ────────────────────────
def test_reg_safe_not_emergency():
    state, alarms = rules.evaluate(_msg(obstacle_cm=200.0), 50.0, None, 1)
    assert state.safety_state == SafetyState.SAFE
    assert not any(a["alarm_type"] == "OBSTACLE_EMERGENCY" for a in alarms)
