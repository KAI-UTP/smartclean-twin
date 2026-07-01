"""Unit tests: command validation logic."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "shared"))

import pytest
from pydantic import ValidationError
from smartclean_common.models import CommandRequest, RobotCommand


class TestValidCommands:
    @pytest.mark.parametrize("cmd", [
        "START", "PAUSE", "RESUME", "STOP", "RETURN_HOME",
        "BRUSH_ON", "BRUSH_OFF", "PUMP_ON", "PUMP_OFF",
    ])
    def test_valid_command(self, cmd: str):
        req = CommandRequest(robot_id="SCR01", command=RobotCommand(cmd))
        assert req.command.value == cmd

    def test_command_as_enum(self):
        req = CommandRequest(robot_id="SCR01", command=RobotCommand.PAUSE)
        assert req.command == RobotCommand.PAUSE


class TestInvalidCommands:
    def test_unknown_command_raises(self):
        with pytest.raises(ValidationError):
            CommandRequest.model_validate({"robot_id": "SCR01", "command": "FLY"})

    def test_empty_command_raises(self):
        with pytest.raises(ValidationError):
            CommandRequest.model_validate({"robot_id": "SCR01", "command": ""})

    def test_missing_robot_id_raises(self):
        with pytest.raises(ValidationError):
            CommandRequest.model_validate({"command": "STOP"})
