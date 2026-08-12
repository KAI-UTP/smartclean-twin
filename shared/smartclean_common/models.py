"""Pydantic data models — single source of truth for all message schemas."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator

# ── Enumerations ──────────────────────────────────────────────────────────────


class MotionState(str, Enum):
    STOPPED = "STOPPED"
    MOVING = "MOVING"
    TURNING = "TURNING"
    AVOIDING = "AVOIDING"


class OperationMode(str, Enum):
    IDLE = "IDLE"
    INSPECTING = "INSPECTING"
    CLEANING = "CLEANING"
    RETURNING = "RETURNING"
    CHARGING = "CHARGING"
    REFILLING = "REFILLING"
    # Operator teleoperation: autonomous path following is suspended.
    MANUAL = "MANUAL"


class SafetyState(str, Enum):
    SAFE = "SAFE"
    WARNING = "WARNING"
    EMERGENCY = "EMERGENCY"


class BatteryState(str, Enum):
    NORMAL = "NORMAL"
    LOW = "LOW"
    CRITICAL = "CRITICAL"
    CHARGING = "CHARGING"


class CleaningState(str, Enum):
    OFF = "OFF"
    ACTIVE = "ACTIVE"
    REPEAT_REQUIRED = "REPEAT_REQUIRED"


class MotorHealth(str, Enum):
    NORMAL = "NORMAL"
    HIGH_LOAD = "HIGH_LOAD"
    OVERHEATED = "OVERHEATED"
    FAULT = "FAULT"


class DirtLevel(str, Enum):
    CLEAN = "CLEAN"
    MODERATE = "MODERATE"
    DIRTY = "DIRTY"


class MissionState(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ConnectionState(str, Enum):
    ONLINE = "ONLINE"
    DELAYED = "DELAYED"
    OFFLINE = "OFFLINE"


class TwinQuality(str, Enum):
    SYNCHRONIZED = "SYNCHRONIZED"
    DELAYED = "DELAYED"
    INVALID = "INVALID"


class RobotCommand(str, Enum):
    START = "START"
    PAUSE = "PAUSE"
    RESUME = "RESUME"
    STOP = "STOP"
    RETURN_HOME = "RETURN_HOME"
    BRUSH_ON = "BRUSH_ON"
    BRUSH_OFF = "BRUSH_OFF"
    PUMP_ON = "PUMP_ON"
    PUMP_OFF = "PUMP_OFF"
    # Manual teleoperation: the operator takes direct control of the robot.
    # MANUAL_MODE suspends autonomous path following; MOVE_* steps the robot
    # one grid cell in the named direction; AUTO_MODE hands control back.
    MANUAL_MODE = "MANUAL_MODE"
    AUTO_MODE = "AUTO_MODE"
    MOVE_UP = "MOVE_UP"
    MOVE_DOWN = "MOVE_DOWN"
    MOVE_LEFT = "MOVE_LEFT"
    MOVE_RIGHT = "MOVE_RIGHT"


# ── Telemetry sub-models ──────────────────────────────────────────────────────


class PoseData(BaseModel):
    x_m: float = Field(..., ge=0.0, le=100.0)
    y_m: float = Field(..., ge=0.0, le=100.0)
    heading_deg: float = Field(..., ge=0.0, lt=360.0)
    speed_mps: float = Field(..., ge=0.0, le=2.0)


class SensorData(BaseModel):
    obstacle_cm: float = Field(..., ge=0.0, le=500.0)
    battery_v: float = Field(..., ge=0.0, le=15.0)
    battery_soc: float = Field(..., ge=0.0, le=100.0)
    battery_a: float = Field(..., ge=0.0, le=10.0)
    motor_current_a: float = Field(..., ge=0.0, le=10.0)
    motor_temperature_c: float = Field(..., ge=-10.0, le=120.0)
    dirt_score: float = Field(..., ge=0.0, le=1.0)
    water_level_pct: float = Field(default=100.0, ge=0.0, le=100.0)
    bumper_active: bool = Field(default=False)


class ActuatorData(BaseModel):
    brush_on: bool
    pump_on: bool


class MissionData(BaseModel):
    mission_id: str
    mode: str


# ── Telemetry message ─────────────────────────────────────────────────────────


class TelemetryMessage(BaseModel):
    schema_version: str = Field(default="1.0")
    robot_id: str
    timestamp: str  # ISO 8601
    sequence: int = Field(..., ge=0)
    pose: PoseData
    sensors: SensorData
    actuators: ActuatorData
    mission: MissionData

    @field_validator("robot_id")
    @classmethod
    def validate_robot_id(cls, v: str) -> str:
        if not v or len(v) > 20:
            raise ValueError("robot_id must be 1-20 characters")
        return v

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, v: str) -> str:
        try:
            datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError(f"Invalid ISO 8601 timestamp: {v}")
        return v


# ── Digital Twin state message ────────────────────────────────────────────────


class DigitalTwinState(BaseModel):
    robot_id: str
    timestamp: str
    sequence: int
    motion_state: MotionState
    operation_mode: OperationMode
    safety_state: SafetyState
    battery_state: BatteryState
    cleaning_state: CleaningState
    motor_health: MotorHealth
    dirt_level: DirtLevel
    mission_state: MissionState
    connection_state: ConnectionState
    twin_quality: TwinQuality
    cleaning_coverage_pct: float = Field(..., ge=0.0, le=100.0)
    active_alarms: list[str] = Field(default_factory=list)


# ── AI prediction message ─────────────────────────────────────────────────────


class PredictionMessage(BaseModel):
    robot_id: str
    timestamp: str
    model_version: str = "1.0"
    motor_health_prediction: MotorHealth
    motor_health_confidence: float = Field(..., ge=0.0, le=1.0)
    dirt_level_prediction: DirtLevel
    dirt_level_confidence: float = Field(..., ge=0.0, le=1.0)
    # Health-state classification + RUL regression
    health_state_prediction: Optional[str] = None
    health_state_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    predicted_rul_minutes: Optional[float] = Field(default=None, ge=0.0)
    # Unsupervised anomaly detection
    anomaly_score: Optional[float] = None
    is_anomaly: Optional[bool] = None
    # Trend-based operational forecasts
    minutes_to_empty: Optional[float] = Field(default=None, ge=0.0)
    minutes_to_finish: Optional[float] = Field(default=None, ge=0.0)
    # Operator guidance
    recommendation: Optional[str] = None


# ── Alert message ─────────────────────────────────────────────────────────────


class AlertMessage(BaseModel):
    robot_id: str
    timestamp: str
    alarm_id: str
    alarm_type: str
    severity: str  # INFO | WARNING | CRITICAL
    description: str
    value: Optional[float] = None
    threshold: Optional[float] = None


# ── Command messages ──────────────────────────────────────────────────────────


class CommandRequest(BaseModel):
    robot_id: str
    command: RobotCommand


class CommandMessage(BaseModel):
    command_id: str
    robot_id: str
    command: RobotCommand
    timestamp: str
    issued_by: str = "command-api"


class AckMessage(BaseModel):
    robot_id: str
    command_id: str
    command: str
    accepted: bool
    timestamp: str
    reason: Optional[str] = None


# ── Service health ────────────────────────────────────────────────────────────


class ServiceHealth(BaseModel):
    service: str
    status: str  # healthy | degraded | unhealthy
    timestamp: str
    uptime_s: float
    details: dict = Field(default_factory=dict)
