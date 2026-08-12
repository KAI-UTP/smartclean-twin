"""Unit tests for the web control panel service.

These exercise the parts that do not need the other services to be running:
the health endpoint, the static console, command and fault validation, and the
InfluxDB CSV parser. The parser test is the important one: field values can
contain commas, so a naive split would corrupt them.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

WEB_DIR = Path(__file__).resolve().parents[2] / "services" / "web-control"
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

fastapi_testclient = pytest.importorskip("fastapi.testclient")
import main as web  # noqa: E402

client = fastapi_testclient.TestClient(web.app)


# ── health and console ────────────────────────────────────────────────────────


def test_health_reports_the_service_name() -> None:
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["service"] == "web-control"
    assert body["status"] == "healthy"
    assert body["uptime_s"] >= 0


def test_root_serves_the_console() -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert "SmartClean Twin" in r.text


# ── command validation ────────────────────────────────────────────────────────


def test_unknown_command_is_rejected_before_any_call_is_made() -> None:
    r = client.post("/api/command", json={"command": "SELF_DESTRUCT"})
    assert r.status_code == 400
    assert "Unknown command" in r.json()["detail"]


@pytest.mark.parametrize(
    "command",
    [
        "START",
        "PAUSE",
        "RESUME",
        "STOP",
        "RETURN_HOME",
        "BRUSH_ON",
        "BRUSH_OFF",
        "PUMP_ON",
        "PUMP_OFF",
    ],
)
def test_every_operating_command_is_allowed(command: str) -> None:
    assert command in web.VALID_COMMANDS


@pytest.mark.parametrize(
    "command",
    ["MANUAL_MODE", "AUTO_MODE", "MOVE_UP", "MOVE_DOWN", "MOVE_LEFT", "MOVE_RIGHT"],
)
def test_every_teleoperation_command_is_allowed(command: str) -> None:
    assert command in web.VALID_COMMANDS


def test_the_console_and_the_robot_agree_on_the_command_set() -> None:
    """The console must not offer a command the robot does not implement."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared"))
    from smartclean_common.models import RobotCommand

    robot_commands = {c.value for c in RobotCommand}
    assert web.VALID_COMMANDS <= robot_commands, (
        "console offers commands the robot does not accept: "
        f"{web.VALID_COMMANDS - robot_commands}"
    )


# ── fault validation ──────────────────────────────────────────────────────────


def test_unknown_fault_is_rejected() -> None:
    r = client.post("/api/fault", json={"fault": "meltdown"})
    assert r.status_code == 400


@pytest.mark.parametrize("fault", ["obstacle", "motor", "battery", "clear"])
def test_supported_faults(fault: str) -> None:
    assert fault in web.VALID_FAULTS


# ── what-if input limits ──────────────────────────────────────────────────────


def test_whatif_rejects_a_physically_impossible_temperature() -> None:
    r = client.post("/api/whatif", json={"motor_temperature_c": 500})
    assert r.status_code == 422


def test_whatif_rejects_a_negative_state_of_charge() -> None:
    r = client.post("/api/whatif", json={"battery_soc": -5})
    assert r.status_code == 422


# ── InfluxDB CSV parsing ──────────────────────────────────────────────────────


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeClient:
    """Stands in for httpx.AsyncClient, returning a canned CSV body."""

    def __init__(self, text: str) -> None:
        self._text = text

    async def post(self, *args, **kwargs) -> _FakeResponse:
        return _FakeResponse(self._text)


CSV_WITH_COMMA_IN_A_VALUE = (
    ",result,table,_start,_stop,_time,_value,_field,_measurement,robot_id\r\n"
    ",_result,0,S,E,T,42.5,battery_soc,robot_telemetry,SCR01\r\n"
    ',_result,1,S,E,T,"Normal operation, no action needed",'
    "recommendation,robot_prediction,SCR01\r\n"
)


def test_parser_keeps_a_value_that_contains_a_comma() -> None:
    """A naive split(",") would corrupt this; the csv module must not."""
    fake = _FakeClient(CSV_WITH_COMMA_IN_A_VALUE)
    out = asyncio.run(web._query_latest(fake, "robot_prediction"))

    assert out["battery_soc"] == 42.5
    assert out["recommendation"] == "Normal operation, no action needed"


def test_parser_converts_numbers_and_keeps_strings() -> None:
    fake = _FakeClient(CSV_WITH_COMMA_IN_A_VALUE)
    out = asyncio.run(web._query_latest(fake, "robot_telemetry"))

    assert isinstance(out["battery_soc"], float)
    assert isinstance(out["recommendation"], str)


def test_parser_returns_nothing_for_an_empty_response() -> None:
    out = asyncio.run(web._query_latest(_FakeClient(""), "robot_telemetry"))
    assert out == {}
