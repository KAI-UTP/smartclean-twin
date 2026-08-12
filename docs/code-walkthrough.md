# SmartClean Twin: Code Walkthrough for the Live Presentation

Every source file in the repository, numbered in the order to present them.
The order follows the data path, so each file builds on the one before it.

Repository: https://github.com/KAI-UTP/smartclean-twin
Total: 74 files, about 11,600 lines (5,100 lines of Python).

**Legend:** "Point at" tells you the one thing to show on screen for that file.
Do not scroll through whole files. Open at the named function or line.

---

## PART A: The contract layer (start here, everything depends on it)

| # | File | Lines | What it is | Point at |
|---|---|---|---|---|
| 1 | `shared/smartclean_common/models.py` | 247 | Single source of truth for every message. Pydantic models with physical range limits. Imported by all five services | `class SensorData` (line 102): `battery_soc` limited to 0-100, `motor_temperature_c` to -10-120. This is the validation gate |
| 2 | `shared/smartclean_common/topics.py` | 26 | Every MQTT topic name in one class, namespaced by robot id | `class Topics` (line 4): `smartclean/{ROBOT_ID}/...` is why a second robot needs no code change |
| 3 | `shared/smartclean_common/mqtt_client.py` | 51 | Shared MQTT connect helper with exponential back-off retry | The retry loop: this is why services self-heal when the broker restarts |
| 4 | `shared/smartclean_common/influx_client.py` | 46 | Shared InfluxDB write helper | Point at briefly, it is small |
| 5 | `contracts/telemetry.schema.json` | 54 | JSON Schema of the telemetry message, language-independent | Shows the contract is documented, not only enforced in Python |
| 6 | `contracts/command.schema.json` | 14 | Command message schema | Mention only |
| 7 | `contracts/acknowledgement.schema.json` | 14 | ACK message schema | Mention only |

---

## PART B: The asset (the simulated robot)

| # | File | Lines | What it is | Point at |
|---|---|---|---|---|
| 8 | `services/robot-simulator/grid_map.py` | 60 | The room: 10x10 grid, 0.5 m cells, blocked cells for desks, lawnmower path generator | `lawnmower_path()` (line 52) and `is_accessible()` (line 34) |
| 9 | `services/robot-simulator/robot_state.py` | 68 | Thread-safe physics state (position, battery, motor, actuators) with a lock | The `lock()` context manager: the MQTT callback thread and the physics thread both touch this |
| 10 | `services/robot-simulator/simulator.py` | 394 | **The physics engine.** 1 s tick, movement, battery discharge and charging, obstacle scan, telemetry publish, command handling | `_update_physics()` (line 125). Inside it show the **autonomous charge cycle**: below 20 % SoC it returns home, charges at 10 %/min, resumes at 80 % |
| 11 | " | " | " | `_apply_command()` (line 78) and `_publish_ack()` (line 112): every command is acknowledged |
| 12 | " | " | " | `inject_fault()` (line 377): how the live demo forces a fault |
| 13 | `services/robot-simulator/main.py` | 70 | Runs the simulator plus a FastAPI app for the fault-injection endpoint | `POST /fault`, the endpoint you call in the demo |
| 14 | `services/robot-simulator/Dockerfile` | 16 | Container build | Mention |
| 15 | `mosquitto/mosquitto.conf` | 15 | Broker config (referenced; the compose file now writes this inline) | Mention |

---

## PART C: Ingestion and validation

| # | File | Lines | What it is | Point at |
|---|---|---|---|---|
| 16 | `services/telemetry-ingestion/main.py` | 192 | **The validation gate.** Subscribes to raw telemetry, validates, writes to InfluxDB, republishes as validated | `_on_message()` (line 106): the try/except around `TelemetryMessage.model_validate` is the gate. Invalid messages are counted and dropped |
| 17 | " | " | " | `_write_invalid_to_influx()` (line 92): rejects are recorded, not silently lost |
| 18 | " | " | " | `health()` (line 163): exposes the rejection counter, so a failing sensor is visible |
| 19 | `services/telemetry-ingestion/Dockerfile` | 16 | Container build. **No fixed container name**, which is what allows scaling | Mention when you demo scaling |

---

## PART D: The Digital Twin state engine

