# SmartClean Twin — Testing Plan

**Project:** SmartClean Twin — RBB2013 Digital Twin May 2026  
**Test Framework:** pytest 8.x with pytest-cov  
**Coverage Target:** ≥ 70% line coverage on `services/` and `shared/`

---

## Test Layers

| Layer | Location | Count | Requires Docker? |
|-------|----------|-------|-----------------|
| Unit | `tests/unit/` | 69 | No |
| Integration | `tests/integration/` | 11 | No (mocked) |
| Regression | `tests/regression/` | 10 | No |
| System | `tests/system/` | 4 | Yes (set `INTEGRATION_TEST=1`) |
| **Total** | | **94+** | |

---

## Unit Tests (`tests/unit/`)

### `test_telemetry_schema.py` — 17 tests
Tests Pydantic v2 schema validation for `TelemetryMessage`:
- Valid message accepted
- Missing required fields raise `ValidationError`
- Out-of-range values rejected (SOC > 100, negative SOC, heading = 360, speed > 2, dirt > 1)
- Invalid types rejected

### `test_state_rules.py` — 17 tests
Tests Digital Twin state engine rule evaluation:
- Obstacle < 25 cm → EMERGENCY + STOPPED
- Obstacle 25–50 cm → WARNING + AVOIDING
- Obstacle ≥ 50 cm → SAFE
- Battery < 10% → CRITICAL + alarm
- Battery 10–20% → LOW
- Motor current > 2.5 A → HIGH_LOAD + alarm
- Motor temperature > 70°C → OVERHEATED + alarm
- Coverage ≥ 90% → COMPLETED
- Message delay > 2 s → DELAYED
- Message delay > 10 s → OFFLINE/INVALID

### `test_grid_map.py` — 10 tests
Tests 10×10 grid map and lawnmower path generation:
- Home cell (1,1) accessible
- Border cells are obstacles
- Total accessible cells computed correctly
- Out-of-bounds returns False
- Lawnmower path covers all accessible cells
- No duplicate cells in path
- Dirt map shape, obstacle zeros, value range, determinism

### `test_ai_predictor.py` — 9 tests
Tests AI predictor with rule-based fallback (no model files):
- NORMAL / HIGH_LOAD / OVERHEATED / FAULT motor health
- CLEAN / MODERATE / DIRTY dirt level
- Output keys present: `motor_health`, `dirt_level`, `motor_health_confidence`, `dirt_level_confidence`
- Confidence values in range [0.0, 1.0]

### `test_command_validation.py` — 10 tests
Tests `CommandRequest` Pydantic validation:
- All 9 valid commands accepted
- Unknown command string raises `ValidationError`
- Empty command raises `ValidationError`
- Missing robot_id raises `ValidationError`

### `test_simulator_commands.py` — 12 tests
Tests `RobotSimulator._apply_command()` and fault injection:
- All command handlers execute without MQTT connection (mock)
- PAUSE sets paused flag
- RESUME clears paused flag
- STOP sets stopped flag
- RETURN_HOME sets returning_home flag
- SET_BRUSH / SET_PUMP update actuators
- Fault injection: obstacle, motor, battery, clear

---

## Integration Tests (`tests/integration/`)

MQTT and InfluxDB are mocked with `unittest.mock.patch`.  
FastAPI `TestClient` is used for HTTP endpoint testing.  
Service `main.py` files are loaded from explicit paths via `importlib.util.spec_from_file_location` to avoid `sys.path` conflicts.

### `test_command_api.py` — 7 tests
- `/health` returns 200 with `status`, `uptime_s`, `commands_issued`
- `GET /api/v1/commands` returns empty list initially
- `POST` with unknown robot_id returns 404
- `POST` with invalid command returns 422
- `POST` with valid command: MQTT publish called, ACK simulated, 200 returned
- `POST` without ACK returns `status: timeout`

### `test_telemetry_ingestion.py` — 4 tests
- Valid payload increments `valid` counter and calls `publish`
- Invalid JSON increments `invalid` counter, no publish
- Missing required field increments `invalid` counter
- `/health` endpoint reflects stats

---

## Regression Tests (`tests/regression/`)

10 named regression tests that must never fail:

| ID | Test | Rule Verified |
|----|------|--------------|
| REG-001 | `test_reg_obstacle_emergency` | obstacle_cm < 25 → EMERGENCY |
| REG-002 | `test_reg_battery_critical` | battery_soc < 10 → CRITICAL alarm |
| REG-003 | `test_reg_motor_overheated` | temperature > 70 → OVERHEATED alarm |
| REG-004 | `test_reg_mission_completed_at_90_pct` | coverage ≥ 90% → COMPLETED |
| REG-005 | `test_reg_schema_v1_parses` | Schema version "1.0" accepted |
| REG-006 | `test_reg_ai_fallback_always_returns_prediction` | Rule fallback returns all keys |
| REG-007 | `test_reg_lawnmower_path_deterministic` | Same seed → same path |
| REG-008 | `test_reg_mqtt_topics_defined` | All 9 topic constants non-empty |
| REG-009 | `test_reg_coverage_formula` | cleaned/total × 100 correct |
| REG-010 | `test_reg_safe_not_emergency` | obstacle_cm = 60 → SAFE, no alarm |

---

## System Tests (`tests/system/`)

Run with `INTEGRATION_TEST=1` against a live Docker stack:
- All 5 service `/health` endpoints return 200
- `POST /api/v1/commands` PAUSE/RESUME round-trip returns ACK
- Fault injection: obstacle → EMERGENCY state in MQTT state topic
- Fault injection: battery → CRITICAL battery state

---

## Running Tests

```bash
# Unit + integration + regression (no Docker required)
pytest tests/unit/ tests/integration/ tests/regression/ -v

# With coverage report
pytest tests/unit/ tests/integration/ tests/regression/ \
  --cov=services --cov=shared --cov-report=term-missing

# System tests (Docker stack must be running)
INTEGRATION_TEST=1 pytest tests/system/ -v

# All tests (Makefile shortcut)
make test
```

---

## Coverage Configuration

See `pyproject.toml`:
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "--cov=services --cov=shared --cov-report=term-missing"

[tool.coverage.run]
source = ["services", "shared"]

[tool.coverage.report]
fail_under = 70
```

---

## CI Integration

The GitHub Actions workflow (`.github/workflows/ci.yml`) runs unit + regression tests on every push.  
Coverage is reported and fails the build if below 70%.  
System tests are excluded from CI (require live Docker).
