"""Command API Service.

POST /api/v1/commands  → validates, publishes MQTT command, awaits ACK.
GET  /api/v1/commands  → returns command history.
GET  /health
"""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

import paho.mqtt.client as mqtt
import uvicorn
from fastapi import FastAPI, HTTPException
from influxdb_client import InfluxDBClient
from influxdb_client.client.write_api import SYNCHRONOUS
from pydantic import BaseModel

sys.path.insert(0, "/app/shared")

from smartclean_common.models import AckMessage, CommandRequest, RobotCommand
from smartclean_common.topics import Topics

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

MQTT_HOST = os.environ.get("MQTT_HOST", "mosquitto")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
INFLUXDB_URL = os.environ.get("INFLUXDB_URL", "http://influxdb:8086")
INFLUXDB_TOKEN = os.environ.get("INFLUXDB_TOKEN", "")
INFLUXDB_ORG = os.environ.get("INFLUXDB_ORG", "smartclean")
INFLUXDB_BUCKET = os.environ.get("INFLUXDB_BUCKET", "smartclean_twin")
ACK_TIMEOUT_S = 5.0
VALID_ROBOT_IDS = {"SCR01"}

_start_time = time.monotonic()
_command_history: list[dict] = []
_pending_acks: dict[str, threading.Event] = {}
_ack_results: dict[str, dict] = {}
_mqtt_client: mqtt.Client | None = None

_influx_client: InfluxDBClient | None = None
_write_api = None


def _get_write_api():
    global _influx_client, _write_api
    if _write_api is None:
        _influx_client = InfluxDBClient(
            url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG
        )
        _write_api = _influx_client.write_api(write_options=SYNCHRONOUS)
    return _write_api


def _write_command(cmd_record: dict) -> None:
    try:
        wa = _get_write_api()
        point = {
            "measurement": "robot_command",
            "tags": {"robot_id": cmd_record["robot_id"], "command": cmd_record["command"]},
            "fields": {
                "command_id": cmd_record["command_id"],
                "status": cmd_record.get("status", "issued"),
            },
            "time": datetime.now(timezone.utc),
        }
        wa.write(bucket=INFLUXDB_BUCKET, org=INFLUXDB_ORG, record=point)
    except Exception as exc:
        logger.error("InfluxDB command write error: %s", exc)


def _write_ack(ack: dict) -> None:
    try:
        wa = _get_write_api()
        point = {
            "measurement": "robot_acknowledgement",
            "tags": {
                "robot_id": ack["robot_id"],
                "command": ack["command"],
                "accepted": str(ack["accepted"]),
            },
            "fields": {
                "command_id": ack["command_id"],
                "latency_ms": ack.get("latency_ms", 0.0),
            },
            "time": datetime.now(timezone.utc),
        }
        wa.write(bucket=INFLUXDB_BUCKET, org=INFLUXDB_ORG, record=point)
    except Exception as exc:
        logger.error("InfluxDB ack write error: %s", exc)


def _on_ack(client: mqtt.Client, userdata, msg: mqtt.MQTTMessage) -> None:
    try:
        data = json.loads(msg.payload.decode())
        cmd_id = data.get("command_id", "")
        if cmd_id in _pending_acks:
            _ack_results[cmd_id] = data
            _pending_acks[cmd_id].set()
            _write_ack(data)
            logger.info("ACK received for command_id=%s accepted=%s", cmd_id, data.get("accepted"))
    except Exception as exc:
        logger.error("ACK parse error: %s", exc)


def _on_connect(client: mqtt.Client, userdata, flags, rc: int) -> None:
    if rc == 0:
        client.subscribe(Topics.ACK, qos=1)
        logger.info("Command API MQTT connected, subscribed to %s", Topics.ACK)
    else:
        logger.error("MQTT connect failed rc=%d", rc)


