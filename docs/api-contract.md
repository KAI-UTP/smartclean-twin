# SmartClean Twin — Microservice Interface Contract

**Project:** SmartClean Twin — RBB2013 Digital Twin May 2026  
**Version:** 1.0  
**Author:** Chan Li Kai (22010900)

This document specifies the complete interface contract between every pair of microservices in the SmartClean Twin system: the route/topic, port, protocol, data format, and the conditions under which each communication is initiated and concluded.

---

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Docker Network                           │
│                                                                 │
│  [Robot Simulator] ──MQTT pub──► [Mosquitto] ──MQTT sub──►      │
│       :8004                        :1883      [Telemetry         │
│         ▲                                      Ingestion]        │
│         │ MQTT sub (ACK)                         :8001           │
│         │                                          │             │
│  [Command API] ──MQTT pub──► [Mosquitto]       InfluxDB write    │
│       :8000           (commands)                   │             │
│         ▲                                          ▼             │
│         │ HTTP POST                           [InfluxDB]         │
│    (operator)                                   :8086            │
│                                                   ▲             │
│                                      ┌────────────┘             │
│                              MQTT sub│         InfluxDB write    │
│                          [State Engine] ──────────────────►      │
│                               :8002                             │
│                          [AI Service]  ──────────────────►      │
│                               :8003                             │
│                                                                 │
│  [Grafana] ──Flux HTTP──► [InfluxDB]                            │
│    :3000                    :8086                               │
└─────────────────────────────────────────────────────────────────┘
```

---

## 1. Robot Simulator → Mosquitto (Telemetry Raw)

| Property | Value |
|----------|-------|
| **Protocol** | MQTT 3.1.1 |
| **Broker host** | `mosquitto` (Docker DNS) |
| **Port** | `1883` |
| **Topic** | `smartclean/telemetry/raw` |
| **QoS** | 1 (at-least-once) |
| **Direction** | Simulator **publishes**, broker forwards |
| **Frequency** | Every 1 second |
| **Initiated** | On simulator startup after MQTT connect succeeds |
| **Concluded** | On SIGTERM / SIGINT received by simulator |

**Data Format (JSON):**
```json
{
  "robot_id": "SCR01",
  "timestamp": "2026-07-01T10:00:00.000000Z",
  "pose": {
    "x_m": 1.5,
    "y_m": 2.0,
    "heading_deg": 90.0,
    "speed_mps": 0.3
  },
  "sensors": {
    "battery_soc": 87.3,
    "battery_v": 24.1,
    "battery_a": 2.1,
    "motor_current_a": 0.85,
    "motor_temperature_c": 26.5,
    "obstacle_cm": 150.0,
    "dirt_score": 0.12
  },
  "actuators": {
    "brush_on": true,
    "pump_on": true,
    "left_motor_pwm": 0.6,
    "right_motor_pwm": 0.6
  },
  "_meta": {
    "cleaning_coverage_pct": 34.2,
    "sequence": 142
  }
}
```

---

## 2. Mosquitto → Telemetry Ingestion Service (Telemetry Raw)

| Property | Value |
|----------|-------|
| **Protocol** | MQTT 3.1.1 |
| **Port** | `1883` |
| **Topic subscribed** | `smartclean/telemetry/raw` |
| **QoS** | 1 |
| **Direction** | Ingestion **subscribes** |
| **Client ID** | `telemetry-ingestion` |
| **Initiated** | On service startup; reconnects with exponential back-off (max 30s) |
| **Concluded** | On SIGTERM |

Ingestion validates the message against the `TelemetryMessage` Pydantic model. Invalid messages are **dropped and logged**; valid messages are forwarded to `smartclean/telemetry/validated`.

---

## 3. Telemetry Ingestion → Mosquitto (Telemetry Validated)

| Property | Value |
|----------|-------|
| **Protocol** | MQTT 3.1.1 |
| **Port** | `1883` |
| **Topic** | `smartclean/telemetry/validated` |
| **QoS** | 1 |
| **Direction** | Ingestion **publishes** |
| **Frequency** | Once per valid raw message (~1 Hz) |
| **Initiated** | Immediately after Pydantic validation passes |
| **Concluded** | When ingestion service stops |

**Data Format:** Same JSON schema as §1, with invalid fields stripped by Pydantic coercion.

---

## 4. Telemetry Ingestion → InfluxDB (Telemetry Write)

| Property | Value |
|----------|-------|
| **Protocol** | HTTP/1.1 |
| **Host** | `influxdb` (Docker DNS) |
| **Port** | `8086` |
| **Route** | `POST /api/v2/write?org=smartclean&bucket=smartclean_twin&precision=ns` |
| **Auth** | `Authorization: Token smartclean-super-secret-token` |
| **Content-Type** | `application/vnd.influxdb.v2+csv` (InfluxDB Line Protocol) |
| **Initiated** | Per valid telemetry message, synchronous write |
| **Concluded** | After write acknowledgement (HTTP 204) |

**InfluxDB Line Protocol — Measurement `robot_telemetry`:**
```
robot_telemetry,robot_id=SCR01 battery_soc=87.3,battery_v=24.1,battery_a=2.1,
  motor_current_a=0.85,motor_temperature_c=26.5,obstacle_cm=150.0,
  dirt_score=0.12,x_m=1.5,y_m=2.0,heading_deg=90.0,speed_mps=0.3 1751356800000000000
