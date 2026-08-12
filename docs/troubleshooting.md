# Troubleshooting Guide

## Container fails to start

```bash
docker compose logs <service-name>
```

Common causes:
- `mosquitto` not healthy yet — services will retry for up to 10 attempts
- `influxdb` not ready — state engine, ingestion and AI service wait for it
- Port already in use — check `netstat -an | findstr 1883`

## No telemetry appearing in Grafana

1. Check simulator is running: `curl http://localhost:8004/health`
2. Check MQTT: `mosquitto_sub -h localhost -t "smartclean/SCR01/telemetry/raw" -C 1`
3. Check ingestion. Its host port is allocated dynamically from 8101-8111 so replicas can
   scale, so look it up first:
   `docker compose port telemetry-ingestion 8001`
   then `curl http://localhost:<that port>/health` and look at the `received` counter
4. Check InfluxDB: open http://localhost:8086, Data Explorer, bucket `smartclean_twin`

## Command API returns 503

MQTT client not yet connected. Wait 10–15 seconds after start, then retry.

## AI model not loaded (using fallback)

Check `docker compose logs ai-service` for `Model files not found`. If the model wasn't built correctly:

```bash
docker compose build --no-cache ai-service
docker compose up -d ai-service
```

## InfluxDB shows no data after restart

This should not happen if volumes are configured correctly. Run:
```bash
docker volume ls | grep influxdb
```
If the volume is missing, the persistence test will fail. Make sure you did not run `docker compose down -v`.

## Grafana datasource shows error

1. Check INFLUXDB_TOKEN matches between `.env` and Grafana provisioning
2. Verify InfluxDB is healthy: `curl http://localhost:8086/health`
3. In Grafana → Configuration → Data Sources → InfluxDB → Test

## Tests fail locally

Ensure PYTHONPATH includes shared and service directories:

```bash
export PYTHONPATH="./shared:./services/robot-simulator:./services/state-engine:./services/ai-service:./services/command-api:./services/telemetry-ingestion"
pytest tests/unit/ tests/regression/ -v
```

## Port conflict

Edit `.env` and the corresponding `docker-compose.yml` port mappings. The internal container port does not need to change.
