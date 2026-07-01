"""Entry point: starts simulator in background thread + FastAPI health/fault API."""

from __future__ import annotations

import os
import signal
import sys
import threading

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

sys.path.insert(0, "/app/shared")

from simulator import RobotSimulator

app = FastAPI(title="SmartClean Robot Simulator", version="1.0")
_simulator: RobotSimulator | None = None


class FaultRequest(BaseModel):
    fault: str  # obstacle | motor | battery | clear


@app.get("/health")
def health() -> dict:
    if _simulator is None:
        raise HTTPException(status_code=503, detail="Simulator not ready")
    s = _simulator.state
    return {
        "status": "healthy",
        "robot_id": os.environ.get("ROBOT_ID", "SCR01"),
        "battery_soc": round(s.battery_soc, 1),
        "mode": s.mode,
        "paused": s.paused,
        "stopped": s.stopped,
    }


@app.post("/fault")
def inject_fault(req: FaultRequest) -> dict:
    """Demo / test endpoint to inject controlled fault conditions."""
    if _simulator is None:
        raise HTTPException(status_code=503, detail="Simulator not ready")
    _simulator.inject_fault(req.fault)
    return {"injected": req.fault}


def _run_simulator() -> None:
    global _simulator
    _simulator = RobotSimulator()
    _simulator.run()


if __name__ == "__main__":
    sim_thread = threading.Thread(target=_run_simulator, daemon=True)
    sim_thread.start()

    # Signal handlers must be registered in the main thread
    def _on_signal(signum, frame):
        if _simulator:
            _simulator.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)

    port = int(os.environ.get("SIMULATOR_PORT", "8004"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
