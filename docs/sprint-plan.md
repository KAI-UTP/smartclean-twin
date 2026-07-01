# SmartClean Twin — Sprint Plan

**Project:** SmartClean Twin — RBB2013 Digital Twin May 2026  
**Duration:** 2 Sprints (Sprint 1: 1–11 July 2026 | Sprint 2: 12–19 July 2026)  
**Main developer:** Chan Li Kai (22010900)

---

## Product Backlog

| ID | User Story | Priority | Story Points |
|----|-----------|----------|-------------|
| US-01 | As an operator, I want live robot telemetry in Grafana so I can see the robot's status | High | 8 |
| US-02 | As an operator, I want the system to detect obstacle emergencies automatically | High | 5 |
| US-03 | As an operator, I want to send PAUSE/RESUME/STOP commands and get an acknowledgement | High | 8 |
| US-04 | As an operator, I want to see cleaning coverage increase toward 90% | High | 5 |
| US-05 | As an operator, I want battery and motor alerts before failure | Medium | 5 |
| US-06 | As an engineer, I want all data to persist after container restart | High | 3 |
| US-07 | As an engineer, I want AI-predicted motor health displayed in Grafana | Medium | 8 |
| US-08 | As an engineer, I want unit and integration tests for every module | High | 8 |
| US-09 | As an engineer, I want a CI pipeline that runs tests on every push | Medium | 3 |
| US-10 | As an engineer, I want to scale the ingestion service without data loss | Low | 3 |

---

## Sprint 1 (1–11 July 2026): Core Data Flow

### Sprint Goal
End-to-end telemetry flows from Robot Simulator to validated MQTT topic, Digital Twin state is computed, and commands return acknowledgements — all runnable with `docker compose up`.

### Sprint Backlog

| ID | Task | Assigned | Status |
|----|------|---------|--------|
| T-01 | Define shared Pydantic models and MQTT topics | Chan Li Kai | Done |
| T-02 | Write JSON schema contracts (telemetry, command, ack) | Chan Li Kai | Done |
| T-03 | Build grid map and lawnmower path (grid_map.py) | Chan Li Kai | Done |
| T-04 | Build robot physics and telemetry publisher (simulator.py) | Chan Li Kai | Done |
| T-05 | Build simulator command handler and ACK publisher | Chan Li Kai | Done |
| T-06 | Configure Eclipse Mosquitto | Chan Li Kai | Done |
| T-07 | Build Telemetry Ingestion Service (validate + forward + InfluxDB write) | Chan Li Kai | Done |
| T-08 | Build Digital Twin State Engine (rules.py + main.py) | Chan Li Kai | Done |
| T-09 | Build Command API (FastAPI + MQTT publish + ACK wait) | Chan Li Kai | Done |
| T-10 | Write unit tests for schema, rules, grid map, commands | Chan Li Kai | Done |
| T-11 | Write integration tests for ingestion and command API | Chan Li Kai | Done |
| T-12 | Create Dockerfiles for all 5 custom services | Chan Li Kai | Done |
| T-13 | Create docker-compose.yml with all services | Chan Li Kai | Done |
| T-14 | Review MQTT topics and telemetry contract | William Wong | Assigned |
| T-15 | Review state rules and test cases | Irvin Chang | Assigned |

### Acceptance Criteria
- [x] Simulator publishes telemetry every 1 second
- [x] Ingestion validates and rejects invalid messages
- [x] State engine produces all 11 state variables
- [x] OBSTACLE_EMERGENCY alarm generated when obstacle_cm < 25
- [x] PAUSE command returns ACK within 2 seconds
- [x] `docker compose up` starts all services without error
- [x] Unit tests pass locally

### Definition of Done
- Code committed to feature branch
- Feature branch merged to develop at sprint end
- All unit tests pass
- Docker Compose starts successfully

---

## Sprint 2 (12–19 July 2026): AI, Persistence, Visualization, CI/CD

### Sprint Goal
AI predictions flow into Grafana, data persists after InfluxDB restart, CI pipeline runs on push, and the system is ready for final demonstration.

### Sprint Backlog

| ID | Task | Assigned | Status |
|----|------|---------|--------|
| T-16 | Build AI training pipeline (train_model.py) | Chan Li Kai | Done |
| T-17 | Build AI microservice with model loading and MQTT publish | Chan Li Kai | Done |
| T-18 | Configure InfluxDB 2.x auto-init via Docker env vars | Chan Li Kai | Done |
| T-19 | Provision Grafana datasource (influxdb.yaml) | Chan Li Kai | Done |
| T-20 | Build Grafana dashboard JSON with 14 panels | Chan Li Kai | Done |
| T-21 | Write persistence test script | Chan Li Kai | Done |
| T-22 | Write system tests for full flow, obstacle, low battery, motor | Chan Li Kai | Done |
| T-23 | Write regression test suite (10 tests) | Chan Li Kai | Done |
| T-24 | Create GitHub Actions CI workflow | Chan Li Kai | Done |
| T-25 | Write smoke test and demo data scripts | Chan Li Kai | Done |
| T-26 | Write all documentation (architecture, sprint plan, demo script) | Chan Li Kai | Done |
| T-27 | Review Grafana panels and dashboard requirements | Liang Yan Ee | Assigned |
| T-28 | Review command flow and ack latency | Liang Yan Ee | Assigned |
| T-29 | Organize sprint evidence and meeting records | Nurin Emelin | Assigned |
| T-30 | Final demonstration preparation | All | Assigned |

### Acceptance Criteria
- [ ] AI model achieves ≥ 80% accuracy on held-out test set
- [ ] AI predictions visible in Grafana
- [ ] Persistence test passes after InfluxDB restart
- [ ] `docker compose up --scale telemetry-ingestion=2` runs without conflict
- [ ] All 10 regression tests pass
- [ ] CI pipeline runs lint, unit tests, and Docker build on push
- [ ] Complete demonstration executable in under 20 minutes

---

## Sprint Review Template

**Sprint:** ___  
**Review Date:** ___  
**Attendees:** ___

**What was completed:**
- 

**What was not completed:**
- 

**Demo performed:** Yes / No  
**Stakeholder feedback:**
- 

---

## Retrospective Template

**Sprint:** ___  
**Date:** ___

**What went well:**
- 

**What could be improved:**
- 

**Action items for next sprint:**
- 

---

## Milestones

| Milestone | Target Date | Status |
|-----------|------------|--------|
| Sprint 1 feature branches created | 1 July 2026 | Done |
| Sprint 1 code complete | 7 July 2026 | Done |
| Sprint 1 merged to develop | 11 July 2026 | Pending |
| Sprint 2 AI service complete | 14 July 2026 | Done |
| Sprint 2 Grafana complete | 15 July 2026 | Done |
| Sprint 2 CI/CD complete | 16 July 2026 | Done |
| Final demonstration ready | 18 July 2026 | Pending |
| Submission | 19 July 2026 | Pending |
