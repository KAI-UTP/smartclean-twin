"""AI / Behaviour Service.

Subscribes to validated telemetry, runs motor-health and dirt-level
classifiers, publishes predictions via MQTT and stores them in InfluxDB.
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
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
from pydantic import ValidationError

sys.path.insert(0, "/app/shared")

from smartclean_common.models import TelemetryMessage
from smartclean_common.topics import Topics
import predictor

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

_start_time = time.monotonic()
_predictions_made: int = 0
_mqtt_client: mqtt.Client | None = None
_influx_client: InfluxDBClient | None = None
_write_api = None


def _get_write_api():
    global _influx_client, _write_api
    if _write_api is None:
        _influx_client = InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)
        _write_api = _influx_client.write_api(write_options=SYNCHRONOUS)
    return _write_api


def _write_prediction(robot_id: str, result: dict) -> None:
    try:
        wa = _get_write_api()
        point = (
            Point("robot_prediction")
            .tag("robot_id", robot_id)
            .tag("model", result.get("model_used", "unknown"))
            .field("motor_health", str(result["motor_health_prediction"]))
            .field("motor_health_confidence", float(result["motor_health_confidence"]))
            .field("dirt_level", str(result["dirt_level_prediction"]))
            .field("dirt_level_confidence", float(result["dirt_level_confidence"]))
            .time(datetime.now(timezone.utc))
        )
        wa.write(bucket=INFLUXDB_BUCKET, org=INFLUXDB_ORG, record=point)
    except Exception as exc:
        logger.error("InfluxDB prediction write error: %s", exc)


def _on_message(client: mqtt.Client, userdata, msg: mqtt.MQTTMessage) -> None:
    global _predictions_made
    try:
        data = json.loads(msg.payload.decode())
        telemetry = TelemetryMessage.model_validate(data)
    except (json.JSONDecodeError, ValidationError):
        return

    s = telemetry.sensors
    a = telemetry.actuators
    result = predictor.predict(
        motor_current_a=s.motor_current_a,
        motor_temperature_c=s.motor_temperature_c,
        speed_mps=telemetry.pose.speed_mps,
        brush_on=a.brush_on,
        pump_on=a.pump_on,
        battery_a=s.battery_a,
        dirt_score=s.dirt_score,
    )

    prediction_msg = {
        "robot_id": telemetry.robot_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model_version": "1.0",
        **result,
    }
    client.publish(Topics.PREDICTION, json.dumps(prediction_msg), qos=1)
    _write_prediction(telemetry.robot_id, result)
    _predictions_made += 1

    if _predictions_made % 60 == 0:
        logger.info(
            "Predictions made=%d motor=%s dirt=%s model=%s",
            _predictions_made,
            result["motor_health_prediction"],
            result["dirt_level_prediction"],
            result.get("model_used"),
        )


def _on_connect(client: mqtt.Client, userdata, flags, rc: int) -> None:
    if rc == 0:
        client.subscribe(Topics.TELEMETRY_VALIDATED, qos=1)
        logger.info("AI service subscribed to %s", Topics.TELEMETRY_VALIDATED)
    else:
        logger.error("MQTT connect failed rc=%d", rc)


def _start_mqtt() -> None:
    global _mqtt_client
    _mqtt_client = mqtt.Client(client_id="ai-service")
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
    logger.error("Cannot connect to MQTT — AI service failed")


app = FastAPI(title="SmartClean AI Service", version="1.0")


@app.get("/health")
def health() -> dict:
    return {
        "status": "healthy",
        "uptime_s": round(time.monotonic() - _start_time, 1),
        "model_loaded": predictor._loaded,
        "predictions_made": _predictions_made,
    }


def _run_api() -> None:
    port = int(os.environ.get("AI_SERVICE_PORT", "8003"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


def _shutdown(signum, frame) -> None:
    if _mqtt_client:
        _mqtt_client.disconnect()
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    predictor.load_models()

    api_thread = threading.Thread(target=_run_api, daemon=True)
    api_thread.start()

    _start_mqtt()
