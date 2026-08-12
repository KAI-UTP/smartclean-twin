# SmartClean Twin: The Complete Walkthrough, 0 to 100

Everything, in the order you should present it. Every file in the project is
covered. Every line number here was read from the actual file.

Repository: `https://github.com/KAI-UTP/smartclean-twin`
Course: RBB2013 Digital Twin
Developer: Chan Li Kai, 22010900

---

# PART A. WHAT THIS IS

## A1. The problem

An indoor cleaning robot works alone in a building. The operator cannot see it,
cannot tell whether it is stuck, cannot tell whether the motor is failing, and
finds out about a problem only when the floor is still dirty. Adding a live
camera does not solve this: a camera shows what happened, not what is about to.

## A2. What was built

A Digital Twin: a synchronised virtual copy of that robot that receives its
sensor data, maintains its own understanding of the robot's condition, predicts
what will happen next, and can send commands back.

Nine Docker containers. Six services written for this project, three pieces of
infrastructure configured for it.

## A3. The one sentence that defines the project

> A dashboard shows you data. A Digital Twin holds a synchronised model of the
> asset, reasons about it, predicts from it, answers hypothetical questions
> about it, and commands it back. This project does all five.

## A4. The 5D framework, which every part maps to

| Dimension | What it is | Where it lives here |
|---|---|---|
| **D1** Physical Entity | The asset itself | `services/robot-simulator/` |
| **D2** Virtual Model | Geometry, physics, behaviour, rules | `omniverse/create_scene.py`, `simulator.py`, `rules.py`, `predictor.py` |
| **D3** Services | What the twin does for you | `ai-service/`, `command-api/` |
| **D4** Data | What is stored and how | InfluxDB, `models.py`, `contracts/` |
| **D5** Connections | How the halves talk | `topics.py`, MQTT, REST |

The two engines that connect D1 and D2:

- **P2V**, physical to virtual: robot to MQTT to validation to database to
  views. This is Part C.
- **V2P**, virtual to physical: console to REST to MQTT to robot to
  acknowledgement. This is Part D.

---

# PART B. THE FOUNDATION FILES

These are shared by every service. Present them first, because everything else
refers back to them.

## B1. `shared/smartclean_common/models.py`, 198 lines

**The single source of truth for every message in the system.**

Structure:

- **Lines 14 to 106**: 12 enumerations. These are the vocabulary of the twin.
  `MotionState`, `OperationMode`, `SafetyState`, `BatteryState`,
  `CleaningState`, `MotorHealth`, `DirtLevel`, `MissionState`,
  `ConnectionState`, `TwinQuality`, `RobotCommand`.
- **Lines 112 to 138**: telemetry sub models. `PoseData`, `SensorData`,
  `ActuatorData`, `MissionData`.
- **Line 144**: `TelemetryMessage`, the whole telemetry contract.
- **Line 174**: `DigitalTwinState`, the 11 dimension twin state.
- **Line 195**: `PredictionMessage`, the AI output.
- **Line 220**: `AlertMessage`. **Line 234**: `CommandRequest`. **Line 247**:
  `AckMessage`.

**What to point at.** Every numeric field has hard bounds:

```python
x_m: float = Field(..., ge=0.0, le=100.0)            # line 113
heading_deg: float = Field(..., ge=0.0, lt=360.0)    # line 115
battery_soc: float = Field(..., ge=0.0, le=100.0)    # line 121
motor_temperature_c: float = Field(..., ge=-10.0, le=120.0)  # line 125
```

Plus two custom validators, **line 154** for `robot_id` length and **line 161**
which actually parses the timestamp to confirm it is real ISO 8601.

**Say:**

> "This one file is imported by four services. They physically cannot disagree
> about what a message looks like, because there is only one definition. If I
> add a field here, every service sees it at once. This is what stops a
> distributed system drifting apart."

**The `OperationMode` enum at line 21 has a story.** `CHARGING`, `REFILLING`
and `MANUAL` were added later. Before that, when the robot reported one of these
modes, the state engine's lookup did not recognise it and silently fell back to
`IDLE`. The robot was charging and the twin said idle. Adding the enum values
and the map entries fixed it. Mention this if asked about testing: it is a
concrete example of the twin lying, and being caught.

## B2. `shared/smartclean_common/topics.py`, 20 lines

Every MQTT topic string, defined once.

```
smartclean/SCR01/telemetry/raw          line 9
smartclean/SCR01/telemetry/validated    line 10
smartclean/SCR01/state                  line 16
smartclean/SCR01/prediction             line 17
smartclean/SCR01/alert                  line 18
smartclean/SCR01/command/motion         line 21
smartclean/SCR01/command/cleaning       line 22
smartclean/SCR01/ack                    line 25
smartclean/SCR01/service/health         line 26
```

**Say:**

> "The hierarchy is prefix, robot ID, then category. The robot ID sits at level
> two on purpose, so a second robot is `smartclean/SCR02/...` and a subscriber
> that wants everything uses `smartclean/+/telemetry/raw`. The topic structure
> is already designed for a fleet."

## B3. `shared/smartclean_common/influx_client.py`, 38 lines

A shared database write helper. **Line 16** reads the four connection settings
from environment variables, **line 21** builds the client, **line 42** writes.
Note **line 43**: a write failure is logged, not raised. A database hiccup must
not kill the service that was writing.

