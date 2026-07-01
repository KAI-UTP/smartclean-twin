"""Telemetry Ingestion Service.

Subscribes to raw telemetry, validates it against the Pydantic schema,
records invalid messages, writes validated telemetry to InfluxDB and
re-publishes to the validated topic for downstream services.
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

_stats = {"received": 0, "valid": 0, "invalid": 0}
_start_time = time.monotonic()
_influx_client: InfluxDBClient | None = None
_write_api = None
_mqtt_client: mqtt.Client | None = None


def _get_write_api():
    global _influx_client, _write_api
    if _write_api is None:
        _influx_client = InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)
        _write_api = _influx_client.write_api(write_options=SYNCHRONOUS)
    return _write_api


def _write_telemetry_to_influx(msg: TelemetryMessage) -> None:
    try:
        wa = _get_write_api()
        tags = {"robot_id": msg.robot_id}
        fields = {
            "x_m": msg.pose.x_m,
            "y_m": msg.pose.y_m,
            "heading_deg": msg.pose.heading_deg,
            "speed_mps": msg.pose.speed_mps,
            "obstacle_cm": msg.sensors.obstacle_cm,
            "battery_v": msg.sensors.battery_v,
            "battery_soc": msg.sensors.battery_soc,
            "battery_a": msg.sensors.battery_a,
            "motor_current_a": msg.sensors.motor_current_a,
            "motor_temperature_c": msg.sensors.motor_temperature_c,
            "dirt_score": msg.sensors.dirt_score,
            "water_level_pct": msg.sensors.water_level_pct,
            "bumper_active": int(msg.sensors.bumper_active),
            "brush_on": int(msg.actuators.brush_on),
            "pump_on": int(msg.actuators.pump_on),
            "sequence": msg.sequence,
        }
        point = {
            "measurement": "robot_telemetry",
            "tags": tags,
            "fields": fields,
            "time": datetime.now(timezone.utc),
        }
        wa.write(bucket=INFLUXDB_BUCKET, org=INFLUXDB_ORG, record=point)
    except Exception as exc:
        logger.error("InfluxDB write error: %s", exc)


def _write_invalid_to_influx(raw: str, reason: str) -> None:
    try:
        wa = _get_write_api()
        point = {
            "measurement": "robot_telemetry_invalid",
            "tags": {"reason": reason[:64]},
            "fields": {"count": 1, "raw_preview": raw[:200]},
            "time": datetime.now(timezone.utc),
        }
        wa.write(bucket=INFLUXDB_BUCKET, org=INFLUXDB_ORG, record=point)
    except Exception as exc:
        logger.error("InfluxDB invalid-msg write error: %s", exc)


def _on_message(client: mqtt.Client, userdata, msg: mqtt.MQTTMessage) -> None:
    raw = msg.payload.decode("utf-8", errors="replace")
    _stats["received"] += 1

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        _stats["invalid"] += 1
        logger.warning("JSON parse error: %s", exc)
        _write_invalid_to_influx(raw, "json_decode_error")
        return

    try:
        validated = TelemetryMessage.model_validate(data)
    except ValidationError as exc:
        _stats["invalid"] += 1
        logger.warning("Validation error seq=%s: %s", data.get("sequence"), exc.error_count())
        _write_invalid_to_influx(raw, "validation_error")
        return

    _stats["valid"] += 1
    # Forward validated message
    client.publish(Topics.TELEMETRY_VALIDATED, json.dumps(data), qos=1)
    _write_telemetry_to_influx(validated)


def _on_connect(client: mqtt.Client, userdata, flags, rc: int) -> None:
    if rc == 0:
        client.subscribe(Topics.TELEMETRY_RAW, qos=1)
        logger.info("Ingestion subscribed to %s", Topics.TELEMETRY_RAW)
    else:
        logger.error("MQTT connect failed rc=%d", rc)


def _start_mqtt() -> None:
    global _mqtt_client
    _mqtt_client = mqtt.Client(client_id="telemetry-ingestion")
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
    logger.error("Cannot connect to MQTT — ingestion service failed")


# ── FastAPI health endpoint ────────────────────────────────────────────────────

app = FastAPI(title="SmartClean Telemetry Ingestion", version="1.0")


@app.get("/health")
def health() -> dict:
    return {
        "status": "healthy",
        "uptime_s": round(time.monotonic() - _start_time, 1),
        "received": _stats["received"],
        "valid": _stats["valid"],
        "invalid": _stats["invalid"],
        "valid_rate_pct": round(_stats["valid"] / max(1, _stats["received"]) * 100, 2),
    }


def _run_api() -> None:
    port = int(os.environ.get("TELEMETRY_INGESTION_PORT", "8001"))
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
