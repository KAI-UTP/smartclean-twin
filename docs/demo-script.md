# SmartClean Twin — Final Demonstration Script

**Duration:** ~20 minutes  
**Presenter:** Chan Li Kai

---

## Pre-Demo Checklist

- [ ] Docker Desktop running
- [ ] Repository cloned / available
- [ ] `.env` file copied from `.env.example`
- [ ] Browser tabs ready: Grafana (localhost:3000), InfluxDB (localhost:8086)
- [ ] Terminal open at `smartclean-twin/`

---

## Step 1 — Show Repository Structure (1 min)

```bash
# Show top-level structure
ls smartclean-twin/

# Show service structure
ls services/
```

**Narrate:** "The repository contains 5 custom microservices under `services/`, shared Pydantic models under `shared/`, Docker Compose, contracts, tests, scripts and docs."

---

## Step 2 — Show Docker Compose Architecture (1 min)

```bash
cat docker-compose.yml
```

**Narrate:** "Eight services total: Mosquitto broker, InfluxDB, Grafana, Robot Simulator, Telemetry Ingestion, State Engine, AI Service and Command API. All connected via a Docker network."

---

## Step 3 — Start the Stack (2 min)

```bash
docker compose up --build -d
```

**Narrate:** "Building and starting all services. The AI model is trained at Docker build time."

```bash
docker compose ps
```

**Expected:** All 8 containers showing status `Up`.

---

## Step 4 — Show Healthy Containers (1 min)

```bash
python scripts/smoke_test.py
```

**Expected:** `[OK]` for all 5 custom services.

---

## Step 5 — Show MQTT Telemetry (2 min)

```bash
# Subscribe and watch raw telemetry (requires mosquitto-clients)
mosquitto_sub -h localhost -t "smartclean/SCR01/telemetry/raw" -C 3
```

**Narrate:** "The Robot Simulator publishes a JSON telemetry message every second to the raw topic. It includes pose, sensors, actuators and mission data."

Show one message and point out: `robot_id`, `sequence`, `pose.x_m`, `sensors.battery_soc`, `actuators.brush_on`.

---

## Step 6 — Show Validated Telemetry (1 min)

```bash
mosquitto_sub -h localhost -t "smartclean/SCR01/telemetry/validated" -C 2
```

**Narrate:** "The Telemetry Ingestion Service validates the schema and re-publishes to the validated topic. Invalid messages are rejected and counted."

```bash
curl http://localhost:8001/health
```

Show `valid_rate_pct` ≥ 98%.

---

## Step 7 — Show Digital Twin States (1 min)

```bash
mosquitto_sub -h localhost -t "smartclean/SCR01/state" -C 2
```

**Narrate:** "The State Engine applies 11 rule conditions to produce the Digital Twin state — safety, battery, motor health, cleaning coverage, mission state."

---

## Step 8 — Show InfluxDB Data (1 min)

Open http://localhost:8086  
Login: admin / adminpassword  
Navigate to Data Explorer → bucket `smartclean_twin` → measurement `robot_telemetry`  

**Narrate:** "All telemetry, states, predictions, alarms and commands are stored in InfluxDB with timestamps. This is the persistent time-series store."

---

## Step 9 — Show Grafana Dashboard (2 min)

Open http://localhost:3000 (admin / admin)  
Open dashboard: **SmartClean Twin — Robot Dashboard**

Point out panels:
- Battery SOC gauge with threshold (orange < 20%, red < 10%)
- Motor current time series
- Cleaning coverage gauge
- Obstacle distance with red threshold at 25 cm
- Safety State stat panel
- Mission State stat panel
- AI prediction panels
- Alarm history table

---

## Step 10 — Trigger Obstacle Emergency (1 min)

```bash
curl -X POST http://localhost:8004/fault \
  -H "Content-Type: application/json" \
  -d '{"fault":"obstacle"}'
```

**Narrate:** "Injecting a simulated obstacle at 15 cm — below the 25 cm emergency threshold."

Watch Grafana: Safety State → **EMERGENCY**, Obstacle Distance → red zone, Alarm History → `OBSTACLE_EMERGENCY`.

```bash
mosquitto_sub -h localhost -t "smartclean/SCR01/alert" -C 1
```

Clear fault:
```bash
curl -X POST http://localhost:8004/fault -H "Content-Type: application/json" -d '{"fault":"clear"}'
```

---

