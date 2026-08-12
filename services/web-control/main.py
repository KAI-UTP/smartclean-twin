"""Web Control Panel service.

Serves a single-page operator console and proxies its requests to the other
microservices. The browser therefore talks to one origin only, which avoids
CORS configuration and keeps every service's port private to the compose
network.

Proxied endpoints
-----------------
GET  /api/state       twin state, latest telemetry and latest prediction (InfluxDB)
POST /api/command     operator command, forwarded to the Command API
POST /api/fault       fault injection, forwarded to the Robot Simulator
POST /api/whatif      what-if simulation, forwarded to the AI Service
GET  /api/history     recent command history from the Command API
GET  /health          service health
"""

from __future__ import annotations

import csv
import io
import logging
import os
import time
from typing import Any

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

COMMAND_API = os.environ.get("COMMAND_API_URL", "http://command-api:8000")
SIMULATOR = os.environ.get("SIMULATOR_URL", "http://robot-simulator:8004")
AI_SERVICE = os.environ.get("AI_SERVICE_URL", "http://ai-service:8003")
INFLUXDB_URL = os.environ.get("INFLUXDB_URL", "http://influxdb:8086")
INFLUXDB_TOKEN = os.environ.get("INFLUXDB_TOKEN", "")
INFLUXDB_ORG = os.environ.get("INFLUXDB_ORG", "smartclean")
INFLUXDB_BUCKET = os.environ.get("INFLUXDB_BUCKET", "smartclean_twin")
ROBOT_ID = os.environ.get("ROBOT_ID", "SCR01")

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

_start_time = time.monotonic()

app = FastAPI(title="SmartClean Web Control Panel", version="1.0")


# ── InfluxDB helpers ──────────────────────────────────────────────────────────


async def _query_latest(client: httpx.AsyncClient, measurement: str) -> dict[str, Any]:
    """Return {field: value} for the most recent point of a measurement."""
    flux = (
        f'from(bucket: "{INFLUXDB_BUCKET}") |> range(start: -60s) '
        f'|> filter(fn: (r) => r._measurement == "{measurement}") |> last()'
    )
    try:
        resp = await client.post(
            f"{INFLUXDB_URL}/api/v2/query?org={INFLUXDB_ORG}",
            content=flux,
            headers={
                "Authorization": f"Token {INFLUXDB_TOKEN}",
                "Content-Type": "application/vnd.flux",
                "Accept": "application/csv",
            },
            timeout=8.0,
        )
    except httpx.HTTPError as exc:
        logger.warning("InfluxDB query failed for %s: %s", measurement, exc)
        return {}

    # Parse with the csv module rather than split(","): field values may
    # themselves contain commas (for example the recommendation text), and a
    # naive split would corrupt both the key and the value.
    out: dict[str, Any] = {}
    for row in csv.reader(io.StringIO(resp.text)):
        if len(row) > 7 and row[1] == "_result":
            key, raw = row[7], row[6]
            try:
                out[key] = float(raw)
            except ValueError:
                out[key] = raw
    return out


# ── API ───────────────────────────────────────────────────────────────────────


@app.get("/health")
def health() -> dict:
    return {
        "service": "web-control",
        "status": "healthy",
        "uptime_s": round(time.monotonic() - _start_time, 1),
    }


@app.get("/api/state")
async def get_state() -> dict:
    """Everything the console needs, in one round trip."""
    async with httpx.AsyncClient() as client:
        telemetry = await _query_latest(client, "robot_telemetry")
        state = await _query_latest(client, "robot_state")
        prediction = await _query_latest(client, "robot_prediction")
    return {
        "robot_id": ROBOT_ID,
        "telemetry": telemetry,
        "state": state,
        "prediction": prediction,
        "connected": bool(telemetry or state),
    }


class CommandRequest(BaseModel):
    command: str


VALID_COMMANDS = {
    "START",
    "PAUSE",
    "RESUME",
    "STOP",
    "RETURN_HOME",
    "BRUSH_ON",
    "BRUSH_OFF",
    "PUMP_ON",
    "PUMP_OFF",
    # Manual teleoperation
    "MANUAL_MODE",
    "AUTO_MODE",
    "MOVE_UP",
    "MOVE_DOWN",
    "MOVE_LEFT",
    "MOVE_RIGHT",
    "MOVE_UP_LEFT",
    "MOVE_UP_RIGHT",
    "MOVE_DOWN_LEFT",
    "MOVE_DOWN_RIGHT",
}

