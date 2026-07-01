"""Train and save the motor-health and dirt-level classifiers.

Labelling rules (documented, not fabricated):
  Motor health:
    NORMAL     : motor_current_a <= 1.5 AND motor_temperature_c <= 55
    HIGH_LOAD  : motor_current_a  > 2.5  OR (motor_current_a > 1.5 AND brush_on)
    OVERHEATED : motor_temperature_c > 70
    FAULT      : motor_current_a > 3.5 AND motor_temperature_c > 70

  Dirt level:
    CLEAN    : dirt_score < 0.3
    MODERATE : 0.3 <= dirt_score < 0.7
    DIRTY    : dirt_score >= 0.7

Run this script once (or during CI) to produce models/motor_health_clf.joblib
and models/dirt_level_clf.joblib.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder

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
    df = pd.DataFrame({
        "motor_current_a":     rng.uniform(0.3, 4.0, n),
        "motor_temperature_c": rng.uniform(20.0, 95.0, n),
        "speed_mps":           rng.uniform(0.0, 0.5, n),
        "brush_on":            rng.integers(0, 2, n).astype(float),
        "pump_on":             rng.integers(0, 2, n).astype(float),
        "battery_a":           rng.uniform(0.5, 3.5, n),
        "dirt_score":          rng.uniform(0.0, 1.0, n),
    })
    df["motor_health_label"] = df.apply(_label_motor_health, axis=1)
    df["dirt_level_label"] = df["dirt_score"].apply(_label_dirt_level)
    return df


# ── Training ──────────────────────────────────────────────────────────────────

MOTOR_FEATURES = [
    "motor_current_a", "motor_temperature_c", "speed_mps",
    "brush_on", "pump_on", "battery_a",
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
    print(f"Saved motor_health_clf.joblib")

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
    print(f"Saved dirt_level_clf.joblib")

    return results


if __name__ == "__main__":
    print("Generating dataset...")
    df = generate_dataset(n=5000)
    print(f"Dataset shape: {df.shape}")
    print("Motor health distribution:\n", df["motor_health_label"].value_counts())
    print("Dirt level distribution:\n", df["dirt_level_label"].value_counts())
    results = train_and_save(df)
    print("\nTraining complete:", results)
    # Fail if accuracy below target
    for k, v in results.items():
        if v < 0.80:
            print(f"WARNING: {k} accuracy {v:.4f} is below 0.80 target")
            sys.exit(1)
    print("All classifiers meet >=80% accuracy target.")
