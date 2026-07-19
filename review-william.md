# Architecture & Data Flow Review — William

**Reviewer:** William (TODO: full name + student ID)
**Date:** TODO
**Documents reviewed:** `docs/architecture.md`, `docs/api-contract.md`

## 1. Telemetry Message Trace

TODO: Using the architecture diagram and Li Kai's screenshots, trace ONE
telemetry message through the pipeline in your own words. Cover each hop:

1. Robot Simulator publishes to MQTT topic `smartclean/SCR01/telemetry/raw` ...
2. Telemetry Ingestion subscribes, validates against the schema, then ...
3. InfluxDB stores it in measurement `robot_telemetry` ...
4. Grafana queries it with Flux every 5 seconds ...

(Write 2-3 sentences per hop. Say what data format is used — JSON over
MQTT, port 1883, etc. Check docs/api-contract.md for exact details.)

## 2. Microservice Design Assessment

TODO: Comment on the service split (simulator, telemetry-ingestion,
state-engine, ai-service, command-api + mosquitto, influxdb, grafana).
- Is each service single-purpose?
- Would you have combined or split any of them differently? Why?

## 3. Contract Verification

TODO: I checked the following 3 topic names in `docs/api-contract.md`
against the code in `shared/smartclean_common/topics.py`:

| Topic in contract | Matches code? |
|---|---|
| smartclean/SCR01/telemetry/raw | TODO yes/no |
| smartclean/SCR01/state | TODO yes/no |
| smartclean/SCR01/command/motion | TODO yes/no |

## 4. Improvement Suggestions

TODO: At least 2 specific suggestions, e.g. about security (MQTT has no
authentication), multi-robot support, message retention, etc.

1. ...
2. ...

## 5. Overall Assessment

TODO: 3-4 sentences summarising the strengths and weaknesses of the
architecture from your point of view.