## B4. `shared/smartclean_common/mqtt_client.py`, 39 lines

A shared broker connection helper with retry. **Line 42** is the retry loop, ten
attempts, and **line 49** is exponential backoff capped at 30 seconds.

## B5. `contracts/`, three JSON Schema files

`telemetry.schema.json` (54 lines), `command.schema.json`, and
`acknowledgement.schema.json`. These are the language independent versions of
the Pydantic models.

**Say:**

> "Pydantic is Python. If a teammate wrote a service in Java tomorrow, they
> would implement against these JSON Schema files. The contract is published,
> not implied."

---

# PART C. P2V, THE ROBOT TO YOUR SCREEN

Follow this path in order. This is the heart of the presentation.

## C1. The robot itself: `services/robot-simulator/`

Four files.

### `grid_map.py`, 47 lines: the world

- **Line 13**: the 10 by 10 layout array. 1 is wall, 0 is floor. The outer ring
  is wall, and there are three interior obstacles representing desks.
- **Line 30**: `CELL_SIZE_M = 0.5`, so the room is 5 m by 5 m.
- **Line 31**: home is cell (1,1).
- **Line 34**: `is_accessible()`, used by both navigation and manual driving.
- **Line 44**: `generate_dirt_map()`, seeded so the demo is reproducible.
- **Line 52**: `lawnmower_path()`. Odd rows go left to right, even rows right to
  left, which is how a real cleaning robot covers a floor without lifting.

### `robot_state.py`, 57 lines: the mutable state

A dataclass holding pose, battery, motor, sensors, actuators, mission, and the
four fault injection flags (**lines 51 to 57**).

**Line 59** is the important one: a `threading.Lock`. **Lines 64 to 74** convert
grid cell to metres: `x_m = col * 0.5`, `y_m = row * 0.5`. Grid indices are the
truth, metres are derived.

### `simulator.py`, 493 lines: the physics engine

This is the largest and most important file. Walk it in this order.

**Constants, lines 35 to 57.**

```python
CHARGE_THRESHOLD = 20.0   # return to dock below this
CHARGE_FULL      = 80.0   # resume cleaning above this
WATER_THRESHOLD  = 15.0
WATER_FULL       = 90.0
MANUAL_MOVES = { ... }    # line 48, the 8 direction table
```

Note the hysteresis: leave at 20, resume at 80. Without the gap the robot would
oscillate at the threshold.

**`_update_physics()`, line 232.** The tick, once per second.

| Lines | What happens |
|---|---|
| 235 | stopped or paused, do nothing |
| 243 | manual mode, operator steers, only consumables update |
| 251 to 264 | **autonomous decision to return to dock** |
| 268 to 300 | charging and refilling at the dock |
| 302 to 310 | fault injections |
| 312 to 326 | returning home movement |
| 329 to 333 | path complete, loop and re dirty the floor |
| 338 to 351 | obstacle scan and speed selection |
| 354 to 371 | move toward target or clean the current cell |
| 373 to 376 | heading update |

**The autonomous behaviour at line 253** is the strongest point in this file:

```python
low_battery = s.battery_soc < CHARGE_THRESHOLD and not s.inject_low_battery
low_water   = s.water_level_pct < WATER_THRESHOLD
if (low_battery or low_water) and not s.returning_home and s.mode == "CLEANING":
```

**Say:**

> "Nobody commanded this. The robot decided by itself to abandon cleaning and
> drive to the dock. And notice line 251 excludes the injected fault, so a fault
> demonstration does not silently turn into a recovery demonstration. Those are
> two different things and mixing them would make the demo dishonest."

**Line 276 to 300, the dock.** It charges and refills, and resumes only when
**both** are ready. Say: "Otherwise the robot sets off with a full battery and
an empty tank and pretends to clean."

**`_update_consumables()`, line 380.** Battery drain, motor thermal model, water
use. It is a separate method because it must run in manual mode too. A robot
driven by hand still drains its battery. **Line 398 to 402** is the thermal
model: heat from current, cooling proportional to the gap above ambient.

**`_build_telemetry()`, line 428.** Builds the 16 field message.

**Point at line 438**, the `with s.lock():` and read the docstring at 429 to 436
out loud. This is a real bug that was found and fixed:

> "Two threads mutate this state, the physics loop and the MQTT command thread.
> Without the lock a message could carry a position from before a command and a
> heading from after it. A twin's telemetry must be one coherent instant, not a
> mix of two."

**`run()`, line 488.** Connect with retry (490), start the network thread (501),
then loop: physics, build, **publish at line 513**, health beacon every 30 ticks
(514), sleep the remainder (526) so the rate stays at exactly 1 Hz regardless of
how long the work took.

**Line 513 is the answer to "where does the message enter MQTT".**

```python
self._mqtt_client.publish(Topics.TELEMETRY_RAW, json.dumps(telemetry), qos=1)
```

QoS 1, at least once. Telemetry must not silently vanish.

**Command handling, lines 75 to 228.** Subscribes at 78 to 80, `_on_command()`
at 84, `_apply_command()` at 97 is the full command table, `_publish_ack()` at
219. Covered in Part D.

**`_nearest_path_index()`, line 161** and **`_manual_step()`, line 177**: also
Part D.

### `main.py`, 51 lines: the entry point

