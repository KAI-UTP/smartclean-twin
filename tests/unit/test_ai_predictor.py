"""Unit tests: AI predictor (rule-based fallback — no model files needed)."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "services", "ai-service"))

import pytest
import predictor


class TestRuleFallbackMotorHealth:
    """Tests run against the rule fallback (model not loaded in CI without Docker)."""

    def setup_method(self):
        # Force rule fallback for unit testing without trained models
        predictor._loaded = False

    def test_normal_conditions(self):
        result = predictor.predict(
            motor_current_a=0.8, motor_temperature_c=35.0, speed_mps=0.2,
            brush_on=True, pump_on=False, battery_a=1.2, dirt_score=0.1,
        )
        assert result["motor_health_prediction"] == "NORMAL"
        assert result["model_used"] == "rule_fallback"

    def test_high_load_from_current(self):
        result = predictor.predict(
            motor_current_a=3.0, motor_temperature_c=45.0, speed_mps=0.2,
            brush_on=True, pump_on=False, battery_a=1.2, dirt_score=0.1,
        )
        assert result["motor_health_prediction"] == "HIGH_LOAD"

    def test_overheated(self):
        result = predictor.predict(
            motor_current_a=1.0, motor_temperature_c=80.0, speed_mps=0.1,
            brush_on=False, pump_on=False, battery_a=0.8, dirt_score=0.0,
        )
        assert result["motor_health_prediction"] == "OVERHEATED"

    def test_fault_both_high(self):
        result = predictor.predict(
            motor_current_a=4.0, motor_temperature_c=85.0, speed_mps=0.0,
            brush_on=True, pump_on=True, battery_a=2.0, dirt_score=0.5,
        )
        assert result["motor_health_prediction"] == "FAULT"


class TestRuleFallbackDirtLevel:
    def setup_method(self):
        predictor._loaded = False

    def test_clean_dirt(self):
        result = predictor.predict(0.5, 30.0, 0.2, True, False, 1.0, dirt_score=0.1)
        assert result["dirt_level_prediction"] == "CLEAN"

    def test_moderate_dirt(self):
        result = predictor.predict(0.5, 30.0, 0.2, True, False, 1.0, dirt_score=0.5)
        assert result["dirt_level_prediction"] == "MODERATE"

    def test_dirty(self):
        result = predictor.predict(0.5, 30.0, 0.2, True, False, 1.0, dirt_score=0.8)
        assert result["dirt_level_prediction"] == "DIRTY"


class TestPredictorOutput:
    def setup_method(self):
        predictor._loaded = False

    def test_result_has_required_keys(self):
        result = predictor.predict(0.5, 30.0, 0.2, True, False, 1.0, 0.3)
        assert "motor_health_prediction" in result
        assert "motor_health_confidence" in result
        assert "dirt_level_prediction" in result
        assert "dirt_level_confidence" in result
        assert "model_used" in result

    def test_confidence_is_float_between_0_and_1(self):
        result = predictor.predict(0.5, 30.0, 0.2, True, False, 1.0, 0.3)
        assert 0.0 <= result["motor_health_confidence"] <= 1.0
        assert 0.0 <= result["dirt_level_confidence"] <= 1.0
