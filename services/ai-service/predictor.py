"""Model loader and prediction logic with rule-based fallback."""

from __future__ import annotations

import logging
import os
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

MODEL_DIR = Path(os.environ.get("MODEL_DIR", "/app/models"))

_motor_clf = None
_dirt_clf = None
_loaded = False


def load_models() -> bool:
    global _motor_clf, _dirt_clf, _loaded
    try:
        import joblib

        motor_path = MODEL_DIR / "motor_health_clf.joblib"
        dirt_path = MODEL_DIR / "dirt_level_clf.joblib"
        if motor_path.exists() and dirt_path.exists():
            _motor_clf = joblib.load(motor_path)
            _dirt_clf = joblib.load(dirt_path)
            _loaded = True
            logger.info("AI models loaded from %s", MODEL_DIR)
            return True
        else:
            logger.warning("Model files not found — using rule-based fallback")
            return False
    except Exception as exc:
        logger.error("Model load failed: %s — using fallback", exc)
        return False


def predict(
    motor_current_a: float,
    motor_temperature_c: float,
    speed_mps: float,
    brush_on: bool,
    pump_on: bool,
    battery_a: float,
    dirt_score: float,
) -> dict:
    """Return motor health and dirt level predictions with confidence."""
    if _loaded and _motor_clf is not None and _dirt_clf is not None:
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
        motor_proba = _motor_clf.predict_proba(motor_features)[0]
        motor_conf = float(np.max(motor_proba))

        dirt_pred = _dirt_clf.predict(dirt_features)[0]
        dirt_proba = _dirt_clf.predict_proba(dirt_features)[0]
        dirt_conf = float(np.max(dirt_proba))

        return {
            "motor_health_prediction": motor_pred,
            "motor_health_confidence": round(motor_conf, 4),
            "dirt_level_prediction": dirt_pred,
            "dirt_level_confidence": round(dirt_conf, 4),
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

        return {
            "motor_health_prediction": motor_pred,
            "motor_health_confidence": 1.0,
            "dirt_level_prediction": dirt_pred,
            "dirt_level_confidence": 1.0,
            "model_used": "rule_fallback",
        }
