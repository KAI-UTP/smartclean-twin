# SmartClean Twin

**A Software-Emulated Digital Twin of a Mobile Inspection and Cleaning Robot**

RBB2013 / FFM2063 / FEM2063 Digital Twin — May 2026  
Universiti Teknologi PETRONAS

---

## Team

| # | Name | Student ID | Assigned Role |
|---|------|-----------|---------------|
| 1 | Chan Li Kai | 22010900 | Project lead, system architecture, programming, integration, Docker deployment, testing, final demonstration |
| 2 | William Wong Xiao Kang | 22010943 | Data-contract review, MQTT-format review, telemetry documentation |
| 3 | Irvin Chang Hou Ceng | 22012342 | Digital Twin state-rule review, cleaning-coverage review, test-case review |
| 4 | Liang Yan Ee | 22011522 | Visualization review, Grafana requirements, command-flow review |
| 5 | Nurin Emelin Binti Marhisyam | 24006706 | Sprint documentation, meeting records, evidence organization, demonstration support |

---

## Quick Start

```bash
# 1. Clone and configure
cp .env.example .env          # review defaults — change passwords for production

# 2. Start the full stack
docker compose up --build -d

# 3. Verify health
python scripts/smoke_test.py

# 4. Open Grafana dashboard
#    http://localhost:3000  (admin / admin)

# 5. Send a command
curl -X POST http://localhost:8000/api/v1/commands \
  -H "Content-Type: application/json" \
  -d '{"robot_id":"SCR01","command":"PAUSE"}'

# 6. Resume
curl -X POST http://localhost:8000/api/v1/commands \
  -H "Content-Type: application/json" \
  -d '{"robot_id":"SCR01","command":"RESUME"}'
```

---

## Architecture

```
Robot Simulator (8004)
    │  MQTT telemetry → smartclean/SCR01/telemetry/raw
    ▼
Eclipse Mosquitto (1883)
    ├──► Telemetry Ingestion (8001)  ──► InfluxDB (8086)
    │        │ validated telemetry
    │        ├──► State Engine (8002) ──► InfluxDB + MQTT state/alert
    │        └──► AI Service (8003)   ──► InfluxDB + MQTT prediction
    │
    └──► Robot Simulator  ◄── MQTT command ◄── Command API (8000) ◄── User (REST)
              │ MQTT ack
              └──► Command API ──► InfluxDB

InfluxDB (8086) ◄──── Grafana (3000)
```

See [docs/architecture.md](docs/architecture.md) for the full interface contract table.

---

## Services

| Service | Port | Technology |
|---------|------|-----------|
| Robot Simulator | 8004 | Python + Paho MQTT |
| Eclipse Mosquitto | 1883 | MQTT broker |
| Telemetry Ingestion | 8001 | FastAPI + Paho |
| Digital Twin State Engine | 8002 | FastAPI + Paho |
| AI / Behaviour Service | 8003 | FastAPI + scikit-learn |
| Command API | 8000 | FastAPI |
| InfluxDB | 8086 | InfluxDB 2.7 |
| Grafana | 3000 | Grafana 11.3 |

---

## Running Tests

```bash
# Install dev dependencies
pip install -r requirements-dev.txt
pip install pydantic paho-mqtt fastapi uvicorn scikit-learn pandas numpy joblib

# Unit + regression tests (no Docker required)
make test

# With coverage
make coverage

# System tests (requires live stack)
make system

# Persistence test
make persist
```

---

## Scaling

The Telemetry Ingestion service is stateless and safe to scale horizontally:

```bash
docker compose up --scale telemetry-ingestion=2 -d
```

Each instance subscribes independently to `smartclean/SCR01/telemetry/raw`.
MQTT fan-out ensures all instances receive the same messages without duplication conflicts.

---

## Data Persistence Proof

```bash
# 1. Generate or wait for telemetry data
# 2. Run the persistence test
python scripts/persistence_test.py
```

This script queries a record count, restarts the InfluxDB container, waits for recovery, and confirms the count is unchanged.

---

## Fault Injection (Demo)

```bash
# Inject obstacle emergency
curl -X POST http://localhost:8004/fault -H "Content-Type: application/json" -d '{"fault":"obstacle"}'

# Inject motor overload
curl -X POST http://localhost:8004/fault -H "Content-Type: application/json" -d '{"fault":"motor"}'

# Inject low battery
curl -X POST http://localhost:8004/fault -H "Content-Type: application/json" -d '{"fault":"battery"}'

# Clear all faults
curl -X POST http://localhost:8004/fault -H "Content-Type: application/json" -d '{"fault":"clear"}'
```

---

## Repository Structure

```
smartclean-twin/
├── .github/workflows/ci.yml      # GitHub Actions CI pipeline
├── contracts/                    # JSON schemas
├── services/
│   ├── robot-simulator/
│   ├── telemetry-ingestion/
│   ├── state-engine/
│   ├── ai-service/
│   └── command-api/
├── shared/smartclean_common/     # Shared models, topics, helpers
├── mosquitto/                    # Mosquitto config
├── influxdb/                     # InfluxDB init
├── grafana/                      # Provisioned dashboard + datasource
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── system/
│   └── regression/
├── scripts/                      # Smoke, persistence, demo data
├── docs/                         # Architecture, sprint plan, demo script
├── docker-compose.yml
└── Makefile
```

---

## Documentation

- [Architecture & Interface Contracts](docs/architecture.md)
- [Sprint Plan](docs/sprint-plan.md)
- [Testing Plan](docs/testing-plan.md)
- [Deployment Guide](docs/deployment-guide.md)
- [Demo Script](docs/demo-script.md)
- [Evidence Checklist](docs/evidence-checklist.md)
- [Troubleshooting](docs/troubleshooting.md)
