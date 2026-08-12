# SmartClean Twin: Presentation Deep Dive

Everything in one place, with the exact file and line for every claim. If Dr
points at the screen and asks "where does that happen", you open the file named
here and scroll to the line named here.

Repository: `https://github.com/KAI-UTP/smartclean-twin`

---

## Part 0. The one minute version

Say this first, before any code:

> "SmartClean Twin is a Digital Twin of an indoor cleaning robot. Nine
> containers. The robot publishes 16 sensor fields every second over MQTT. A
> validation service checks every message against a schema and writes it to a
> time series database. A state engine turns raw sensors into eleven twin state
> dimensions. An AI service runs five models on the same stream. Three views
> read that one database: a Grafana dashboard, a 3D scene in NVIDIA Omniverse,
> and a web console I can drive the robot from, including from my phone. The
> commands go back down the same MQTT path and the robot acknowledges each one,
> which is what makes it a twin and not a dashboard."

---

## Part 1. The nine containers

Defined in `docker-compose.yml`.

| Container | Port | What it is | Line |
|---|---|---|---|
| `mosquitto` | 1883 | MQTT broker | 18 |
| `influxdb` | 8086 | Time series database | 35 |
| `grafana` | 3001 | Dashboard | 57 |
| `robot-simulator` | 8004 | The physical entity (D1) | 77 |
| `telemetry-ingestion` | 8101-8111 | Validation and storage | 96 |
| `state-engine` | 8002 | Twin state rules (D2) | 119 |
| `ai-service` | 8003 | Five AI models (D3) | 137 |
| `command-api` | 8000 | Command entry point | 156 |
| `web-control` | 8005 | Operator console | 176 |

Six of these are services I wrote. Three are infrastructure I configured.

**If Dr asks why ingestion has a port range and the others do not:**
`docker-compose.yml:101-105`. The comment there is the answer. Ingestion is the
only service that can be scaled horizontally, so it gets a range. The range is
deliberately 8101-8111 and not 8001-8011, because Docker allocates from a range
blindly and 8003 inside that range would have been stolen from the AI service.

---

## Part 2. The data path, robot to screen (P2V)

This is the question Dr asked the other group. Walk it in this exact order.

### Step 1. The robot produces a state snapshot

**File: `services/robot-simulator/simulator.py`**

- `_update_physics()` at **line 232** is the physics tick. It runs once per
  second: navigation, battery drain, motor heating, water use.
- `_build_telemetry()` at **line 428** turns that state into one JSON message,
  16 fields, grouped into `pose`, `sensors`, `actuators`, `mission`.

Point at **line 438**, the `with s.lock():`. Say:

> "The whole message is built while holding the state lock. Two threads mutate
> this state, the physics loop and the MQTT command thread. Without the lock a
> message could carry a position from before a command and a heading from after
> it. A twin's telemetry has to be one coherent instant, not a mix of two."

That is a real bug I found and fixed, and it is the kind of detail that
separates a twin from a data logger.

### Step 2. It is published to MQTT

**`simulator.py:513`**

```python
self._mqtt_client.publish(Topics.TELEMETRY_RAW, json.dumps(telemetry), qos=1)
```

- The topic string is defined once in `shared/smartclean_common/topics.py:9`:
  `smartclean/SCR01/telemetry/raw`.
- QoS 1 means at least once delivery. Telemetry must not silently vanish.
- The connection itself is made at **`simulator.py:492`**, with ten retry
  attempts and exponential backoff, and `loop_start()` at **line 501** runs the
  network loop on its own thread.

**This is the "where is the message going to MQTT" answer. Line 513.**

To prove it live, in a terminal:

```bash
docker exec smartclean-mosquitto mosquitto_sub -t "smartclean/SCR01/#" -v
```

Every topic scrolls past in real time. This is the single most convincing thing
you can show for the messaging question.

### Step 3. Validation, the gate

**File: `services/telemetry-ingestion/main.py`**

- Subscribes at **line 134** to `telemetry/raw`.
- `_on_message()` at **line 106** is the callback that fires per message.
- **Line 111** parses JSON. Bad JSON is counted and quarantined.
- **Line 119**, `TelemetryMessage.model_validate(data)`. This is the gate.

The schema is `shared/smartclean_common/models.py:144`. Every field has bounds:
`battery_soc` must be 0 to 100 (**models.py:121**), `heading_deg` must be 0 to
under 360 (**models.py:115**). There are two custom validators at
**models.py:154** and **161**.

Say:

