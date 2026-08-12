# InfluxDB Queries for the Presentation

Copy and paste these into the InfluxDB web UI.

## How to open the query editor

1. Go to **http://localhost:8086**
2. Sign in: `admin` / `adminpassword`
3. Left sidebar, click the **arrow icon** (Data Explorer)
4. Click **SCRIPT EDITOR** on the right, above the query area
5. Paste a query below
6. Set the time range at the top right to **Past 15 minutes**
7. Press **SUBMIT**

The Data Explorer looks empty until a query is submitted. That is normal, it is
not a sign that the data is missing.

---

## Query 1. Robot position over time

**The best one to open with.** Two lines that trace the robot moving around the
room.

```
from(bucket: "smartclean_twin")
  |> range(start: -15m)
  |> filter(fn: (r) => r._measurement == "robot_telemetry")
  |> filter(fn: (r) => r._field == "x_m" or r._field == "y_m")
```

**Say:** "One row per second. This is the raw position the robot reported, stored
exactly as it arrived, with nothing interpreted."

---

## Query 2. Battery draining, and recharging

Shows the sawtooth: a slow decline, then a sharp climb when the robot docks.

```
from(bucket: "smartclean_twin")
  |> range(start: -30m)
  |> filter(fn: (r) => r._measurement == "robot_telemetry")
  |> filter(fn: (r) => r._field == "battery_soc")
```

**Say:** "The robot decided by itself to return to the dock at 20 percent, and
resumed only above 80 percent. Nobody commanded that."

---

## Query 3. Everything the robot measured, as one table

Switch the view from **Graph** to **Table** at the top left for this one.

```
from(bucket: "smartclean_twin")
  |> range(start: -5m)
  |> filter(fn: (r) => r._measurement == "robot_telemetry")
  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
```

**Say:** "16 fields, once per second, all in one row. `pivot` turns the long
format InfluxDB stores natively into the wide table people expect."

---

## Query 4. The twin's own state, all 11 dimensions

View as **Table**.

```
from(bucket: "smartclean_twin")
  |> range(start: -5m)
  |> filter(fn: (r) => r._measurement == "robot_state")
  |> last()
```

**Say:** "This is not sensor data. This is what the twin concluded from the
sensor data: safety state, battery state, motor health, mission state, and its
own quality assessment."

---

## Query 5. Measurement versus conclusion versus prediction

**The most important query for explaining the architecture.** It puts all three
measurements side by side.

```
from(bucket: "smartclean_twin")
  |> range(start: -5m)
  |> filter(fn: (r) =>
        r._measurement == "robot_telemetry" or
        r._measurement == "robot_state" or
        r._measurement == "robot_prediction")
  |> last()
  |> keep(columns: ["_measurement", "_field", "_value"])
```

**Say:** "Three separate measurements on purpose. `robot_telemetry` is what the
sensors measured. `robot_state` is what the twin concluded. `robot_prediction` is
what the AI expects. Mixing a measurement with a prediction in one table means
never being able to tell them apart again."

---

## Query 6. The AI predictions

```
from(bucket: "smartclean_twin")
  |> range(start: -15m)
  |> filter(fn: (r) => r._measurement == "robot_prediction")
  |> filter(fn: (r) => r._field == "predicted_rul_minutes" or
                       r._field == "anomaly_score")
```

**Say:** "Remaining useful life in minutes, and the anomaly score. The anomaly
score crossing below zero means a sensor went more than 4.5 standard deviations
from normal."

---

## Query 7. Commands and acknowledgements

Proves the V2P direction. Press a button on the console first, then run this.

```
from(bucket: "smartclean_twin")
  |> range(start: -30m)
  |> filter(fn: (r) => r._measurement == "robot_command" or
                       r._measurement == "robot_acknowledgement")
  |> keep(columns: ["_time", "_measurement", "command", "accepted", "_field", "_value"])
```

**Say:** "Every command issued, and every acknowledgement the robot sent back.
The system records not just what was asked, but what was actually confirmed."

---

## Query 8. Alarms

```
from(bucket: "smartclean_twin")
  |> range(start: -1h)
  |> filter(fn: (r) => r._measurement == "robot_alarm")
  |> keep(columns: ["_time", "alarm_type", "severity", "_field", "_value"])
```

Inject a fault from the console first, or this may be empty.

---

## Query 9. Rejected messages, proving the validation gate

```
from(bucket: "smartclean_twin")
  |> range(start: -1h)
  |> filter(fn: (r) => r._measurement == "robot_telemetry_invalid")
```

**Say:** "A message that fails the schema is not thrown away. It is recorded here
with the reason and a preview of the payload, so the rejection rate is itself
measurable."

Empty unless an invalid message has been sent. Section 4 of the presentation
notebook sends one deliberately.

---

## Query 10. Data volume, to show the system has been running

```
from(bucket: "smartclean_twin")
  |> range(start: -1h)
  |> filter(fn: (r) => r._measurement == "robot_telemetry")
  |> filter(fn: (r) => r._field == "battery_soc")
  |> count()
```

3600 points in an hour means one per second with nothing dropped.

---

## Query 11. Motor temperature with a moving average

Shows that InfluxDB does computation, not just storage.

```
from(bucket: "smartclean_twin")
  |> range(start: -30m)
  |> filter(fn: (r) => r._measurement == "robot_telemetry")
  |> filter(fn: (r) => r._field == "motor_temperature_c")
  |> aggregateWindow(every: 30s, fn: mean, createEmpty: false)
```

**Say:** "`aggregateWindow` averages into 30 second buckets. The database does the
downsampling, so a dashboard showing 24 hours does not have to transfer 86,400
points."

---

## Query 12. Cleaning coverage climbing

```
from(bucket: "smartclean_twin")
  |> range(start: -30m)
  |> filter(fn: (r) => r._measurement == "robot_state")
  |> filter(fn: (r) => r._field == "cleaning_coverage_pct")
```

A rising line that resets when the robot finishes the room and starts again.

---

## If a query returns nothing

| Cause | Fix |
|---|---|
| Time range too short | Set it to Past 1 hour at the top right |
| Containers not running | `docker compose ps`, then `docker compose up -d` |
| Still in Query Builder mode | Click **SCRIPT EDITOR** |
| Wrong bucket name | It is `smartclean_twin`, with an underscore |

---

## The three to use if time is short

1. **Query 1**, position, because it is visual and immediately obvious.
2. **Query 5**, measurement versus conclusion versus prediction, because it
   explains the architecture better than any diagram.
3. **Query 9**, rejected messages, because it proves the validation gate is real.
