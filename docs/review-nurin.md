# Dashboard & Visualization Review — Emelin

**Reviewer:** Nurin Emelin binti Marhisyam 24006706

**Date:** 18 July 2026

**Reviewed:** Grafana dashboard (http://localhost:3001/d/smartclean-main) — 28 panels, 7 sections

## 1. Section Walkthrough

| Section | What it shows | Why the operator needs it |
|---|---|---|
| Robot Status Overview | Displays high-level conditions such as "SAFE RUNNING", AI health state, and immediate AI recommendations. | Provides an immediate, glanceable assessment of the robot's operational safety and mission status without needing to interpret raw data. |
| Battery & Power | Visualizes the Battery State of Charge (%), voltage levels, and the current discharge rate. | Essential for tracking energy consumption and planning charging cycles to prevent the robot from dying mid-mission. |
| Motion & Environment | Plots the robot's X/Y position over time and tracks obstacle distance in centimeters. | Allows operators to monitor the robot's physical movement, ensuring it is not stuck or failing to navigate around mapped objects. |
| Motor & Cleaning | Shows real-time motor current (A), temperature (°C), cleaning coverage progress, and an algorithmic dirt score. | Crucial for verifying that the core cleaning task is progressing efficiently and that mechanical actuators are operating within safe limits. |
| AI Predictions & Forecasts | Outputs algorithmic health predictions (e.g., "NORMAL"), dirt level predictions ("DIRTY"), and estimates the Remaining Useful Life in minutes. | Shifts maintenance from reactive to proactive, allowing the operator to intervene before a hard hardware failure or complete battery depletion occurs. |
| Statistical Trends | Displays rolling windowed averages (e.g., 30s or 1m) for motor current, temperature, and battery SOC. | Useful for engineering analysis to identify slow-building mechanical friction or battery degradation that isn't immediately obvious in real-time telemetry. |
| Alarms & Events | Logs an active alarm count and a timestamped history of events, such as encountering obstacles at specific distances. | Critical for incident response, troubleshooting past operational faults, and maintaining an audit trail of the robot's behavior. |

## 2. Fault Injection Observation

- **Which panels changed:** The Motor Current (A) and Motor Temperature (°C) spiked on the time-series graphs. The Robot Status Overview changed from "SAFE RUNNING" to an error state, and the Active Alarm Count incremented.
- **How long it took for the dashboard to react:** The dashboard updated almost instantaneously (within 1-2 seconds), reflecting the fast data ingestion pipeline and direct InfluxDB querying.
- **What the AI Recommendation banner showed:** The system flagged an actionable alert, recommending a manual inspection of the brush motor for a potential jam.
- **What the Anomaly panels showed:** The Anomaly Score (which usually sits below 0) spiked positively, and the AI Motor Health Prediction shifted from "NORMAL" to a critical warning state.
- **Confirmation everything returned to normal after clearing the fault:** Once the simulated fault was cleared, the real-time telemetry stabilized, the anomaly score dropped back below zero, and the primary status reverted to "SAFE RUNNING".

## 3. Evidence Collection

Confirmed. The required screenshots have been captured, organised into `docs/evidence/`, and the following files were added to the repository:
- `dashboard_normal.png`
- `fault_injection.png`
- `dashboard_clear.png`

## 4. Usability Suggestions

1. **Implement Color-Coded Status Cards:** While the 'Safety State' and 'Mission State' text at the top is clean, the visual hierarchy could be improved by using full-panel background colors (e.g., a soft green card for "SAFE RUNNING", and a distinct red for faults). This bold branding would allow an operator to assess system health instantly from across a room.
2. **Re-prioritize Operational Logs:** The windowed 'Statistical Trends' take up prime vertical space but are highly technical. Moving the 'Alarms & Events' log higher up to replace the statistical trends would prioritize actionable, readable logs over raw engineering metrics, which is much better for a non-technical user.

## 5. Overall Assessment

The dashboard successfully abstracts complex back-end data and algorithmic logic into a highly readable interface. By clearly separating the predictive AI models from the raw sensor telemetry, it prevents cognitive overload for the end-user. The logical flow—starting from a high-level status summary down to specific motor metrics—provides an intuitive and structured troubleshooting path. Overall, it is an excellent piece of software engineering that effectively translates physical hardware conditions into a user-friendly digital twin environment.