> "Nothing enters the twin without passing this schema. One Pydantic model is
> the single source of truth, shared by four services, so they cannot disagree
> about what a message looks like."

Rejected messages are not dropped silently. `_write_invalid_to_influx()` at
**line 92** records them in a separate measurement with the reason, so the
rejection rate is itself measurable. `/health` at **line 162** reports
`valid_rate_pct`.

### Step 4. Written to the database

**`telemetry-ingestion/main.py:59-89`**, `_write_telemetry_to_influx()`.

**This is the "where do you connect to the database" answer.**

- The client is built at **line 54**: `InfluxDBClient(url=..., token=..., org=...)`.
- The connection details come from environment variables at **lines 39-42**.
- Those variables are injected by `docker-compose.yml:7-13`, the
  `x-common-env` anchor, which is reused by every service. One definition, six
  consumers.
- The URL is `http://influxdb:8086`. That hostname is the container name on the
  Docker network, resolved by Docker's internal DNS. There is no IP address
  anywhere in the code.
- The write happens at **line 87**, into measurement `robot_telemetry`, tagged
  by `robot_id`, with 16 fields.

The write API is cached in a module level global (**line 51-56**) so a new HTTP
connection is not opened every second.

There is also a shared helper at `shared/smartclean_common/influx_client.py:25`
for services that write occasionally rather than every tick.

### Step 5. Republished for downstream services

**`telemetry-ingestion/main.py:128`** publishes to `telemetry/validated`.

Say:

> "Two topics, not one, on purpose. Raw is what the robot said. Validated is
> what the system accepted. Everything downstream subscribes to validated, so no
> service ever has to re-check the schema, and I can measure exactly what was
> rejected."

### Step 6a. The state engine turns sensors into twin state

**File: `services/state-engine/main.py`**

- Subscribes to validated at **line 159**.
- **Line 135** calls `rules.evaluate(...)`.
- Publishes the state to `smartclean/SCR01/state` at **line 138**.
- Writes it to InfluxDB measurement `robot_state` at **line 144**, implemented
  at **lines 62-83**.

**File: `services/state-engine/rules.py`**, the behaviour model.

| Dimension | Line | Rule |
|---|---|---|
| Safety state | 59 | obstacle under 25 cm or bumper active is EMERGENCY, under 50 cm is WARNING |
| Battery state | 83 | under 10 percent CRITICAL, under 20 percent LOW |
| Motor health | 101 | over 70 C OVERHEATED, over 2.5 A HIGH_LOAD |
| Dirt level | 129 | 0.7 and above DIRTY, 0.3 and above MODERATE |
| Cleaning state | 137 | driven by brush and dirt score |
| Operation mode | 148 | mapped from the robot's reported mode |
| Mission state | 161 | composite of coverage, battery and mode |
| Connection and twin quality | 179 | message age: over 2 s DELAYED, over 10 s OFFLINE |

Say, pointing at **rules.py:179**:

> "This is the part most projects miss. The twin knows how good it is. If
> telemetry is more than two seconds late, the twin marks itself DELAYED, and
> over ten seconds INVALID. A twin that does not know it is stale is dangerous,
> because the operator keeps trusting it."

Alarms are generated alongside state, published at **main.py:141** and written
to `robot_alarm` at **line 86**.

### Step 6b. The AI service predicts, on the same stream

**File: `services/ai-service/main.py`**

- Subscribes to validated telemetry **and** to twin state, **lines 221-222**.
- `_on_message()` at **line 153** dispatches.
- **Line 175** runs all five models in one call.
- **Lines 189-194** add the two trend forecasts.
- **Line 195** produces the plain English recommendation.
- Publishes to `smartclean/SCR01/prediction` at **line 203**.
- Writes to `robot_prediction` at **line 204**, implemented at **line 117**.

Note that the prediction is stored as a *separate measurement* from telemetry
and from state. Say:

> "Three measurements, deliberately. `robot_telemetry` is what the sensors
> measured. `robot_state` is what the twin concluded. `robot_prediction` is what
> the AI thinks will happen. Module 2 makes that distinction and I kept it in
> the storage layer, because mixing a measurement with a prediction in one table
> is how you end up unable to tell them apart later."

---

## Part 3. The command path, screen to robot (V2P)

This is the half that makes it a twin. Walk it top to bottom.

### Step 1. The browser

**`services/web-control/static/app.js:184`** posts to `/api/command`.

The manual pad is at **line 251**, `move()`. Arrow keys are wired at **line
376**. Press and hold repeat is at **lines 302-317**.

### Step 2. The console service proxies it

**`services/web-control/main.py:193`**, `send_command()`.

