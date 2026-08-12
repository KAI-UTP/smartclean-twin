"""Unit tests for the robot's autonomous return to the dock.

The robot must go home and service itself when either consumable runs low:
a flat battery, or an empty water tank. Cleaning resumes only when both have
been replenished.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SIM_DIR = Path(__file__).resolve().parents[2] / "services" / "robot-simulator"
if str(SIM_DIR) not in sys.path:
    sys.path.insert(0, str(SIM_DIR))

import grid_map as gm  # noqa: E402
import simulator as simmod  # noqa: E402
from simulator import RobotSimulator  # noqa: E402


@pytest.fixture
def sim() -> RobotSimulator:
    return RobotSimulator()


def _park_at_dock(sim: RobotSimulator) -> None:
    sim.state.row, sim.state.col = gm.HOME_ROW, gm.HOME_COL


def _away_from_dock(sim: RobotSimulator) -> None:
    sim.state.row, sim.state.col = 4, 2
    assert (sim.state.row, sim.state.col) != (gm.HOME_ROW, gm.HOME_COL)


# ── the trigger ───────────────────────────────────────────────────────────────


def test_low_battery_sends_the_robot_home(sim: RobotSimulator) -> None:
    _away_from_dock(sim)
    sim.state.mode = "CLEANING"
    sim.state.battery_soc = simmod.CHARGE_THRESHOLD - 1.0

    sim._update_physics()

    assert sim.state.returning_home is True
    assert sim.state.mode == "RETURNING"


def test_low_water_sends_the_robot_home(sim: RobotSimulator) -> None:
    _away_from_dock(sim)
    sim.state.mode = "CLEANING"
    sim.state.battery_soc = 90.0  # battery is fine
    sim.state.water_level_pct = simmod.WATER_THRESHOLD - 1.0

    sim._update_physics()

    assert sim.state.returning_home is True, "an empty tank must send the robot home"
    assert sim.state.mode == "RETURNING"


def test_healthy_consumables_do_not_send_the_robot_home(sim: RobotSimulator) -> None:
    _away_from_dock(sim)
    sim.state.mode = "CLEANING"
    sim.state.battery_soc = 90.0
    sim.state.water_level_pct = 90.0

    sim._update_physics()

    assert sim.state.returning_home is False
    assert sim.state.mode == "CLEANING"


def test_injected_low_battery_does_not_trigger_the_recovery(sim: RobotSimulator) -> None:
    """The fault demonstration must not be masked by the robot recovering."""
    _away_from_dock(sim)
    sim.state.mode = "CLEANING"
    sim.state.water_level_pct = 90.0
    sim.state.battery_soc = 5.0
    sim.state.inject_low_battery = True

    sim._update_physics()

    assert sim.state.returning_home is False


# ── servicing at the dock ─────────────────────────────────────────────────────


def test_battery_charges_at_the_dock(sim: RobotSimulator) -> None:
    _park_at_dock(sim)
    sim.state.mode = "RETURNING"
    sim.state.battery_soc = 30.0
    sim.state.water_level_pct = 100.0

    sim._update_physics()

    assert sim.state.mode == "CHARGING"
    assert sim.state.battery_soc > 30.0


def test_tank_refills_at_the_dock(sim: RobotSimulator) -> None:
    _park_at_dock(sim)
    sim.state.mode = "RETURNING"
    sim.state.battery_soc = 100.0  # nothing to charge
    sim.state.water_level_pct = 10.0

    sim._update_physics()

    assert sim.state.mode == "REFILLING"
    assert sim.state.water_level_pct > 10.0


def test_both_consumables_replenish_together(sim: RobotSimulator) -> None:
    _park_at_dock(sim)
    sim.state.mode = "RETURNING"
    sim.state.battery_soc = 30.0
    sim.state.water_level_pct = 10.0

    sim._update_physics()

    assert sim.state.battery_soc > 30.0
    assert sim.state.water_level_pct > 10.0


def test_the_robot_does_not_clean_while_docked(sim: RobotSimulator) -> None:
    _park_at_dock(sim)
    sim.state.mode = "RETURNING"
    sim.state.battery_soc = 30.0
    sim.state.brush_on = True
    sim.state.pump_on = True

    sim._update_physics()

    assert sim.state.brush_on is False
    assert sim.state.pump_on is False
    assert sim.state.speed_mps == 0.0


def test_battery_does_not_drain_while_docked(sim: RobotSimulator) -> None:
    """On the dock the robot is on mains power, including while refilling."""
    _park_at_dock(sim)
    sim.state.mode = "RETURNING"
    sim.state.battery_soc = 100.0  # no charging needed
    sim.state.water_level_pct = 10.0
    before = sim.state.battery_soc

    sim._update_physics()

    assert sim.state.mode == "REFILLING"
    assert sim.state.battery_soc >= before


# ── resuming ──────────────────────────────────────────────────────────────────


def test_cleaning_resumes_only_when_both_are_replenished(sim: RobotSimulator) -> None:
    _park_at_dock(sim)
    sim.state.mode = "CHARGING"
    sim.state.battery_soc = simmod.CHARGE_FULL + 1.0  # battery is ready
    sim.state.water_level_pct = 20.0  # tank is not

    sim._update_physics()

    assert sim.state.mode == "REFILLING", "must not resume cleaning on an empty tank"


def test_cleaning_resumes_when_battery_and_tank_are_ready(sim: RobotSimulator) -> None:
    _park_at_dock(sim)
    sim.state.mode = "CHARGING"
    sim.state.battery_soc = simmod.CHARGE_FULL + 1.0
    sim.state.water_level_pct = simmod.WATER_FULL + 1.0

    sim._update_physics()

    assert sim.state.mode == "CLEANING"
    assert sim.state.brush_on is True
    assert sim.state.returning_home is False


# ── the full cycle ────────────────────────────────────────────────────────────


def test_empty_tank_recovers_over_a_full_cycle(sim: RobotSimulator) -> None:
    """Drive the loop end to end: low water, home, refill, back to cleaning."""
    _park_at_dock(sim)
    sim.state.mode = "CLEANING"
    sim.state.battery_soc = 100.0
    sim.state.water_level_pct = 5.0

    for _ in range(400):  # a few simulated minutes
        sim._update_physics()
        if sim.state.mode == "CLEANING" and sim.state.water_level_pct > simmod.WATER_FULL:
            break

    assert sim.state.water_level_pct > simmod.WATER_FULL, "tank should have been refilled"
    assert sim.state.mode == "CLEANING", "robot should be cleaning again"


# ── the injected water fault, used for the live demonstration ─────────────────


def test_water_fault_drains_the_tank_quickly(sim: RobotSimulator) -> None:
    _away_from_dock(sim)
    sim.state.mode = "CLEANING"
    before = sim.state.water_level_pct

    sim.inject_fault("water")
    sim._update_physics()

    assert sim.state.water_level_pct < before - 1.0, "the fault should drain fast"


def test_water_fault_is_suppressed_on_the_dock_so_the_refill_wins(
    sim: RobotSimulator,
) -> None:
    _park_at_dock(sim)
    sim.state.mode = "REFILLING"
    sim.state.battery_soc = 100.0
    sim.state.water_level_pct = 10.0
    sim.inject_fault("water")

    sim._update_physics()

    assert sim.state.water_level_pct > 10.0, "refilling must beat the injected drain"


def test_clear_removes_the_water_fault(sim: RobotSimulator) -> None:
    sim.inject_fault("water")
    assert sim.state.inject_low_water is True

    sim.inject_fault("clear")
    assert sim.state.inject_low_water is False
