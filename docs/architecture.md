# SmartClean Twin — Architecture & Interface Contracts

## System Overview

SmartClean Twin is a software-emulated Digital Twin for a mobile inspection and cleaning robot. All services run as Docker containers communicating through Eclipse Mosquitto (MQTT) and InfluxDB (HTTP). No physical hardware is required for the assessed prototype.

---

## Interface Contract Table

| Source | Destination | Route / Topic | Port | Protocol | Format | Initiated when | Concluded when |
|--------|------------|--------------|------|----------|--------|---------------|---------------|
| Robot Simulator | MQTT Broker | `smartclean/SCR01/telemetry/raw` | 1883 | MQTT QoS 1 | JSON | Every `TELEMETRY_INTERVAL_S` seconds | Simulator stops |
| MQTT Broker | Telemetry Ingestion | Subscription to `telemetry/raw` | 1883 | MQTT | JSON | On broker receipt | After validation |
| Telemetry Ingestion | MQTT Broker | `smartclean/SCR01/telemetry/validated` | 1883 | MQTT QoS 1 | JSON | On valid message | After publish |
| Telemetry Ingestion | InfluxDB | `POST /api/v2/write` | 8086 | HTTP | InfluxDB line protocol | After validation | After write confirmation |
| MQTT Broker | State Engine | Subscription to `telemetry/validated` | 1883 | MQTT | JSON | On broker receipt | After state publish |
| State Engine | MQTT Broker | `smartclean/SCR01/state` | 1883 | MQTT QoS 1 | JSON | After rule evaluation | After publish |
| State Engine | MQTT Broker | `smartclean/SCR01/alert` | 1883 | MQTT QoS 1 | JSON | When alarm condition met | After publish |
| State Engine | InfluxDB | `POST /api/v2/write` | 8086 | HTTP | Line protocol | After state computation | After write |
| MQTT Broker | AI Service | Subscription to `telemetry/validated` | 1883 | MQTT | JSON | On broker receipt | After prediction |
| AI Service | MQTT Broker | `smartclean/SCR01/prediction` | 1883 | MQTT QoS 1 | JSON | After inference | After publish |
| AI Service | InfluxDB | `POST /api/v2/write` | 8086 | HTTP | Line protocol | After inference | After write |
| User | Command API | `POST /api/v1/commands` | 8000 | HTTP/REST | JSON | User request | ACK received or timeout |
| Command API | MQTT Broker | `smartclean/SCR01/command/motion` or `command/cleaning` | 1883 | MQTT QoS 1 | JSON | On command receipt | After publish |
| MQTT Broker | Robot Simulator | Subscription to `command/#` | 1883 | MQTT | JSON | On broker receipt | After command applied |
| Robot Simulator | MQTT Broker | `smartclean/SCR01/ack` | 1883 | MQTT QoS 1 | JSON | After command applied | After publish |
| MQTT Broker | Command API | Subscription to `ack` | 1883 | MQTT | JSON | On broker receipt | ACK delivered to waiting thread |
| Command API | InfluxDB | `POST /api/v2/write` | 8086 | HTTP | Line protocol | On command + ACK | After write |
| InfluxDB | Grafana | Flux query via data source | 8086 | HTTP | CSV | On dashboard panel refresh | After result |
| User | Grafana | Dashboard | 3000 | HTTP | Web | User browser | User closes browser |

---

## MQTT Topic Table

| Topic | Publisher | Subscriber(s) | QoS | Description |
|-------|-----------|--------------|-----|-------------|
| `smartclean/SCR01/telemetry/raw` | Robot Simulator | Telemetry Ingestion | 1 | Full telemetry message every tick |
| `smartclean/SCR01/telemetry/validated` | Telemetry Ingestion | State Engine, AI Service | 1 | Validated and timestamped telemetry |
| `smartclean/SCR01/state` | State Engine | (Grafana via InfluxDB) | 1 | DT state computed from rules |
| `smartclean/SCR01/prediction` | AI Service | (Grafana via InfluxDB) | 1 | Motor health + dirt level prediction |
| `smartclean/SCR01/alert` | State Engine | (logging, InfluxDB) | 1 | Alarm messages |
| `smartclean/SCR01/command/motion` | Command API | Robot Simulator | 1 | START, PAUSE, RESUME, STOP, RETURN_HOME |
| `smartclean/SCR01/command/cleaning` | Command API | Robot Simulator | 1 | BRUSH_ON/OFF, PUMP_ON/OFF |
| `smartclean/SCR01/ack` | Robot Simulator | Command API | 1 | Command acknowledgement |
| `smartclean/SCR01/service/health` | Robot Simulator | (monitoring) | 0 | Heartbeat |

---

## Digital Twin State Table

