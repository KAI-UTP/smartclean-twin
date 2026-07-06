"""
omniverse/create_scene.py
Creates the SmartClean Twin 3D office scene in NVIDIA Omniverse / Kit.

RUN LOCATION: paste and run inside the Omniverse Kit "Script Editor"
(Window > Script Editor). Uses omni.usd and pxr — only available inside
a Kit/Isaac Sim Python environment.

Run this ONCE to build the scene. Afterwards open the saved .usd file
directly (File > Open) — no need to re-run this script.

Scene hierarchy
---------------
/World
├── Room
│   ├── Floor                 (Cube 10m × 10m)
│   ├── WallNorth/South/East/West  (Cubes 3m high)
│   ├── Desk01 / Desk02 / Desk03   (Cube obstacles)
│   └── CeilingLight          (Sphere — visual only)
├── CoverageGrid
│   └── Tile_X_Y  (100 flat cubes, X/Y in 0–9; live_update.py changes colour)
└── CleaningRobot             (Xform — live_update.py moves this)
    ├── BrushDeck             (Cylinder, wide flat disc, dark)
    ├── Body                  (Cylinder, main disc — colour = safety state)
    ├── StatusLight           (Sphere on top — flashes red on EMERGENCY)
    └── BatteryBar            (Thin Cube — scale X = battery SoC %)

Improvements over HW3 omniverse_create_scene.py
------------------------------------------------
- Full office room (walls + floor + desk obstacles) vs empty stage
- Disc-shaped cleaning robot vs boxy mobile platform
- 100-tile coverage grid for visualising cleaning progress
- BatteryBar and StatusLight prims driven by live sensor data
"""

import omni.usd
from pxr import Gf, Sdf, UsdGeom, Vt

# ---------------------------------------------------------------------------
# Scene constants
# ---------------------------------------------------------------------------
ROOM_SIZE_M = 10.0
WALL_HEIGHT_M = 3.0
WALL_THICKNESS = 0.2
TILE_COUNT = 10

ROBOT_BODY_RADIUS = 0.25
ROBOT_BODY_HEIGHT = 0.08
ROBOT_BRUSH_RADIUS = 0.28
ROBOT_BRUSH_HEIGHT = 0.02

# Colours (RGB, 0–1)
COL_FLOOR = (0.82, 0.78, 0.72)
COL_WALL = (0.90, 0.90, 0.90)
COL_DESK = (0.55, 0.40, 0.25)
COL_CEILING_LIGHT = (1.00, 1.00, 0.90)
COL_TILE_UNCLEANED = (0.82, 0.78, 0.72)
COL_ROBOT_SAFE = (0.20, 0.78, 0.30)
COL_ROBOT_BRUSH = (0.12, 0.12, 0.12)
COL_STATUS_LIGHT_SAFE = (0.20, 0.78, 0.30)
COL_BATTERY = (0.20, 0.78, 0.30)

SAVE_PATH = "C:/Omniverse/smartclean_twin_scene.usd"


# ---------------------------------------------------------------------------
# USD helpers
# ---------------------------------------------------------------------------
def _xform(stage, path):
    return UsdGeom.Xform.Define(stage, Sdf.Path(path))


def _cube(stage, path, translate, scale, color):
    prim = UsdGeom.Cube.Define(stage, Sdf.Path(path))
    prim.CreateSizeAttr(1.0)
    UsdGeom.XformCommonAPI(prim).SetTranslate(Gf.Vec3d(*translate))
    UsdGeom.XformCommonAPI(prim).SetScale(Gf.Vec3f(*scale))
    prim.CreateDisplayColorAttr(Vt.Vec3fArray([Gf.Vec3f(*color)]))
    return prim


def _cylinder(stage, path, translate, radius, height, color, axis="Z"):
    prim = UsdGeom.Cylinder.Define(stage, Sdf.Path(path))
    prim.CreateRadiusAttr(radius)
    prim.CreateHeightAttr(height)
    prim.CreateAxisAttr(axis)
    UsdGeom.XformCommonAPI(prim).SetTranslate(Gf.Vec3d(*translate))
    prim.CreateDisplayColorAttr(Vt.Vec3fArray([Gf.Vec3f(*color)]))
    return prim


def _sphere(stage, path, translate, radius, color):
    prim = UsdGeom.Sphere.Define(stage, Sdf.Path(path))
    prim.CreateRadiusAttr(radius)
    UsdGeom.XformCommonAPI(prim).SetTranslate(Gf.Vec3d(*translate))
    prim.CreateDisplayColorAttr(Vt.Vec3fArray([Gf.Vec3f(*color)]))
    return prim


