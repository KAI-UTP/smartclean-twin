"""
omniverse/fault_demo.py
Demonstration script: injects an obstacle fault and shows the EMERGENCY →
SAFE colour transition in the Omniverse 3D scene.

RUN LOCATION: paste and run inside Omniverse Kit "Script Editor" while
live_update.py is already running (so the 3D scene is active).

What this script does
----------------------
1. Calls POST http://localhost:8004/fault {"fault": "obstacle"}
   → Simulator sets obstacle_cm = 15 → State Engine sets safety_state = EMERGENCY
   → live_update.py turns CleaningRobot/Body RED and flashes StatusLight
2. Waits 8 seconds (enough time to screenshot the red robot)
3. Calls POST http://localhost:8004/fault {"fault": "clear"}
   → safety_state returns to SAFE → robot body turns GREEN

This reproduces the same state transition visible in the Grafana dashboard,
but in 3D — both update from the same InfluxDB source simultaneously.

Prerequisite: Docker stack running (docker compose up -d) and live_update.py
already started with start_live_update().
"""

import asyncio

try:
    import urllib.request
    import urllib.error
    import json as _json
except ImportError:
    pass  # always available in Kit

SIMULATOR_URL = "http://localhost:8004/fault"


def _post_fault(fault: str) -> bool:
    """Send a fault injection request to the Robot Simulator HTTP API."""
    payload = _json.dumps({"fault": fault}).encode()
    req = urllib.request.Request(
        SIMULATOR_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = resp.read().decode()
            print(f"[FAULT] POST /fault fault={fault!r} → HTTP {resp.status}: {body}")
            return resp.status == 200
    except urllib.error.URLError as exc:
        print(f"[ERROR] Could not reach simulator at {SIMULATOR_URL}: {exc}")
        print("        Is 'docker compose up -d' running?")
        return False


async def _demo_sequence():
    print("=" * 60)
    print("SmartClean Twin — Omniverse Fault Demo")
    print("=" * 60)
    print()

    # Step 1: inject obstacle fault
    print("[STEP 1] Injecting obstacle fault...")
    ok = _post_fault("obstacle")
    if not ok:
        print("[ABORT] Fault injection failed — demo cancelled.")
        return

    print("[INFO] Robot Simulator now reports obstacle_cm = 15 cm")
    print("[INFO] State Engine will set safety_state = EMERGENCY within ~2s")
    print("[INFO] Watch: CleaningRobot/Body → RED, StatusLight → flashing")
    print()
    print("[WAIT] Holding EMERGENCY state for 8 seconds — take your screenshot now...")
    await asyncio.sleep(8)

    # Step 2: clear the fault
    print()
    print("[STEP 2] Clearing obstacle fault...")
    _post_fault("clear")
    print("[INFO] safety_state will return to SAFE within ~2s")
    print("[INFO] Watch: CleaningRobot/Body → GREEN, StatusLight → solid green")
    print()
    await asyncio.sleep(3)

    print("=" * 60)
    print("[DONE] Fault demo complete.")
    print("       Both Grafana and Omniverse reflect the same state transition")
    print("       because both read from the same InfluxDB source.")
    print("=" * 60)


def run_fault_demo():
    """Run the EMERGENCY → SAFE demonstration sequence (non-blocking)."""
    loop = asyncio.get_event_loop()
    asyncio.ensure_future(_demo_sequence(), loop=loop)


if __name__ == "__main__":
    run_fault_demo()