Runs the simulator on a background thread (**line 57**) and a FastAPI app on the
main thread. **Line 26** is `/health`, **line 41** is `/fault`, the demo fault
injection endpoint.

**Say:** "Signal handlers must be registered on the main thread, which is why
the simulator is the background one and the API is the foreground one, at line
57 to 67. That is not arbitrary."

## C2. Validation: `services/telemetry-ingestion/main.py`, 154 lines

**The gate. Nothing enters the twin without passing here.**

| Line | What |
|---|---|
| 134 | subscribe to `telemetry/raw`, QoS 1 |
| 106 | `_on_message()`, fires per message |
| 111 | JSON parse, failure goes to quarantine |
| 119 | **`TelemetryMessage.model_validate(data)`, the schema gate** |
| 123 | validation failure goes to quarantine |
| 128 | republish to `telemetry/validated` |
| 129 | write to InfluxDB |
| 92 | `_write_invalid_to_influx()`, the quarantine |
| 54 | **build the InfluxDB client** |
| 59 to 89 | `_write_telemetry_to_influx()`, 16 fields |
| 162 | `/health`, reports `valid_rate_pct` |

**Line 54 is the answer to "where do you connect to the database".**

```python
_influx_client = InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)
```

The values come from environment variables at **lines 39 to 42**, injected by
`docker-compose.yml:7-13`. The URL is `http://influxdb:8086`, where `influxdb`
is the container name resolved by Docker's internal DNS. There is no IP address
anywhere in this codebase.

**Lines 51 to 56 matter:** the write API is cached in a module global. Without
it a new HTTP connection would be opened every single second.

**Say about the two topics:**

> "Raw is what the robot said. Validated is what the system accepted. Everything
> downstream subscribes to validated, so no other service ever re checks the
> schema, and I can measure exactly what was rejected. A bad message is not
> dropped silently. It goes into its own measurement with the reason, and the
> health endpoint reports the rejection rate."

## C3. The twin's understanding: `services/state-engine/`

### `rules.py`, 222 lines: the behaviour model

`evaluate()` at **line 37** takes validated telemetry and returns twin state
plus alarms.

| Dimension | Line | Rule |
|---|---|---|
| Safety state | 59 | obstacle under 25 cm or bumper is EMERGENCY, under 50 cm is WARNING |
| Battery state | 83 | under 10 percent CRITICAL, under 20 percent LOW |
| Motor health | 101 | over 70 C OVERHEATED, over 2.5 A HIGH_LOAD |
| Dirt level | 129 | 0.7 and above DIRTY, 0.3 and above MODERATE |
| Cleaning state | 137 | from brush state and dirt score |
| Operation mode | 148 | mapped from the robot's reported mode |
| Mission state | 161 | composite of coverage, battery and mode |
| Connection and twin quality | 179 | message age |

**Line 179 is the line to be proud of:**

```python
delay_s = (now - last_msg_time).total_seconds()
if delay_s > 10.0:   connection_state = OFFLINE; twin_quality = INVALID
elif delay_s > 2.0:  connection_state = DELAYED; twin_quality = DELAYED
```

**Say:**

> "This is the part most projects miss. The twin knows how good it is. If
> telemetry is more than two seconds late it marks itself DELAYED, and past ten
> seconds INVALID. A twin that does not know it is stale is worse than no twin,
> because the operator keeps trusting it."

Alarms are built by `_alarm()` at **line 228**, each with type, severity, value
and the threshold it crossed. Not just "something is wrong", but what, how bad,
and by how much.

### `main.py`, 169 lines

**Line 159** subscribes to validated. **Line 135** calls `rules.evaluate`.
**Line 138** publishes state to MQTT. **Line 141** publishes alarms. **Line 144**
writes state to InfluxDB measurement `robot_state`, implemented at **line 62**.
**Line 86** writes alarms to `robot_alarm`.

Note **line 66 onward** uses the `Point` builder rather than a dict, because
state fields are strings and the fluent API makes the types explicit.

## C4. The intelligence: `services/ai-service/`

### `train_model.py`, 345 lines: how the models were made

Three dataset generators and three training functions.

| Lines | What |
|---|---|
| 71 | `generate_dataset()`, 5000 rows for the two original classifiers |
| 102 | `train_and_save()`, motor health and dirt level |
| 153 | `generate_hw4_dataset()`, 1200 rows in the 9 feature space |
| 180 | the risk score formula, a weighted sum of five factors |
| 189 | labels: CRITICAL at 0.65, WARNING at 0.35 |
| 194 | the RUL formula |
| 222 | `train_and_save_hw4()`, classifier and regressor |
| 298 | `generate_normal_operation_dataset()`, healthy operation only |
| 339 | `train_and_save_anomaly()` |
| 398 to 406 | **the quality gates** |

**Point at lines 234 to 249, the Pipeline:**

```python
Pipeline(steps=[("scaler", StandardScaler()),
                ("model", RandomForestClassifier(...))])
```

**Say:**

> "The scaler is inside the pipeline, not applied before the split. If I scaled
> the whole dataset first, the training fold would have seen the test fold's
> mean and standard deviation. That is data leakage, and the reported accuracy
> would be a lie. `train_test_split` at line 229 is also stratified, so all
> three classes appear in both folds in the right proportion."

**Point at lines 398 to 406:**

