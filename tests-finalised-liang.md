# Testing Verification Report — Liang

**Reviewer:** Liang Yan Ee (TODO: add your student ID — Nurin's format was "Nurin Emelin binti Marhisyam 24006706")

**Date:** 27 July 2026
**Suites reviewed:** `tests/unit`, `tests/integration`, `tests/system`, `tests/regression`

**Environment:** Run locally on Windows 10, Python 3.12.10, pytest 8.3.5, in an isolated
virtualenv built from `requirements-dev.txt` plus all five `services/*/requirements.txt`.

**Provenance of evidence.** Every test result in sections 1, 2 and 4 was produced by running
the suites on my own machine — none is transcribed from another team member's screenshots.
The two findings that concern the system and scaling layers (sections 1 and 3) are derived
from output already committed to this repository in `submission_5_deployment.ipynb`, which is
independently checkable by anyone reading it. The Docker-dependent steps were not run by me;
see the environment note at the end.

## 1. Test Suite Results

**Unit tests** (`pytest tests/unit -q`):
```
platform win32 -- Python 3.12.10, pytest-8.3.5, pluggy-1.6.0
configfile: pyproject.toml
collected 81 items

tests\unit\test_ai_predictor.py .........                                [ 11%]
tests\unit\test_command_validation.py .............                      [ 27%]
tests\unit\test_grid_map.py ..........                                   [ 39%]
tests\unit\test_simulator_commands.py ............                       [ 54%]
tests\unit\test_state_rules.py ....................                      [ 79%]
tests\unit\test_telemetry_schema.py .................                    [100%]

============================= 81 passed in 2.52s ==============================
```
Matches the expected count of 81.

**Integration tests** (`pytest tests/integration -q`):
```
collected 11 items

tests\integration\test_command_api.py .......                            [ 63%]
tests\integration\test_telemetry_ingestion.py ....                       [100%]

============================= 11 passed in 2.39s ==============================
```
Note: these do **not** require `docker compose up`. MQTT and InfluxDB are mocked with
`unittest.mock.patch`, and FastAPI endpoints are driven through `TestClient`.

**Regression tests** (`pytest tests/regression -q`):
```
collected 10 items

tests\regression\test_regression_suite.py ..........                     [100%]

============================= 10 passed in 0.41s ==============================
```
All 10 named regression cases (REG-001 … REG-010) pass.

**Offline total: 102 passed, 0 failed.**

**System tests** (`INTEGRATION_TEST=1 pytest tests/system -q`):
```
NOT RUN on my machine — the Docker engine would not start (see note at end).
14 tests collected across test_full_flow.py and test_persistence.py.
```

**Finding: 11 of the 14 system tests have never actually executed.**
`submission_5_deployment.ipynb` runs `pytest tests/system/test_full_flow.py -v` and the
committed output is:

```
tests/system/test_full_flow.py::TestServiceHealth::test_ingestion_health     SKIPPED [ 18%]
tests/system/test_full_flow.py::TestServiceHealth::test_state_engine_health  SKIPPED [ 27%]
tests/system/test_full_flow.py::TestServiceHealth::test_ai_service_health    SKIPPED [ 36%]
tests/system/test_full_flow.py::TestServiceHealth::test_simulator_health     SKIPPED [ 45%]
tests/system/test_full_flow.py::TestCommandFlow::test_pause_command_returns_ack  SKIPPED [ 54%]
tests/system/test_full_flow.py::TestCommandFlow::test_resume_after_pause     SKIPPED [ 63%]
tests/system/test_full_flow.py::TestCommandFlow::test_command_history_grows  SKIPPED [ 72%]
tests/system/test_full_flow.py::TestObstacleEmergencyScenario::...           SKIPPED [ 81%]
...
```

Every test is `SKIPPED`, not passed. `tests/system/test_full_flow.py` line 17 reads
`STACK_RUNNING = os.environ.get("INTEGRATION_TEST", "0") == "1"`, and the notebook invokes
pytest through `subprocess.run` without setting that variable — so the `skipif` guard
suppressed the entire file even though the stack was live at the time. This appears in a
notebook committed under the description *"executed live evidence."*

`tests/system/test_persistence.py` **did** genuinely run and pass (3 passed in 12.24 s) —
it has no `skipif` guard. So the honest count for the system layer is **3 of 14 executed**.

Fix: set the variable before invoking pytest, e.g.
`env={**os.environ, "INTEGRATION_TEST": "1"}` in the `subprocess.run` call.

Separately, the `[OK]`-for-all-services screenshot circulating in the group chat is
`scripts/smoke_test.py` — a health-check script that polls each `/health` endpoint. It is
not the pytest system suite and reports no test count.

> **Issue found while running these:** `tests/system/` imports `requests`, but `requests`
> is not listed in `requirements-dev.txt` or in any `services/*/requirements.txt`.
> On a clean environment the system suite fails at *collection* with
> `ModuleNotFoundError: No module named 'requests'` before a single test runs.
> Recommend adding `requests` to `requirements-dev.txt`.

## 2. Demonstrated FAIL Case

Rather than stopping the MQTT broker (which only proves the network is down), I injected a
deliberate **logic regression** into the state-engine rule set. This demonstrates that the
regression suite actually detects a behavioural change, which is what the suite exists for.

**What was broken:** In `services/state-engine/rules.py` line 59, the obstacle emergency
threshold was changed from 25 cm to 5 cm — simulating a developer "tuning" a constant:

```python
# before
if s.obstacle_cm < 25.0 or s.bumper_active:
# after (injected fault)
if s.obstacle_cm < 5.0 or s.bumper_active:
```

**Baseline before the change** — `pytest tests/regression -q`:
```
tests\regression\test_regression_suite.py ..........                     [100%]
============================= 10 passed in 1.60s ==============================
```

**Which tests failed and with what error** — `pytest tests/regression tests/unit -q`:
```
_________________________ test_reg_obstacle_emergency _________________________
    assert state.safety_state == SafetyState.EMERGENCY
E   AssertionError: assert <SafetyState....NG: 'WARNING'> == <SafetyState....: 'EMERGENCY'>

_____________ TestSafetyRules.test_obstacle_under_25_is_emergency _____________
    assert state.safety_state == SafetyState.EMERGENCY
E   AssertionError: assert <SafetyState....NG: 'WARNING'> == <SafetyState....: 'EMERGENCY'>

FAILED tests/regression/test_regression_suite.py::test_reg_obstacle_emergency
FAILED tests/unit/test_state_rules.py::TestSafetyRules::test_obstacle_under_25_is_emergency
======================== 2 failed, 89 passed in 1.23s =========================
```

Exactly two tests failed — REG-001 in the regression suite and its unit-test counterpart.
The other 89 continued to pass, so the failure was precisely localised to the changed rule.

**Why they failed** — TODO, your words. Facts to work from: with the threshold at 5 cm, an
obstacle at (for example) 20 cm no longer satisfies `< 5.0`, so control falls through to the
`elif s.obstacle_cm < 50.0` branch on line 72 and the twin reports `WARNING` / `AVOIDING`
instead of `EMERGENCY` / `STOPPED`. The robot would not be commanded to stop for an obstacle
it should have stopped for. Note the alarm threshold literal on line 69 stayed at `25.0`,
so the rule and the alarm it raises would have silently disagreed.

**Confirmation tests pass again after reverting** — `git checkout services/state-engine/rules.py`:
```
tests\unit\test_state_rules.py ....................                      [ 81%]
tests\unit\test_telemetry_schema.py .................                    [100%]
============================= 91 passed in 0.77s ==============================
```
Threshold confirmed restored to `if s.obstacle_cm < 25.0 or s.bumper_active:`.
Working tree clean — the injected fault was not committed.

> Broker-stop variant (`docker stop smartclean-mosquitto`) — not run; Docker would not
> start on this machine. Worth noting either way: the offline suites pass regardless of
> broker state, because the integration tests mock MQTT. Only `tests/system/` touches a
> real broker.

## 3. Scaling Demonstration

**Finding: the scaling demonstration does not currently work, and the existing evidence
shows it failing.**

`submission_5_deployment.ipynb` (commit `6d8be34`) runs the scale command under the heading
*"Scale to 2 instances, show both running, scale back."* The committed cell output is:

```
With 2 ingestion instances:
smartclean-twin-telemetry-ingestion-1  Up 3 minutes

Scaled back to 1.
```

Only **one** instance is listed, and its status is `Up 3 minutes` — i.e. it is the
pre-existing container, untouched. A newly created second replica would have reported an
uptime of a few seconds. The scale-up did not happen.

**Why it did not happen.** In `docker-compose.yml`, `telemetry-ingestion` publishes a fixed
host port:

```yaml
  telemetry-ingestion:
    ports:
      - "8001:8001"
```

A host port can only be bound by one container, so the second replica cannot start —
Docker rejects it with a port-allocation error. Two lines below that same block sits the
comment:

```
    # Scale with: docker compose up --scale telemetry-ingestion=2
    # Uses MQTT subscribe (fan-out) — safe to scale
```

The comment is right about the *application* design — the service is stateless and MQTT
fan-out means replicas do not conflict over message delivery — but the **deployment
configuration contradicts it**. The service cannot be scaled as written.

**Why the failure was invisible.** The notebook cell discards the result of the scale
command:

```python
subprocess.run(["docker", "compose", "up", "--scale", "telemetry-ingestion=2", "-d"],
               capture_output=True, text=True, cwd=".")
```

`capture_output=True` with no inspection of `returncode` or `stderr` means the port-allocation
error was captured and silently thrown away. The cell then prints a heading asserting success
regardless of what actually occurred.

**Recommended fix** — remove the fixed host-port binding so Docker can assign ephemeral ports:

```yaml
    ports:
      - "8001"        # host port assigned dynamically; allows N replicas
```

The service is reached over MQTT, not over HTTP, so the only thing lost is the fixed-port
`/health` endpoint on the host. After that change `--scale telemetry-ingestion=2` should
produce both `-1` and `-2`.

- How many telemetry-ingestion instances are running: **1** (scale-up silently failed)
- Why the *service* is nonetheless safe to scale in principle: TODO, your words — base it on
  the MQTT fan-out and stateless-per-message points above.

> Not verified on my machine (Docker would not start — see note at end). The finding above is
> derived from the committed notebook output and `docker-compose.yml`, both of which are in
> the repository and independently checkable.

## 4. Coverage Assessment

Measured with `pytest tests/unit tests/regression tests/integration --cov=services --cov=shared`:

| Module | Stmts | Miss | Cover |
|---|---|---|---|
| `services/robot-simulator/grid_map.py` | 25 | 0 | **100%** |
| `shared/smartclean_common/topics.py` | 19 | 0 | **100%** |
| `shared/smartclean_common/models.py` | 168 | 1 | **99%** |
| `services/state-engine/rules.py` | 81 | 6 | **93%** |
| `services/robot-simulator/robot_state.py` | 42 | 4 | **90%** |
| `services/ai-service/predictor.py` | 85 | 47 | **45%** |
| `services/robot-simulator/simulator.py` | 239 | 161 | **33%** |
| **TOTAL** | **659** | **219** | **67%** |

### Strongest coverage

Taken literally, `grid_map.py` and `topics.py` at 100%. That figure needs qualifying,
though: `topics.py` is 19 statements of string constants, so 100% on it demonstrates very
little. Weighing test *depth* rather than percentage, the best-tested module is
`rules.py` — despite showing the lowest number of the four:

| Module | Stmts | Cover | Tests behind it |
|---|---|---|---|
| `topics.py` | 19 | 100% | none (constants only) |
| `grid_map.py` | 25 | 100% | 10 unit |
| `models.py` | 168 | 99% | 17 schema tests |
| `rules.py` | 81 | 93% | 20 unit + 10 regression |

`rules.py` encodes all eleven safety and mission rules and is the only module covered at
two layers, including the ten named REG-001…REG-010 cases. Highest coverage percentage and
strongest testing are not the same property here.

TODO — one sentence in your own words on which of those two you'd call "strongest" and why.

### Weakest coverage

`simulator.py` at 33% (161 of 239 statements uncovered). The gaps split into two kinds:

- **Defensibly untested:** `run()` (lines 333-372), `_on_connect` (57-63), `_on_command`
  (66-74) and the `__init__` MQTT setup (43-52). These need a live broker, which is what
  the system layer is for.
- **Not defensible:** `_update_physics()` (lines 126-265) — 140 statements, **zero**
  coverage. It has no network or I/O dependency; it is pure arithmetic over the robot's
  state. Nothing prevented it from being unit tested.

That second gap matters more than the raw percentage suggests, because `_update_physics()`
computes every telemetry value the rest of the system consumes — position, battery drain,
coverage, dirt score, motor current and temperature. The state engine's rules are heavily
tested against *hand-constructed* telemetry, but the code that produces *real* telemetry is
untested. A defect there would propagate into the twin state, the AI predictions, InfluxDB
and Grafana while every existing test stayed green.

Second weakest is `predictor.py` at 45%: lines 42-67 (`load_models`) and 118-166 of
`predict()` are uncovered, meaning only the rule-based fallback path is exercised and the
trained-model path — the one that actually runs in the deployed container — never is.

TODO — one sentence in your own words naming the weakest module and why.

### Test I would add

A deterministic unit test for `_update_physics()`. `SIMULATOR_SEED=42` is fixed in
`docker-compose.yml`, so the physics loop is reproducible without a broker. Concrete
assertions, each mapping to a documented behaviour:

1. **Battery monotonicity** — stepping the physics N times with the motor running, assert
   `battery_soc` strictly decreases and never goes below 0 or above 100.
2. **Coverage gated on the brush** — assert `cleaning_coverage_pct` increases only while
   `brush_on` is true, and is unchanged across a step with the brush off.
3. **Thermal coupling** — assert `motor_temperature_c` rises across consecutive steps while
   `motor_current_a` is held high, since the OVERHEATED rule at 70 °C depends on it.
4. **Grid containment** — assert the robot's `(x_m, y_m)` never leaves the 10×10 accessible
   area after any number of steps, and never enters a border cell.

Test 4 is the highest value of the four: `grid_map.py` proves the *map* marks borders as
obstacles, but nothing currently proves the *simulator* respects them.

TODO — one sentence in your own words on which test you'd add and why.

**Discrepancy against `docs/testing-plan.md`:**

| Claim in testing-plan.md | Measured |
|---|---|
| Coverage target ≥ 70% | 66.77% actual (`pyproject.toml` sets `fail_under = 65`, so CI passes) |
| Unit tests: 69 | 81 |
| System tests: 4 | 14 collected |
| Total "94+" | 102 offline + 14 system |

## 5. Overall Assessment

TODO — 3-4 sentences, your own words. Each bullet below is roughly one sentence; the
supporting facts are all in sections 1-4 above, so you can defend any of these.

- **Give credit where it's due.** The pyramid is genuinely well built at the bottom:
  102 offline tests across four layers, 81 of them unit, all passing, and a regression
  suite that provably catches a real logic change (section 2 demonstrates this).
- **Name the pattern in the weaknesses.** Both defects I found (sections 1 and 3) are in
  the *top* layer — the one meant to prove the system works end to end. The lower layers
  are solid; the layer that validates the whole is largely unexercised, with 3 of 14
  system tests actually running.
- **Say what the real problem is.** In both cases the output *looked* green. A skipped test
  reports as success, and a discarded `stderr` hides a failure. That is more dangerous than
  a visibly failing test, because nobody investigates a passing run.
- **One concrete recommendation.** Pick whichever you find most convincing — e.g. CI should
  fail on skipped system tests rather than reporting them as passes, or subprocess calls in
  the evidence notebooks should assert `returncode == 0` before printing a success heading.

---

## Summary of Findings

| # | Finding | Where | Severity |
|---|---|---|---|
| 1 | `--scale telemetry-ingestion=2` cannot work; fixed host port `8001:8001` blocks the second replica, contradicting the "safe to scale" comment | `docker-compose.yml` | High — rubric item does not work |
| 2 | 11 of 14 system tests are `SKIPPED`, not passed; `INTEGRATION_TEST=1` never set | `submission_5_deployment.ipynb` | High — presented as live evidence |
| 3 | Scale-command failure hidden by `capture_output=True` with no `returncode` check | `submission_5_deployment.ipynb` | Medium — masks defect 1 |
| 4 | `requests` absent from all requirements files; `tests/system` fails at collection on a clean environment | `requirements-dev.txt` | Medium |
| 5 | Coverage is 66.77% against a documented ≥70% target; `fail_under = 65` lets CI pass | `docs/testing-plan.md` vs `pyproject.toml` | Low |
| 6 | Test counts in the testing plan are stale (69 unit / 4 system documented; 81 / 14 actual) | `docs/testing-plan.md` | Low |

---

## Note on Environment Limitation

The Docker-dependent steps (system suite, broker-stop variant, scaling demo) could not be
executed on my machine. The Docker engine fails to start with:

```
Insufficient system resources exist to complete the requested service.
Error code: Wsl/Service/AttachDisk/CreateVm/HCS/0x800705aa
```

This is a host memory limit, not a fault in the project: the machine has 7.4 GB of RAM with
roughly 0.5 GB free, and WSL2 cannot allocate a VM for the Docker engine. Restarting Docker
Desktop and running `wsl --shutdown` did not resolve it. Every result reported above was
produced locally by me; nothing in this report is transcribed from another team member's
screenshots.
