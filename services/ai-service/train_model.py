"""Train and save all AI models for SmartClean Twin.

Models trained
--------------
1. motor_health_clf   : NORMAL / HIGH_LOAD / OVERHEATED / FAULT  (existing)
2. dirt_level_clf     : CLEAN / MODERATE / DIRTY                  (existing)
3. health_state_clf   : NORMAL / WARNING / CRITICAL               (HW4 classification)
4. rul_regressor      : predicted_rul_minutes (continuous)        (HW4 regression)

HW4 feature mapping — SmartClean robot sensors → HW4 feature space
-------------------------------------------------------------------
temperature_c        ← motor_temperature_c
vibration_rms_mm_s   ← speed_mps * 12.0  (moving robot vibrates)
rotational_speed_rpm ← speed_mps * 500 + 100  (brush motor proxy)
power_kw             ← (battery_v * battery_a) / 1000
load_percent         ← (motor_current_a / 3.5) * 100
motor_current_a      ← motor_current_a
acoustic_noise_db    ← 42 + 12*brush_on + 8*pump_on + speed_mps*5
asset_age_hours      ← 100*(1 - battery_soc/100)  (depletion proxy for age)
maintenance_score    ← water_level_pct  (full tank = good maintenance state)

HW4 health_state labelling rules (risk_score derived from sensor values):
  NORMAL   : risk_score < 0.35
  WARNING  : 0.35 <= risk_score < 0.65
  CRITICAL : risk_score >= 0.65

HW4 RUL formula: remaining_useful_life_minutes = f(battery_soc, wear, load, maintenance)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.metrics import classification_report, mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

MODEL_DIR = Path(os.environ.get("MODEL_DIR", "/app/models"))
MODEL_DIR.mkdir(parents=True, exist_ok=True)
SEED = 42


# ── Dataset generation ────────────────────────────────────────────────────────


def _label_motor_health(row: pd.Series) -> str:
    if row["motor_current_a"] > 3.5 and row["motor_temperature_c"] > 70:
        return "FAULT"
    if row["motor_temperature_c"] > 70:
        return "OVERHEATED"
    if row["motor_current_a"] > 2.5 or (row["motor_current_a"] > 1.5 and row["brush_on"] == 1):
        return "HIGH_LOAD"
    return "NORMAL"


def _label_dirt_level(dirt_score: float) -> str:
    if dirt_score >= 0.7:
        return "DIRTY"
    if dirt_score >= 0.3:
        return "MODERATE"
    return "CLEAN"


def generate_dataset(n: int = 5000, seed: int = SEED) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    df = pd.DataFrame(
        {
            "motor_current_a": rng.uniform(0.3, 4.0, n),
            "motor_temperature_c": rng.uniform(20.0, 95.0, n),
            "speed_mps": rng.uniform(0.0, 0.5, n),
            "brush_on": rng.integers(0, 2, n).astype(float),
            "pump_on": rng.integers(0, 2, n).astype(float),
            "battery_a": rng.uniform(0.5, 3.5, n),
            "dirt_score": rng.uniform(0.0, 1.0, n),
        }
    )
    df["motor_health_label"] = df.apply(_label_motor_health, axis=1)
    df["dirt_level_label"] = df["dirt_score"].apply(_label_dirt_level)
    return df


# ── Training ──────────────────────────────────────────────────────────────────

MOTOR_FEATURES = [
    "motor_current_a",
    "motor_temperature_c",
    "speed_mps",
    "brush_on",
    "pump_on",
    "battery_a",
]
DIRT_FEATURES = ["dirt_score"]


def train_and_save(df: pd.DataFrame) -> dict[str, float]:
    results = {}

    # Motor health classifier
    X_motor = df[MOTOR_FEATURES].values
    y_motor = df["motor_health_label"].values
    X_tr, X_te, y_tr, y_te = train_test_split(
        X_motor, y_motor, test_size=0.2, random_state=SEED, stratify=y_motor
    )
    clf_motor = RandomForestClassifier(n_estimators=100, random_state=SEED, n_jobs=-1)
    clf_motor.fit(X_tr, y_tr)
    acc_motor = clf_motor.score(X_te, y_te)
    results["motor_health_accuracy"] = acc_motor
    print(f"\nMotor Health Classifier — test accuracy: {acc_motor:.4f}")
    print(classification_report(y_te, clf_motor.predict(X_te)))
    joblib.dump(clf_motor, MODEL_DIR / "motor_health_clf.joblib")
    print("Saved motor_health_clf.joblib")

    # Dirt level classifier
    X_dirt = df[DIRT_FEATURES].values
    y_dirt = df["dirt_level_label"].values
    X_tr2, X_te2, y_tr2, y_te2 = train_test_split(
        X_dirt, y_dirt, test_size=0.2, random_state=SEED, stratify=y_dirt
    )
    clf_dirt = RandomForestClassifier(n_estimators=50, random_state=SEED, n_jobs=-1)
    clf_dirt.fit(X_tr2, y_tr2)
    acc_dirt = clf_dirt.score(X_te2, y_te2)
    results["dirt_level_accuracy"] = acc_dirt
    print(f"\nDirt Level Classifier — test accuracy: {acc_dirt:.4f}")
    print(classification_report(y_te2, clf_dirt.predict(X_te2)))
    joblib.dump(clf_dirt, MODEL_DIR / "dirt_level_clf.joblib")
    print("Saved dirt_level_clf.joblib")

    return results


# ── HW4 dataset generation ────────────────────────────────────────────────────

HW4_FEATURES = [
    "temperature_c",
    "vibration_rms_mm_s",
    "rotational_speed_rpm",
    "power_kw",
    "load_percent",
    "motor_current_a",
    "acoustic_noise_db",
    "asset_age_hours",
    "maintenance_score",
]


def generate_hw4_dataset(n: int = 1200, seed: int = SEED) -> pd.DataFrame:
    """Generate synthetic SmartClean robot dataset using HW4 methodology."""
    rng = np.random.default_rng(seed)

    motor_current_a = rng.uniform(0.3, 4.0, n)
    motor_temperature_c = rng.uniform(20.0, 95.0, n)
    speed_mps = rng.uniform(0.0, 0.5, n)
    brush_on = rng.integers(0, 2, n).astype(float)
    pump_on = rng.integers(0, 2, n).astype(float)
    battery_v = rng.uniform(10.0, 12.6, n)
    battery_a = rng.uniform(0.5, 3.5, n)
    battery_soc = rng.uniform(5.0, 100.0, n)
    water_level_pct = rng.uniform(0.0, 100.0, n)

    # Map to HW4 feature space
    temperature_c = motor_temperature_c
    vibration_rms_mm_s = np.clip(speed_mps * 12.0 + rng.normal(0, 0.2, n), 0.0, 7.0)
    rotational_speed_rpm = np.clip(speed_mps * 500 + 100 + rng.normal(0, 30, n), 50, 800)
    power_kw = (battery_v * battery_a) / 1000.0
    load_percent = np.clip((motor_current_a / 3.5) * 100, 0, 100)
    acoustic_noise_db = np.clip(
        42 + 12 * brush_on + 8 * pump_on + speed_mps * 5 + rng.normal(0, 1.5, n), 35, 80
    )
    asset_age_hours = np.clip(100 * (1 - battery_soc / 100) + rng.uniform(0, 20, n), 0, 100)
    maintenance_score = water_level_pct

    # HW4 risk score formula adapted for robot sensors
    risk_score = (
        0.28 * ((temperature_c - 25) / 70)
        + 0.30 * ((vibration_rms_mm_s - 0.5) / 6.0)
        + 0.18 * (load_percent / 100)
        + 0.14 * (asset_age_hours / 100)
        + 0.10 * ((100 - maintenance_score) / 100)
        + rng.normal(0, 0.03, n)
    )

    health_state = np.where(
        risk_score >= 0.65, "CRITICAL", np.where(risk_score >= 0.35, "WARNING", "NORMAL")
    )

    # RUL in minutes: high risk and low battery reduce remaining life
    remaining_useful_life_minutes = np.clip(
        120
        - 80 * risk_score
        - 0.8 * asset_age_hours
        + 0.5 * maintenance_score
        - 0.4 * load_percent
        + rng.normal(0, 5, n),
        5,
        130,
    )

    return pd.DataFrame(
        {
            "temperature_c": np.round(temperature_c, 2),
            "vibration_rms_mm_s": np.round(vibration_rms_mm_s, 3),
            "rotational_speed_rpm": np.round(rotational_speed_rpm, 1),
            "power_kw": np.round(power_kw, 3),
            "load_percent": np.round(load_percent, 1),
            "motor_current_a": np.round(motor_current_a, 3),
            "acoustic_noise_db": np.round(acoustic_noise_db, 2),
            "asset_age_hours": np.round(asset_age_hours, 1),
            "maintenance_score": np.round(maintenance_score, 1),
            "health_state": health_state,
            "remaining_useful_life_minutes": np.round(remaining_useful_life_minutes, 1),
        }
    )


def train_and_save_hw4(df: pd.DataFrame) -> dict[str, float]:
    """Train and save HW4 health-state classifier and RUL regressor."""
    results = {}
    X = df[HW4_FEATURES].values
    y_class = df["health_state"].values
    y_rul = df["remaining_useful_life_minutes"].values

    X_tr, X_te, y_cls_tr, y_cls_te, y_rul_tr, y_rul_te = train_test_split(
        X, y_class, y_rul, test_size=0.20, random_state=SEED, stratify=y_class
    )

    # HW4 classification model (Pipeline with scaler, same as HW4 notebook)
    clf_health = Pipeline(
        steps=[
            ("scaler", StandardScaler()),
            (
                "model",
                RandomForestClassifier(
                    n_estimators=150,
                    max_depth=9,
                    min_samples_leaf=3,
                    class_weight="balanced",
                    random_state=SEED,
                    n_jobs=1,
                ),
            ),
        ]
    )
    clf_health.fit(X_tr, y_cls_tr)
    acc_health = clf_health.score(X_te, y_cls_te)
    results["health_state_accuracy"] = acc_health
    print(f"\nHW4 Health-State Classifier — test accuracy: {acc_health:.4f}")
    print(classification_report(y_cls_te, clf_health.predict(X_te)))
    joblib.dump(clf_health, MODEL_DIR / "health_state_clf.joblib")
    print("Saved health_state_clf.joblib")

    # HW4 regression model (Pipeline with scaler, same as HW4 notebook)
    reg_rul = Pipeline(
        steps=[
            ("scaler", StandardScaler()),
            (
                "model",
                RandomForestRegressor(
                    n_estimators=150,
                    max_depth=10,
                    min_samples_leaf=3,
                    random_state=SEED,
                    n_jobs=1,
                ),
            ),
        ]
    )
    reg_rul.fit(X_tr, y_rul_tr)
    y_rul_pred = reg_rul.predict(X_te)
    r2 = r2_score(y_rul_te, y_rul_pred)
    mae = mean_absolute_error(y_rul_te, y_rul_pred)
    results["rul_r2"] = r2
    results["rul_mae_minutes"] = mae
    print(f"\nHW4 RUL Regressor — R²: {r2:.4f}  MAE: {mae:.2f} min")
    joblib.dump(reg_rul, MODEL_DIR / "rul_regressor.joblib")
    print("Saved rul_regressor.joblib")

    return results


# ── Anomaly detection (unsupervised) ─────────────────────────────────────────

ANOMALY_FEATURES = [
    "motor_current_a",
    "motor_temperature_c",
    "speed_mps",
    "battery_v",
    "battery_a",
]


def generate_normal_operation_dataset(n: int = 4000, seed: int = SEED) -> pd.DataFrame:
    """Sample sensor values from NORMAL robot operation only.

    Ranges mirror the simulator's healthy behaviour:
      motor_current_a     0.6 (idle) to 0.9 (brush on)
      motor_temperature_c 20-70 (normal thermal envelope)
      speed_mps           0.0 / 0.1 / 0.2 discrete speeds
      battery_v           10.0-12.6 (SoC-linked)
      battery_a           1.2-1.5
    Fault-injected values (current 3.5 A, temp > 80) fall outside these
    ranges, so the IsolationForest flags them as anomalies.
    """
    rng = np.random.default_rng(seed)
    return pd.DataFrame(
        {
            "motor_current_a": rng.normal(0.75, 0.18, n).clip(0.3, 1.4),
            "motor_temperature_c": rng.normal(42, 11, n).clip(20, 70),
            "speed_mps": rng.choice([0.0, 0.1, 0.2], n, p=[0.15, 0.15, 0.70])
            + rng.normal(0, 0.01, n),
            "battery_v": rng.uniform(10.0, 12.6, n),
            "battery_a": rng.normal(1.35, 0.12, n).clip(1.0, 1.8),
        }
    )


ANOMALY_Z_THRESHOLD = 4.5  # sigmas — beyond this any single sensor is anomalous


def anomaly_predict(params: dict, X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Score samples against the learned normal-operation statistics.

    Returns (scores, is_anomaly). Score = threshold - max |z-score| across
    features, so score > 0 means normal and score < 0 means anomaly. Used
    by both this training script (sanity check) and predictor.py.
    """
    z = np.abs((X - params["mean"]) / params["std"])
    max_z = z.max(axis=1)
    scores = params["threshold"] - max_z
    return scores, scores < 0


