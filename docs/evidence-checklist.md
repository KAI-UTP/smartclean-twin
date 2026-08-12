# SmartClean Twin — Evidence Checklist

This checklist documents what evidence must be collected for submission.
**Do not fabricate evidence.** Each item must show real screenshots, logs, or outputs.

---

## Specification & Plan (5%)

- [ ] Proposal PDF submitted (SmartClean_Twin_Project_Specification_and_Plan_Proposal.pdf)
- [ ] Architecture block diagram (see architecture.md)
- [ ] Interface contract table (see architecture.md)
- [ ] MQTT topic table (see architecture.md)
- [ ] Digital Twin state table (see architecture.md)
- [ ] Performance targets table (see sprint-plan.md)

---

## Visualization (5%)

- [ ] Screenshot: Grafana dashboard showing all 18 panels
- [ ] Screenshot: Battery SOC gauge with threshold colours
- [ ] Screenshot: Cleaning coverage at 90%+
- [ ] Screenshot: Safety State = EMERGENCY during obstacle injection
- [ ] Screenshot: Motor current spike and HIGH_LOAD state
- [ ] Screenshot: Alarm history table with real alarms
- [ ] Screenshot: AI prediction panels showing motor health and dirt level
- [ ] Screenshot: Grafana provisioning files (datasource + dashboard YAML)
- [ ] Screenshot: 4 aggregation panels (mean motor current 30s, max motor temp 30s, mean battery SoC 1m, alarm count/min)

---

## NVIDIA Omniverse (Bonus)

- [ ] Screenshot: Omniverse 3D scene with office room, coverage grid tiles, and CleaningRobot disc visible
- [ ] Screenshot: Robot body colour = green (SAFE state)
- [ ] Screenshot: Robot body colour = red (EMERGENCY state during obstacle fault injection)
- [ ] Screenshot: Coverage tiles lighting up teal as robot cleans
- [ ] Screenshot: Battery bar shrinking / colour change as battery drains

---

## AI Model (5%)

- [ ] train_model.py output showing accuracy ≥ 80%
- [ ] Classification report (precision, recall, F1 per class)
- [ ] Evidence that model is trained deterministically (seed=42)
- [ ] Screenshot: AI predictions visible in InfluxDB and Grafana
- [ ] Evidence of rule-based fallback when model unavailable

---

## Data, Streaming, Aggregation (5%)

- [ ] `mosquitto_sub` output showing real telemetry messages
- [ ] `mosquitto_sub` output showing validated messages
- [ ] `mosquitto_sub` output showing state messages
- [ ] `mosquitto_sub` output showing ACK messages
- [ ] InfluxDB Data Explorer screenshot showing robot_telemetry measurement
- [ ] InfluxDB screenshot showing robot_state measurement
- [ ] InfluxDB screenshot showing robot_prediction measurement
- [ ] InfluxDB screenshot showing robot_alarm measurement

---

## Development Practices (5%)

- [ ] Git repository with meaningful commit messages
- [ ] Branches: main, develop, feature/simulator, feature/ingestion, feature/state-engine, feature/command-api, feature/ai-service, feature/grafana, feature/testing-ci
- [ ] Pull requests (or merge evidence) for Sprint 1 and Sprint 2
- [ ] Unit test output: all tests pass (screenshot)
- [ ] Integration test output
- [ ] Regression test output: all 10 tests pass
- [ ] CI workflow file (.github/workflows/ci.yml)
- [ ] CI run evidence (screenshot from GitHub Actions)
- [ ] Sprint planning evidence (sprint-plan.md with backlog)
- [ ] Sprint retrospective records (filled templates)

---

## Deployment (5%)

- [ ] `docker compose ps` showing all 9 containers running
- [ ] `docker compose up --build` log excerpt
- [ ] Health endpoint responses from all 6 custom services
- [ ] `docker compose up --scale telemetry-ingestion=2` output
- [ ] persistence_test.py output showing `[PASS]`
- [ ] Evidence of service auto-recovery (stop a container, it restarts)
- [ ] Interface contract table in docs/architecture.md
- [ ] Dockerfile for each of the 6 custom services

---

## Evidence Collection Instructions for Teammates

### William Wong Xiao Kang
1. Review `contracts/telemetry.schema.json` — confirm all fields match the proposal Section 8
2. Review `smartclean_common/topics.py` — confirm topic names match Section 12 of proposal
3. Write a one-paragraph confirmation document: `docs/review-william.md`

### Irvin Chang Hou Ceng
1. Review `services/state-engine/rules.py` — confirm all 11 states and rules match proposal Section 13
2. Review `tests/unit/test_state_rules.py` — confirm test cases are valid
3. Write a one-paragraph confirmation document: `docs/review-irvin.md`

### Liang Yan Ee
1. Review `grafana/dashboards/smartclean_twin.json` — confirm 14 panels cover proposal Section 15
2. Confirm command flow from docs/architecture.md matches proposal Section 17
3. Write a one-paragraph confirmation document: `docs/review-liang.md`

### Nurin Emelin Binti Marhisyam
1. Record attendance at sprint reviews (dates, attendees)
2. Collect screenshot evidence for all checklist items above
3. Organize evidence into a submission folder: `evidence/sprint1/`, `evidence/sprint2/`
4. Record final demonstration attendance