```python
if results.get("health_state_accuracy", 0) < 0.80: sys.exit(1)
if results.get("rul_r2", 0) < 0.80:                sys.exit(1)
if results.get("anomaly_fault_detection", 0) < 0.99: sys.exit(1)
```

**Say:**

> "Training exits non zero if the model is not good enough. This script runs in
> CI on every push. A model that degrades cannot be merged. The quality gate is
> automated, not a promise."

### `predictor.py`, 195 lines: the five models at runtime

`load_models()` at **line 40** loads all five, and **line 52** requires all five
to be present or none are used.

`predict()` at **line 103**:

| Model | Type | Paradigm | Line |
|---|---|---|---|
| `motor_health_clf` | Random Forest | Supervised classification | 132 |
| `dirt_level_clf` | Random Forest | Supervised classification | 135 |
| `health_state_clf` | Random Forest in Pipeline | Supervised classification | 154 |
| `rul_regressor` | Random Forest in Pipeline | Supervised regression | 156 |
| `anomaly_detector` | per sensor mean and standard deviation | **Unsupervised** | 162 |

**Three learning paradigms in one service.**

`_hw4_features()` at **line 70** maps robot sensors into the 9 feature space, for
example vibration is derived from speed and acoustic noise from actuator state.

**The anomaly detector, line 162, is the one to explain:**

```python
z = np.abs((anomaly_vec - _anomaly_detector["mean"]) / _anomaly_detector["std"])
anomaly_score = float(_anomaly_detector["threshold"] - z.max())
is_anomaly = anomaly_score < 0
```

**Say:**

> "It learned from normal operation only. It never saw a fault during training.
> It stores the mean and standard deviation of five sensors and flags anything
> more than 4.5 standard deviations out on any one of them. An injected 3.5 amp
> motor current is 15 sigma from the 0.75 amp normal mean, so it is caught
> instantly. It catches faults nobody labelled, which a supervised classifier by
> definition cannot. And unlike a black box, I can say exactly why it fired:
> this sensor, this many sigma."

**The fallback, line 178.** If the model files are missing, `predict` falls back
to rule based logic and reports `model_used: "rule_fallback"`.

**Say:** "The twin degrades, it does not crash, and it tells you which path it
took. That last part is the important one."

### `main.py`, 258 lines: the service

| Line | What |
|---|---|
| 221 to 222 | subscribes to validated telemetry **and** twin state |
| 153 | `_on_message()`, dispatches by topic |
| 175 | runs all five models |
| 64 | `_trend_per_minute()`, linear rate over a 60 second window |
| 78 | `_battery_minutes_to_empty()` |
| 86 | `_cleaning_minutes_to_finish()` |
| 94 | `_build_recommendation()`, plain English for the operator |
| 203 | publishes to `prediction` |
| 204 | writes to `robot_prediction` |
| 273 | **`/whatif`, the what if endpoint** |

**Say about the three separate measurements:**

> "`robot_telemetry` is what the sensors measured. `robot_state` is what the twin
> concluded. `robot_prediction` is what the AI expects. Three measurements, kept
> apart deliberately. Module 2 makes exactly that distinction and I kept it in
> the storage layer, because once you mix a measurement with a prediction in one
> table you can never tell them apart again."

**`/whatif` at line 273 is the strongest single moment in the demo:**

> "This is the defining capability of a Digital Twin. I can ask the virtual copy
> a question the real robot must never be asked. What happens at 95 degrees and
> 3.8 amps? It answers with the health state, the remaining useful life, whether
> it is anomalous, and what the operator should do. The robot was never touched.
> That is simulation. A dashboard fundamentally cannot do this."

**`_build_recommendation()` at line 94** is worth showing because of its order:
CRITICAL first, then anomaly, then battery, then WARNING. The most urgent thing
wins. An operator gets one sentence, not five competing numbers.

---

# PART D. V2P, YOUR SCREEN TO THE ROBOT

This half is what makes it a twin rather than a dashboard.

## D1. The browser: `services/web-control/static/`

### `index.html`, 199 lines

Nine cards: status strip (25), live map (51), control (63), **manual control
(88)**, quick actions (117), phone access (137), telemetry (146), what if (171),
fault injection (188), command history (203).

Note **line 65**, the hint text visible on screen: "Each command travels REST to
MQTT to robot, and the robot's acknowledgement is shown below." The architecture
is written on the interface itself.

### `app.js`, 378 lines

| Line | What |
|---|---|
| 14 | `poll()`, once per second |
| 36 | `render()`, paints the whole console |
| 49 to 53 | the robot's own mode is authoritative, the pad disarms itself if the robot leaves manual |
| 107 | `drawMap()`, canvas floor, grid, desks, dock, robot, heading arrow |
| 180 | command buttons |
| 202 | fault buttons |
| 220 | `setManual()` |
| 233 | `setMode()` |
| 251 | `move()`, one grid cell |
| 272 | **detects a refused move and flashes the button red** |
| 302 to 317 | press and hold to keep moving, pointer events so mouse, touch and pen share one path |
| 376 | arrow keys |
| 389 | what if |
| 410 | command history |

**Point at line 49 to 53.** The console does not trust its own toggle. It reads
the robot's reported mode every second and disarms the pad if they disagree.

## D2. The console service: `services/web-control/main.py`, 272 lines