# ---------------------------------------------------------------------------
# Scene sections
# ---------------------------------------------------------------------------
def _create_room(stage):
    half = ROOM_SIZE_M / 2

    _xform(stage, "/World/Room")

    _cube(stage, "/World/Room/Floor",
          translate=(half, half, -0.05),
          scale=(ROOM_SIZE_M, ROOM_SIZE_M, 0.10),
          color=COL_FLOOR)

    _cube(stage, "/World/Room/WallNorth",
          translate=(half, ROOM_SIZE_M, WALL_HEIGHT_M / 2),
          scale=(ROOM_SIZE_M, WALL_THICKNESS, WALL_HEIGHT_M),
          color=COL_WALL)
    _cube(stage, "/World/Room/WallSouth",
          translate=(half, 0.0, WALL_HEIGHT_M / 2),
          scale=(ROOM_SIZE_M, WALL_THICKNESS, WALL_HEIGHT_M),
          color=COL_WALL)
    _cube(stage, "/World/Room/WallEast",
          translate=(ROOM_SIZE_M, half, WALL_HEIGHT_M / 2),
          scale=(WALL_THICKNESS, ROOM_SIZE_M, WALL_HEIGHT_M),
          color=COL_WALL)
    _cube(stage, "/World/Room/WallWest",
          translate=(0.0, half, WALL_HEIGHT_M / 2),
          scale=(WALL_THICKNESS, ROOM_SIZE_M, WALL_HEIGHT_M),
          color=COL_WALL)

    # Desk obstacles — positions match hard-blocked cells in simulator grid_map.py
    _cube(stage, "/World/Room/Desk01",
          translate=(2.0, 2.0, 0.50),
          scale=(1.4, 0.7, 1.0), color=COL_DESK)
    _cube(stage, "/World/Room/Desk02",
          translate=(7.5, 8.0, 0.50),
          scale=(1.4, 0.7, 1.0), color=COL_DESK)
    _cube(stage, "/World/Room/Desk03",
          translate=(5.0, 5.0, 0.40),
          scale=(0.8, 0.8, 0.8), color=COL_DESK)

    _sphere(stage, "/World/Room/CeilingLight",
            translate=(half, half, WALL_HEIGHT_M - 0.15),
            radius=0.25, color=COL_CEILING_LIGHT)

    print("[OK] Room: floor + 4 walls + 3 desk obstacles + ceiling light")


def _create_coverage_grid(stage):
    _xform(stage, "/World/CoverageGrid")
    for x in range(TILE_COUNT):
        for y in range(TILE_COUNT):
            _cube(stage,
                  f"/World/CoverageGrid/Tile_{x}_{y}",
                  translate=(x + 0.5, y + 0.5, 0.001),
                  scale=(0.92, 0.92, 0.002),
                  color=COL_TILE_UNCLEANED)
    print(f"[OK] Coverage grid: {TILE_COUNT * TILE_COUNT} tiles (Tile_0_0 … Tile_9_9)")


def _create_cleaning_robot(stage):
    robot = _xform(stage, "/World/CleaningRobot")
    # Start at grid cell (0, 0) centre
    UsdGeom.XformCommonAPI(robot).SetTranslate(Gf.Vec3d(0.5, 0.5, 0.0))
    UsdGeom.XformCommonAPI(robot).SetRotate(Gf.Vec3f(0.0, 0.0, 0.0))

    z_brush = ROBOT_BRUSH_HEIGHT / 2
    z_body = ROBOT_BRUSH_HEIGHT + ROBOT_BODY_HEIGHT / 2
    z_top = ROBOT_BRUSH_HEIGHT + ROBOT_BODY_HEIGHT

    # Brush deck — slightly wider, very dark disc at the bottom
    _cylinder(stage, "/World/CleaningRobot/BrushDeck",
              translate=(0.0, 0.0, z_brush),
              radius=ROBOT_BRUSH_RADIUS,
              height=ROBOT_BRUSH_HEIGHT,
              color=COL_ROBOT_BRUSH)

    # Main body — colour changes with safety state (green / orange / red)
    _cylinder(stage, "/World/CleaningRobot/Body",
              translate=(0.0, 0.0, z_body),
              radius=ROBOT_BODY_RADIUS,
              height=ROBOT_BODY_HEIGHT,
              color=COL_ROBOT_SAFE)

    # Status light — small sphere on top, flashes on EMERGENCY
    _sphere(stage, "/World/CleaningRobot/StatusLight",
            translate=(0.0, 0.0, z_top + 0.07),
            radius=0.06,
            color=COL_STATUS_LIGHT_SAFE)

    # Battery bar — thin flat cube; live_update.py scales X by battery SoC
    _cube(stage, "/World/CleaningRobot/BatteryBar",
          translate=(0.0, 0.0, z_top + 0.03),
          scale=(0.40, 0.06, 0.03),
          color=COL_BATTERY)

    print("[OK] CleaningRobot: BrushDeck + Body + StatusLight + BatteryBar")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def create_scene():
    context = omni.usd.get_context()
    stage = context.get_stage()
    if stage is None:
        print("[ERROR] No active stage — File > New first, then re-run.")
        return None

    if not stage.GetPrimAtPath("/World"):
        UsdGeom.Xform.Define(stage, Sdf.Path("/World"))

    _create_room(stage)
    _create_coverage_grid(stage)
    _create_cleaning_robot(stage)

    try:
        context.save_as_stage(SAVE_PATH)
        print(f"\n[OK] Stage saved → {SAVE_PATH}")
        print("     Re-open this file next time (File > Open) — no need to re-run.")
    except Exception as exc:
        print(f"\n[WARN] Could not auto-save to {SAVE_PATH}: {exc}")
        print("       Save manually: File > Save As")

    print("\nNext: run omniverse/live_update.py in Script Editor to start the live feed.")
    return stage


if __name__ == "__main__":
    create_scene()
