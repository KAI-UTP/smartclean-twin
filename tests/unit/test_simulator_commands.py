"""Unit tests: simulator command handling (no MQTT, no Docker)."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "services", "robot-simulator"))

import pytest


class TestSimulatorCommandApply:
    """Tests _apply_command without MQTT by calling the method directly."""

    def _make_sim(self):
        # Avoid MQTT init — patch the client
        from unittest.mock import MagicMock, patch
        with patch("paho.mqtt.client.Client"):
            from simulator import RobotSimulator
            sim = RobotSimulator.__new__(RobotSimulator)
        from robot_state import RobotPhysicsState
        import grid_map as gm
        sim._state = RobotPhysicsState()
        sim._dirt_map = gm.generate_dirt_map(42)
        sim._path = gm.lawnmower_path()
        sim._cleaned = set()
        return sim

    def test_pause_sets_paused(self):
        sim = self._make_sim()
        accepted = sim._apply_command("PAUSE")
        assert accepted is True
        assert sim._state.paused is True

    def test_resume_clears_paused(self):
        sim = self._make_sim()
        sim._state.paused = True
        sim._apply_command("RESUME")
        assert sim._state.paused is False

    def test_stop_sets_stopped(self):
        sim = self._make_sim()
        sim._apply_command("STOP")
        assert sim._state.stopped is True

    def test_brush_on(self):
        sim = self._make_sim()
        sim._state.brush_on = False
        sim._apply_command("BRUSH_ON")
        assert sim._state.brush_on is True

    def test_brush_off(self):
        sim = self._make_sim()
        sim._apply_command("BRUSH_OFF")
        assert sim._state.brush_on is False

    def test_pump_on(self):
        sim = self._make_sim()
        sim._apply_command("PUMP_ON")
        assert sim._state.pump_on is True

    def test_return_home_sets_flag(self):
        sim = self._make_sim()
        sim._apply_command("RETURN_HOME")
        assert sim._state.returning_home is True
        assert sim._state.mode == "RETURNING"

    def test_unknown_command_returns_false(self):
        sim = self._make_sim()
        result = sim._apply_command("INVALID_COMMAND")
        assert result is False


class TestFaultInjection:
    def _make_sim(self):
        from unittest.mock import patch
        with patch("paho.mqtt.client.Client"):
            from simulator import RobotSimulator
            sim = RobotSimulator.__new__(RobotSimulator)
        from robot_state import RobotPhysicsState
        import grid_map as gm
        sim._state = RobotPhysicsState()
        sim._dirt_map = gm.generate_dirt_map(42)
        sim._path = gm.lawnmower_path()
        sim._cleaned = set()
        return sim

    def test_inject_obstacle(self):
        sim = self._make_sim()
        sim.inject_fault("obstacle")
        assert sim._state.inject_obstacle is True

    def test_inject_motor(self):
        sim = self._make_sim()
        sim.inject_fault("motor")
        assert sim._state.inject_motor_overload is True

    def test_inject_battery(self):
        sim = self._make_sim()
        sim.inject_fault("battery")
        assert sim._state.inject_low_battery is True

    def test_clear_fault(self):
        sim = self._make_sim()
        sim.inject_fault("obstacle")
        sim.inject_fault("clear")
        assert sim._state.inject_obstacle is False
        assert sim._state.inject_motor_overload is False
        assert sim._state.inject_low_battery is False