| Line | What |
|---|---|
| 66 | `require_login()`, optional password gate |
| 91 | `_query_latest()`, reads InfluxDB over HTTP |
| 116 | **parses with `csv.reader`, not `split(",")`** |
| 138 | `/api/state`, three measurements in one round trip |
| 158 | `VALID_COMMANDS` |
| 184 | `MACROS`, five named sequences |
| 193 | `/api/command` |
| 225 | `/api/macro` |
| 247 | `/api/access`, the phone address |
| 278 | `/api/fault` |
| 298 | `/api/whatif` |
| 324 | serves the static console |

**Say about the proxy design:**

> "The browser only ever talks to this one service. It proxies to the others, so
> no other port is exposed to the browser, and there is no CORS configuration to
> get wrong."

**Line 116 has a real bug story.** The original code split the CSV response on
commas. Then the AI recommendation text became "Normal operation, no action
needed", which contains a comma, and the split corrupted both the key and the
value. Using the `csv` module fixed it. Comment is at lines 112 to 114.

**Line 66, the password gate.** Uses `secrets.compare_digest` at line 77 so a
wrong password cannot be discovered by timing the response. It is off by default
on a laptop and required before exposing the console through a tunnel.

## D3. The command entry point: `services/command-api/main.py`, 226 lines

| Line | What |
|---|---|
| 173 | `issue_command()` |
| 175 | unknown robot ID gives 404 |
| 178 | mint `CMD-XXXXXXXX` |
| 182 to 200 | **choose the topic**: motion versus cleaning |
| 211 to 212 | register a pending acknowledgement |
| 215 | **publish to MQTT, QoS 1** |
| 228 | record the command in `robot_command` |
| 231 | **block waiting for the acknowledgement** |
| 237 to 244 | compute round trip latency |
| 104 | `_on_ack()`, receives the acknowledgement |
| 119 | subscribes to the ack topic |
| 83 | write the ack to `robot_acknowledgement` |

The request body is typed as `CommandRequest` from `models.py:234`, so an
unknown command is rejected by FastAPI with a 422 before any of this code runs.
Validation is free because the schema is shared.

**Line 231 is the line that makes this a twin:**

```python
ack_received = ack_event.wait(timeout=ACK_TIMEOUT_S)
```

**Say:**

> "The HTTP response does not return until the robot has actually confirmed. The
> operator is told what the robot did, not what the API hoped it would do. If
> the robot is offline, the call returns status timeout, honestly, after five
> seconds. It never pretends."

## D4. The robot obeys: back to `simulator.py`

- **Lines 78 to 80**: subscribes to the command topics.
- **Line 84**: `_on_command()`.
- **Line 97**: `_apply_command()`, the whole command table, under the state lock.
- **Line 151**: a `MOVE_*` command is refused outright if not in manual mode.
- **Line 177**: `_manual_step()`. **Line 187** checks the target cell is
  accessible. **Line 192** additionally refuses a diagonal that would cut a
  corner between two obstacles.
- **Line 199**: a blocked move still turns the robot to face the obstruction,
  but does not move it.
- **Line 219**: `_publish_ack()`.

**Say while driving into a wall live:**

> "The robot refused that, not the web page. Validation lives with the asset,
> which is where it belongs. If the wall check were in the browser, anyone with
> curl could drive straight through it."

**`_nearest_path_index()`, line 161.** When control is handed back, the robot
resumes from the waypoint nearest to where it actually is, preferring cells not
yet cleaned.

**Say:**

> "Before this, handing control back teleported the robot across the room to
> rejoin its old path position. A real bug, found during testing, fixed at line
> 143, and covered by tests in `tests/unit/test_manual_control.py`."

## D5. The complete round trip

```
app.js:184  ->  web-control/main.py:200  ->  command-api/main.py:215
                                                      |  MQTT
                                                      v
                                             simulator.py:84
                                             simulator.py:97   apply
                                             simulator.py:227  publish ACK
                                                      |  MQTT
                                                      v
                                          command-api/main.py:104
                                          command-api/main.py:231 unblocks
                                                      |  HTTP
                                                      v
                                                  app.js:188
```

**Six files, one button press.** Draw this on the whiteboard if there is one.

---

# PART E. THE THREE VIEWS

All three read the same InfluxDB. That is why they can never disagree.

## E1. Grafana

**Connection: `grafana/provisioning/datasources/influxdb.yaml`**
Line 7 is the url `http://influxdb:8086`, line 9 sets Flux as the query
language, line 14 injects the token from the environment so no secret is in the
repository.

**Dashboard: `grafana/dashboards/smartclean_twin.json`**, 1515 lines, 28 panels
in 7 sections.

**Say:**

> "The datasource and the dashboard are both files in version control, baked into
> the image. Nothing was clicked in the UI. If the Grafana volume is deleted,
> `docker compose up` restores all 28 panels exactly. That is infrastructure as
> code."

## E2. NVIDIA Omniverse

### `create_scene.py`, 254 lines: builds the world once

Hierarchy documented at lines 13 to 26.

| Function | Line | Creates |
|---|---|---|
| `_create_room()` | 105 | floor, 4 walls, 3 desks, ceiling light |
| `_create_coverage_grid()` | 182 | 100 tiles, `Tile_0_0` to `Tile_9_9` |
| `_create_cleaning_robot()` | 198 | BrushDeck, Body, StatusLight, BatteryBar, DirectionArrow |
| `_create_obstacle_indicator()` | 261 | red cube parked underground at z = -5 |
| `create_scene()` | 272 | runs all four and saves the USD |