- **Line 196** rejects anything not in `VALID_COMMANDS` (**line 158**).
- **Line 200** forwards to the Command API over HTTP.

Say:

> "The browser only ever talks to this one service. It proxies to the others, so
> no other port is exposed to the browser and there is no CORS configuration to
> get wrong."

Macros are at **line 225**: one button press sends three commands and returns
all three acknowledgements, so a partial failure is visible.

### Step 3. The Command API validates and publishes

**File: `services/command-api/main.py`**

- `issue_command()` at **line 173**.
- **Line 175** checks the robot ID exists, 404 otherwise.
- The request body is typed as `CommandRequest` (`models.py:234`), so an unknown
  command is rejected by FastAPI with a 422 before any code runs.
- **Line 178** mints a command ID, `CMD-XXXXXXXX`.
- **Line 200** chooses the topic. Motion commands go to `command/motion`,
  everything else to `command/cleaning`.
- **Line 215** publishes with QoS 1.

Say:

> "The REST call ends here. From this point it is MQTT. REST is right at the
> edge because a browser speaks HTTP and a command is a single request that
> wants a single answer. MQTT is right inside because telemetry is one publisher
> and many subscribers, and a request-response protocol would force every
> service to poll."

### Step 4. The robot receives and obeys

**File: `services/robot-simulator/simulator.py`**

- Subscribes to the command topics at **lines 78-80**.
- `_on_command()` at **line 84** is the callback.
- `_apply_command()` at **line 97** is the whole command table.

Show these two specifically:

- **Line 151**, a `MOVE_*` command is rejected outright if the robot is not in
  manual mode.
- **Line 177**, `_manual_step()`. **Line 187** checks the target cell is
  accessible. **Line 192** additionally refuses a diagonal that would cut a
  corner between two obstacles.

Say while driving into a wall in the demo:

> "The robot refused that, not the web page. Validation lives with the asset,
> which is where it belongs. If I moved the wall check into the browser, anyone
> with curl could drive through it."

### Step 5. The acknowledgement comes back

- `_publish_ack()` at **`simulator.py:219`** publishes to `smartclean/SCR01/ack`.
- Back in `command-api/main.py`, `_on_ack()` at **line 104** receives it.
- **Line 231** is the interesting line: the HTTP request is *blocked* on a
  `threading.Event` until the ACK arrives or five seconds pass.
- **Lines 237-244** compute the round trip latency.
- The ACK is written to `robot_acknowledgement` at **line 83**.

Say:

> "This is the closed loop. The HTTP response does not return until the robot
> has actually confirmed. The operator is told what the robot did, not what the
> API hoped it would do. If the robot is offline the call returns status
> timeout, honestly, after five seconds."

**Full round trip: `app.js:184` to `web-control/main.py:200` to
`command-api/main.py:215` to `simulator.py:84` to `simulator.py:227` to
`command-api/main.py:104` and back up. Six files, one command.**

---

## Part 4. The 3D layer, and the question you must get right

Dr asked the other group "where can I see the message transfer from 3D to MQTT".
For this project the honest answer is: **the 3D scene does not talk to MQTT. It
reads InfluxDB.** Do not fudge this. Explain why it is the right choice.

**File: `omniverse/live_update.py`**

- The InfluxDB client is created at **line 87**.
- `_query_latest()` at **line 102** is the Flux query.
- The two queries are at **lines 265-268**: one for `robot_telemetry`, one for
  `robot_state`.
- The 1 second loop is at **line 306**, started by `start_live_update()` at
  **line 324**.

Say:

> "The 3D view is a consumer, not a participant. It reads the same database
> Grafana reads, which is exactly why the dashboard and the 3D scene can never
> disagree. If I had subscribed the 3D scene to MQTT directly, it would show
> live messages but it would have no history, it would miss everything published
> while Omniverse was closed, and the two views could drift apart. Reading the
> store means the 3D scene shows the twin's state, not a stream of packets."

Then add the honest limit:

> "The trade off is latency. MQTT would be milliseconds, this is up to one
> second because of the poll interval at line 64. For a robot moving at 0.2
> metres per second that is 20 centimetres of error, which is acceptable here.
> For a high speed asset I would subscribe to MQTT and use the database only for
> history."

That answer is stronger than claiming a direct MQTT link, because it shows you
chose.

### What is actually driven in 3D

