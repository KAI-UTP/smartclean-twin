"""Robot Simulator — physics loop, telemetry publisher, command handler."""

from __future__ import annotations

import json
import logging
import math
import os
import sys
import time
import uuid
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

# Ensure shared package is on path when running inside container
sys.path.insert(0, "/app/shared")

from smartclean_common.topics import Topics

import grid_map as gm
from robot_state import RobotPhysicsState

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

ROBOT_ID = os.environ.get("ROBOT_ID", "SCR01")
TELEMETRY_INTERVAL = float(os.environ.get("TELEMETRY_INTERVAL_S", "1.0"))
SEED = int(os.environ.get("SIMULATOR_SEED", "42"))
MQTT_HOST = os.environ.get("MQTT_HOST", "mosquitto")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
TICKS_TO_CLEAN = 3  # ticks the robot must stay in a cell to clean it
CHARGE_THRESHOLD = 20.0  # % SoC, auto-return home below this
CHARGE_FULL = 80.0  # % SoC, resume cleaning above this
CHARGE_RATE = 10.0  # % per minute charge rate at the dock
# The robot cannot wet-clean without water, so an empty tank sends it home to
# refill in the same way a flat battery sends it home to charge.
WATER_THRESHOLD = 15.0  # % tank, auto-return home below this
WATER_FULL = 90.0  # % tank, resume cleaning above this
REFILL_RATE = 25.0  # % per minute refill rate at the dock

# Manual teleoperation steps, as (delta row, delta column, heading in degrees).
# Grid convention: x_m = col * CELL_SIZE_M, y_m = row * CELL_SIZE_M, and the
# heading matches the autonomous path, atan2(d_col, d_row) in degrees.
MANUAL_MOVES = {
    "MOVE_UP": (1, 0, 0.0),  # +row, north
    "MOVE_UP_RIGHT": (1, 1, 45.0),
    "MOVE_RIGHT": (0, 1, 90.0),  # +col, east
    "MOVE_DOWN_RIGHT": (-1, 1, 135.0),
    "MOVE_DOWN": (-1, 0, 180.0),  # -row, south
    "MOVE_DOWN_LEFT": (-1, -1, 225.0),
    "MOVE_LEFT": (0, -1, 270.0),  # -col, west
    "MOVE_UP_LEFT": (1, -1, 315.0),
}


