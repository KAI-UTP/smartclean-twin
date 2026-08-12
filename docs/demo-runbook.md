# Demonstration Runbook

Every scenario below was rehearsed end to end and passed: 36 of 36 checks.
Values in brackets are what was actually observed during the rehearsal.

---

## Before the audience arrives, about 10 minutes

1. Double-click **START-SMARTCLEAN-TWIN.bat**. It starts Docker if needed, the
   nine containers, the control panel, Grafana, the walkthrough PDF and
   Omniverse.
2. In Omniverse, once the window opens: **Window > Script Editor**, paste all of
   `smartclean-twin\omniverse\live_update.py`, click Run, then run
   `start_live_update()`. Paste it only once per session.
3. Check the robot is moving in 3D and the tiles are turning green.
4. Optional, only if you want the phone: run **PHONE-ACCESS.bat**, note the
   https address, and open it on the phone once so it is ready.

If Docker refuses to start with an "Inference manager" or "Secrets Engine"
error, run **FIX-DOCKER.bat**, then start again.

---

## Scenario 1: the system is running

**Show:** a terminal.

```
docker compose ps
```

Nine containers, all Up. Then:

```
py scripts\smoke_test.py
```

**Say:** "Nine containers: six microservices I wrote, plus the MQTT broker, the
time-series database and Grafana. One command starts all of them."

---

## Scenario 2: the operator console

**Show:** http://localhost:8005

**Say:** "This is the operator console. Everything on it comes from the same
InfluxDB the dashboard reads, so the two can never disagree. The browser talks
only to this one service, which proxies to the others."

Point at the status strip: safety state, mission state, AI health, anomaly
flag, and the AI recommendation in plain words.

---

## Scenario 3: commands, and why this is a twin

**Show:** the Control card. Press **Pause**, then **Resume**.

**Say:** "The command goes REST to MQTT to the robot, the robot obeys and sends
an acknowledgement back, and that acknowledgement is what you see here. A
dashboard only displays. A twin also commands, and confirms."

The command history table fills in as you go.

---

## Scenario 4: manual driving

**Show:** the Manual control card.

1. Press **Take manual control**. Badge turns orange, the pad arms.
2. Drive with the pad or the arrow keys. Each press is one grid cell, 0.5 m.
3. Drive into a wall on purpose. The button flashes red.
4. Press **Return to autonomous**.

**Say while driving into the wall:** "The robot refused that, not the web page.
Validation lives with the asset, which is where it belongs."

**Say on handover:** "It carries on cleaning from where I left it. It does not
jump back to where it was before I took over. That was a bug we found and
fixed."

*Rehearsed: moved (1.5, 2.0) to (1.5, 2.5), wall move refused, handover moved
only 1.0 m, no jump.*

---

## Scenario 5: quick actions

**Show:** the Quick actions card. Press **Start wet clean**.

**Say:** "One press, three commands, and every acknowledgement is reported. If
one of the three failed I would see it rather than a single misleading OK."

*Rehearsed: 3 of 3 accepted.*

---

## Scenario 6: what-if simulation, the strongest single moment

**Show:** the What-if card. Set temperature about 95 and current about 3.8,
press **Run scenario**.

**Say:** "This is the defining capability of a Digital Twin: I can ask the
virtual copy a question without touching the real asset. What would happen if
the motor reached 95 degrees at 3.8 amps? It answers with the condition, the
remaining useful life, whether it is anomalous, and what the operator should
do. The robot was never affected."

Then run a healthy scenario to contrast.

*Rehearsed: healthy gave NORMAL with 108.8 minutes of life. Hot gave WARNING,
anomaly true, and the recommendation changed to inspect the robot.*

---

## Scenario 7: fault injection, the visual highlight

**Have Grafana and Omniverse both visible.** Press **Obstacle** on the console.

Within a few seconds: the console status strip turns red, the Grafana overview
strip turns red, and the robot turns red in 3D with a flashing light and a red
obstacle marker in front of it.

**Say:** "One injected fault, and three views react to the same state change,
because all three read the same store."

Press **Clear all** and everything returns to green.

*Rehearsed: SAFE to EMERGENCY to SAFE.*

---

## Scenario 8: autonomous recovery, empty tank

Press **Empty tank**, then **Clear all** a few seconds later so the fault does
not keep draining.

Watch the mode: CLEANING, then RETURNING, then REFILLING, then back to
CLEANING once the tank passes 90 percent.

**Say:** "The robot decided by itself to abandon cleaning, drive to the dock and
refill. Cleaning only resumes when both the battery and the tank are ready, so
it cannot set off with a full battery and an empty tank."

*Rehearsed: CLEANING to REFILLING observed.*

---

## Scenario 9: deployment and scaling

```
docker compose up --scale telemetry-ingestion=2 -d
docker compose ps
```

Two ingestion replicas appear.

**Say:** "Ingestion is stateless, and MQTT delivers each message to every
subscriber, so it scales horizontally. The state engine and the AI service hold
in-memory state, so they deliberately do not."

Scale back with `--scale telemetry-ingestion=1 -d`.

*Rehearsed: 2 replicas confirmed.*

---

## Scenario 10: tests and CI

```
py -m pytest tests/unit -q
```

Then show the GitHub Actions page, green.

**Say:** "204 tests across four levels. The interesting ones are the failure
cases: stopping the broker makes the system tests fail, and restarting it makes
them pass again with no code change."

*Rehearsed: unit 169, integration 11, system 14, regression 10, all passing.*

---

## Scenario 11: the phone, optional

Open the tunnel address on the phone, sign in, and drive the robot from it
while the laptop screen shows Grafana reacting.

---

## If something goes wrong

| Problem | Fix |
|---|---|
| Docker will not start | Run FIX-DOCKER.bat |
| A container is unhealthy | `docker compose restart <service>` |
| Console shows "disconnected" | Wait 5 seconds; it polls once per second |
| Robot not moving in 3D | In Omniverse: `stop_live_update()` then `start_live_update()` |
| Robot not moving at all | Press Start on the console, and check it is not in manual mode |
| Everything looks wrong | `docker compose restart` and give it 30 seconds |

**Reset to a clean demo state at any time:** press **Clear all**, then
**Return to autonomous**, then **Start wet clean**.

---

## Numbers worth remembering

| | |
|---|---|
| Containers | 9, six of them services I wrote |
| Telemetry | 16 fields, once per second |
| Twin state | 11 dimensions |
| AI models | 5, across 3 learning paradigms |
| Health classifier | 90.8 percent accuracy |
| RUL regressor | R squared 0.91, average error 6.6 minutes |
| Anomaly detector | 100 percent of known faults, no false alarms |
| Dashboard | 28 panels in 7 sections |
| Tests | 204, coverage 82 percent |
| Contract | 18 documented service pairs |
