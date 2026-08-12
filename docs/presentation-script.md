# SmartClean Twin — Presentation Script (~13 minutes)

How to use: each part shows **[SCREEN: what to show]** then the words to say.
Say it naturally in your own way — these are your lines, not to read robotically.
Before recording: run `START-SMARTCLEAN-TWIN.bat`, start Omniverse live update,
and log into Grafana. Have these windows ready: browser (Grafana + Jupyter tabs),
Omniverse, PowerShell terminal, GitHub page.

---

## Part 1 — Introduction (1 min)
**[SCREEN: title slide or the walkthrough notebook title cell with team table]**

> "Hello, we are Group SmartClean Twin. Our members are Chan Li Kai, William
> Wong Xiao Kang, Irvin Chang Hou Ceng, Liang Yan Ee, and Nurin Emelin.
> Our project is a Digital Twin of a mobile cleaning robot.
>
> The PROBLEM: cleaning robots work unattended — nobody sees a failing motor,
> a stuck robot, or a dying battery until the job is not done. Manual checking
> does not scale.
>
> Our PURPOSE is a SMART outcome: the twin monitors the robot every second,
> detects unsafe conditions within five seconds, predicts remaining useful
> life, and reports cleaning progress toward one hundred percent room
> coverage — and coverage percentage is our measure of success, displayed
> live on the dashboard.
>
> The SENSOR INPUTS are sixteen measurables: position, heading, speed,
> obstacle distance, battery voltage, current and state of charge, motor
> current and temperature, dirt score, water level, bumper, and brush and
> pump states.
>
> A digital twin is a live virtual copy of a physical machine. Our twin does
> four things: it MONITORS the robot in real time, it PREDICTS failures using
> AI, it ADVISES the operator what to do, and it can CONTROL the robot with
> commands. The robot is simulated, but everything else is real production
> architecture. If we buy a real robot tomorrow, we only replace one
> container — the simulator — and everything else works unchanged."

## Part 2 — Architecture (1.5 min)
**[SCREEN: architecture diagram cell in project_walkthrough.ipynb]**

> "Let me follow one sensor reading through the system.
> The Robot Simulator runs physics every second and publishes JSON telemetry
> to the MQTT broker — Mosquitto on port 1883. Services never talk to each
> other directly; they publish and subscribe to topics, so any service can
> crash and restart without breaking the others.
>
> The Telemetry Ingestion service validates every message against a schema —
> wrong fields or impossible values are rejected. Valid data goes into
> InfluxDB, a time-series database.
>
> The State Engine turns raw numbers into twin state — eleven dimensions like
> safety state, battery state, mission state, and cleaning coverage.
> The AI Service runs five machine-learning models on every message.
> And two visualizations read the same database: Grafana and NVIDIA Omniverse.
> One source of truth, two views.
>
> Commands go the opposite direction: REST API to MQTT to the robot, and the
> robot sends an acknowledgement back. So the twin is bidirectional."

## Part 3 — Deployment / Terminal (1 min)
**[SCREEN: PowerShell terminal]**
**[TYPE: `docker compose ps`]**

> "The system is partitioned into nine containers — one per microservice,
> deployed with a single command: docker compose up. Here you can see all
> eight running: simulator, MQTT broker, ingestion, state engine, AI service,
> command API, InfluxDB and Grafana.
>
> The interface contract between every pair of services — topic, port,
> protocol and data format — is documented in our api-contract document."

**[TYPE: `docker compose up --scale telemetry-ingestion=2 -d` then `docker compose ps`]**

> "The ingestion service scales horizontally — here I start a second instance.
> This is safe because MQTT delivers messages to all subscriber instances."

**[TYPE: `docker compose up --scale telemetry-ingestion=1 -d` to scale back]**

**[Now demonstrate command & control — TYPE:]**
```
curl.exe --% -X POST http://localhost:8000/api/v1/commands -H "Content-Type: application/json" -d "{\"robot_id\":\"SCR01\",\"command\":\"PAUSE\"}"
```

> "The twin also CONTROLS the robot. I send a PAUSE command through the REST
> API — it travels over MQTT to the robot, the robot obeys, and sends back an
> acknowledgement — you can see it accepted in the response. Watch the speed
> drop to zero on the dashboard and the robot stop in Omniverse."

**[Wait 5 seconds, then RESUME:]**
```
curl.exe --% -X POST http://localhost:8000/api/v1/commands -H "Content-Type: application/json" -d "{\"robot_id\":\"SCR01\",\"command\":\"RESUME\"}"
```

> "And RESUME — the robot continues cleaning. This two-way loop with
> acknowledgements is what makes it a true digital twin, not just a
> monitoring dashboard."