| Property | USD prim | Source | Line |
|---|---|---|---|
| Position | `/World/CleaningRobot` | `x_m`, `y_m` | 184 |
| Heading | same | `heading_deg` | 185 |
| Body colour | `.../Body` | `safety_state` | 243 |
| Status light, flashing | `.../StatusLight` | `safety_state` | 236-244 |
| Battery bar scale and colour | `.../BatteryBar` | `battery_soc` | 247 |
| Tile turns green | `/World/CoverageGrid/Tile_X_Y` | position | 198 |
| Breadcrumb trail | `/World/Trail/Dot_N` | position change | 160 |
| Obstacle marker | `/World/ObstacleIndicator` | `safety_state` | 213 |

**The direction arrow**, if asked: `omniverse/create_scene.py:246-253`. It is a
cone parented under `/World/CleaningRobot`, so it inherits the parent's
rotation automatically. It shows which way the robot is facing, which a
symmetric disc otherwise cannot express. The robot can be stationary and still
be facing somewhere, and during a blocked manual move it turns to face the
obstruction without moving, which you can only see because of the arrow
(`simulator.py:199`).

**One flux detail worth knowing**, `live_update.py:112-114`. InfluxDB returns
one table per field, and `safety_state` is a string while the others are floats.
The `map` casts everything to string, `group()` merges the tables, then `pivot`
gives one row with every field. Without those three lines the robot never turned
red, and that was a real bug I had to debug.

**Rule for the demo: paste `live_update.py` only once per Omniverse session.**
Pasting twice starts two loops that fight each other.

---

## Part 5. Grafana

**Connection: `grafana/provisioning/datasources/influxdb.yaml:7`**, url
`http://influxdb:8086`, query language Flux (**line 9**), token injected from
the environment at **line 14** so no secret is in the repository.

The datasource is provisioned as a file baked into the image, not clicked in the
UI. Say:

> "The dashboard and its datasource are both in version control. If the Grafana
> volume is deleted, `docker compose up` restores all 28 panels exactly. Nothing
> about this system is configured by hand."

The dashboard is `grafana/dashboards/smartclean_twin.json`, 28 panels in 7
sections.

---

## Part 6. The AI

**File: `services/ai-service/predictor.py`**

| Model | Type | Paradigm | Line |
|---|---|---|---|
| `motor_health_clf` | Random Forest | Supervised classification | 132 |
| `dirt_level_clf` | Random Forest | Supervised classification | 135 |
| `health_state_clf` | Random Forest | Supervised classification | 154 |
| `rul_regressor` | Random Forest | Supervised regression | 156 |
| `anomaly_detector` | Per sensor mean and standard deviation | Unsupervised | 162 |

Three learning paradigms. Training is in `train_model.py`, using a
`StandardScaler` inside a `Pipeline` so the scaler is fitted on the training
fold only and cannot leak test statistics.

The anomaly detector at **line 162** is the one to explain, because it is
unsupervised:

> "It learned from normal operation only. It never saw a fault during training.
> It stores the mean and standard deviation of five sensors, and flags a sample
> when any one of them is more than 4.5 standard deviations out. It catches
> faults nobody labelled, which a supervised classifier by definition cannot."

**The fallback at line 178** is worth pointing out unprompted:

> "If the model files are missing, `predict` falls back to rule based logic and
> reports `model_used: rule_fallback`. The twin degrades, it does not crash, and
> it tells you which path it took."

**What-if simulation, `ai-service/main.py:273`**, is the single strongest moment
in the demo. Say:

> "This is the defining capability of a Digital Twin. I can ask the virtual copy
> a question the real robot must never be asked. What happens at 95 degrees and
> 3.8 amps? It answers with the health state, the remaining useful life, whether
> it is anomalous, and what the operator should do. The robot was never touched.
> That is simulation, and it is the thing a dashboard fundamentally cannot do."

---

## Part 7. The autonomous behaviour, if asked to prove intelligence

**`simulator.py:251-264`.** When battery drops below 20 percent *or* water below
15 percent, the robot sets its own mode to RETURNING. Nobody commanded it.

**`simulator.py:268-300`.** At the dock it charges and refills, and resumes
cleaning only when **both** are ready.

Say:

> "Both conditions, not either. Otherwise the robot could set off with a full
> battery and an empty tank and pretend to clean."

**`simulator.py:251`** has a subtlety worth showing: the injected low battery
fault is deliberately excluded from this trigger, so a fault demonstration does
not silently turn into a recovery demonstration.

**`simulator.py:161`, `_nearest_path_index()`.** When manual control is handed
back, the robot resumes from the waypoint nearest to where it actually is,
preferring cells not yet cleaned. Say:

> "Before I fixed this, handing control back teleported the robot across the
> room to rejoin its old path position. That was a real bug found during
> testing, and there are 15 tests in `tests/unit/test_manual_control.py`
> covering it."

---

## Part 8. The 5D framework, if Dr asks to map it

| Dimension | In this project | Where |
|---|---|---|
| D1 Physical Entity | The robot, software emulated | `services/robot-simulator/` |
| D2 Virtual Model | Geometry, physics, behaviour, rules | `omniverse/create_scene.py`, `simulator.py:232`, `rules.py`, `predictor.py` |
| D3 Services | Prediction, what-if, commands, alarms | `ai-service/`, `command-api/` |
| D4 Data | Three measurements, one schema | InfluxDB, `models.py` |
| D5 Connections | MQTT both ways, REST at the edge | `topics.py`, `mqtt_client.py` |

P2V is Part 2 of this document. V2P is Part 3.

---

## Part 9. Question bank

**"Where does the message go into MQTT?"**
`simulator.py:513`. Topic defined at `topics.py:9`. Prove it with
`mosquitto_sub`.

**"Where do you connect to the database?"**
`telemetry-ingestion/main.py:54` builds the client, line 87 writes. Credentials
from `docker-compose.yml:7-13`. Hostname `influxdb` is the container name,
resolved by Docker DNS.

**"How does the 3D scene get the data?"**
It reads InfluxDB, not MQTT: `live_update.py:87` and `102`. Then give the
justification in Part 4.

**"Why MQTT and not REST for telemetry?"**
One publisher, four subscribers. With REST each service would poll the robot,
which is four times the load and gives four different views of "now". MQTT
delivers one message to every subscriber. Also a 2 byte fixed header versus HTTP
headers, at one message per second per robot, which matters at fleet scale.

**"Why REST and not MQTT for commands?"**
A command is one request wanting one answer, and browsers speak HTTP. But look
at `command-api/main.py:231`: the REST call still blocks on the MQTT
acknowledgement, so the operator gets the robot's real answer, not the API's
optimism.

**"What if a bad message arrives?"**
`telemetry-ingestion/main.py:119` rejects it, line 92 quarantines it in a
separate measurement with the reason, line 162 reports the rejection rate. It is
never silently dropped. Tests for this are in
`tests/unit/test_telemetry_schema.py`.

**"What if the broker dies?"**
Every service retries with exponential backoff, ten attempts:
`simulator.py:490`, `telemetry-ingestion/main.py:146`,
`command-api/main.py:131`. The twin marks itself OFFLINE via `rules.py:185`
after ten seconds of silence. You can demonstrate this: stop mosquitto, the
system tests fail, start it, they pass again with no code change.

**"Is this real time?"**
One second telemetry, sub second command acknowledgement. The 3D view polls at
one second, `live_update.py:64`. Grafana refreshes at five seconds. Give the
honest number, do not claim milliseconds.

**"How do you know it works?"**
204 tests, 82 percent coverage, four levels: unit, integration, system,
regression. CI at `.github/workflows/ci.yml` runs lint, tests, an AI training
gate, Docker builds and a compose validation on every push.

**"What would you do differently?"**
Three honest answers, pick one. Subscribe the 3D view to MQTT for sub second
latency and keep the database for history. Replace the fixed thresholds in
`rules.py` with learned ones. Add a second robot, which the topic structure at
`topics.py:7` already anticipates but the state engine's module level globals at
`state-engine/main.py:44-46` currently do not, because they assume one robot.

That last one is a real limitation. Saying it before Dr finds it is worth more
than hiding it.

---

## Part 10. Screen order for the live demo

1. Terminal: `docker compose ps`, nine containers up.
2. Terminal: `mosquitto_sub -t "smartclean/SCR01/#" -v`, the messages flowing.
   **This is the moment for the MQTT question.**
3. Console at `localhost:8005`: the twin, the map, the status strip.
4. Console: Pause, then Resume, and read the acknowledgement out loud.
5. Console: manual control, drive into a wall, hand back to autonomous.
6. Console: what-if, healthy scenario then 95 degrees.
7. Console: inject Obstacle, with Grafana and Omniverse both visible. Three
   views turn red together. Clear all.
8. InfluxDB at `localhost:8086`: the three measurements side by side.
9. Code: `simulator.py:513`, `telemetry-ingestion.py:119`, `rules.py:179`,
   `command-api/main.py:231`. Four lines, the whole architecture.
10. Terminal: `py -m pytest tests/unit -q`, and the green CI page.

Everything above is launched by `START-SMARTCLEAN-TWIN.bat`.
