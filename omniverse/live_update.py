"""
omniverse/live_update.py
Streams live SmartClean Twin state from InfluxDB into the 3D scene every 1 second.

RUN LOCATION: paste and run inside Omniverse Kit "Script Editor" AFTER
create_scene.py has been run (so /World/CleaningRobot already exists).

One-time prerequisite (run once in Script Editor):
    import omni.kit.pipapi
    omni.kit.pipapi.install("influxdb-client", module="influxdb_client")

What updates every second
--------------------------
Property             USD prim                             Source measurement
-------------------  -----------------------------------  ------------------
Robot X, Y           /World/CleaningRobot  translate XY   robot_telemetry
Robot heading        /World/CleaningRobot  rotate Z        robot_telemetry
Body colour          /World/CleaningRobot/Body             robot_state.safety_state
Status light colour  /World/CleaningRobot/StatusLight      robot_state.safety_state
  (flashes on EMERGENCY)
Battery bar scale X  /World/CleaningRobot/BatteryBar       robot_telemetry.battery_soc
Battery bar colour   /World/CleaningRobot/BatteryBar       robot_telemetry.battery_soc
Tile colour          /World/CoverageGrid/Tile_X_Y          robot position (visited set)

Improvements over HW3 omniverse_live_update.py
-----------------------------------------------
- 7 live visual properties vs 4 (position + heading only in HW3)
- 1 s poll vs 2 s
- 2 InfluxDB measurements queried (robot_telemetry + robot_state) vs 1
- Coverage tiles light up green as robot visits each grid cell
- Safety state drives dual visual: body colour AND blinking status light
- Battery bar shrinks + changes colour (green → orange → red)
- Class-based design with visited-tile memory across ticks
"""

import asyncio
import math
import random

import omni.usd
from pxr import Gf, Usd, UsdGeom, Vt

try:
    from influxdb_client import InfluxDBClient
except ImportError:
    print("[ERROR] influxdb-client not installed in Kit Python. Run:")
    print("  import omni.kit.pipapi")
    print("  omni.kit.pipapi.install('influxdb-client', module='influxdb_client')")
    raise

# ---------------------------------------------------------------------------
# Configuration — matches SmartClean Twin docker-compose / .env
# ---------------------------------------------------------------------------
INFLUX_URL = "http://localhost:8086"
INFLUX_TOKEN = "smartclean-super-secret-token"
INFLUX_ORG = "smartclean"
INFLUX_BUCKET = "smartclean_twin"

ROBOT_PATH = "/World/CleaningRobot"
BODY_PATH = "/World/CleaningRobot/Body"
LIGHT_PATH = "/World/CleaningRobot/StatusLight"
BATTERY_PATH = "/World/CleaningRobot/BatteryBar"

UPDATE_INTERVAL_S = 1.0
TILE_COUNT = 10
CELL_SIZE_M = 0.5  # matches grid_map.CELL_SIZE_M

# Safety state colour map
_SAFETY_COLOR = {
    "SAFE": Gf.Vec3f(0.20, 0.78, 0.30),
    "WARNING": Gf.Vec3f(1.00, 0.55, 0.05),
    "EMERGENCY": Gf.Vec3f(0.90, 0.10, 0.10),
}
_EMERGENCY_DIM = Gf.Vec3f(0.35, 0.04, 0.04)  # dark-red for flash "off" frame

COL_TILE_CLEANED = Gf.Vec3f(0.40, 0.85, 0.72)
COL_TILE_UNCLEANED = Gf.Vec3f(0.82, 0.78, 0.72)
COL_BATTERY_OK = Gf.Vec3f(0.20, 0.78, 0.30)
COL_BATTERY_LOW = Gf.Vec3f(1.00, 0.55, 0.05)
COL_BATTERY_CRIT = Gf.Vec3f(0.90, 0.10, 0.10)

# ---------------------------------------------------------------------------
# InfluxDB client
# ---------------------------------------------------------------------------
OBSTACLE_INDICATOR_PATH = "/World/ObstacleIndicator"

_influx = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
_query_api = _influx.query_api()


def _reconnect_influx():
    global _influx, _query_api
    try:
        _influx.close()
    except Exception:
        pass
    _influx = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
    _query_api = _influx.query_api()
    print("[INFO] InfluxDB client reconnected")


def _query_latest(measurement, fields):
    """Return a dict of {field: value} for the most recent row of measurement."""
    flt = " or ".join(f'r._field == "{f}"' for f in fields)
    flux = (
        f'from(bucket: "{INFLUX_BUCKET}")'
        f" |> range(start: -15s)"
        f' |> filter(fn: (r) => r._measurement == "{measurement}")'
        f" |> filter(fn: (r) => {flt})"
        f" |> last()"
        f" |> group()"  # merge per-field tables so pivot yields ONE row with all fields
        f' |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")'
    )
    tables = _query_api.query(flux)
    # Merge all returned rows — guarantees every requested field is collected
    merged: dict = {}
    for table in tables:
        for record in table.records:
            merged.update({k: v for k, v in record.values.items() if v is not None})
    return merged


