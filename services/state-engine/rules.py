"""Digital Twin state-rule engine.

All rules documented here map directly to the proposal Section 13 and the
behaviour table in the project prompt. No rule is fabricated.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone

sys.path.insert(0, "/app/shared")

from smartclean_common.models import (
    BatteryState,
    CleaningState,
    ConnectionState,
    DigitalTwinState,
    DirtLevel,
    MotionState,
    MotorHealth,
    MissionState,
    OperationMode,
    SafetyState,
    TelemetryMessage,
    TwinQuality,
)

# Alarm type constants
ALARM_OBSTACLE_EMERGENCY = "OBSTACLE_EMERGENCY"
ALARM_BATTERY_CRITICAL = "BATTERY_CRITICAL"
ALARM_MOTOR_HIGH_LOAD = "MOTOR_HIGH_LOAD"
ALARM_MOTOR_OVERHEATED = "MOTOR_OVERHEATED"
ALARM_LOW_WATER = "LOW_WATER"


def evaluate(
    msg: TelemetryMessage,
    cleaning_coverage_pct: float,
    last_msg_time: datetime | None,
    sequence: int,
) -> tuple[DigitalTwinState, list[dict]]:
    """Apply all state rules and return (state, alarms).

    Args:
        msg: validated telemetry message
        cleaning_coverage_pct: coverage from state engine memory
        last_msg_time: time last message was received (for delay detection)
        sequence: monotonic DT sequence number
    """
    now = datetime.now(timezone.utc)
    alarms: list[dict] = []

    s = msg.sensors
    a = msg.actuators
    p = msg.pose

    # ── Safety state ──────────────────────────────────────────────────────────
    if s.obstacle_cm < 25.0 or s.bumper_active:
        safety_state = SafetyState.EMERGENCY
        motion_state = MotionState.STOPPED
        alarms.append(
            _alarm(
                msg.robot_id,
                ALARM_OBSTACLE_EMERGENCY,
                "CRITICAL",
                f"Obstacle at {s.obstacle_cm:.1f} cm",
                s.obstacle_cm,
                25.0,
            )
        )
    elif s.obstacle_cm < 50.0:
        safety_state = SafetyState.WARNING
        motion_state = MotionState.AVOIDING
    else:
        safety_state = SafetyState.SAFE
        if p.speed_mps == 0.0:
            motion_state = MotionState.STOPPED
        else:
            motion_state = MotionState.MOVING

    # ── Battery state ─────────────────────────────────────────────────────────
    if s.battery_soc < 10.0:
        battery_state = BatteryState.CRITICAL
        alarms.append(
            _alarm(
                msg.robot_id,
                ALARM_BATTERY_CRITICAL,
                "CRITICAL",
                f"Battery SOC {s.battery_soc:.1f}%",
                s.battery_soc,
                10.0,
            )
        )
    elif s.battery_soc < 20.0:
        battery_state = BatteryState.LOW
    else:
        battery_state = BatteryState.NORMAL

    # ── Motor health ──────────────────────────────────────────────────────────
    if s.motor_temperature_c > 70.0:
        motor_health = MotorHealth.OVERHEATED
        alarms.append(
            _alarm(
                msg.robot_id,
                ALARM_MOTOR_OVERHEATED,
                "CRITICAL",
                f"Motor temp {s.motor_temperature_c:.1f}°C",
                s.motor_temperature_c,
                70.0,
            )
        )
    elif s.motor_current_a > 2.5:
        motor_health = MotorHealth.HIGH_LOAD
        alarms.append(
            _alarm(
                msg.robot_id,
                ALARM_MOTOR_HIGH_LOAD,
                "WARNING",
                f"Motor current {s.motor_current_a:.2f} A",
                s.motor_current_a,
                2.5,
            )
        )
    else:
        motor_health = MotorHealth.NORMAL

    # ── Dirt level ────────────────────────────────────────────────────────────
    if s.dirt_score >= 0.7:
        dirt_level = DirtLevel.DIRTY
    elif s.dirt_score >= 0.3:
        dirt_level = DirtLevel.MODERATE
    else:
        dirt_level = DirtLevel.CLEAN

    # ── Cleaning state ────────────────────────────────────────────────────────
    if a.brush_on:
        cleaning_state = (
            CleaningState.ACTIVE if dirt_level != DirtLevel.CLEAN else CleaningState.ACTIVE
        )
        if dirt_level == DirtLevel.DIRTY and cleaning_coverage_pct > 0:
            cleaning_state = (
                CleaningState.REPEAT_REQUIRED if s.dirt_score > 0.8 else CleaningState.ACTIVE
            )
    else:
        cleaning_state = CleaningState.OFF

    # ── Operation mode ────────────────────────────────────────────────────────
    raw_mode = msg.mission.mode
    mode_map = {
        "IDLE": OperationMode.IDLE,
        "INSPECTING": OperationMode.INSPECTING,
        "CLEANING": OperationMode.CLEANING,
        "RETURNING": OperationMode.RETURNING,
        "CHARGING": OperationMode.CHARGING,
        "REFILLING": OperationMode.REFILLING,
        "MANUAL": OperationMode.MANUAL,
    }
    operation_mode = mode_map.get(raw_mode, OperationMode.IDLE)

    # ── Mission state ─────────────────────────────────────────────────────────
    critical_alarm_active = any(
        al["severity"] == "CRITICAL"
        for al in alarms
        if al["alarm_type"] not in [ALARM_OBSTACLE_EMERGENCY]
    )

    if operation_mode == OperationMode.IDLE and cleaning_coverage_pct == 0.0:
        mission_state = MissionState.NOT_STARTED
    elif battery_state == BatteryState.LOW or operation_mode == OperationMode.RETURNING:
        mission_state = MissionState.RUNNING  # robot returning but mission not complete
    elif cleaning_coverage_pct >= 90.0 and not critical_alarm_active:
        mission_state = MissionState.COMPLETED
    elif operation_mode == OperationMode.IDLE and cleaning_coverage_pct > 0:
        mission_state = MissionState.PAUSED
    else:
        mission_state = MissionState.RUNNING

    # ── Connection / twin quality ─────────────────────────────────────────────
    if last_msg_time is None:
        connection_state = ConnectionState.ONLINE
        twin_quality = TwinQuality.SYNCHRONIZED
    else:
        delay_s = (now - last_msg_time).total_seconds()
        if delay_s > 10.0:
            connection_state = ConnectionState.OFFLINE
            twin_quality = TwinQuality.INVALID
        elif delay_s > 2.0:
            connection_state = ConnectionState.DELAYED
            twin_quality = TwinQuality.DELAYED
        else:
            connection_state = ConnectionState.ONLINE
            twin_quality = TwinQuality.SYNCHRONIZED

    # ── Low water alarm ───────────────────────────────────────────────────────
    if s.water_level_pct < 10.0:
        alarms.append(
            _alarm(
                msg.robot_id,
                ALARM_LOW_WATER,
                "WARNING",
                f"Water level {s.water_level_pct:.1f}%",
                s.water_level_pct,
                10.0,
            )
        )

    state = DigitalTwinState(
        robot_id=msg.robot_id,
        timestamp=now.isoformat(),
        sequence=sequence,
        motion_state=motion_state,
        operation_mode=operation_mode,
        safety_state=safety_state,
        battery_state=battery_state,
        cleaning_state=cleaning_state,
        motor_health=motor_health,
        dirt_level=dirt_level,
        mission_state=mission_state,
        connection_state=connection_state,
        twin_quality=twin_quality,
        cleaning_coverage_pct=round(cleaning_coverage_pct, 2),
        active_alarms=[al["alarm_type"] for al in alarms],
    )
    return state, alarms


def _alarm(
    robot_id: str,
    alarm_type: str,
    severity: str,
    description: str,
    value: float | None = None,
    threshold: float | None = None,
) -> dict:
    return {
        "robot_id": robot_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "alarm_id": f"{alarm_type}-{int(datetime.now(timezone.utc).timestamp())}",
        "alarm_type": alarm_type,
        "severity": severity,
        "description": description,
        "value": value,
        "threshold": threshold,
    }