| # | File | Lines | What it is | Point at |
|---|---|---|---|---|
| 20 | `services/state-engine/rules.py` | 242 | **Where sensor data becomes twin state.** All 11 state variables and the alarm rules | `evaluate()` (line 37). Show the safety rule: `obstacle_cm < 25` produces `EMERGENCY` plus an `OBSTACLE_EMERGENCY` alarm |
| 21 | " | " | " | `_alarm()` (line 225): alarm construction with value and threshold recorded |
| 22 | `services/state-engine/main.py` | 213 | Subscribes to validated telemetry, calls `evaluate()`, publishes state and alerts, writes state to InfluxDB, tracks cleaning coverage | The publish of `Topics.STATE` and the coverage calculation |
| 23 | `services/state-engine/Dockerfile` | 16 | Container build | Mention |

---

## PART E: The AI layer

| # | File | Lines | What it is | Point at |
|---|---|---|---|---|
| 24 | `services/ai-service/train_model.py` | 407 | **All model training.** Runs at Docker build time, so models cannot drift from the code | `_label_motor_health()` (line 53): the documented labelling rules, not arbitrary labels |
| 25 | " | " | " | `train_and_save_hw4()` (line 222): `Pipeline(StandardScaler, RandomForest)`, stratified 80/20 split. **Scaling inside the pipeline prevents data leakage** |
| 26 | " | " | " | `generate_normal_operation_dataset()` (line 298): the anomaly detector sees **only healthy data** during training |
| 27 | " | " | " | `anomaly_predict()` (line 326): anomaly = any sensor beyond 4.5 sigma. Fully explainable |
| 28 | " | " | " | Bottom of file: the script **exits non-zero if accuracy or R-squared is below target**, so a bad model fails the CI build |
| 29 | `services/ai-service/predictor.py` | 222 | Loads the five models and runs inference; falls back to threshold rules if artefacts are missing | `predict()` (line 103), and the `rule_fallback` branch: the twin stays observable when degraded |
| 30 | " | " | " | `_hw4_features()` (line 70): maps robot sensors into the 9-feature model space |
| 31 | `services/ai-service/main.py` | 317 | Scores every telemetry message, computes forecasts, produces the recommendation, serves what-if | `_build_recommendation()` (line 94): **severity-ordered**, so a critical condition is never masked by a milder one |
| 32 | " | " | " | `_trend_per_minute()` (line 64) and `_battery_minutes_to_empty()` (line 78): rolling-window stream aggregation |
| 33 | " | " | " | `@app.post("/whatif")` (line 273): **the what-if endpoint. Demo this live** |
| 34 | `services/ai-service/Dockerfile` | 20 | Container build. Note `RUN python train_model.py`: **training happens in the build** | Point at that one line |
| 35 | `services/ai-service/requirements.txt` | 9 | Pinned versions, so builds are reproducible | Mention |

---

## PART F: Control (the twin commands the asset)

| # | File | Lines | What it is | Point at |
|---|---|---|---|---|
| 36 | `services/command-api/main.py` | 263 | REST to MQTT bridge with acknowledgement tracking | `issue_command()` (line 174): validates, publishes, **waits for the ACK**, returns the result. This is what makes the twin bidirectional |
| 37 | " | " | " | `_on_ack()` (line 104): correlates the ACK back to the command id |
| 38 | `services/command-api/Dockerfile` | 16 | Container build | Mention |

---

## PART G: Visualization

| # | File | Lines | What it is | Point at |
|---|---|---|---|---|
| 39 | `grafana/dashboards/smartclean_twin.json` | 1514 | **The whole dashboard as code**, 28 panels in 7 sections | Search for `derivative` (battery discharge rate) and `aggregateWindow` (the 30 s and 1 min windows) |
| 40 | `grafana/provisioning/datasources/influxdb.yaml` | 16 | Datasource provisioned as code | Mention |
| 41 | `grafana/provisioning/dashboards/provider.yaml` | 11 | Dashboard auto-loading | Mention |
| 42 | `grafana/Dockerfile` | 4 | Bakes the dashboard into the image, so it is reproducible | Point at: this is why the dashboard is version-controlled |
| 43 | `omniverse/create_scene.py` | 300 | Builds the USD 3D scene once: room, 100 coverage tiles, robot hierarchy | `_create_cleaning_robot()`: `DirectionArrow` is a **child prim**, so it rotates with the parent automatically |
| 44 | `omniverse/live_update.py` | 342 | **Drives the 3D scene from InfluxDB every second** | `_query_latest()`: the `group()` and `pivot()` that make all fields arrive in one row. This was a real defect we fixed |
| 45 | " | " | " | `_apply_pose()`: tile index is `int(x / CELL_SIZE_M)`, another defect we found and fixed |
| 46 | " | " | " | `_apply_safety()`: body colour and the flashing EMERGENCY light |
| 47 | `omniverse/fault_demo.py` | 100 | Scripted fault demonstration inside Omniverse | Mention, or run it |