# ---------------------------------------------------------------------------
# USD helpers
# ---------------------------------------------------------------------------
def _set_color(stage, path, color):
    prim = stage.GetPrimAtPath(path)
    if not prim.IsValid():
        return
    attr = UsdGeom.Gprim(prim).GetDisplayColorAttr()
    if attr:
        attr.Set(Vt.Vec3fArray([color]))


def _set_scale_x(stage, path, sx):
    prim = stage.GetPrimAtPath(path)
    if not prim.IsValid():
        return
    _, _, scale, _, _ = UsdGeom.XformCommonAPI(prim).GetXformVectors(Usd.TimeCode.Default())
    UsdGeom.XformCommonAPI(prim).SetScale(Gf.Vec3f(max(0.01, sx), scale[1], scale[2]))


# ---------------------------------------------------------------------------
# Updater — keeps state across ticks
# ---------------------------------------------------------------------------
TRAIL_LENGTH = 60  # breadcrumb dots behind the robot (oldest is reused)
TRAIL_COLOR = Gf.Vec3f(0.15, 0.45, 0.95)  # blue


class SmartCleanTwinUpdater:
    def __init__(self):
        self._visited = set()  # grid cells (tx, ty) the robot has cleaned
        self._flash = False  # toggles each tick during EMERGENCY
        self._trail_idx = 0  # next breadcrumb slot (cycles 0..TRAIL_LENGTH-1)
        self._last_trail_pos = None

    # ------------------------------------------------------------------
    def _apply_trail(self, stage, x, y):
        """Drop a breadcrumb dot at the robot position — shows the path taken."""
        pos = (round(float(x), 2), round(float(y), 2))
        if pos == self._last_trail_pos:
            return  # robot stationary — don't stack dots
        self._last_trail_pos = pos
        dot = UsdGeom.Sphere.Define(stage, f"/World/Trail/Dot_{self._trail_idx}")
        dot.CreateRadiusAttr(0.03)
        UsdGeom.XformCommonAPI(dot).SetTranslate(Gf.Vec3d(float(x), float(y), 0.03))
        dot.CreateDisplayColorAttr(Vt.Vec3fArray([TRAIL_COLOR]))
        self._trail_idx = (self._trail_idx + 1) % TRAIL_LENGTH

    # ------------------------------------------------------------------
    def _apply_pose(self, stage, tel):
        x = tel.get("x_m")
        y = tel.get("y_m")
        if x is None or y is None:
            return

        prim = stage.GetPrimAtPath(ROBOT_PATH)
        if not prim.IsValid():
            print(f"[ERROR] {ROBOT_PATH} missing — run create_scene.py first")
            return

        UsdGeom.XformCommonAPI(prim).SetTranslate(Gf.Vec3d(float(x), float(y), 0.0))
        UsdGeom.XformCommonAPI(prim).SetRotate(
            Gf.Vec3f(0.0, 0.0, float(tel.get("heading_deg", 0.0))),
            UsdGeom.XformCommonAPI.RotationOrderXYZ,
        )

        self._apply_trail(stage, x, y)

        # Light up the tile the robot is currently on (x_m / 0.5 = col index)
        tx = int(float(x) / CELL_SIZE_M)
        ty = int(float(y) / CELL_SIZE_M)
        if 0 <= tx < TILE_COUNT and 0 <= ty < TILE_COUNT:
            if (tx, ty) not in self._visited:
                self._visited.add((tx, ty))
                _set_color(stage, f"/World/CoverageGrid/Tile_{tx}_{ty}", COL_TILE_CLEANED)

        # Detect new cleaning loop: robot returns to home cell after cleaning many tiles
        if tx == 1 and ty == 1 and len(self._visited) > 20:
            self._visited.clear()
            rng = random.Random(42)
            for c in range(TILE_COUNT):
                for r in range(TILE_COUNT):
                    dirt = rng.uniform(0.0, 1.0)
                    # Vary tile colour from clean beige (0.82,0.78,0.72) to dirty brown (0.45,0.35,0.25)
                    col = Gf.Vec3f(0.82 - dirt * 0.37, 0.78 - dirt * 0.43, 0.72 - dirt * 0.47)
                    _set_color(stage, f"/World/CoverageGrid/Tile_{c}_{r}", col)
            print("[INFO] New cleaning loop — floor re-dirtied with randomised dirt map")

    # ------------------------------------------------------------------
    def _apply_obstacle_indicator(self, stage, tel, state):
        """Move the red obstacle cube in front of the robot during EMERGENCY."""
        prim = stage.GetPrimAtPath(OBSTACLE_INDICATOR_PATH)
        if not prim.IsValid():
            return
        safety = str(state.get("safety_state", "SAFE")).upper()
        if safety == "EMERGENCY":
            x = float(tel.get("x_m", 0.0))
            y = float(tel.get("y_m", 0.0))
            heading = float(tel.get("heading_deg", 0.0))
            rad = math.radians(heading)
            ox = x + 0.35 * math.cos(rad)
            oy = y + 0.35 * math.sin(rad)
            UsdGeom.XformCommonAPI(prim).SetTranslate(Gf.Vec3d(ox, oy, 0.20))
        else:
            # Park underground — invisible
            UsdGeom.XformCommonAPI(prim).SetTranslate(Gf.Vec3d(0.0, 0.0, -5.0))

    # ------------------------------------------------------------------
    def _apply_safety(self, stage, state):
        safety = str(state.get("safety_state", "SAFE")).upper()
        body_color = _SAFETY_COLOR.get(safety, _SAFETY_COLOR["SAFE"])

        if safety == "EMERGENCY":
            self._flash = not self._flash
            light_color = _EMERGENCY_DIM if self._flash else body_color
        else:
            self._flash = False
            light_color = body_color

        _set_color(stage, BODY_PATH, body_color)
        _set_color(stage, LIGHT_PATH, light_color)

    # ------------------------------------------------------------------
    def _apply_battery(self, stage, tel):
        soc = tel.get("battery_soc")
        if soc is None:
            return
        soc = float(soc)
        # Battery bar max width = 0.40m (set in create_scene.py)
        _set_scale_x(stage, BATTERY_PATH, (soc / 100.0) * 0.40)

        col = COL_BATTERY_OK if soc > 40 else (COL_BATTERY_LOW if soc > 20 else COL_BATTERY_CRIT)
        _set_color(stage, BATTERY_PATH, col)

    # ------------------------------------------------------------------
    def tick(self):
        stage = omni.usd.get_context().get_stage()
        if stage is None:
            print("[ERROR] No active USD stage.")
            return

        tel = _query_latest("robot_telemetry", ["x_m", "y_m", "heading_deg", "battery_soc"])
        state = _query_latest(
            "robot_state", ["safety_state", "mission_state", "cleaning_coverage_pct"]
        )

        if not tel and not state:
            print("[WARN] No data — is 'docker compose up -d' running?")
            return

        self._apply_pose(stage, tel)
        self._apply_safety(stage, state)
        self._apply_battery(stage, tel)
        self._apply_obstacle_indicator(stage, tel, state)

        x = tel.get("x_m", "?")
        y = tel.get("y_m", "?")
        heading = tel.get("heading_deg", "?")
        safety = state.get("safety_state", "?")
        coverage = state.get("cleaning_coverage_pct", "?")
        battery = tel.get("battery_soc", "?")
        tiles = len(self._visited)
        fmt_x = f"{x:.2f}" if isinstance(x, (int, float)) else x
        fmt_y = f"{y:.2f}" if isinstance(y, (int, float)) else y
        fmt_h = f"{heading:.0f}" if isinstance(heading, (int, float)) else heading
        fmt_cov = f"{coverage:.1f}" if isinstance(coverage, (int, float)) else coverage
        fmt_bat = f"{battery:.1f}" if isinstance(battery, (int, float)) else battery
        print(
            f"[TICK] pos=({fmt_x},{fmt_y}) heading={fmt_h}° "
            f"safety={safety} coverage={fmt_cov}% battery={fmt_bat}% "
            f"tiles_visited={tiles}/100"
        )