def _start_mqtt() -> None:
    global _mqtt_client
    _mqtt_client = mqtt.Client(client_id="command-api")
    _mqtt_client.on_connect = _on_connect
    _mqtt_client.on_message = _on_ack

    for attempt in range(1, 11):
        try:
            _mqtt_client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
            _mqtt_client.loop_start()
            return
        except Exception as exc:
            logger.warning("MQTT attempt %d: %s", attempt, exc)
            time.sleep(min(2 ** attempt, 30))
    logger.error("Cannot connect to MQTT broker")


# ── FastAPI ────────────────────────────────────────────────────────────────────

app = FastAPI(title="SmartClean Command API", version="1.0")


class CommandResponse(BaseModel):
    command_id: str
    robot_id: str
    command: str
    status: str
    request_timestamp: str
    ack_received: bool
    ack_timestamp: Optional[str] = None
    ack_accepted: Optional[bool] = None
    ack_reason: Optional[str] = None


@app.get("/health")
def health() -> dict:
    return {
        "status": "healthy" if _mqtt_client and _mqtt_client.is_connected() else "degraded",
        "uptime_s": round(time.monotonic() - _start_time, 1),
        "commands_issued": len(_command_history),
    }


@app.get("/api/v1/commands")
def list_commands() -> list[dict]:
    return _command_history[-100:]


@app.post("/api/v1/commands", response_model=CommandResponse)
def issue_command(req: CommandRequest) -> CommandResponse:
    if req.robot_id not in VALID_ROBOT_IDS:
        raise HTTPException(status_code=404, detail=f"Unknown robot_id: {req.robot_id}")

    cmd_id = f"CMD-{uuid.uuid4().hex[:8].upper()}"
    issued_at = datetime.now(timezone.utc).isoformat()

    # Determine MQTT topic
    motion_commands = {
        RobotCommand.START, RobotCommand.PAUSE, RobotCommand.RESUME,
        RobotCommand.STOP, RobotCommand.RETURN_HOME,
    }
    topic = (Topics.COMMAND_MOTION if req.command in motion_commands
             else Topics.COMMAND_CLEANING)

    payload = {
        "command_id": cmd_id,
        "robot_id": req.robot_id,
        "command": req.command.value,
        "timestamp": issued_at,
        "issued_by": "command-api",
    }

    # Register pending ACK
    ack_event = threading.Event()
    _pending_acks[cmd_id] = ack_event

    if _mqtt_client:
        _mqtt_client.publish(topic, json.dumps(payload), qos=1)
        logger.info("Command published: %s id=%s", req.command.value, cmd_id)
    else:
        raise HTTPException(status_code=503, detail="MQTT not connected")

    cmd_record = {
        "command_id": cmd_id,
        "robot_id": req.robot_id,
        "command": req.command.value,
        "request_timestamp": issued_at,
        "status": "issued",
    }
    _command_history.append(cmd_record)
    _write_command(cmd_record)

    # Wait for ACK
    ack_received = ack_event.wait(timeout=ACK_TIMEOUT_S)
    ack_data = _ack_results.get(cmd_id, {})
    _pending_acks.pop(cmd_id, None)

    ack_ts = ack_data.get("timestamp")
    latency_ms: float = 0.0
    if ack_received and ack_ts:
        try:
            t_ack = datetime.fromisoformat(ack_ts.replace("Z", "+00:00"))
            t_issue = datetime.fromisoformat(issued_at.replace("Z", "+00:00"))
            latency_ms = (t_ack - t_issue).total_seconds() * 1000
            ack_data["latency_ms"] = latency_ms
        except Exception:
            pass

    cmd_record["status"] = "acked" if ack_received else "timeout"
    cmd_record["ack_received"] = ack_received

    return CommandResponse(
        command_id=cmd_id,
        robot_id=req.robot_id,
        command=req.command.value,
        status=cmd_record["status"],
        request_timestamp=issued_at,
        ack_received=ack_received,
        ack_timestamp=ack_data.get("timestamp"),
        ack_accepted=ack_data.get("accepted"),
        ack_reason=ack_data.get("reason"),
    )


def _shutdown(signum, frame) -> None:
    if _mqtt_client:
        _mqtt_client.loop_stop()
        _mqtt_client.disconnect()
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)
    _start_mqtt()
    port = int(os.environ.get("COMMAND_API_PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