| State Variable | Possible Values | Derived From |
|---------------|----------------|-------------|
| motion_state | STOPPED, MOVING, TURNING, AVOIDING | speed_mps, obstacle_cm |
| operation_mode | IDLE, INSPECTING, CLEANING, RETURNING | mission.mode |
| safety_state | SAFE, WARNING, EMERGENCY | obstacle_cm, bumper_active |
| battery_state | NORMAL, LOW, CRITICAL, CHARGING | battery_soc |
| cleaning_state | OFF, ACTIVE, REPEAT_REQUIRED | brush_on, dirt_score |
| motor_health | NORMAL, HIGH_LOAD, OVERHEATED, FAULT | motor_current_a, motor_temperature_c |
| dirt_level | CLEAN, MODERATE, DIRTY | dirt_score |
| mission_state | NOT_STARTED, RUNNING, PAUSED, COMPLETED, FAILED | operation_mode, coverage, alarms |
| connection_state | ONLINE, DELAYED, OFFLINE | message arrival time |
| twin_quality | SYNCHRONIZED, DELAYED, INVALID | message delay |
| cleaning_coverage_pct | 0–100 | cleaned_cells / total_accessible × 100 |

---

## Behaviour Rule Table

| Condition | Effect | Alarm Generated |
|-----------|--------|----------------|
| obstacle_cm < 25 | safety_state = EMERGENCY, motion_state = STOPPED | OBSTACLE_EMERGENCY (CRITICAL) |
| 25 ≤ obstacle_cm < 50 | safety_state = WARNING, motion_state = AVOIDING | — |
| bumper_active = true | safety_state = EMERGENCY | OBSTACLE_EMERGENCY (CRITICAL) |
| battery_soc < 10 | battery_state = CRITICAL | BATTERY_CRITICAL (CRITICAL) |
| battery_soc < 20 | battery_state = LOW, mission_state → RETURNING | — |
| motor_current_a > 2.5 | motor_health = HIGH_LOAD | MOTOR_HIGH_LOAD (WARNING) |
| motor_temperature_c > 70 | motor_health = OVERHEATED | MOTOR_OVERHEATED (CRITICAL) |
| motor_current_a > 3.5 AND motor_temp > 70 | motor_health = FAULT | MOTOR_OVERHEATED (CRITICAL) |
| water_level_pct < 10 | — | LOW_WATER (WARNING) |
| message delay > 2s | connection_state = DELAYED, twin_quality = DELAYED | — |
| message delay > 10s | connection_state = OFFLINE, twin_quality = INVALID | — |
| coverage ≥ 90% AND no critical alarm | mission_state = COMPLETED | — |

---

## AI Model Documentation

**Model:** Random Forest Classifier  
**Framework:** scikit-learn 1.6  
**Training data:** 5000 synthetically generated samples with deterministic labelling rules  
**No data leakage:** train/test split is performed before any feature transformation  

### Motor Health Classifier

**Input features:** motor_current_a, motor_temperature_c, speed_mps, brush_on, pump_on, battery_a  
**Output classes:** NORMAL, HIGH_LOAD, OVERHEATED, FAULT  

**Labelling rules:**
- FAULT: current > 3.5 A AND temperature > 70°C
- OVERHEATED: temperature > 70°C
- HIGH_LOAD: current > 2.5 A OR (current > 1.5 A AND brush_on)
- NORMAL: otherwise

### Dirt Level Classifier

**Input features:** dirt_score  
**Output classes:** CLEAN, MODERATE, DIRTY  

**Labelling rules:**
- DIRTY: dirt_score ≥ 0.7
- MODERATE: 0.3 ≤ dirt_score < 0.7
- CLEAN: dirt_score < 0.3

**Target accuracy:** ≥ 80% on held-out test set  
**Fallback:** Rule-based predictor is used if model files are not found  
**Model persistence:** Saved with `joblib` to `/app/models/` inside the container  

---

## InfluxDB Measurements

| Measurement | Tags | Key Fields | Written by |
|-------------|------|-----------|-----------|
| robot_telemetry | robot_id | x_m, y_m, battery_soc, motor_current_a, dirt_score, … | Telemetry Ingestion |
| robot_telemetry_invalid | reason | count, raw_preview | Telemetry Ingestion |
| robot_state | robot_id | safety_state, battery_state, motor_health, cleaning_coverage_pct, … | State Engine |
| robot_alarm | robot_id, alarm_type, severity | description, value, threshold | State Engine |
| robot_prediction | robot_id, model | motor_health, motor_health_confidence, dirt_level, … | AI Service |
| robot_command | robot_id, command | command_id, status | Command API |
| robot_acknowledgement | robot_id, command, accepted | command_id, latency_ms | Command API |