# ---------------------------------------------------------------------------
# Async run loop
# ---------------------------------------------------------------------------
_updater = None
_task = None
_running = False


async def _loop():
    global _running
    _running = True
    print(f"[INFO] SmartClean Twin live update started — polling every {UPDATE_INTERVAL_S}s")
    print("[INFO] Call stop_live_update() to stop.")
    while _running:
        try:
            _updater.tick()
        except Exception as exc:
            print(f"[ERROR] Tick: {exc} — attempting InfluxDB reconnect")
            try:
                _reconnect_influx()
            except Exception as reconn_exc:
                print(f"[ERROR] Reconnect failed: {reconn_exc}")
        await asyncio.sleep(UPDATE_INTERVAL_S)
    print("[INFO] Live update stopped.")


def start_live_update():
    """Start the non-blocking 1-second update loop. Call once per session."""
    global _updater, _task
    if _task is not None and not _task.done():
        print("[INFO] Already running. Call stop_live_update() first to restart.")
        return
    _updater = SmartCleanTwinUpdater()
    loop = asyncio.get_event_loop()
    _task = asyncio.ensure_future(_loop(), loop=loop)


def stop_live_update():
    """Safely stop the update loop after the current tick completes."""
    global _running
    _running = False


if __name__ == "__main__":
    start_live_update()
