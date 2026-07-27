# Testing Verification Report — Liang

**Reviewer:** Liang Yan Ee 22011522

**Date:** 27 July 2026

**Suites reviewed:** `tests/unit`, `tests/integration`, `tests/system`, `tests/regression`

**Method.** All offline suites were re-run independently on a second machine — Windows 10,
Python 3.12.10, in a clean virtualenv built from `requirements-dev.txt` plus all five
`services/*/requirements.txt`. Running on a different machine and a different Python version
from the development environment is deliberate: it is what exposed finding 4 below. Results
attributed to the submission notebooks are labelled as such and were not run by me; the
Docker-dependent suites could not be executed on my hardware (see final note).

## 1. Test Suite Results

Verified by me at commit `f26c326`:

| Suite | Command | Result |
|---|---|---|
| Unit | `pytest tests/unit -q` | **81 passed** |
| Integration | `pytest tests/integration -q` | **11 passed** |
| Regression | `pytest tests/regression -q` | **10 passed** |
| **Offline total** | | **102 passed, 0 failed** in 4.13 s |

Integration tests do not require a running stack — MQTT and InfluxDB are mocked with
`unittest.mock.patch` and FastAPI endpoints driven through `TestClient`. All ten named
regression cases REG-001…REG-010 pass.

**System tests:** reported as `14 passed in 21.04s` in `submission_4_dev_practices.ipynb`.
Not independently verified by me — Docker would not start on my machine.

### Finding 4 — `requests` is missing from every requirements file

`tests/system/` imports `requests`, but it appears in neither `requirements-dev.txt` nor any
`services/*/requirements.txt`. On a clean environment the system suite fails at *collection*:

```
tests\system\test_persistence.py:16: in <module>
    import requests
E   ModuleNotFoundError: No module named 'requests'
!!!!!!!!!!!!!!!!!!! Interrupted: 2 errors during collection !!!!!!!!!!!!!!!!!!!
```

This is invisible on the development machine because `requests` is already installed there
as a transitive dependency. I hit it on both of my environment builds and had to install it
by hand each time. **Still unfixed at the time of writing.** Recommend adding `requests` to
`requirements-dev.txt`.

## 2. Demonstrated FAIL Case

Rather than stopping the MQTT broker — which proves only that the network is down — I
injected a deliberate **logic regression**, to test whether the regression suite actually
detects a behavioural change.

**What was broken:** `services/state-engine/rules.py` line 59, obstacle emergency threshold
changed from 25 cm to 5 cm, simulating a developer "tuning" a constant:

```python
if s.obstacle_cm < 25.0 or s.bumper_active:   # before
if s.obstacle_cm <  5.0 or s.bumper_active:   # injected fault
```

**Result** — `pytest tests/regression tests/unit -q` (baseline immediately before: 10 passed):

```
FAILED tests/regression/test_regression_suite.py::test_reg_obstacle_emergency
FAILED tests/unit/test_state_rules.py::TestSafetyRules::test_obstacle_under_25_is_emergency
E   AssertionError: assert <SafetyState...'WARNING'> == <SafetyState...'EMERGENCY'>
======================== 2 failed, 89 passed in 1.23s =========================
```

Exactly two tests failed — REG-001 and its unit-test counterpart — while the other 89 passed,
so the failure was precisely localised to the changed rule.

**Why they failed** — TODO, one or two sentences in your own words. The mechanism: at a 5 cm
threshold an obstacle at 20 cm no longer satisfies `< 5.0`, so control falls through to the
`elif s.obstacle_cm < 50.0` branch and the twin reports `WARNING`/`AVOIDING` instead of
`EMERGENCY`/`STOPPED` — the robot would not stop for an obstacle it should stop for. Note the
alarm threshold literal on line 69 remained `25.0`, so the rule and the alarm it raises would
have silently disagreed.

**After reverting** (`git checkout services/state-engine/rules.py`): **91 passed**, threshold
confirmed restored. The injected fault was never committed.

## 3. Scaling — Defect Found and Verified Fixed

An earlier revision of `docker-compose.yml` bound `telemetry-ingestion` to a fixed host port:

```yaml
    ports:
      - "8001:8001"
```

A host port can only be held by one container, so `--scale telemetry-ingestion=2` could not
start a second replica — despite the comment eleven lines below reading
`# Uses MQTT subscribe (fan-out) — safe to scale`. The comment was correct about the
*application* (stateless, fan-out delivery); the *deployment configuration* contradicted it.

The failure was hard to see because the evidence notebook called
`subprocess.run(..., capture_output=True)` without checking `returncode`, so the
port-allocation error was captured and discarded while a success heading printed regardless.
The committed output showed one instance at `Up 3 minutes` — the pre-existing container.

**Verified fixed** in commit `69a4ba9`. The binding is now a host port range:

```yaml
      # host port range so replicas can scale: instance 1 -> 8001, instance 2 -> 8011, ...
      - "8001-8011:8001"
```

and the current notebook output shows both replicas, the second freshly created:

```
telemetry-ingestion-1   Up About an hour
telemetry-ingestion-2   Up 15 seconds
```

- Instances now running under `--scale 2`: **2** (verified from committed output, not on my machine)
- Why the service is safe to scale — TODO, one sentence in your own words, based on the MQTT
  fan-out and stateless-per-message points above.

## 4. Coverage Assessment

