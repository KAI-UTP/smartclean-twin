"""Unit tests for manual teleoperation in the robot simulator.

Covers the operator taking control, stepping the robot one grid cell in each
direction, refusal of moves into walls and desks, and the fact that the robot
keeps consuming battery and water while being driven manually.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SIM_DIR = Path(__file__).resolve().parents[2] / "services" / "robot-simulator"
if str(SIM_DIR) not in sys.path:
    sys.path.insert(0, str(SIM_DIR))

import grid_map as gm  # noqa: E402
from simulator import RobotSimulator  # noqa: E402


@pytest.fixture
def sim() -> RobotSimulator:
    """A simulator instance that is not connected to MQTT."""
    return RobotSimulator()


def _place(sim: RobotSimulator, row: int, col: int) -> None:
    """Put the robot on a known accessible cell."""
    assert gm.is_accessible(row, col), f"test setup error: ({row},{col}) is not floor"
    sim.state.row, sim.state.col = row, col


# ── mode switching ────────────────────────────────────────────────────────────


def test_manual_mode_suspends_autonomous_control(sim: RobotSimulator) -> None:
    assert sim._apply_command("MANUAL_MODE") is True
    assert sim.state.manual_mode is True
    assert sim.state.mode == "MANUAL"
    assert sim.state.speed_mps == 0.0


def test_manual_mode_clears_paused_and_stopped(sim: RobotSimulator) -> None:
    sim._apply_command("STOP")
    assert sim.state.stopped is True

    sim._apply_command("MANUAL_MODE")
    assert sim.state.stopped is False
    assert sim.state.paused is False


def test_auto_mode_returns_control_to_the_robot(sim: RobotSimulator) -> None:
    sim._apply_command("MANUAL_MODE")
    assert sim._apply_command("AUTO_MODE") is True
    assert sim.state.manual_mode is False
    assert sim.state.mode == "CLEANING"


# ── movement ──────────────────────────────────────────────────────────────────


def test_move_is_rejected_when_not_in_manual_mode(sim: RobotSimulator) -> None:
    assert sim.state.manual_mode is False
    assert sim._apply_command("MOVE_UP") is False


@pytest.mark.parametrize(
    "command, d_row, d_col, heading",
    [
        ("MOVE_UP", 1, 0, 0.0),
        ("MOVE_RIGHT", 0, 1, 90.0),
        ("MOVE_DOWN", -1, 0, 180.0),
        ("MOVE_LEFT", 0, -1, 270.0),
    ],
)
def test_each_direction_moves_exactly_one_cell(
    sim: RobotSimulator, command: str, d_row: int, d_col: int, heading: float
) -> None:
    sim._apply_command("MANUAL_MODE")
    _place(sim, 4, 2)  # open floor in every direction, verified against the layout
    start_row, start_col = sim.state.row, sim.state.col

    assert sim._apply_command(command) is True
    assert sim.state.row == start_row + d_row
    assert sim.state.col == start_col + d_col
    assert sim.state.heading_deg == heading


def test_one_cell_is_half_a_metre(sim: RobotSimulator) -> None:
    sim._apply_command("MANUAL_MODE")
    _place(sim, 4, 2)
    x_before = sim.state.x_m

    sim._apply_command("MOVE_RIGHT")
    assert sim.state.x_m == pytest.approx(x_before + gm.CELL_SIZE_M)


def test_move_into_a_wall_is_refused_but_the_robot_turns(sim: RobotSimulator) -> None:
    sim._apply_command("MANUAL_MODE")
    _place(sim, 1, 1)  # home cell, row 0 and col 0 are perimeter wall
    assert not gm.is_accessible(0, 1)

    assert sim._apply_command("MOVE_DOWN") is False
    assert (sim.state.row, sim.state.col) == (1, 1), "robot must not enter a wall"
    assert sim.state.heading_deg == 180.0, "robot should still turn to face the wall"
    assert sim.state.speed_mps == 0.0


def test_move_into_a_desk_is_refused(sim: RobotSimulator) -> None:
    # Layout row 2 has an obstacle at column 4.
    assert not gm.is_accessible(2, 4)
    sim._apply_command("MANUAL_MODE")
    _place(sim, 2, 3)

    assert sim._apply_command("MOVE_RIGHT") is False
    assert (sim.state.row, sim.state.col) == (2, 3)


def test_manual_driving_cleans_when_the_brush_is_on(sim: RobotSimulator) -> None:
    sim._apply_command("MANUAL_MODE")
    sim._apply_command("BRUSH_ON")
    _place(sim, 4, 2)

    sim._apply_command("MOVE_UP")
    assert (sim.state.row, sim.state.col) in sim._cleaned


def test_manual_driving_does_not_clean_with_the_brush_off(sim: RobotSimulator) -> None:
    sim._apply_command("MANUAL_MODE")
    sim._apply_command("BRUSH_OFF")
    _place(sim, 4, 2)

    sim._apply_command("MOVE_UP")
    assert (sim.state.row, sim.state.col) not in sim._cleaned


# ── physics keeps running under manual control ────────────────────────────────


def test_battery_still_drains_while_driving_manually(sim: RobotSimulator) -> None:
    sim._apply_command("MANUAL_MODE")
    before = sim.state.battery_soc

    sim._update_physics()
    assert sim.state.battery_soc < before, "manual driving must still cost energy"


def test_water_still_depletes_with_the_pump_on(sim: RobotSimulator) -> None:
    sim._apply_command("MANUAL_MODE")
    sim._apply_command("PUMP_ON")
    before = sim.state.water_level_pct

    sim._update_physics()
    assert sim.state.water_level_pct < before


def test_manual_mode_does_not_follow_the_cleaning_path(sim: RobotSimulator) -> None:
    sim._apply_command("MANUAL_MODE")
    _place(sim, 4, 2)
    index_before = sim.state.path_index
    position_before = (sim.state.row, sim.state.col)

    for _ in range(5):
        sim._update_physics()

    assert (sim.state.row, sim.state.col) == position_before, "robot must not drive itself"
    assert sim.state.path_index == index_before


# ── diagonal movement ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "command, d_row, d_col, heading",
    [
        ("MOVE_UP_RIGHT", 1, 1, 45.0),
        ("MOVE_DOWN_RIGHT", -1, 1, 135.0),
        ("MOVE_DOWN_LEFT", -1, -1, 225.0),
        ("MOVE_UP_LEFT", 1, -1, 315.0),
    ],
)
def test_each_diagonal_moves_one_cell_on_both_axes(
    sim: RobotSimulator, command: str, d_row: int, d_col: int, heading: float
) -> None:
    sim._apply_command("MANUAL_MODE")
    _place(sim, 4, 2)
    start_row, start_col = sim.state.row, sim.state.col

    assert sim._apply_command(command) is True
    assert sim.state.row == start_row + d_row
    assert sim.state.col == start_col + d_col
    assert sim.state.heading_deg == heading


def test_a_diagonal_may_not_cut_a_corner(sim: RobotSimulator) -> None:
    """Both orthogonal neighbours must be clear, or the chassis would not fit."""
    # From (1,3): up-right target (2,4) is floor-adjacent but (2,4) is a desk.
    assert not gm.is_accessible(2, 4)
    sim._apply_command("MANUAL_MODE")
    _place(sim, 1, 3)

    assert sim._apply_command("MOVE_UP_RIGHT") is False
    assert (sim.state.row, sim.state.col) == (1, 3)


def test_a_diagonal_into_the_wall_is_refused(sim: RobotSimulator) -> None:
    sim._apply_command("MANUAL_MODE")
    _place(sim, 1, 1)  # corner cell, down-left is the perimeter

    assert sim._apply_command("MOVE_DOWN_LEFT") is False
    assert (sim.state.row, sim.state.col) == (1, 1)


def test_all_eight_directions_are_defined(sim: RobotSimulator) -> None:
    import simulator as simmod

    assert len(simmod.MANUAL_MOVES) == 8
    headings = sorted(h for _, _, h in simmod.MANUAL_MOVES.values())
    assert headings == [0.0, 45.0, 90.0, 135.0, 180.0, 225.0, 270.0, 315.0]


# ── returning to autonomous control ───────────────────────────────────────────


def test_auto_mode_resumes_from_where_the_robot_actually_is(sim: RobotSimulator) -> None:
    """The robot must not beeline back to its pre-manual waypoint."""
    far_index = len(sim._path) - 1  # was heading to the far end of the room
    sim.state.path_index = far_index
    far_target = sim._path[far_index]

    sim._apply_command("MANUAL_MODE")
    _place(sim, 2, 2)  # operator parks it here
    sim._apply_command("AUTO_MODE")

    resumed = sim._path[sim.state.path_index]
    distance_to_resumed = abs(resumed[0] - 2) + abs(resumed[1] - 2)
    distance_to_old = abs(far_target[0] - 2) + abs(far_target[1] - 2)

    assert distance_to_resumed <= distance_to_old, "should resume near the robot"
    assert distance_to_resumed <= 2, "the resumed waypoint should be adjacent or on the cell"


def test_auto_mode_does_not_move_the_robot(sim: RobotSimulator) -> None:
    sim._apply_command("MANUAL_MODE")
    _place(sim, 3, 7)
    position = (sim.state.row, sim.state.col)

    sim._apply_command("AUTO_MODE")

    assert (sim.state.row, sim.state.col) == position, "handing back control must not teleport"


def test_the_robot_does_not_jump_across_the_room_on_the_next_tick(
    sim: RobotSimulator,
) -> None:
    """One tick may step one cell, never more."""
    sim.state.path_index = len(sim._path) - 1
    sim._apply_command("MANUAL_MODE")
    _place(sim, 2, 2)
    sim._apply_command("AUTO_MODE")

    before = (sim.state.row, sim.state.col)
    sim._update_physics()
    after = (sim.state.row, sim.state.col)

    step = abs(after[0] - before[0]) + abs(after[1] - before[1])
    assert step <= 2, f"robot moved {step} cells in one tick, that is a jump"


def test_nearest_index_prefers_a_cell_that_still_needs_cleaning(
    sim: RobotSimulator,
) -> None:
    target = sim._path[0]
    sim._cleaned.add(target)  # mark the closest waypoint as already done

    index = sim._nearest_path_index(target[0], target[1])

    assert sim._path[index] not in sim._cleaned or len(sim._cleaned) == len(sim._path)
