#!/usr/bin/env python3
"""Pre-populate InfluxDB with 15 minutes of realistic demo data.

Useful for Grafana dashboard screenshots when the simulator has just started.
Run AFTER the stack is up: python scripts/generate_demo_data.py
"""

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))

from influxdb_client import InfluxDBClient
from influxdb_client.client.write_api import SYNCHRONOUS

URL = os.environ.get("INFLUXDB_URL", "http://localhost:8086")
TOKEN = os.environ.get("INFLUXDB_TOKEN", "smartclean-super-secret-token")
ORG = os.environ.get("INFLUXDB_ORG", "smartclean")
BUCKET = os.environ.get("INFLUXDB_BUCKET", "smartclean_twin")

client = InfluxDBClient(url=URL, token=TOKEN, org=ORG)
write_api = client.write_api(write_options=SYNCHRONOUS)

start = datetime.now(timezone.utc) - timedelta(minutes=15)
N = 900  # one point per second


def write_batch(points: list[dict]) -> None:
    write_api.write(bucket=BUCKET, org=ORG, record=points)


print(f"Writing {N} demo data points...")
telemetry_points = []
state_points = []
pred_points = []

for i in range(N):
    t = start + timedelta(seconds=i)
    soc = max(60.0, 100.0 - i * 0.022)
    coverage = min(95.0, i / N * 100.0)
    current = 0.8 + (0.5 if i % 60 < 10 else 0.0)
    temp = 30.0 + min(45.0, i * 0.04)

    telemetry_points.append(
        {
            "measurement": "robot_telemetry",
            "tags": {"robot_id": "SCR01"},
            "fields": {
                "battery_soc": soc,
                "battery_v": 10.0 + soc / 100.0 * 2.6,
                "battery_a": 1.2,
                "motor_current_a": current,
                "motor_temperature_c": temp,
                "obstacle_cm": 150.0 if i % 90 != 45 else 15.0,
                "dirt_score": max(0.0, 0.7 - coverage / 200.0),
                "speed_mps": 0.2,
                "x_m": (i % 8) * 0.5,
                "y_m": (i // 8 % 8) * 0.5,
                "heading_deg": 90.0,
                "water_level_pct": max(20.0, 100.0 - i * 0.008),
                "bumper_active": 0,
                "brush_on": 1,
                "pump_on": 0,
                "sequence": i,
            },
            "time": t,
        }
    )

    state_points.append(
        {
            "measurement": "robot_state",
            "tags": {"robot_id": "SCR01"},
            "fields": {
                "safety_state": "EMERGENCY" if i % 90 == 45 else "SAFE",
                "battery_state": "CRITICAL" if soc < 10 else "LOW" if soc < 20 else "NORMAL",
                "motor_health": "HIGH_LOAD" if current > 2.5 else "NORMAL",
                "mission_state": "COMPLETED" if coverage >= 90 else "RUNNING",
                "cleaning_coverage_pct": coverage,
                "alarm_count": 1 if i % 90 == 45 else 0,
            },
            "time": t,
        }
    )

    pred_points.append(
        {
            "measurement": "robot_prediction",
            "tags": {"robot_id": "SCR01", "model": "random_forest"},
            "fields": {
                "motor_health": "HIGH_LOAD" if current > 2.5 else "NORMAL",
                "motor_health_confidence": 0.95,
                "dirt_level": (
                    "DIRTY" if coverage < 30 else "MODERATE" if coverage < 70 else "CLEAN"
                ),
                "dirt_level_confidence": 0.92,
            },
            "time": t,
        }
    )

    if len(telemetry_points) >= 100:
        write_batch(telemetry_points)
        write_batch(state_points)
        write_batch(pred_points)
        telemetry_points.clear()
        state_points.clear()
        pred_points.clear()
        print(f"  Written {i+1}/{N} points...")

if telemetry_points:
    write_batch(telemetry_points)
    write_batch(state_points)
    write_batch(pred_points)

client.close()
print(f"Done. {N} telemetry, state and prediction points written.")