Measured by me: `pytest tests/unit tests/regression tests/integration --cov=services --cov=shared`

| Module | Stmts | Miss | Cover |
|---|---|---|---|
| `robot-simulator/grid_map.py` | 25 | 0 | **100%** |
| `smartclean_common/topics.py` | 19 | 0 | **100%** |
| `smartclean_common/models.py` | 168 | 1 | **99%** |
| `state-engine/rules.py` | 81 | 6 | **93%** |
| `robot-simulator/robot_state.py` | 42 | 4 | **90%** |
| `ai-service/predictor.py` | 85 | 47 | **45%** |
| `robot-simulator/simulator.py` | 239 | 161 | **33%** |
| **TOTAL** | **659** | **219** | **66.77%** |

**Strongest.** Literally `grid_map.py` and `topics.py` at 100% — but `topics.py` is 19
statements of string constants, so the figure proves little. By test *depth* the best-covered
module is `rules.py`: 93%, but backed by 20 unit plus 10 regression tests, the only module
tested at two layers, and the one encoding all eleven safety rules. Highest percentage and
strongest testing are not the same property.
*TODO — one sentence: which you'd call strongest, and why.*

**Weakest.** `simulator.py` at 33%. The gaps are of two kinds:

- *Defensible:* `run()`, `_on_connect`, `_on_command`, `__init__` MQTT setup — these need a
  live broker, which is what the system layer is for.
- *Not defensible:* `_update_physics()` (lines 126-265, 140 statements) at **zero** coverage.
  Pure arithmetic, no I/O, directly unit-testable.

That second gap matters more than the percentage suggests: `_update_physics()` produces every
telemetry value the rest of the system consumes — position, battery drain, coverage, dirt
score, motor current and temperature. The state rules are heavily tested against
*hand-constructed* telemetry, but the code generating *real* telemetry is untested, so a
defect there would propagate into the twin state, AI predictions, InfluxDB and Grafana with
every existing test still green. Second weakest is `predictor.py` (45%): only the rule-based
fallback is exercised, never the trained-model path that runs in the deployed container.
*TODO — one sentence: weakest module and why.*

**Test I would add.** A deterministic unit test for `_update_physics()` — `SIMULATOR_SEED=42`
is fixed in compose, so it is reproducible without a broker. Assertions: battery SOC decreases
monotonically and stays within 0-100; coverage increases only while `brush_on`; motor
temperature rises under sustained high current (the 70 °C OVERHEATED rule depends on it); and
the robot never leaves the 10×10 accessible area. The last is the highest value —
`grid_map.py` proves the *map* marks borders as obstacles, but nothing proves the *simulator*
respects them.
*TODO — one sentence: which test, and why.*

### Findings 5 and 6 — documentation does not match measurement

| Claim in `docs/testing-plan.md` | Measured |
|---|---|
| "Coverage Target: ≥ 70%" (line 5) | **66.77%** — CI passes only because `pyproject.toml` sets `fail_under = 65` |
| Unit tests: 69 | **81** |
| System tests: 4 | **14** |
| Total "94+" | **102 offline + 14 system** |

Both still unfixed. The coverage gap is the more substantive of the two: the documented target
is not being met, and the configured gate is set below it.

## 5. Overall Assessment

TODO — 3-4 sentences, your own words. Each bullet is roughly one sentence; every supporting
fact is in sections 1-4 above, so you can defend any of them.

- **Credit where due.** The pyramid is well built at the base — 102 offline tests across four
  layers, all passing, and a regression suite that provably catches a real logic change
  (section 2).
- **The pattern in the weaknesses.** Every defect I found sat in verification *plumbing*
  rather than in the twin's logic: a missing dependency, a discarded exit code, documentation
  drifting from measurement.
- **The real risk.** In each case the output *looked* green. A discarded `stderr` and a
  skipped test both report as success, which is more dangerous than a visible failure because
  nobody investigates a passing run.
- **One recommendation.** Your pick — e.g. evidence notebooks should assert `returncode == 0`
  before printing a success heading, or `fail_under` should be raised to the documented 70%.

---

## Summary of Findings

| # | Finding | Status |
|---|---|---|
| 1 | Fixed host port `8001:8001` prevented `--scale telemetry-ingestion=2` | ✅ Fixed in `69a4ba9` |
| 2 | System tests reported as run but `INTEGRATION_TEST` unset, so all skipped | ✅ Fixed — now 14 passed |
| 3 | Scale-command failure hidden by `capture_output=True` with no `returncode` check | ✅ Fixed |
| 4 | `requests` absent from all requirements files; `tests/system` fails at collection | ❌ **Open** |
| 5 | Coverage 66.77% against documented ≥70% target; `fail_under = 65` | ❌ **Open** |
| 6 | Test counts in `testing-plan.md` stale (69/4 documented vs 81/14 actual) | ❌ **Open** |

## Note on Environment

The Docker-dependent steps could not be run on my machine — the engine fails with
`Insufficient system resources … Wsl/Service/AttachDisk/CreateVm/HCS/0x800705aa`, a host
memory limit (7.4 GB RAM, ~0.5 GB free), not a fault in the project. Restarting Docker Desktop
and `wsl --shutdown` did not resolve it. Sections 1 and 2 were produced by running the suites
myself; section 3's verification is derived from `docker-compose.yml` and committed notebook
output, both independently checkable in this repository.
