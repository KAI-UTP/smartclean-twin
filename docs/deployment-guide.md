# Deployment Guide

## Prerequisites

- Docker Desktop 4.x or Docker Engine 24+ with Compose v2
- Python 3.11 (for running tests and scripts locally)
- Git

## First-Time Setup

```bash
git clone <your-repo-url> smartclean-twin
cd smartclean-twin
cp .env.example .env
# Edit .env if you want to change passwords
```

## Start the Stack

```bash
docker compose up --build -d
```

Build time: ~3–5 minutes (AI model trains during `ai-service` Docker build).

## Verify

```bash
docker compose ps          # all 8 containers should show "Up"
python scripts/smoke_test.py  # all [OK]
```

## Access Points

| Service | URL | Credentials |
|---------|-----|-------------|
| Grafana | http://localhost:3000 | admin / admin |
| InfluxDB | http://localhost:8086 | admin / adminpassword |
| Command API docs | http://localhost:8000/docs | none |
| Simulator health | http://localhost:8004/health | none |

## Stop

```bash
docker compose down          # stop but keep volumes
docker compose down -v       # stop and DELETE all data
```

## Rebuild a single service

```bash
docker compose build ai-service
docker compose up -d ai-service
```

## Scale ingestion

```bash
docker compose up --scale telemetry-ingestion=2 -d
```

## Run local tests (no Docker)

```bash
pip install pydantic paho-mqtt fastapi uvicorn scikit-learn pandas numpy joblib pytest pytest-cov httpx
pytest tests/unit/ tests/regression/ -v
```

## Load demo data

```bash
python scripts/generate_demo_data.py
```

## Prove persistence

```bash
python scripts/persistence_test.py
```

## Troubleshooting

See [troubleshooting.md](troubleshooting.md).
