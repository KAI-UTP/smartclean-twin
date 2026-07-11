# Team Task Assignments — Final Week (Due: 19 July 2026)

Development of all modules is complete. The remaining work is **review,
verification, documentation and presentation** — and it matters for marks:
the rubric awards *Development Practices (5%)* partly on "deliverables from
every team member and consistent version control", and *Peer Review* is a
separate **10%** (double any technical component).

**IMPORTANT — every task below must be committed and pushed from YOUR OWN
GitHub account.** That is what puts your name in the project history.

---

## How to commit your work (one-time setup)

1. Install Git and clone the repo:
   ```
   git clone https://github.com/KAI-UTP/smartclean-twin.git
   cd smartclean-twin
   ```
2. Create your file (see your task below), then:
   ```
   git add docs/<your-file>.md
   git commit -m "docs: add review by <your name>"
   git push origin main
   ```
3. If push is rejected, run `git pull --rebase origin main` then push again.

Ask Li Kai for collaborator access to the repository first.

---

## Task 1 — William: Review of Architecture & Data Flow

**File:** `docs/review-william.md`

Read `docs/architecture.md` and `docs/api-contract.md`, then run the system
(`docker compose up -d`) and write a 1–2 page review covering:

- Trace one telemetry message through the full pipeline
  (simulator → MQTT → validation → InfluxDB → Grafana) and confirm each hop
  matches the api-contract.md description. Note anything unclear or wrong.
- Comment on the microservice split: is each service single-purpose?
  Would you have split it differently?
- Verify 3 MQTT topic names in the contract against the actual code in
  `shared/smartclean_common/topics.py`.
- At least 2 improvement suggestions (be specific).

## Task 2 — Irvin: Review of AI Models & Predictions

**File:** `docs/review-irvin.md`

Read `services/ai-service/train_model.py` and `predictor.py`, then write a
1–2 page review covering:

- Explain in your own words what each of the 5 models does and what its
  inputs are (this proves you understand it — examiners may ask ANY member).
- Run the what-if endpoint with 3 scenarios of your choice and paste the
  results with your interpretation:
  ```powershell
  $body = @{motor_temperature_c=90; motor_current_a=3.5} | ConvertTo-Json
  Invoke-RestMethod -Method Post -Uri http://localhost:8003/whatif -ContentType "application/json" -Body $body
  ```
- Comment on the labelling rules: are the thresholds reasonable for a
  cleaning robot? Anything you would change?
- At least 2 improvement suggestions.

## Task 3 — Liang: Testing Verification & Evidence

**File:** `docs/review-liang.md`

Run the entire test suite yourself and document the results:

- `py -m pytest tests/unit -v` — paste summary (should be 81 passed)
- `py -m pytest tests/integration -v` and `tests/system -v` (needs
  `docker compose up -d` running)
- Deliberately break one thing (e.g. stop the mosquitto container) and
  document which tests fail and why — the rubric explicitly asks for
  demonstrated **pass AND fail cases**. Restart it after.
- Run the scaling demo and screenshot it:
  ```
  docker compose up --scale telemetry-ingestion=2 -d
  docker compose ps
  ```
- Comment on test coverage: which module has the weakest coverage?

## Task 4 — Nurin: Dashboard & Demo Documentation

**File:** `docs/review-nurin.md`

Open Grafana (http://localhost:3001/d/smartclean-main, admin/admin) and:

- Walk through all 7 dashboard sections; for each, write 1–2 sentences on
  what it shows and why an operator needs it.
- Trigger a fault and document what changes on the dashboard
  (which panels react, how long it takes):
  ```powershell
  Invoke-RestMethod -Method Post -Uri http://localhost:8004/fault -ContentType "application/json" -Body '{"fault":"motor"}'
  # wait 30s, screenshot, then clear:
  Invoke-RestMethod -Method Post -Uri http://localhost:8004/fault -ContentType "application/json" -Body '{"fault":"clear"}'
  ```
- Collect and organise the evidence screenshots listed in
  `docs/evidence-checklist.md` into a `docs/evidence/` folder.
- At least 2 usability suggestions for the dashboard.

## Everyone — Presentation Prep

- Read `docs/demo-script.md`. Each member presents at least one section.
- Each member must be able to answer: "explain the architecture",
  "what does the AI predict", "how is data stored", "how do you test it".
- Rehearse the demo at least once together before 18 July.

## Deadlines

| Item | Deadline |
|---|---|
| Review docs committed & pushed | **16 July** |
| Evidence screenshots collected | 17 July |
| Full demo rehearsal | 18 July |
| Submission | 19 July |
