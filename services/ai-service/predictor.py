"""Model loader and prediction logic with rule-based fallback.

Models
------
Existing:
  motor_health_clf  — NORMAL / HIGH_LOAD / OVERHEATED / FAULT
  dirt_level_clf    — CLEAN / MODERATE / DIRTY

HW4 (new):
  health_state_clf  — NORMAL / WARNING / CRITICAL  (classification)
  rul_regressor     — predicted_rul_minutes         (regression)
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

MODEL_DIR = Path(os.environ.get("MODEL_DIR", "/app/models"))

_motor_clf = None
_dirt_clf = None
_health_state_clf = None
_rul_regressor = None
_loaded = False


def load_models() -> bool:
    global _motor_clf, _dirt_clf, _health_state_clf, _rul_regressor, _loaded
    try:
        import joblib

        motor_path = MODEL_DIR / "motor_health_clf.joblib"
        dirt_path = MODEL_DIR / "dirt_level_clf.joblib"
        health_path = MODEL_DIR / "health_state_clf.joblib"
        rul_path = MODEL_DIR / "rul_regressor.joblib"

        if all(p.exists() for p in [motor_path, dirt_path, health_path, rul_path]):
            _motor_clf = joblib.load(motor_path)
            _dirt_clf = joblib.load(dirt_path)
            _health_state_clf = joblib.load(health_path)
            _rul_regressor = joblib.load(rul_path)
            _loaded = True
            logger.info("All 4 AI models loaded from %s", MODEL_DIR)
            return True
        else:
            missing = [
                p.name for p in [motor_path, dirt_path, health_path, rul_path] if not p.exists()
            ]
            logger.warning("Missing model files %s — using rule-based fallback", missing)
            return False
    except Exception as exc:
        logger.error("Model load failed: %s — using fallback", exc)
        return False


def _hw4_features(
    motor_temperature_c: float,
    speed_mps: float,
    motor_current_a: float,
    battery_v: float,
    battery_a: float,
    battery_soc: float,
    brush_on: bool,
    pump_on: bool,
    water_level_pct: float,
) -> list[float]:
    """Map SmartClean robot sensors to HW4 9-feature vector."""
    temperature_c = motor_temperature_c
    vibration_rms_mm_s = speed_mps * 12.0
    rotational_speed_rpm = speed_mps * 500 + 100
    power_kw = (battery_v * battery_a) / 1000.0
    load_percent = (motor_current_a / 3.5) * 100
    acoustic_noise_db = 42 + 12 * float(brush_on) + 8 * float(pump_on) + speed_mps * 5
    asset_age_hours = 100 * (1 - battery_soc / 100)
    maintenance_score = water_level_pct
    return [
        temperature_c,
        vibration_rms_mm_s,
        rotational_speed_rpm,
        power_kw,
        load_percent,
        motor_current_a,
        acoustic_noise_db,
        asset_age_hours,
        maintenance_score,
    ]


def predict(
    motor_current_a: float,
    motor_temperature_c: float,
    speed_mps: float,
    brush_on: bool,
    pump_on: bool,
    battery_a: float,
    dirt_score: float,
    battery_v: float = 11.3,
    battery_soc: float = 80.0,
    water_level_pct: float = 100.0,
) -> dict:
    """Return motor health, dirt level, HW4 health state and RUL predictions."""
    if _loaded:
        # Existing models
        motor_features = np.array(
            [
                [
                    motor_current_a,
                    motor_temperature_c,
                    speed_mps,
                    float(brush_on),
                    float(pump_on),
                    battery_a,
                ]
            ]
        )
        dirt_features = np.array([[dirt_score]])

        motor_pred = _motor_clf.predict(motor_features)[0]
        motor_conf = float(np.max(_motor_clf.predict_proba(motor_features)[0]))

        dirt_pred = _dirt_clf.predict(dirt_features)[0]
        dirt_conf = float(np.max(_dirt_clf.predict_proba(dirt_features)[0]))

        # HW4 models
        hw4_vec = np.array(
            [
                _hw4_features(
                    motor_temperature_c,
                    speed_mps,
                    motor_current_a,
                    battery_v,
                    battery_a,
                    battery_soc,
                    brush_on,
                    pump_on,
                    water_level_pct,
                )
            ]
        )
        health_pred = _health_state_clf.predict(hw4_vec)[0]
        health_conf = float(np.max(_health_state_clf.predict_proba(hw4_vec)[0]))
        rul_minutes = float(np.clip(_rul_regressor.predict(hw4_vec)[0], 0, 200))

        return {
            "motor_health_prediction": motor_pred,
            "motor_health_confidence": round(motor_conf, 4),
            "dirt_level_prediction": dirt_pred,
            "dirt_level_confidence": round(dirt_conf, 4),
            "health_state_prediction": health_pred,
            "health_state_confidence": round(health_conf, 4),
            "predicted_rul_minutes": round(rul_minutes, 1),
            "model_used": "random_forest",
        }
    else:
        # Rule-based fallback (always available)
        if motor_current_a > 3.5 and motor_temperature_c > 70:
            motor_pred = "FAULT"
        elif motor_temperature_c > 70:
            motor_pred = "OVERHEATED"
        elif motor_current_a > 2.5:
            motor_pred = "HIGH_LOAD"
        else:
            motor_pred = "NORMAL"

        if dirt_score >= 0.7:
            dirt_pred = "DIRTY"
        elif dirt_score >= 0.3:
            dirt_pred = "MODERATE"
        else:
            dirt_pred = "CLEAN"

        # Fallback health state from motor state
        if motor_pred == "FAULT":
            health_pred = "CRITICAL"
        elif motor_pred in ("OVERHEATED", "HIGH_LOAD"):
            health_pred = "WARNING"
        else:
            health_pred = "NORMAL"

        # Fallback RUL from battery_soc
        rul_minutes = round(battery_soc * 1.2, 1)

        return {
            "motor_health_prediction": motor_pred,
            "motor_health_confidence": 1.0,
            "dirt_level_prediction": dirt_pred,
            "dirt_level_confidence": 1.0,
            "health_state_prediction": health_pred,
            "health_state_confidence": 1.0,
            "predicted_rul_minutes": rul_minutes,
            "model_used": "rule_fallback",
        }