---

## PART H: Tests (the evidence that it works)

| # | File | Lines | What it is | Point at |
|---|---|---|---|---|
| 48 | `tests/unit/test_telemetry_schema.py` | 142 | 17 tests: field presence, types, physical ranges, ISO timestamps | A range test: proves an impossible reading is rejected |
| 49 | `tests/unit/test_state_rules.py` | 202 | 20 tests: every state variable and alarm threshold, including boundary values | A boundary test at `obstacle_cm == 25` |
| 50 | `tests/unit/test_grid_map.py` | 68 | 10 tests: path covers all accessible cells, obstacles excluded | Mention |
| 51 | `tests/unit/test_simulator_commands.py` | 114 | 12 tests: every command changes state correctly | Mention |
| 52 | `tests/unit/test_command_validation.py` | 48 | Invalid robot id and invalid command are rejected | Mention |
| 53 | `tests/unit/test_ai_predictor.py` | 100 | Prediction shape and the fallback path | Mention |
| 54 | `tests/integration/test_command_api.py` | 113 | REST to MQTT to ACK round trip across the interface | Point at: this is an **interface** test, not a unit test |
| 55 | `tests/integration/test_telemetry_ingestion.py` | 121 | Valid message stored; invalid message rejected and counted | Mention |
| 56 | `tests/system/test_full_flow.py` | 124 | 11 tests: service health, telemetry to storage, state derivation, command path, and the three fault scenarios | The fault-scenario tests: they prove the twin **interprets** the asset, not just moves data |
| 57 | `tests/system/test_persistence.py` | 194 | 3 tests: restart InfluxDB, prove no data loss | `_fixed_window()`: the window must be frozen, or the restart looks like data loss. We had this bug |
| 58 | `tests/regression/test_regression_suite.py` | 166 | 10 golden-snapshot tests that catch behaviour drift | Mention |
| 59 | `tests/conftest.py` | 12 | Shared fixtures and path setup | Mention |

---

## PART I: Deployment and automation

| # | File | Lines | What it is | Point at |
|---|---|---|---|---|
| 60 | `docker-compose.yml` | 177 | **The whole system in one file.** 8 services, health checks, ordered start-up, named volumes | `depends_on: condition: service_healthy`: services wait until dependencies can actually serve |
| 61 | " | " | " | `ports: "8101-8111:8001"` on ingestion: a **port range**, which is what allows scaling to 2 replicas. The range deliberately sits clear of the other services' fixed ports, since Docker allocates from it blindly |
| 62 | " | " | " | The named volumes: `influxdb_data` is why data survives container restarts |
| 63 | `.github/workflows/ci.yml` | 129 | **CI/CD pipeline**, 5 jobs with a dependency graph | The `train-ai-model` job: model quality is a build gate |
| 64 | " | " | " | Pinned `ruff==0.15.20 black==26.5.1`: we pinned these after unpinned versions broke the build for the whole team |
| 65 | `requirements-dev.txt` | 6 | Dev tooling versions | Mention |
| 66 | `scripts/smoke_test.py` | 55 | Quick post-deploy health check of all services | Good to run live |
| 67 | `scripts/persistence_test.py` | 115 | Standalone persistence check | Mention |
| 68 | `scripts/generate_demo_data.py` | 111 | Seeds data for a demo | Mention |
| 69 | `scripts/notebooks_to_webpdf.py` | 102 | Notebook to PDF export tooling | Mention only if asked |
| 70 | `scripts/notebooks_to_html.py` | 95 | Notebook to printable HTML | Mention only if asked |
| 71 | `scripts/notebooks_to_pdf.py` | 123 | Alternative PDF export via Chrome | Mention only if asked |

---

## PART J: Documentation