```

---

## 5. Mosquitto → State Engine (Telemetry Validated)

| Property | Value |
|----------|-------|
| **Protocol** | MQTT 3.1.1 |
| **Port** | `1883` |
| **Topic subscribed** | `smartclean/telemetry/validated` |
| **QoS** | 1 |
| **Client ID** | `state-engine` |
| **Initiated** | On State Engine startup |
| **Concluded** | On SIGTERM |

State engine applies rule-based logic (`rules.py`) to compute 11 state variables and 0–N alarms.

---

## 6. State Engine → Mosquitto (State + Alerts)

| Property | Value |
|----------|-------|
| **Protocol** | MQTT 3.1.1 |
| **Port** | `1883` |
| **Topic (state)** | `smartclean/state` |
| **Topic (alerts)** | `smartclean/alerts` |
| **QoS** | 1 |
| **Frequency** | Once per validated telemetry message |
| **Initiated** | After `rules.evaluate()` returns |

**State Message Format (JSON):**
```json
{
  "robot_id": "SCR01",
  "timestamp": "2026-07-01T10:00:00Z",
  "safety_state": "SAFE",
  "battery_state": "NORMAL",
  "mission_state": "RUNNING",
  "motion_state": "MOVING",
  "motor_health": "NORMAL",
  "dirt_level": "MODERATE",
  "connection_state": "ONLINE",
  "twin_quality": "SYNCHRONIZED",
  "cleaning_coverage_pct": 34.2,
  "active_alarms": []
}
```

**Alert Message Format (JSON):**
```json
{
  "robot_id": "SCR01",
  "alarm_type": "OBSTACLE_EMERGENCY",
  "severity": "CRITICAL",
  "description": "Obstacle at 18.0 cm — below 25 cm threshold",
  "value": 18.0,
  "threshold": 25.0
}
```

---

## 7. State Engine → InfluxDB (State Write)

| Property | Value |
|----------|-------|
| **Protocol** | HTTP/1.1 |
| **Port** | `8086` |
| **Route** | `POST /api/v2/write` |
| **Measurement** | `robot_state`, `robot_alarm` |
| **Initiated** | Per telemetry cycle (synchronous, SYNCHRONOUS write mode) |

**Measurement `robot_state` fields:**

| Field | Type | Example |
|-------|------|---------|
| `safety_state` | string | `"SAFE"` |
| `battery_state` | string | `"NORMAL"` |
| `mission_state` | string | `"RUNNING"` |
| `motion_state` | string | `"MOVING"` |
| `motor_health` | string | `"NORMAL"` |
| `dirt_level` | string | `"MODERATE"` |
| `connection_state` | string | `"ONLINE"` |
| `twin_quality` | string | `"SYNCHRONIZED"` |
| `cleaning_coverage_pct` | float | `34.2` |
| `alarm_count` | int | `0` |

---

## 8. Mosquitto → AI Service (Telemetry Validated)

| Property | Value |
|----------|-------|
| **Protocol** | MQTT 3.1.1 |
| **Port** | `1883` |
| **Topic subscribed** | `smartclean/telemetry/validated` |
| **QoS** | 1 |
| **Client ID** | `ai-service` |

AI service extracts 7 features (motor_current_a, motor_temperature_c, speed_mps, brush_on, pump_on, battery_a, dirt_score) and runs two RandomForest classifiers.

---

## 9. AI Service → Mosquitto (Predictions)

| Property | Value |
|----------|-------|
| **Protocol** | MQTT 3.1.1 |
| **Port** | `1883` |
| **Topic** | `smartclean/predictions` |
| **QoS** | 1 |

**Prediction Message Format (JSON):**
```json
{
  "robot_id": "SCR01",
  "timestamp": "2026-07-01T10:00:00Z",
  "model_version": "1.0",
  "motor_health_prediction": "NORMAL",
  "motor_health_confidence": 0.89,
  "dirt_level_prediction": "CLEAN",
  "dirt_level_confidence": 1.0,
  "model_used": "random_forest"
}
```

---

## 10. AI Service → InfluxDB (Prediction Write)

| Property | Value |
|----------|-------|
| **Protocol** | HTTP/1.1 |
| **Port** | `8086` |
| **Measurement** | `robot_prediction` |
| **Tags** | `robot_id`, `model` |
| **Fields** | `motor_health` (string), `motor_health_confidence` (float), `dirt_level` (string), `dirt_level_confidence` (float) |

---

## 11. Operator → Command API (Command Injection)

| Property | Value |
|----------|-------|
| **Protocol** | HTTP/1.1 |
| **Host** | `localhost` |
| **Port** | `8000` |
| **Route** | `POST /command` |
| **Content-Type** | `application/json` |
| **Auth** | None (internal network) |
| **Initiated** | On operator request (manual or programmatic) |

**Request Body:**
```json
{"robot_id": "SCR01", "command": "PAUSE", "params": {}}
```

**Valid commands:** `PAUSE`, `RESUME`, `STOP`, `EMERGENCY_STOP`, `SET_SPEED`

**Response (HTTP 200):**
```json
{
  "status": "acknowledged",
  "command": "PAUSE",
  "robot_id": "SCR01",
  "latency_ms": 45
}
```

---

## 12. Command API → Mosquitto → Simulator (Command Flow)

| Property | Value |
|----------|-------|
| **Protocol** | MQTT 3.1.1 |
| **Port** | `1883` |
| **Topic (command)** | `smartclean/commands` |
| **Topic (ACK)** | `smartclean/acks` |
| **QoS** | 1 |
| **Timeout** | 5 seconds (Command API waits for ACK) |
| **Initiated** | Command API receives HTTP POST |
| **Concluded** | ACK received from simulator OR timeout |

---

## 13. Robot Simulator → Fault Injection API

| Property | Value |
|----------|-------|
| **Protocol** | HTTP/1.1 |
| **Host** | `localhost` |
| **Port** | `8004` |
| **Route** | `POST /fault` |
| **Content-Type** | `application/json` |

**Request Body:**
```json
{"fault": "obstacle"}
```

**Valid faults:** `obstacle`, `motor`, `battery`, `clear`

---

## 14. Grafana → InfluxDB (Flux Queries)

| Property | Value |
|----------|-------|
| **Protocol** | HTTP/1.1 |
| **Port** | `8086` |
| **Route** | `POST /api/v2/query?org=smartclean` |
| **Content-Type** | `application/vnd.flux` |
| **Auth** | `Authorization: Token smartclean-super-secret-token` |
| **Frequency** | Every 5 seconds (Grafana auto-refresh) |
| **Initiated** | On dashboard load and on each refresh tick |
| **Measurements queried** | `robot_telemetry`, `robot_state`, `robot_prediction`, `robot_alarm` |

---

## 15. Health Check Endpoints

Each microservice exposes a REST health endpoint:

| Service | Port | Route | Response |
|---------|------|-------|----------|
| Command API | 8000 | `GET /health` | `{"status": "healthy", ...}` |
| Telemetry Ingestion | 8001 | `GET /health` | `{"status": "healthy", ...}` |
| State Engine | 8002 | `GET /health` | `{"status": "healthy", "messages_processed": N}` |
| AI Service | 8003 | `GET /health` | `{"status": "healthy", "predictions_made": N}` |
| Robot Simulator | 8004 | `GET /health` | `{"status": "healthy", "battery_soc": X}` |
| Mosquitto | 1883 | TCP connect | (MQTT protocol) |
| InfluxDB | 8086 | `GET /health` | `{"status": "pass"}` |
| Grafana | 3000 | `GET /api/health` | `{"database": "ok"}` |

---

## Port Summary

| Service | Internal Port | External Port | Protocol |
|---------|--------------|---------------|----------|
| Mosquitto | 1883 | 1883 | MQTT |
| InfluxDB | 8086 | 8086 | HTTP |
| Grafana | 3000 | 3000 | HTTP |
| Command API | 8000 | 8000 | HTTP |
| Telemetry Ingestion | 8001 | 8001 | HTTP |
| State Engine | 8002 | 8002 | HTTP |
| AI Service | 8003 | 8003 | HTTP |
| Robot Simulator | 8004 | 8004 | HTTP |