## Part 4 — Grafana Dashboard (2 min)
**[SCREEN: browser — http://localhost:3001/d/smartclean-main]**

> "This is the operator dashboard — 28 panels in 7 sections, refreshing every
> 5 seconds, arranged like a control room."

**[SCROLL slowly through each section while talking]**

> "The top strip gives one-glance status: safety state, mission state, AI
> health prediction, anomaly flag, and the AI recommendation in plain words.
>
> Battery and Power — state of charge, voltage, and the discharge rate
> calculated with a derivative query.
>
> Motion and Environment — position and obstacle distance.
>
> Motor and Cleaning — here is our measure of success: cleaning coverage
> percentage, live from the state engine.
>
> AI Predictions — all five model outputs including remaining useful life in
> minutes and the anomaly score.
>
> Statistical Trends — 30-second and 1-minute aggregation windows.
> And the full alarm history at the bottom."

## Part 5 — Omniverse 3D Twin (1.5 min)
**[SCREEN: Omniverse window with robot moving]**

> "This is the same twin in 3D, built with NVIDIA Omniverse — the same
> platform BMW and Siemens use for factory digital twins.
>
> The robot moves using live positions from InfluxDB, updated every second.
> The green arrow shows heading. Floor tiles turn green as cells are cleaned.
> The bar on top of the robot is the battery — it shrinks and changes colour.
> The blue dots are the breadcrumb trail of the path taken.
> The robot body colour is the safety state — green means SAFE.
> Watch what happens to it in the fault demo in a moment."

## Part 6 — AI Models (2 min)
**[SCREEN: Jupyter — project_walkthrough.ipynb, AI section table]**

> "Our AI layer has five models covering all three machine-learning paradigms.
> Classification: motor health, dirt level, and a three-class health state
> with 90.8 percent accuracy. Regression: remaining useful life in minutes,
> with R-squared 0.91 and average error of 6.6 minutes.
> And unsupervised anomaly detection — this model was trained only on NORMAL
> operation. It learned the statistics of healthy sensors, so it can flag
> faults it was never shown during training.
>
> Models are trained with a stratified 80/20 split, and training runs during
> the Docker build, so the models are baked into the image — reproducible."

**[RUN the what-if cell in the notebook]**

> "This is what-if simulation — the defining digital twin capability.
> We ask the models hypothetical questions without touching the robot.
> What if the motor reaches 90 degrees at 3.6 amps? The twin answers:
> health WARNING, remaining life drops to about 30 minutes, anomaly detected,
> and it recommends inspecting the robot."

## Part 7 — Live Fault Demo (1.5 min) — THE HIGHLIGHT
**[SCREEN: split or switch between — Grafana overview strip + Omniverse]**
**[TERMINAL — TYPE:]**
```
curl.exe --% -X POST http://localhost:8004/fault -H "Content-Type: application/json" -d "{\"fault\":\"motor\"}"
curl.exe --% -X POST http://localhost:8004/fault -H "Content-Type: application/json" -d "{\"fault\":\"obstacle\"}"
```

> "Now the live proof. I inject a motor overload fault into the robot...
> Watch both visualizations. Within a few seconds — the dashboard status
> strip turns red, the anomaly score dives below zero, the AI recommendation
> changes to 'verify sensors and inspect robot' — and in Omniverse, the robot
> body turns red with a flashing warning light. Both react to the same state
> change, from the same data, at the same time."

**[TYPE the clear command:]**
```
curl.exe --% -X POST http://localhost:8004/fault -H "Content-Type: application/json" -d "{\"fault\":\"clear\"}"
```

> "I clear the fault... and everything returns to green automatically."

## Part 8 — Development Practices (1 min)
**[SCREEN: GitHub repo — Actions page with green runs, then commit history]**

> "We followed professional development practices. Two documented sprint
> cycles. Eighty-one unit tests plus integration, system and regression
> suites — including demonstrated fail cases. Every push triggers CI on
> GitHub Actions: linting, the full test suite, and Docker image builds.
> Here you can see the commit history with contributions from all team
> members, and our persistence test proves data survives container restarts."

## Part 9 — Closing (30 sec)
**[SCREEN: back to dashboard or team slide]**

> "To summarise: a complete digital twin — real-time monitoring, five AI
> models, operator recommendations, what-if simulation, 3D visualization,
> nine containerized microservices, tested and deployed with CI/CD.
> The limitations are documented: the robot is simulated and the security is
> not production-grade — both have clear upgrade paths.
> Thank you for watching."

---

## Pre-recording checklist
- [ ] START-SMARTCLEAN-TWIN.bat run, all 9 containers up
- [ ] Omniverse live update running (robot moving, tiles turning green)
- [ ] Grafana logged in, dashboard open, all panels showing data
- [ ] Jupyter open on project_walkthrough.ipynb (outputs visible)
- [ ] Terminal ready in the smartclean-twin folder
- [ ] GitHub Actions page open in a tab (green runs visible)
- [ ] Both fault commands copied somewhere ready to paste
- [ ] Do one practice run of Part 7 before recording (timing of the red state)