**The direction arrow, lines 246 to 253.** A cone parented under
`/World/CleaningRobot`, so it inherits the parent rotation automatically. It
shows which way the robot faces, which a symmetric disc cannot express. It
matters most when the robot is stationary but still facing somewhere, such as
during a blocked manual move.

**The obstacle indicator, line 261.** Parked at z = -5 rather than toggling
visibility, because moving a prim is one transform write and needs no visibility
API.

### `live_update.py`, 288 lines: streams the twin into 3D

| Line | What |
|---|---|
| 87 | **builds the InfluxDB client** |
| 102 | `_query_latest()`, the Flux query |
| 112 to 114 | **cast to string, group, then pivot** |
| 160 | `_apply_trail()`, breadcrumb dots |
| 173 | `_apply_pose()`, position, heading, tile colouring |
| 213 | `_apply_obstacle_indicator()` |
| 232 | `_apply_safety()`, body colour and the flashing light |
| 247 | `_apply_battery()`, bar scale and colour |
| 259 | `tick()`, one update |
| 265 to 268 | the two queries: `robot_telemetry` and `robot_state` |
| 306 | the async 1 second loop |
| 324 | `start_live_update()` |

**This is the answer to Dr's question about 3D and MQTT. Be honest and be
specific:**

> "The 3D scene does not talk to MQTT. It reads InfluxDB, at line 87 and line
> 102. That is deliberate. The 3D view is a consumer, not a participant. It
> reads the same store Grafana reads, which is exactly why the dashboard and the
> 3D scene can never disagree. If I had subscribed it to MQTT directly it would
> have no history and would miss everything published while Omniverse was
> closed."

Then give the cost, unprompted:

> "The trade off is latency. MQTT would be milliseconds. This is up to one
> second because of the poll interval at line 64. For a robot at 0.2 metres per
> second that is 20 centimetres of error, which is acceptable here. For a high
> speed asset I would subscribe to MQTT and keep the database for history only."

Showing you chose, and knowing the price, is worth more than claiming a direct
link.

**Lines 112 to 114 are worth showing as a debugging story:**

```python
|> map(fn: (r) => ({r with _value: string(v: r._value)}))
|> group()
|> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
```

> "InfluxDB returns one table per field, and `safety_state` is a string while the
> others are floats. Without the cast they cannot share a pivot table. Without
> the group, pivot produces one row per field instead of one row with every
> field. Before these three lines the robot never turned red during an emergency.
> That took real debugging to find."

**What is driven live:**

| Property | Prim | Source | Line |
|---|---|---|---|
| Position | `/World/CleaningRobot` | `x_m`, `y_m` | 184 |
| Heading | same | `heading_deg` | 185 |
| Body colour | `.../Body` | `safety_state` | 243 |
| Status light, flashing | `.../StatusLight` | `safety_state` | 236 to 244 |
| Battery bar | `.../BatteryBar` | `battery_soc` | 247 |
| Tile turns green | `/World/CoverageGrid/Tile_X_Y` | position | 198 |
| Trail | `/World/Trail/Dot_N` | position change | 160 |
| Obstacle marker | `/World/ObstacleIndicator` | `safety_state` | 213 |

**Demo rule: paste `live_update.py` only once per Omniverse session.** Two loops
fight each other. If you need to restart it, run `stop_live_update()` first.

### `fault_demo.py`, 81 lines

Injects an obstacle, waits 8 seconds, clears it. A scripted version of the
manual fault demo, useful if your hands are busy.

## E3. The web console

Covered in Part D. It is both a view and a controller, which is the point.

---

# PART F. DEPLOYMENT

## F1. `docker-compose.yml`, 195 lines

**Lines 7 to 13, the `x-common-env` anchor.** Six services share one definition
of the MQTT and InfluxDB settings. Change the token once, every service follows.

**The nine services:** mosquitto (18), influxdb (35), grafana (57),
robot-simulator (77), telemetry-ingestion (96), state-engine (119), ai-service
(137), command-api (156), web-control (176).

**Healthchecks and ordering.** Mosquitto's healthcheck at **line 28** actually
subscribes to a topic, it does not just check the port is open. Services then
declare `depends_on: condition: service_healthy` (for example **line 109 to
113**), so a service never starts against a broker that is not ready.

**Lines 101 to 105, the port range.** Read the comment out loud:

```yaml
# A host port range lets replicas scale without clashing. The range must
# not overlap the fixed ports of the other services (8000, 8002, 8003,
# 8004, 8005): Docker allocates from it blindly and would otherwise steal
# a port another service needs, leaving that service unpublished.
- "8101-8111:8001"
```

**Say:**

> "This was originally 8001 to 8011. Docker allocated 8003 from that range for
> an ingestion replica, which is the AI service's port. The AI service was left
> unpublished and `localhost:8003` was answering with the wrong service's health
> endpoint. Predictions silently stopped reaching the console. Moving the range
> fixed it. That is the kind of bug you only find by actually running the thing."

**Volumes at line 202.** Named volumes for mosquitto, influxdb and grafana, so
data survives `docker compose down`.

Ingestion is the only service that scales, because MQTT fans out to every
subscriber and ingestion holds no state. The state engine and AI service hold in
memory history and deliberately do not scale.

## F2. `.github/workflows/ci.yml`, 104 lines

