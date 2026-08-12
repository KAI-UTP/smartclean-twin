"""Create a SmartClean Twin dashboard inside InfluxDB via its v2 API.

Re-runnable: an existing dashboard with the same name is deleted first, so the
script never leaves duplicates behind.
"""

import json
import sys
import requests

URL = "http://localhost:8086"
TOKEN = "smartclean-super-secret-token"
ORG = "smartclean"
BUCKET = "smartclean_twin"
NAME = "SmartClean Twin: Presentation"

H = {"Authorization": f"Token {TOKEN}", "Content-Type": "application/json"}

# ---------------------------------------------------------------- org id
r = requests.get(f"{URL}/api/v2/orgs", headers=H, params={"org": ORG}, timeout=15)
r.raise_for_status()
ORG_ID = r.json()["orgs"][0]["id"]
print(f"org {ORG} -> {ORG_ID}")

# ---------------------------------------------------- remove old copies
r = requests.get(f"{URL}/api/v2/dashboards", headers=H,
                 params={"orgID": ORG_ID, "limit": 100}, timeout=15)
r.raise_for_status()
for d in r.json().get("dashboards", []):
    if d["name"] == NAME:
        requests.delete(f"{URL}/api/v2/dashboards/{d['id']}", headers=H, timeout=15)
        print(f"removed previous dashboard {d['id']}")

# ---------------------------------------------------------------- create
r = requests.post(f"{URL}/api/v2/dashboards", headers=H, timeout=15, json={
    "name": NAME,
    "description": "Live Digital Twin data. Every cell is a Flux query against smartclean_twin.",
    "orgID": ORG_ID,
})
r.raise_for_status()
DASH_ID = r.json()["id"]
print(f"created dashboard {DASH_ID}")

LINE_COLORS = [
    {"id": "0", "type": "scale", "hex": "#31C0F6", "name": "Nineteen Eighty Four", "value": 0},
    {"id": "1", "type": "scale", "hex": "#A500A5", "name": "Nineteen Eighty Four", "value": 0},
    {"id": "2", "type": "scale", "hex": "#FF7E27", "name": "Nineteen Eighty Four", "value": 0},
]


def xy_view(name, flux, note=""):
    return {
        "name": name,
        "properties": {
            "type": "xy", "shape": "chronograf-v2",
            "queries": [{"text": flux, "editMode": "advanced", "name": "",
                         "builderConfig": {"buckets": [], "tags": [], "functions": [],
                                           "aggregateWindow": {"period": "auto"}}}],
            "axes": {"x": {"bounds": ["", ""], "label": "", "prefix": "", "suffix": "",
                           "base": "10", "scale": "linear"},
                     "y": {"bounds": ["", ""], "label": "", "prefix": "", "suffix": "",
                           "base": "10", "scale": "linear"}},
            "colors": LINE_COLORS, "geom": "line", "position": "overlaid",
            "legend": {}, "note": note, "showNoteWhenEmpty": True,
            "xColumn": "_time", "yColumn": "_value",
            "hoverDimension": "auto", "generateXAxisTicks": [], "generateYAxisTicks": [],
        },
    }


def table_view(name, flux, note=""):
    return {
        "name": name,
        "properties": {
            "type": "table", "shape": "chronograf-v2",
            "queries": [{"text": flux, "editMode": "advanced", "name": "",
                         "builderConfig": {"buckets": [], "tags": [], "functions": [],
                                           "aggregateWindow": {"period": "auto"}}}],
            "colors": [{"id": "base", "type": "text", "hex": "#00C9FF",
                        "name": "laser", "value": 0}],
            "tableOptions": {"verticalTimeAxis": True, "fixFirstColumn": False,
                             "sortBy": {"internalName": "", "displayName": "",
                                        "visible": False}},
            "fieldOptions": [], "timeFormat": "YYYY-MM-DD HH:mm:ss",
            "decimalPlaces": {"isEnforced": False, "digits": 2},
            "note": note, "showNoteWhenEmpty": True,
        },
    }


def single_stat(name, flux, suffix="", note=""):
    return {
        "name": name,
        "properties": {
            "type": "single-stat", "shape": "chronograf-v2",
            "queries": [{"text": flux, "editMode": "advanced", "name": "",
                         "builderConfig": {"buckets": [], "tags": [], "functions": [],
                                           "aggregateWindow": {"period": "auto"}}}],
            "colors": [{"id": "base", "type": "text", "hex": "#00C9FF",
                        "name": "laser", "value": 0}],
            "prefix": "", "suffix": suffix, "tickPrefix": "", "tickSuffix": "",
            "decimalPlaces": {"isEnforced": True, "digits": 1},
            "note": note, "showNoteWhenEmpty": True,
        },
    }


B = BUCKET

