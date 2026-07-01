"""Mutable robot state — updated by simulator loop and command handler."""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RobotPhysicsState:
    # Pose
    row: int = 1
    col: int = 1
    heading_deg: float = 0.0
    speed_mps: float = 0.0

    # Battery
    battery_v: float = 12.6
    battery_soc: float = 100.0
    battery_a: float = 0.5

    # Motor
    motor_current_a: float = 0.5
    motor_temperature_c: float = 25.0

    # Sensors
    obstacle_cm: float = 200.0
    bumper_active: bool = False
    dirt_score: float = 0.0
    water_level_pct: float = 100.0

    # Actuators
    brush_on: bool = True
    pump_on: bool = False

    # Mission
    mission_id: str = "MISSION-001"
    mode: str = "CLEANING"
    paused: bool = False
    stopped: bool = False
    returning_home: bool = False

    # Internal
    sequence: int = 0
    path_index: int = 0
    ticks_in_cell: int = 0  # counts ticks spent cleaning current cell

    # Fault injection flags
    inject_obstacle: bool = False
    inject_motor_overload: bool = False
    inject_low_battery: bool = False

    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def lock(self) -> threading.Lock:
        return self._lock

    @property
    def x_m(self) -> float:
        from grid_map import CELL_SIZE_M
        return self.col * CELL_SIZE_M

    @property
    def y_m(self) -> float:
        from grid_map import CELL_SIZE_M
        return self.row * CELL_SIZE_M