class RobotSimulator:
    def __init__(self) -> None:
        self._state = RobotPhysicsState()
        self._dirt_map = gm.generate_dirt_map(SEED)
        self._path = gm.lawnmower_path()
        self._cleaned: set[tuple[int, int]] = set()
        self._start_time = time.monotonic()

        self._mqtt_client = mqtt.Client(client_id=f"simulator-{ROBOT_ID}")
        self._mqtt_client.on_connect = self._on_connect
        self._mqtt_client.on_message = self._on_command
        self._running = True

    # ── MQTT callbacks ────────────────────────────────────────────────────────

    def _on_connect(self, client: mqtt.Client, userdata, flags, rc: int) -> None:
        if rc == 0:
            logger.info("Simulator MQTT connected")
            client.subscribe(Topics.COMMAND_ALL)
            client.subscribe(Topics.COMMAND_MOTION)
            client.subscribe(Topics.COMMAND_CLEANING)
        else:
            logger.error("MQTT connect failed rc=%d", rc)

    def _on_command(self, client: mqtt.Client, userdata, msg: mqtt.MQTTMessage) -> None:
        try:
            payload = json.loads(msg.payload.decode())
            cmd = payload.get("command", "")
            cmd_id = payload.get("command_id", str(uuid.uuid4()))
            logger.info("Received command: %s (id=%s)", cmd, cmd_id)
            accepted = self._apply_command(cmd)
            self._publish_ack(cmd_id, cmd, accepted)
        except Exception as exc:
            logger.error("Command parse error: %s", exc)

    # ── Command handling ──────────────────────────────────────────────────────

    def _apply_command(self, command: str) -> bool:
        s = self._state
        with s.lock():
            if command == "START":
                s.paused = False
                s.stopped = False
                s.returning_home = False
                s.mode = "CLEANING"
            elif command == "PAUSE":
                s.paused = True
                s.speed_mps = 0.0
            elif command == "RESUME":
                s.paused = False
            elif command == "STOP":
                s.stopped = True
                s.paused = False
                s.speed_mps = 0.0
                s.mode = "IDLE"
            elif command == "RETURN_HOME":
                s.returning_home = True
                s.mode = "RETURNING"
            elif command == "BRUSH_ON":
                s.brush_on = True
            elif command == "BRUSH_OFF":
                s.brush_on = False
            elif command == "PUMP_ON":
                s.pump_on = True
            elif command == "PUMP_OFF":
                s.pump_on = False
            elif command == "MANUAL_MODE":
                # Operator takes over: stop following the cleaning path.
                s.manual_mode = True
                s.paused = False
                s.stopped = False
                s.returning_home = False
                s.mode = "MANUAL"
                s.speed_mps = 0.0
                logger.info("Manual control enabled by operator")
            elif command == "AUTO_MODE":
                # Hand control back. The stored path index still points at the
                # waypoint the robot was heading for before the operator took
                # over, which may now be far away, so resume from the waypoint
                # nearest to where the robot actually is. Without this the robot
                # beelines back across the room to rejoin its old position.
                s.manual_mode = False
                s.mode = "CLEANING"
                s.path_index = self._nearest_path_index(s.row, s.col)
                s.ticks_in_cell = 0
                logger.info(
                    "Autonomous control restored, resuming at path index %d for cell (%d,%d)",
                    s.path_index,
                    s.row,
                    s.col,
                )
            elif command in MANUAL_MOVES:
                if not s.manual_mode:
                    logger.warning("%s rejected: robot is not in manual mode", command)
                    return False
                return self._manual_step(s, command)
            else:
                logger.warning("Unknown command: %s", command)
                return False
        return True

    def _nearest_path_index(self, row: int, col: int) -> int:
        """Index of the cleaning waypoint closest to the given cell.

        Cells that have not been cleaned yet are preferred, so handing control
        back does not skip work that still needs doing. Distance is Manhattan
        because the robot moves on a grid.
        """
        best_index, best_key = 0, None
        for index, (p_row, p_col) in enumerate(self._path):
            distance = abs(p_row - row) + abs(p_col - col)
            already_cleaned = (p_row, p_col) in self._cleaned
            key = (already_cleaned, distance, index)
            if best_key is None or key < best_key:
                best_index, best_key = index, key
        return best_index

    def _manual_step(self, s: RobotPhysicsState, command: str) -> bool:
        """Move one grid cell under operator control.

        The move is refused if the target cell is a wall or a desk, so manual
        driving cannot put the robot somewhere the physical robot could not go.
        Must be called with the state lock already held.
        """
        d_row, d_col, heading = MANUAL_MOVES[command]
        new_row, new_col = s.row + d_row, s.col + d_col

        blocked = not gm.is_accessible(new_row, new_col)

        # A diagonal step must not cut a corner between two obstacles: both
        # orthogonal neighbours have to be clear as well, otherwise the robot
        # would squeeze through a gap its chassis could not fit.
        if not blocked and d_row != 0 and d_col != 0:
            if not gm.is_accessible(s.row + d_row, s.col) or not gm.is_accessible(
                s.row, s.col + d_col
            ):
                blocked = True

        if blocked:
            s.heading_deg = heading  # turn to face the obstruction, but do not move
            s.speed_mps = 0.0
            s.obstacle_cm = 20.0
            logger.info("Manual move %s blocked at (%d,%d)", command, new_row, new_col)
            return False

        s.row, s.col = new_row, new_col
        s.heading_deg = heading
        s.speed_mps = 0.2
        s.obstacle_cm = 200.0
        s.ticks_in_cell = 0

        # Manual driving still cleans, so coverage reflects what the robot did.
        if s.brush_on:
            cell = (s.row, s.col)
            if cell not in self._cleaned:
                self._cleaned.add(cell)
                self._dirt_map[s.row, s.col] = 0.0
        return True

    def _publish_ack(self, cmd_id: str, cmd: str, accepted: bool) -> None:
        ack = {
            "robot_id": ROBOT_ID,
            "command_id": cmd_id,
            "command": cmd,
            "accepted": accepted,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._mqtt_client.publish(Topics.ACK, json.dumps(ack), qos=1)
        logger.info("ACK published for %s accepted=%s", cmd, accepted)

    # ── Physics update ────────────────────────────────────────────────────────

    def _update_physics(self) -> None:
        s = self._state
        with s.lock():
            if s.stopped or s.paused:
                s.speed_mps = 0.0
                return

            # Manual teleoperation: the operator steers, so no autonomous
            # navigation happens. Movement is applied by _manual_step when a
            # MOVE_* command arrives; here we only decay speed and keep the
            # battery, motor and water models running.
            if s.manual_mode:
                s.speed_mps = 0.0
                self._update_consumables(s)
                return

            # Auto-return home when a consumable runs low. Injected low battery
            # is a fault demonstration, so it must not trigger the normal
            # recovery behaviour.
            low_battery = s.battery_soc < CHARGE_THRESHOLD and not s.inject_low_battery
            low_water = s.water_level_pct < WATER_THRESHOLD
            if (low_battery or low_water) and not s.returning_home and s.mode == "CLEANING":
                s.returning_home = True
                s.mode = "RETURNING"
                if low_battery and low_water:
                    reason = (
                        f"battery {s.battery_soc:.1f}% and water {s.water_level_pct:.1f}% both low"
                    )
                elif low_battery:
                    reason = f"battery {s.battery_soc:.1f}% below {CHARGE_THRESHOLD:.0f}%"
                else:
                    reason = f"water {s.water_level_pct:.1f}% below {WATER_THRESHOLD:.0f}%"
                logger.info("Returning to the dock: %s", reason)

            # Servicing at the dock: charge the battery and refill the tank.
            # Cleaning only resumes once both are sufficiently replenished.
            if (
                s.row == gm.HOME_ROW
                and s.col == gm.HOME_COL
                and s.mode in ("RETURNING", "CHARGING", "REFILLING")
            ):
                needs_charge = s.battery_soc < CHARGE_FULL
                needs_water = s.water_level_pct < WATER_FULL

                if needs_charge or needs_water:
                    s.returning_home = False
                    # Report the limiting consumable, so the operator can see
                    # why the robot is still at the dock.
                    s.mode = "CHARGING" if needs_charge else "REFILLING"
                    s.speed_mps = 0.0
                    s.brush_on = False
                    s.pump_on = False
                    if needs_charge:
                        s.battery_soc = min(
                            100.0, s.battery_soc + CHARGE_RATE * TELEMETRY_INTERVAL / 60.0
                        )
                    if needs_water:
                        s.water_level_pct = min(
                            100.0, s.water_level_pct + REFILL_RATE * TELEMETRY_INTERVAL / 60.0
                        )
                    return
                else:
                    s.mode = "CLEANING"
                    s.brush_on = True
                    logger.info(
                        "Servicing complete: battery %.1f%%, water %.1f%%, resuming cleaning",
                        s.battery_soc,
                        s.water_level_pct,
                    )

            # Fault injections
            if s.inject_obstacle:
                s.obstacle_cm = 15.0
                s.speed_mps = 0.0
                return
            if s.inject_motor_overload:
                s.motor_current_a = 3.5
            if s.inject_low_battery and s.mode != "CHARGING":
                s.battery_soc = max(0.0, s.battery_soc - 5.0)

            if s.returning_home:
                if s.row == gm.HOME_ROW and s.col == gm.HOME_COL:
                    s.returning_home = False
                    s.stopped = True
                    s.mode = "IDLE"
                    s.speed_mps = 0.0
                    return
                # Move toward home
                dr = gm.HOME_ROW - s.row
                dc = gm.HOME_COL - s.col
                s.row += int(math.copysign(1, dr)) if dr != 0 else 0
                s.col += int(math.copysign(1, dc)) if dc != 0 else 0
                s.speed_mps = 0.2
                s.mode = "RETURNING"
                return

            # Normal lawnmower navigation — loop continuously
            if s.path_index >= len(self._path):
                s.path_index = 0
                self._cleaned.clear()
                self._dirt_map = gm.generate_dirt_map(SEED)
                return

            target_row, target_col = self._path[s.path_index]

            # Check obstacle ahead
            next_obstacle_cm = self._scan_obstacle(s.row, s.col, target_row, target_col)
            s.obstacle_cm = next_obstacle_cm if not s.inject_obstacle else 15.0

            if s.obstacle_cm < 25.0:
                s.speed_mps = 0.0
                s.bumper_active = s.obstacle_cm < 5.0
                # Try next waypoint
                s.path_index += 1
                return

            if s.obstacle_cm < 50.0:
                s.speed_mps = 0.1
            else:
                s.speed_mps = 0.2

            # Move to target cell
            if s.row == target_row and s.col == target_col:
                # In target cell — apply cleaning
                s.ticks_in_cell += 1
                s.dirt_score = float(self._dirt_map[s.row, s.col])
                if s.brush_on and s.ticks_in_cell >= TICKS_TO_CLEAN:
                    cell = (s.row, s.col)
                    if cell not in self._cleaned:
                        self._cleaned.add(cell)
                        self._dirt_map[s.row, s.col] = 0.0
                    s.path_index += 1
                    s.ticks_in_cell = 0
            else:
                # Step toward target
                dr = target_row - s.row
                dc = target_col - s.col
                s.row += int(math.copysign(1, dr)) if dr != 0 else 0
                s.col += int(math.copysign(1, dc)) if dc != 0 else 0
                s.ticks_in_cell = 0

            # Update heading
            if s.row != target_row or s.col != target_col:
                angle = math.degrees(math.atan2(target_col - s.col, target_row - s.row))
                s.heading_deg = angle % 360.0

            self._update_consumables(s)

    def _update_consumables(self, s: RobotPhysicsState) -> None:
        """Battery, motor thermal and water models.

        These run every tick regardless of who is steering, so a robot driven
        manually still drains its battery and heats its motor. Must be called
        with the state lock already held.
        """
        # Battery drain, suppressed while the robot sits on the dock, where it
        # is on mains power whether it is charging or refilling.
        drain = 0.05 + (0.02 if s.brush_on else 0.0) + (0.01 if s.pump_on else 0.0)
        if not s.inject_low_battery and s.mode not in ("CHARGING", "REFILLING"):
            s.battery_soc = max(0.0, s.battery_soc - drain * TELEMETRY_INTERVAL / 60.0)
        s.battery_v = 10.0 + s.battery_soc / 100.0 * 2.6
        s.battery_a = 1.2 + (0.3 if s.brush_on else 0.0)

        # Motor temperature
        if not s.inject_motor_overload:
            s.motor_current_a = 0.6 + (0.3 if s.brush_on else 0.0)
        heat = s.motor_current_a * 5.0
        cool = (s.motor_temperature_c - 25.0) * 0.05
        s.motor_temperature_c = min(
            120.0, max(20.0, s.motor_temperature_c + heat * TELEMETRY_INTERVAL / 60.0 - cool)
        )

        # Water consumption. The injected fault drains the tank rapidly so the
        # return-to-dock behaviour can be demonstrated, but it is suppressed on
        # the dock so the refill is not fighting the drain.
        if s.inject_low_water and s.mode not in ("CHARGING", "REFILLING"):
            s.water_level_pct = max(0.0, s.water_level_pct - 5.0)
        elif s.pump_on:
            s.water_level_pct = max(0.0, s.water_level_pct - 0.1)

        s.dirt_score = float(self._dirt_map[s.row, s.col])
        s.sequence += 1

    def _scan_obstacle(self, row: int, col: int, target_row: int, target_col: int) -> float:
        """Return simulated obstacle distance in the direction of travel."""
        dr = target_row - row
        dc = target_col - col
        nr, nc = row + (1 if dr > 0 else -1 if dr < 0 else 0), col + (
            1 if dc > 0 else -1 if dc < 0 else 0
        )
        if not gm.is_accessible(nr, nc):
            return 20.0
        return 200.0

    # ── Telemetry publisher ───────────────────────────────────────────────────

    def _build_telemetry(self) -> dict:
        s = self._state
        coverage = len(self._cleaned) / gm.total_accessible_cells() * 100.0
        return {
            "schema_version": "1.0",
            "robot_id": ROBOT_ID,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "sequence": s.sequence,
            "pose": {
                "x_m": round(s.x_m, 3),
                "y_m": round(s.y_m, 3),
                "heading_deg": round(s.heading_deg, 1),
                "speed_mps": round(s.speed_mps, 3),
            },
            "sensors": {
                "obstacle_cm": round(s.obstacle_cm, 1),
                "battery_v": round(s.battery_v, 3),
                "battery_soc": round(s.battery_soc, 2),
                "battery_a": round(s.battery_a, 3),
                "motor_current_a": round(s.motor_current_a, 3),
                "motor_temperature_c": round(s.motor_temperature_c, 2),
                "dirt_score": round(s.dirt_score, 4),
                "water_level_pct": round(s.water_level_pct, 2),
                "bumper_active": s.bumper_active,
            },
            "actuators": {
                "brush_on": s.brush_on,
                "pump_on": s.pump_on,
            },
            "mission": {
                "mission_id": s.mission_id,
                "mode": s.mode,
            },
            "_meta": {
                "cleaning_coverage_pct": round(coverage, 2),
                "cleaned_cells": len(self._cleaned),
                "total_accessible": gm.total_accessible_cells(),
            },
        }

    # ── Main loop ─────────────────────────────────────────────────────────────

    def _publish_health(self) -> None:
        health = {
            "service": "robot-simulator",
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "uptime_s": round(time.monotonic() - self._start_time, 1),
        }
        self._mqtt_client.publish(Topics.SERVICE_HEALTH, json.dumps(health), qos=0, retain=True)

    def run(self) -> None:
        # Connect MQTT
        for attempt in range(1, 11):
            try:
                self._mqtt_client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
                break
            except Exception as exc:
                logger.warning("MQTT connect attempt %d failed: %s", attempt, exc)
                time.sleep(min(2**attempt, 30))
        else:
            logger.error("Cannot connect to MQTT after 10 attempts — exiting")
            sys.exit(1)

        self._mqtt_client.loop_start()
        logger.info(
            "Simulator started. Path length=%d, accessible cells=%d",
            len(self._path),
            gm.total_accessible_cells(),
        )

        tick = 0
        while self._running:
            loop_start = time.monotonic()
            self._update_physics()
            telemetry = self._build_telemetry()
            self._mqtt_client.publish(Topics.TELEMETRY_RAW, json.dumps(telemetry), qos=1)
            if tick % 30 == 0:
                self._publish_health()
                logger.info(
                    "Coverage=%.1f%% battery=%.1f%% pos=(%d,%d) mode=%s",
                    telemetry["_meta"]["cleaning_coverage_pct"],
                    self._state.battery_soc,
                    self._state.row,
                    self._state.col,
                    self._state.mode,
                )
            tick += 1
            elapsed = time.monotonic() - loop_start
            time.sleep(max(0.0, TELEMETRY_INTERVAL - elapsed))

        self._mqtt_client.loop_stop()
        self._mqtt_client.disconnect()

    def stop(self) -> None:
        self._running = False

    def inject_fault(self, fault: str) -> None:
        """Expose fault injection for demo and testing."""
        s = self._state
        with s.lock():
            if fault == "obstacle":
                s.inject_obstacle = True
            elif fault == "motor":
                s.inject_motor_overload = True
            elif fault == "battery":
                s.inject_low_battery = True
            elif fault == "water":
                s.inject_low_water = True
            elif fault == "clear":
                s.inject_obstacle = False
                s.inject_motor_overload = False
                s.inject_low_battery = False
                s.inject_low_water = False

    @property
    def state(self) -> RobotPhysicsState:
        return self._state