# Named sequences of commands, so a common operator action is one button press
# instead of three. The sequence is issued server side and every acknowledgement
# is returned, so a partial failure is visible rather than hidden.
MACROS: dict[str, list[str]] = {
    "wet_clean": ["START", "BRUSH_ON", "PUMP_ON"],
    "dry_sweep": ["START", "BRUSH_ON", "PUMP_OFF"],
    "actuators_off": ["BRUSH_OFF", "PUMP_OFF"],
    "park": ["BRUSH_OFF", "PUMP_OFF", "RETURN_HOME"],
    "emergency_stop": ["STOP", "BRUSH_OFF", "PUMP_OFF"],
}


@app.post("/api/command")
async def send_command(req: CommandRequest) -> dict:
    """Forward an operator command to the Command API and return its ACK."""
    if req.command not in VALID_COMMANDS:
        raise HTTPException(status_code=400, detail=f"Unknown command: {req.command}")
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                f"{COMMAND_API}/api/v1/commands",
                json={"robot_id": ROBOT_ID, "command": req.command},
                timeout=15.0,
            )
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"Command API unreachable: {exc}")
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


class MacroRequest(BaseModel):
    macro: str


async def _issue(client: httpx.AsyncClient, command: str) -> dict:
    resp = await client.post(
        f"{COMMAND_API}/api/v1/commands",
        json={"robot_id": ROBOT_ID, "command": command},
        timeout=15.0,
    )
    return resp.json()


@app.post("/api/macro")
async def run_macro(req: MacroRequest) -> dict:
    """Run a named command sequence and return every acknowledgement."""
    if req.macro not in MACROS:
        raise HTTPException(status_code=400, detail=f"Unknown macro: {req.macro}")
    results = []
    async with httpx.AsyncClient() as client:
        for command in MACROS[req.macro]:
            try:
                results.append({"command": command, "result": await _issue(client, command)})
            except httpx.HTTPError as exc:
                raise HTTPException(status_code=502, detail=f"Command API unreachable: {exc}")
    accepted = sum(1 for r in results if r["result"].get("ack_accepted"))
    return {
        "macro": req.macro,
        "commands": MACROS[req.macro],
        "accepted": accepted,
        "total": len(results),
        "results": results,
    }


@app.get("/api/access")
def access(request: Request) -> dict:
    """The address to open this console from a phone on the same network.

    The service runs inside a container, so it cannot see the host's LAN
    address itself. LAN_HOST is supplied by the launcher; failing that, the
    address the browser used is reported back, which is already correct when
    the console was opened from another device.
    """
    port = int(os.environ.get("WEB_CONTROL_PORT", "8005"))
    host = os.environ.get("LAN_HOST", "").strip()
    browser_host = (request.headers.get("host") or "").split(":")[0]
    is_local = browser_host in ("localhost", "127.0.0.1", "")

    if not host and not is_local:
        host = browser_host

    return {
        "lan_url": f"http://{host}:{port}" if host else "",
        "port": port,
        "viewing_locally": is_local,
    }


class FaultRequest(BaseModel):
    fault: str


VALID_FAULTS = {"obstacle", "motor", "battery", "water", "clear"}


@app.post("/api/fault")
async def inject_fault(req: FaultRequest) -> dict:
    """Forward a fault injection to the Robot Simulator (demonstration use)."""
    if req.fault not in VALID_FAULTS:
        raise HTTPException(status_code=400, detail=f"Unknown fault: {req.fault}")
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(f"{SIMULATOR}/fault", json={"fault": req.fault}, timeout=10.0)
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"Simulator unreachable: {exc}")
    return resp.json()


class WhatIfRequest(BaseModel):
    motor_temperature_c: float = Field(default=40.0, ge=-10, le=120)
    motor_current_a: float = Field(default=0.8, ge=0, le=10)
    battery_soc: float = Field(default=90.0, ge=0, le=100)
    water_level_pct: float = Field(default=80.0, ge=0, le=100)


@app.post("/api/whatif")
async def whatif(req: WhatIfRequest) -> dict:
    """Forward a what-if scenario to the AI service."""
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(f"{AI_SERVICE}/whatif", json=req.model_dump(), timeout=15.0)
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"AI service unreachable: {exc}")
    return resp.json()


@app.get("/api/history")
async def history() -> list[dict]:
    """Recent command history, newest first."""
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{COMMAND_API}/api/v1/commands", timeout=10.0)
        except httpx.HTTPError:
            return []
    if resp.status_code >= 400:
        return []
    return list(reversed(resp.json()))[:12]


# ── Static console ────────────────────────────────────────────────────────────

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


if __name__ == "__main__":
    port = int(os.environ.get("WEB_CONTROL_PORT", "8005"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