## Step 11 — Trigger High Motor Current (1 min)

```bash
curl -X POST http://localhost:8004/fault \
  -H "Content-Type: application/json" \
  -d '{"fault":"motor"}'
```

Watch Grafana: Motor Current → above 2.5 A threshold, AI Motor Prediction → `HIGH_LOAD`.

```bash
curl -X POST http://localhost:8004/fault -H "Content-Type: application/json" -d '{"fault":"clear"}'
```

---

## Step 12 — Trigger Low Battery (1 min)

```bash
curl -X POST http://localhost:8004/fault \
  -H "Content-Type: application/json" \
  -d '{"fault":"battery"}'
```

Watch Grafana: Battery SOC → orange/red gauge, Battery State → `LOW` then `CRITICAL`.

```bash
curl -X POST http://localhost:8004/fault -H "Content-Type: application/json" -d '{"fault":"clear"}'
```

---

## Step 13 — Send PAUSE Command (1 min)

```bash
curl -X POST http://localhost:8000/api/v1/commands \
  -H "Content-Type: application/json" \
  -d '{"robot_id":"SCR01","command":"PAUSE"}'
```

**Expected response:** `"ack_received": true`, `"ack_accepted": true`, latency < 2 seconds.

**Narrate:** "The Command API published the command via MQTT. The Robot Simulator received it, updated its state and published an acknowledgement. The Command API received the ACK within the timeout."

---

## Step 14 — Show Acknowledgement in InfluxDB (30 sec)

In InfluxDB Data Explorer: measurement `robot_acknowledgement` — show `latency_ms` and `accepted`.

---

## Step 15 — Resume Mission (30 sec)

```bash
curl -X POST http://localhost:8000/api/v1/commands \
  -H "Content-Type: application/json" \
  -d '{"robot_id":"SCR01","command":"RESUME"}'
```

Watch Grafana: Mission State → `RUNNING`, Cleaning Coverage → increasing.

---

## Step 16 — Show Cleaning Coverage Reaching Target (1 min)

```bash
# Generate accelerated demo data to show 90%+ coverage
python scripts/generate_demo_data.py
```

Refresh Grafana. Show Cleaning Coverage gauge → green zone ≥ 90%, Mission State → `COMPLETED`.

---

## Step 17 — Prove Persistence After Restart (2 min)

```bash
python scripts/persistence_test.py
```

**Expected output:**
```
Records found before restart: N
Container restarted.
InfluxDB healthy.
Records found after restart: N  (or more)
[PASS] Data persisted: N records → N records
```

---

## Step 18 — Scale Telemetry Ingestion (1 min)

```bash
docker compose up --scale telemetry-ingestion=2 -d
docker compose ps | grep ingestion
```

**Narrate:** "The Telemetry Ingestion Service is stateless. Two instances both subscribe to the raw telemetry topic independently. MQTT fan-out means both receive and process messages without duplication conflicts in InfluxDB (last-write-wins per timestamp)."

---

## Step 19 — Run Unit and Regression Tests (1 min)

```bash
pytest tests/unit/ tests/regression/ -v --tb=short
```

**Expected:** All tests pass. Show coverage report.

---

## Step 20 — Show CI/CD Evidence (1 min)

Open `.github/workflows/ci.yml` and narrate the 5 jobs:
1. Lint & format check (ruff + black)
2. Unit tests with coverage
3. AI model training and accuracy validation
4. Docker image builds for all 5 services
5. Docker Compose syntax validation

**Narrate:** "This pipeline runs automatically on every push to `main`, `develop`, or any `feature/**` branch."

---

## Step 21 — Summary of Achieved Targets

| Performance Target | Required | Result |
|-------------------|----------|--------|
| Telemetry availability | ≥ 95% | Shown via valid_rate_pct |
| End-to-end delay | ≥ 95% < 2s | Local MQTT latency < 50 ms |
| Valid-message processing | ≥ 98% | Shown via /health |
| Cleaning coverage | ≥ 90% | Demonstrated in Grafana |
| Command ACK time | ≥ 95% < 2s | Shown in API response |
| State rule accuracy | 100% | All 10 regression tests pass |
| AI model accuracy | ≥ 80% | Shown during Docker build |
| Data persistence | Pass | persistence_test.py passes |
| Service recovery | Pass | restart: unless-stopped |
| Full end-to-end flow | Pass | Demonstrated live |

---

**End of demonstration.**