def train_and_save_anomaly(df: pd.DataFrame) -> dict[str, float]:
    """Learn normal-operation statistics for unsupervised anomaly detection.

    The model is the per-sensor mean and standard deviation of healthy
    operation. A sample is anomalous when ANY sensor deviates by more than
    ANOMALY_Z_THRESHOLD sigmas — e.g. fault-injected 3.5 A motor current
    is (3.5 - 0.75) / 0.18 = 15 sigma, far past the threshold, while all
    healthy readings stay within ~4 sigma. Simple, fully explainable, and
    learned from data (no hand-tuned per-sensor limits).
    """
    X = df[ANOMALY_FEATURES].values
    params = {
        "features": ANOMALY_FEATURES,
        "mean": X.mean(axis=0),
        "std": X.std(axis=0),
        "threshold": ANOMALY_Z_THRESHOLD,
    }

    # Sanity check: known fault signatures must be flagged as anomalies
    fault_samples = np.array(
        [
            [3.5, 85.0, 0.0, 10.2, 1.5],  # motor overload + overheat
            [0.7, 110.0, 0.2, 11.0, 1.3],  # extreme overheat
            [4.0, 40.0, 0.2, 11.5, 1.4],  # current spike
        ]
    )
    _, fault_flags = anomaly_predict(params, fault_samples)
    _, normal_flags = anomaly_predict(params, X[:500])
    fault_flagged = fault_flags.mean()
    normal_ok = 1.0 - normal_flags.mean()

    print(f"\nAnomaly Detector — fault detection rate: {fault_flagged:.2%}")
    print(f"Anomaly Detector — normal pass rate: {normal_ok:.2%}")
    joblib.dump(params, MODEL_DIR / "anomaly_detector.joblib")
    print("Saved anomaly_detector.joblib")
    return {"anomaly_fault_detection": fault_flagged, "anomaly_normal_pass": normal_ok}