| # | File | Lines | What it is | Point at |
|---|---|---|---|---|
| 72 | `docs/api-contract.md` | 421 | **All 16 communicating pairs**: topic, port, protocol, data format, and when communication is initiated and concluded | Open at any pair and show the Initiated / Concluded rows |
| 73 | `docs/architecture.md` | 158 | Block diagram and component functions | The block diagram |
| 74 | `docs/sprint-plan.md` | 220 | Backlog, 31 tasks, both sprints, acceptance criteria, reviews, per-member assignment | The per-member task assignment table |
| 75 | `docs/testing-plan.md` | 170 | Test strategy and the four levels | Mention |
| 76 | `docs/deployment-guide.md` | 101 | How to deploy and scale | Mention |
| 77 | `docs/evidence-checklist.md` | 115 | Evidence items for the rubric | Mention |
| 78 | `docs/demo-script.md` | 339 | Step-by-step demonstration script | Mention |
| 79 | `docs/troubleshooting.md` | 59 | Known issues and fixes | Mention |
| 80 | `docs/presentation-script.md` | 213 | Narration for the video | Mention |
| 81 | `docs/review-william.md` | 106 | William's architecture review | Show that it exists, committed by William |
| 82 | `docs/review-irvin.md` | 90 | Irvin's AI review | Committed by Irvin |
| 83 | `docs/review-nurin.md` | 42 | Nurin's dashboard review | Committed by Nurin |
| 84 | `docs/review-liang.md` | 374 | Liang's testing verification | Committed by Liang |
| 85 | `docs/team-tasks.md` | 120 | Task assignment to the team | Mention |
| 86 | `README.md` | 190 | Project overview and quick start | The quick start section |

---

## Suggested 15 minute live route (do not show all 86)

If Dr wants to see the real code, this is the shortest path that still proves
the whole system. Twelve files, in this order:

| Step | Show | Say |
|---|---|---|
| 1 | **#1** `models.py`, `class SensorData` | "One schema, imported by every service. Ranges are enforced here" |
| 2 | **#2** `topics.py` | "Every topic namespaced by robot id, so a second robot needs no code change" |
| 3 | **#10** `simulator.py`, `_update_physics()` | "The asset. Note the autonomous charge cycle: returns home below 20 %, resumes at 80 %" |
| 4 | **#16** `telemetry-ingestion/main.py`, `_on_message()` | "The validation gate. Invalid messages are counted and dropped, never stored" |
| 5 | **#20** `state-engine/rules.py`, `evaluate()` | "Where sensor data becomes twin state. Safety is a deterministic rule, not a model" |
| 6 | **#24, #25** `train_model.py` | "Documented labelling rules. Scaler inside the pipeline so there is no leakage. Stratified split" |
| 7 | **#28** end of `train_model.py` | "Exits non-zero below target, so a bad model fails the build" |
| 8 | **#31, #33** `ai-service/main.py` | "Severity-ordered recommendation, then the what-if endpoint" then **run a what-if live** |
| 9 | **#36** `command-api/main.py`, `issue_command()` | "Waits for the ACK. This is what makes it a twin and not a dashboard" |
| 10 | **#57** `test_persistence.py`, `_fixed_window()` | "A real bug we found: a sliding window looked like data loss" |
| 11 | **#60, #61** `docker-compose.yml` | "Health-gated start-up, and the port range that allows scaling" then **run the scaling demo** |
| 12 | **#72** `docs/api-contract.md` | "All 16 pairs, including when each communication starts and ends" |

### Two moments that impress most

1. **The what-if endpoint (#33).** Ask the twin a hypothetical live:
   "what if the motor reaches 90 C at 3.6 A?" and it answers with health,
   remaining life, anomaly and a recommendation, without touching the robot.
2. **The defects your tests caught (#44, #45, #57).** Showing that the test
   suite found real bugs is stronger evidence of good practice than showing
   green ticks.

### Commands to have ready

```
docker compose ps
docker compose up --scale telemetry-ingestion=2 -d
curl.exe --% -X POST http://localhost:8003/whatif -H "Content-Type: application/json" -d "{\"motor_temperature_c\":90,\"motor_current_a\":3.6}"
curl.exe --% -X POST http://localhost:8004/fault -H "Content-Type: application/json" -d "{\"fault\":\"obstacle\"}"
curl.exe --% -X POST http://localhost:8004/fault -H "Content-Type: application/json" -d "{\"fault\":\"clear\"}"
py -m pytest tests/unit -q
```