Five jobs, in a dependency chain:

```
lint-and-format
   |-> unit-tests --------> build-docker-images -> validate-compose
   `-> train-ai-model
```

| Job | Line | What |
|---|---|---|
| `lint-and-format` | 10 | ruff and black, pinned versions at line 22 |
| `unit-tests` | 30 | unit, integration and regression with coverage |
| `train-ai-model` | 66 | **retrains all five models and fails if quality drops** |
| `build-docker-images` | 88 | builds all five service images |
| `validate-compose` | 118 | `docker compose config --quiet` |

**Say about line 66:**

> "The AI model is retrained on every push and the job fails if accuracy falls
> below 0.80 or the anomaly detector misses a known fault. A model that degrades
> cannot reach main. Most student projects test code and trust the model. I gate
> both."

**Line 22, the pinned versions**, has a story: an unpinned linter released a new
version and failed CI on a teammate's docs only commit. Pinning fixed it.

## F3. The launcher scripts

- **`START-SMARTCLEAN-TWIN.bat`**: 7 steps. Docker, the 9 containers, the
  console, Grafana, InfluxDB, the walkthrough notebook in Jupyter Lab, and
  Omniverse with the scene.
- **`FIX-DOCKER.bat`**: recovers Docker Desktop from its Inference manager and
  Secrets Engine startup crash.
- **`PHONE-ACCESS.bat`**: opens a Cloudflare tunnel. **It refuses to open the
  tunnel unless an unauthenticated request returns 401**, so the robot controls
  can never reach the public internet without a password. That check exists
  because during an audit a restart dropped the password variable and the
  console was briefly exposed.
- **`MAKE-PDFS.bat`**: renders the notebooks to PDF.

---

# PART G. TESTING

204 tests, 82 percent coverage, four levels.

| Level | Files | Count | What it proves |
|---|---|---|---|
| Unit | `tests/unit/` 9 files | 169 | each function in isolation |
| Integration | `tests/integration/` 2 files | 11 | two services agreeing |
| System | `tests/system/` 2 files | 14 | the whole stack end to end |
| Regression | `tests/regression/` 1 file | 10 | fixed bugs stay fixed |

Notable files:

- `test_telemetry_schema.py`, 118 lines: valid and invalid messages, boundary
  values.
- `test_state_rules.py`, 165 lines: every threshold in `rules.py`.
- `test_manual_control.py`, 225 lines, 29 tests: manual driving, wall refusal,
  corner cutting, and the teleport fix.
- `test_return_to_dock.py`, 154 lines, 15 tests: low battery, low water, both,
  and the resume condition.
- `test_web_control.py`, 155 lines, 31 tests: the proxy, the macros, the
  password gate.
- `test_persistence.py`, 157 lines: data survives a container restart. Uses a
  frozen `[start, stop]` window, not a sliding `-60m`, because a sliding window
  made the test fail for reasons that had nothing to do with persistence.

**Say:**

> "The interesting tests are the failure cases. Stop the broker and the system
> tests fail. Start it and they pass again with no code change. That proves the
> tests are actually testing the connection and not just passing regardless."

**Coverage story worth telling:** the gate is `fail_under = 65`. A change once
took coverage to 64 percent. Rather than lower the gate, 44 new tests were
written and coverage went to 82 percent.

---

# PART H. THE LIVE DEMO, IN ORDER

Before the audience arrives, run `START-SMARTCLEAN-TWIN.bat` and paste
`live_update.py` into the Omniverse Script Editor once, then run
`start_live_update()`.

### 1. It is running. Terminal.

```bash
docker compose ps
```

```bash
py scripts\smoke_test.py
```

Nine containers, eight green health checks.

> "Nine containers. Six microservices I wrote, plus the MQTT broker, the time
> series database and Grafana. One command starts all of them."

### 2. The messages. Terminal. This is the MQTT moment.

```bash
docker exec smartclean-mosquitto mosquitto_sub -t "smartclean/SCR01/#" -v
```

Every topic scrolls live: raw, validated, state, prediction, ack.

> "This is the nervous system. The robot publishes raw telemetry once a second.
> Ingestion validates it and republishes to validated. The state engine and the
> AI service both subscribe to validated and publish their own conclusions. One
> message, three consumers, no polling."

**If Dr asks where in the code: `simulator.py:513`.**

### 3. The console. `localhost:8005`

Point at the status strip: safety, mission, AI health, anomaly, and the plain
English recommendation.

> "Everything here comes from the same InfluxDB that Grafana reads, so the two
> can never disagree. The browser talks to one service, which proxies to the
> others."

### 4. A command. Press Pause, then Resume.

Read the acknowledgement box out loud: command ID, status, ACK received,
accepted, timestamp.

> "REST to MQTT to the robot, the robot obeys and acknowledges, and that
> acknowledgement is what you are reading. A dashboard only displays. A twin
> commands, and confirms."

### 5. Manual driving.

Take manual control, drive with the pad or the arrow keys, then **drive into a
wall on purpose**. The button flashes red.

> "The robot refused that, not the web page."

Return to autonomous.

> "It carries on from where I left it. It does not jump back. That was a bug we
> found and fixed."

### 6. What if. The strongest moment.

Set temperature 95, current 3.8, run. Then a healthy scenario to contrast.

> "I asked the virtual copy a question the real robot must never be asked. The
> robot was never touched."

### 7. Fault injection. Grafana and Omniverse both visible.

Press Obstacle. Within seconds: console red, Grafana red, robot red in 3D with
a flashing light and a red obstacle marker in front of it.

> "One injected fault, three views react to the same state change, because all
> three read the same store."

Press Clear all. Everything returns to green.

### 8. The database. `localhost:8086`

Show `robot_telemetry`, `robot_state`, `robot_prediction` side by side.

> "Measurement, conclusion, prediction. Three separate measurements on purpose."

### 9. The code. Four files.

`simulator.py:513`, `telemetry-ingestion/main.py:119`, `rules.py:179`,
`command-api/main.py:231`.

### 10. Scaling.

```bash
docker compose up --scale telemetry-ingestion=2 -d
```

> "Ingestion is stateless and MQTT fans out, so it scales. The state engine and
> the AI service hold in memory state, so they deliberately do not."

### 11. Tests and CI.

```bash
py -m pytest tests/unit -q
```

Then the green GitHub Actions page.

### 12. Optional: the phone.

Drive the robot from your phone while the laptop shows Grafana reacting.

---

# PART I. QUESTION BANK

**"Where does the message enter MQTT?"**
`simulator.py:513`. Topic defined once at `topics.py:9`. Prove it with
`mosquitto_sub`.

**"Where do you connect to the database?"**
`telemetry-ingestion/main.py:54` builds the client, line 87 writes. Credentials
from `docker-compose.yml:7-13`. Hostname `influxdb` is the container name,
resolved by Docker DNS. No IP addresses anywhere.

**"How does the 3D scene get its data?"**
InfluxDB, not MQTT: `live_update.py:87` and `102`. Then the justification and
the latency trade off from Part E2.

**"Why MQTT for telemetry and REST for commands?"**
Telemetry is one publisher and four subscribers. REST would mean four services
polling the robot, four times the load, and four different views of "now". MQTT
delivers one message to every subscriber, with a 2 byte fixed header. A command
is one request wanting one answer, and browsers speak HTTP. But `command-api/main.py:231`
still blocks on the MQTT acknowledgement, so REST at the edge does not weaken
the loop.

**"What happens to a bad message?"**
`telemetry-ingestion/main.py:119` rejects it, line 92 quarantines it in a
separate measurement with the reason, line 162 reports the rejection rate. Never
silently dropped.

**"What if the broker dies?"**
Ten retries with exponential backoff in every service: `simulator.py:490`,
`telemetry-ingestion/main.py:146`, `command-api/main.py:131`. The twin marks
itself OFFLINE via `rules.py:185` after ten seconds of silence. Demonstrable:
stop mosquitto, the system tests fail, start it, they pass again.

**"Is this real time?"**
1 second telemetry, sub second command acknowledgement, 1 second 3D poll, 5
second Grafana refresh. Give the real numbers. Do not claim milliseconds.

**"Is the AI actually necessary, or is it decoration?"**
Three of the five outputs drive the recommendation at `ai-service/main.py:94`,
which appears on the console. The anomaly detector catches faults nobody
labelled. And the RUL regressor answers a question no threshold can: not "is it
bad now" but "how long until it is".

**"How do you know it works?"**
204 tests, 82 percent coverage, four levels, and CI that gates the model as well
as the code.

**"What are the limitations?"**
Have three ready, and volunteer one before you are asked:

1. The state engine uses module level globals at `state-engine/main.py:44-46`,
   so it assumes a single robot. The topic structure at `topics.py:7` already
   anticipates a fleet, but the state engine does not yet.
2. The 3D view is up to one second behind because it polls rather than
   subscribes.
3. The thresholds in `rules.py` are fixed constants. On a real fleet they should
   be learned per asset.

**Say:**

> "Those are real limits and I know exactly where each one lives in the code.
> That is different from not having found them."

---

# PART J. NUMBERS TO MEMORISE

| | |
|---|---|
| Containers | 9, six of them services I wrote |
| Telemetry | 16 fields, once per second |
| Twin state | 11 dimensions |
| AI models | 5, across 3 learning paradigms |
| Health classifier accuracy | 90.8 percent |
| RUL regressor | R squared 0.91, mean error 6.6 minutes |
| Anomaly detector | 100 percent of known faults, no false alarms |
| Grafana | 28 panels in 7 sections |
| Tests | 204, coverage 82 percent |
| Documented service pairs | 18, in `docs/api-contract.md` |
| Room | 5 m by 5 m, 10 by 10 grid, 0.5 m cells |
| MQTT topics | 9 |
| InfluxDB measurements | 7 |

---

# PART K. IF SOMETHING BREAKS

| Problem | Fix |
|---|---|
| Docker will not start | `FIX-DOCKER.bat` |
| A container unhealthy | `docker compose restart <service>` |
| Console says disconnected | wait 5 seconds, it polls once per second |
| Robot not moving in 3D | in Omniverse: `stop_live_update()` then `start_live_update()` |
| Robot not moving at all | press Start, and check it is not in manual mode |
| Everything looks wrong | `docker compose restart`, wait 30 seconds |

**Reset to a clean demo state:** Clear all, then Return to autonomous, then
Start wet clean.

**If a question goes somewhere you did not prepare:** say what you do know, say
where in the code you would look, and offer to open it. Knowing where the answer
lives is a legitimate answer.