if __name__ == "__main__":
    print("=== Existing models (motor health + dirt level) ===")
    print("Generating dataset...")
    df = generate_dataset(n=5000)
    print(f"Dataset shape: {df.shape}")
    print("Motor health distribution:\n", df["motor_health_label"].value_counts())
    print("Dirt level distribution:\n", df["dirt_level_label"].value_counts())
    results = train_and_save(df)

    print("\n=== HW4 models (health state classifier + RUL regressor) ===")
    df_hw4 = generate_hw4_dataset(n=1200)
    print(f"HW4 dataset shape: {df_hw4.shape}")
    print("Health state distribution:\n", df_hw4["health_state"].value_counts())
    results.update(train_and_save_hw4(df_hw4))

    print("\n=== Anomaly detector (unsupervised, Mahalanobis distance) ===")
    df_normal = generate_normal_operation_dataset(n=4000)
    results.update(train_and_save_anomaly(df_normal))

    print("\nAll training complete:", results)
    # Fail if classification accuracy or RUL R² below target
    if results.get("health_state_accuracy", 0) < 0.80:
        print("WARNING: health_state accuracy below 0.80")
        sys.exit(1)
    if results.get("rul_r2", 0) < 0.80:
        print("WARNING: RUL R2 below 0.80")
        sys.exit(1)
    if results.get("anomaly_fault_detection", 0) < 0.99:
        print("WARNING: anomaly detector missed known fault signatures")
        sys.exit(1)
    print("All models meet performance targets.")
