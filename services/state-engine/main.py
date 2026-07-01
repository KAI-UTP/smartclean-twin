"""Digital Twin State Engine.

Subscribes to validated telemetry, applies state rules, publishes state
and alarms, and writes everything to InfluxDB.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import threading
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
import uvicorn
from fastapi import FastAPI
from influxdb_client import InfluxDBClient
from influxdb_client.client.write_api import SYNCHRONOUS
from pydantic import ValidationError

sys.path.insert(0, "/app/shared")

from smartclean_common.models import TelemetryMessage
from smartclean_common.topics import Topics
import rules

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

_last_msg_time: datetime | None = None
_cleaning_coverage_pct: float = 0.0
_sequence: int = 0
_start_time = time.monotonic()
_mqtt_client: mqtt.Client | None = None

_influx_client: InfluxDBClient | None = None
_write_api = None


def _get_write_api():
    global _influx_client, _write_api
    if _write_api is None:
        _influx_client = InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)
        _write_api = _influx_client.write_api(write_options=SYNCHRONOUS)
    return _write_api


def _write_state(state_dict: dict) -> None:
    try:
        wa = _get_write_api()
        fields = {
            "motion_state": state_dict["motion_state"],
            "operation_mode": state_dict["operation_mode"],
            "safety_state": state_dict["safety_state"],
            "battery_state": state_dict["battery_state"],
            "cleaning_state": state_dict["cleaning_state"],
            "motor_health": state_dict["motor_health"],
            "dirt_level": state_dict["dirt_level"],
            "mission_state": state_dict["mission_state"],
            "connection_state": state_dict["connection_state"],
            "twin_quality": state_dict["twin_quality"],
            "cleaning_coverage_pct": state_dict["cleaning_coverage_pct"],
            "alarm_count": len(state_dict["active_alarms"]),
        }
        point = {
            "measurement": "robot_state",
            "tags": {"robot_id": state_dict["robot_id"]},
            "fields": fields,
            "time": datetime.now(timezone.utc),
        }
        wa.write(bucket=INFLUXDB_BUCKET, org=INFLUXDB_ORG, record=point)
    except Exception as exc:
        logger.error("InfluxDB state write error: %s", exc)


def _write_alarm(alarm: dict) -> None:
    try:
        wa = _get_write_api()
        point = {
            "measurement": "robot_alarm",
            "tags": {
                "robot_id": alarm["robot_id"],
                "alarm_type": alarm["alarm_type"],
                "severity": alarm["severity"],
            },
            "fields": {
                "description": alarm["description"],
                "value": float(alarm["value"]) if alarm.get("value") is not None else 0.0,
                "threshold": (
                    float(alarm["threshold"]) if alarm.get("threshold") is not None else 0.0
                ),
            },
            "time": datetime.now(timezone.utc),
        }
        wa.write(bucket=INFLUXDB_BUCKET, org=INFLUXDB_ORG, record=point)
    except Exception as exc:
        logger.error("InfluxDB alarm write error: %s", exc)


def _on_message(client: mqtt.Client, userdata, msg: mqtt.MQTTMessage) -> None:
    global _last_msg_time, _cleaning_coverage_pct, _sequence

    raw = msg.payload.decode("utf-8", errors="replace")
    recv_time = datetime.now(timezone.utc)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return

    try:
        telemetry = TelemetryMessage.model_validate(data)
    except ValidationError:
        return

    # Update coverage from _meta field if present (provided by simulator)
    meta = data.get("_meta", {})
    if "cleaning_coverage_pct" in meta:
        _cleaning_coverage_pct = float(meta["cleaning_coverage_pct"])

    prev_msg_time = _last_msg_time
    _last_msg_time = recv_time
    _sequence += 1

    state, alarms = rules.evaluate(telemetry, _cleaning_coverage_pct, prev_msg_time, _sequence)

    state_dict = state.model_dump()
    client.publish(Topics.STATE, json.dumps(state_dict), qos=1)

    for alarm in alarms:
        client.publish(Topics.ALERT, json.dumps(alarm), qos=1)
        _write_alarm(alarm)

    _write_state(state_dict)

    if _sequence % 30 == 0:
        logger.info(
            "State: safety=%s battery=%s motor=%s coverage=%.1f%% alarms=%d",
            state.safety_state,
            state.battery_state,
            state.motor_health,
            state.cleaning_coverage_pct,
            len(alarms),
        )


def _on_connect(client: mqtt.Client, userdata, flags, rc: int) -> None:
    if rc == 0:
        client.subscribe(Topics.TELEMETRY_VALIDATED, qos=1)
        logger.info("State engine subscribed to %s", Topics.TELEMETRY_VALIDATED)
    else:
        logger.error("MQTT connect failed rc=%d", rc)


def _start_mqtt() -> None:
    global _mqtt_client
    _mqtt_client = mqtt.Client(client_id="state-engine")
    _mqtt_client.on_connect = _on_connect
    _mqtt_client.on_message = _on_message

    for attempt in range(1, 11):
        try:
            _mqtt_client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
            _mqtt_client.loop_forever()
            return
        except Exception as exc:
            logger.warning("MQTT attempt %d: %s", attempt, exc)
            time.sleep(min(2**attempt, 30))
    logger.error("Cannot connect to MQTT — state engine failed")


app = FastAPI(title="SmartClean State Engine", version="1.0")


@app.get("/health")
def health() -> dict:
    return {
        "status": "healthy",
        "uptime_s": round(time.monotonic() - _start_time, 1),
        "messages_processed": _sequence,
        "cleaning_coverage_pct": _cleaning_coverage_pct,
        "last_message": _last_msg_time.isoformat() if _last_msg_time else None,
    }


def _run_api() -> None:
    port = int(os.environ.get("STATE_ENGINE_PORT", "8002"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


def _shutdown(signum, frame) -> None:
    if _mqtt_client:
        _mqtt_client.disconnect()
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    api_thread = threading.Thread(target=_run_api, daemon=True)
    api_thread.start()

    _start_mqtt()