CELLS = [
    # x, y, w, h, view
    (0, 0, 6, 4, xy_view(
        "1. Robot position, x and y in metres",
        f'from(bucket: "{B}")\n'
        f'  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)\n'
        f'  |> filter(fn: (r) => r._measurement == "robot_telemetry")\n'
        f'  |> filter(fn: (r) => r._field == "x_m" or r._field == "y_m")',
        "One row per second, exactly as the robot reported it.")),

    (6, 0, 6, 4, xy_view(
        "2. Battery state of charge",
        f'from(bucket: "{B}")\n'
        f'  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)\n'
        f'  |> filter(fn: (r) => r._measurement == "robot_telemetry")\n'
        f'  |> filter(fn: (r) => r._field == "battery_soc")',
        "The robot returns to the dock by itself below 20 percent.")),

    (0, 4, 4, 3, single_stat(
        "Telemetry points stored",
        f'from(bucket: "{B}")\n'
        f'  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)\n'
        f'  |> filter(fn: (r) => r._measurement == "robot_telemetry")\n'
        f'  |> filter(fn: (r) => r._field == "battery_soc")\n'
        f'  |> count()',
        note="One per second. 3600 in an hour means nothing was dropped.")),

    (4, 4, 4, 3, single_stat(
        "Cleaning coverage", suffix=" %", flux=(
            f'from(bucket: "{B}")\n'
            f'  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)\n'
            f'  |> filter(fn: (r) => r._measurement == "robot_state")\n'
            f'  |> filter(fn: (r) => r._field == "cleaning_coverage_pct")\n'
            f'  |> last()'))),

    (8, 4, 4, 3, single_stat(
        "Predicted remaining life", suffix=" min", flux=(
            f'from(bucket: "{B}")\n'
            f'  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)\n'
            f'  |> filter(fn: (r) => r._measurement == "robot_prediction")\n'
            f'  |> filter(fn: (r) => r._field == "predicted_rul_minutes")\n'
            f'  |> last()'))),

    (0, 7, 12, 5, table_view(
        "3. Measured, concluded, predicted: the three kinds of truth",
        f'from(bucket: "{B}")\n'
        f'  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)\n'
        f'  |> filter(fn: (r) =>\n'
        f'        r._measurement == "robot_telemetry" or\n'
        f'        r._measurement == "robot_state" or\n'
        f'        r._measurement == "robot_prediction")\n'
        f'  |> last()\n'
        f'  // safety_state is a string while battery_soc is a float, so they\n'
        f'  // cannot share one _value column until both are cast to string\n'
        f'  |> map(fn: (r) => ({{r with _value: string(v: r._value)}}))\n'
        f'  |> keep(columns: ["_measurement", "_field", "_value"])\n'
        f'  |> group()\n'
        f'  |> sort(columns: ["_measurement", "_field"])',
        "robot_telemetry is what the sensors measured. robot_state is what the "
        "twin concluded. robot_prediction is what the AI expects. Three separate "
        "measurements on purpose.")),

    (0, 12, 6, 4, xy_view(
        "4. Motor temperature, 30 second average",
        f'from(bucket: "{B}")\n'
        f'  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)\n'
        f'  |> filter(fn: (r) => r._measurement == "robot_telemetry")\n'
        f'  |> filter(fn: (r) => r._field == "motor_temperature_c")\n'
        f'  |> aggregateWindow(every: 30s, fn: mean, createEmpty: false)',
        "aggregateWindow downsamples in the database, not in the browser.")),

    (6, 12, 6, 4, xy_view(
        "5. AI anomaly score, below zero means anomalous",
        f'from(bucket: "{B}")\n'
        f'  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)\n'
        f'  |> filter(fn: (r) => r._measurement == "robot_prediction")\n'
        f'  |> filter(fn: (r) => r._field == "anomaly_score")',
        "Learned unsupervised from normal operation only, 4.5 sigma threshold.")),

    (0, 16, 12, 4, table_view(
        "6. Twin state, all 11 dimensions",
        f'from(bucket: "{B}")\n'
        f'  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)\n'
        f'  |> filter(fn: (r) => r._measurement == "robot_state")\n'
        f'  |> last()\n'
        f'  |> map(fn: (r) => ({{r with _value: string(v: r._value)}}))\n'
        f'  |> keep(columns: ["_field", "_value"])\n'
        f'  |> group()\n'
        f'  |> sort(columns: ["_field"])',
        "Raw sensors are numbers. Twin state is meaning.")),

    (0, 20, 6, 4, table_view(
        "7. Commands issued and acknowledged",
        f'from(bucket: "{B}")\n'
        f'  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)\n'
        f'  |> filter(fn: (r) => r._measurement == "robot_acknowledgement")\n'
        f'  |> keep(columns: ["_time", "command", "accepted"])\n'
        f'  |> group()\n'
        f'  |> sort(columns: ["_time"], desc: true)\n'
        f'  |> limit(n: 15)',
        "Proof of the virtual to physical direction: what the robot confirmed.")),

    (6, 20, 6, 4, table_view(
        "8. Rejected messages, the validation gate",
        f'from(bucket: "{B}")\n'
        f'  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)\n'
        f'  |> filter(fn: (r) => r._measurement == "robot_telemetry_invalid")\n'
        f'  |> map(fn: (r) => ({{r with _value: string(v: r._value)}}))\n'
        f'  |> keep(columns: ["_time", "reason", "_field", "_value"])\n'
        f'  |> group()\n'
        f'  |> sort(columns: ["_time"], desc: true)\n'
        f'  |> limit(n: 10)',
        "A message failing the schema is recorded with its reason, never stored "
        "as if it were real. Empty until an invalid message is sent.")),
]

for x, y, w, h, view in CELLS:
    r = requests.post(f"{URL}/api/v2/dashboards/{DASH_ID}/cells", headers=H, timeout=15,
                      json={"x": x, "y": y, "w": w, "h": h})
    r.raise_for_status()
    cell_id = r.json()["id"]
    r = requests.patch(f"{URL}/api/v2/dashboards/{DASH_ID}/cells/{cell_id}/view",
                       headers=H, timeout=15, json=view)
    if r.status_code >= 400:
        print(f"  FAILED {view['name']}: {r.status_code} {r.text[:300]}")
        sys.exit(1)
    print(f"  added: {view['name']}")

print(f"\nDashboard ready:\n  {URL}/orgs/{ORG_ID}/dashboards/{DASH_ID}")
