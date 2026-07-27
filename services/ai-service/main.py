"""AI / Behaviour Service.

Subscribes to validated telemetry and twin state, runs five AI models
(motor health, dirt level, health state, RUL regression, anomaly
detection), computes operational forecasts (battery time-to-empty,
cleaning time-to-finish), generates operator recommendations, publishes
everything via MQTT and stores it in InfluxDB.

Also exposes POST /whatif — a what-if simulation endpoint where
hypothetical sensor values return predicted health/RUL without touching
the real robot.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import threading
import time
from collections import deque
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
import uvicorn
from fastapi import FastAPI
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
from pydantic import BaseModel, Field, ValidationError

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

# Rolling history for trend-based forecasts: (monotonic_seconds, value)
_soc_history: deque[tuple[float, float]] = deque(maxlen=90)
_coverage_history: deque[tuple[float, float]] = deque(maxlen=90)
_history_lock = threading.Lock()


def _trend_per_minute(history: deque[tuple[float, float]], window_s: float = 60.0) -> float | None:
    """Rate of change per minute over the recent window, or None if not enough data."""
    with _history_lock:
        points = list(history)
    if len(points) < 5:
        return None
    now = points[-1][0]
    recent = [(t, v) for t, v in points if now - t <= window_s]
    if len(recent) < 5 or recent[-1][0] == recent[0][0]:
        return None
    dt_min = (recent[-1][0] - recent[0][0]) / 60.0
    return (recent[-1][1] - recent[0][1]) / dt_min


def _battery_minutes_to_empty(current_soc: float) -> float | None:
    """Minutes until 20% SoC (auto-return threshold) at the current discharge rate."""
    rate = _trend_per_minute(_soc_history)
    if rate is None or rate >= -0.001:  # not discharging (charging or idle)
        return None
    return max(0.0, (current_soc - 20.0) / -rate)


def _cleaning_minutes_to_finish(current_coverage: float) -> float | None:
    """Minutes until 100% coverage at the current cleaning rate."""
    rate = _trend_per_minute(_coverage_history)
    if rate is None or rate <= 0.001:  # not making progress
        return None
    return max(0.0, (100.0 - current_coverage) / rate)


def _build_recommendation(result: dict, minutes_to_empty: float | None) -> str:
    """Operator recommendation derived from the combined AI outputs."""
    if result["health_state_prediction"] == "CRITICAL":
        return "STOP robot and inspect motor immediately"
    if result["is_anomaly"]:
        return "Sensor anomaly detected: verify sensors and inspect robot"
    if minutes_to_empty is not None and minutes_to_empty < 10:
        return "Battery low: return to dock within 10 minutes"
    if result["health_state_prediction"] == "WARNING":
        return "Schedule maintenance soon: monitor temperature and load"
    if result["motor_health_prediction"] in ("OVERHEATED", "FAULT"):
        return "Motor issue detected: reduce load or stop for cooling"
    return "Normal operation, no action needed"


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
            .field("health_state", str(result["health_state_prediction"]))
            .field("health_state_confidence", float(result["health_state_confidence"]))
            .field("predicted_rul_minutes", float(result["predicted_rul_minutes"]))
            .field("anomaly_score", float(result["anomaly_score"]))
            .field("is_anomaly", 1 if result["is_anomaly"] else 0)
            .field("recommendation", str(result.get("recommendation", "")))
            .time(datetime.now(timezone.utc))
        )
        if result.get("minutes_to_empty") is not None:
            point = point.field("minutes_to_empty", float(result["minutes_to_empty"]))
        if result.get("minutes_to_finish") is not None:
            point = point.field("minutes_to_finish", float(result["minutes_to_finish"]))
        wa.write(bucket=INFLUXDB_BUCKET, org=INFLUXDB_ORG, record=point)
    except Exception as exc:
        logger.error("InfluxDB prediction write error: %s", exc)


def _on_state_message(data: dict) -> None:
    """Track cleaning coverage from twin state for time-to-finish forecast."""
    coverage = data.get("cleaning_coverage_pct")
    if coverage is not None:
        with _history_lock:
            _coverage_history.append((time.monotonic(), float(coverage)))


def _on_message(client: mqtt.Client, userdata, msg: mqtt.MQTTMessage) -> None:
    global _predictions_made
    try:
        data = json.loads(msg.payload.decode())
    except json.JSONDecodeError:
        return

    if msg.topic == Topics.STATE:
        _on_state_message(data)
        return

    try:
        telemetry = TelemetryMessage.model_validate(data)
    except ValidationError:
        return

    s = telemetry.sensors
    a = telemetry.actuators

    with _history_lock:
        _soc_history.append((time.monotonic(), s.battery_soc))

    result = predictor.predict(
        motor_current_a=s.motor_current_a,
        motor_temperature_c=s.motor_temperature_c,
        speed_mps=telemetry.pose.speed_mps,
        brush_on=a.brush_on,
        pump_on=a.pump_on,
        battery_a=s.battery_a,
        dirt_score=s.dirt_score,
        battery_v=s.battery_v,
        battery_soc=s.battery_soc,
        water_level_pct=s.water_level_pct,
    )

    # Trend-based operational forecasts
    minutes_to_empty = _battery_minutes_to_empty(s.battery_soc)
    minutes_to_finish = _cleaning_minutes_to_finish(
        _coverage_history[-1][1] if _coverage_history else 0.0
    )
    result["minutes_to_empty"] = round(minutes_to_empty, 1) if minutes_to_empty else None
    result["minutes_to_finish"] = round(minutes_to_finish, 1) if minutes_to_finish else None
    result["recommendation"] = _build_recommendation(result, minutes_to_empty)

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
            "Predictions made=%d motor=%s dirt=%s health=%s rul=%.1fmin model=%s",
            _predictions_made,
            result["motor_health_prediction"],
            result["dirt_level_prediction"],
            result["health_state_prediction"],
            result["predicted_rul_minutes"],
            result.get("model_used"),
        )


def _on_connect(client: mqtt.Client, userdata, flags, rc: int) -> None:
    if rc == 0:
        client.subscribe(Topics.TELEMETRY_VALIDATED, qos=1)
        client.subscribe(Topics.STATE, qos=1)
        logger.info("AI service subscribed to %s and %s", Topics.TELEMETRY_VALIDATED, Topics.STATE)
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


class WhatIfRequest(BaseModel):
    """Hypothetical sensor values for what-if simulation."""

    motor_current_a: float = Field(default=0.8, ge=0.0, le=10.0)
    motor_temperature_c: float = Field(default=40.0, ge=-10.0, le=120.0)
    speed_mps: float = Field(default=0.2, ge=0.0, le=2.0)
    brush_on: bool = True
    pump_on: bool = False
    battery_a: float = Field(default=1.4, ge=0.0, le=10.0)
    dirt_score: float = Field(default=0.3, ge=0.0, le=1.0)
    battery_v: float = Field(default=11.5, ge=0.0, le=15.0)
    battery_soc: float = Field(default=70.0, ge=0.0, le=100.0)
    water_level_pct: float = Field(default=80.0, ge=0.0, le=100.0)


@app.post("/whatif")
def whatif(req: WhatIfRequest) -> dict:
    """What-if simulation: run all AI models on hypothetical sensor values.

    Lets an operator test scenarios ("what if the motor hits 85 °C under
    full load?") without touching the real robot — a core Digital Twin
    capability.
    """
    result = predictor.predict(
        motor_current_a=req.motor_current_a,
        motor_temperature_c=req.motor_temperature_c,
        speed_mps=req.speed_mps,
        brush_on=req.brush_on,
        pump_on=req.pump_on,
        battery_a=req.battery_a,
        dirt_score=req.dirt_score,
        battery_v=req.battery_v,
        battery_soc=req.battery_soc,
        water_level_pct=req.water_level_pct,
    )
    result["recommendation"] = _build_recommendation(result, None)
    return {"scenario": req.model_dump(), "prediction": result}


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
