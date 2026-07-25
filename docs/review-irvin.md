# AI Models Review — Irvin Chang

**Reviewer:** IRVIN CHANG HOU CENG (22012342)
**Date:** 25 JULY 2026
**Files reviewed:** `services/ai-service/train_model.py`, `services/ai-service/predictor.py`

## 1. Model Descriptions 

| # | Model | Type | What it predicts |
|---|---|---|---|
| 1 | motor_health_clf | Supervised classification | Predicts whether the motor condition is NORMAL, HIGH_LOAD, OVERHEATED, or FAULT |
| 2 | dirt_level_clf | Supervised classification | Predicts whether the detected floor condition is CLEAN, MODERATE, or DIRTY |
| 3 | health_state_clf | Supervised classification | Predicts the overall robot health state as NORMAL, WARNING, or CRITICAL |
| 4 | rul_regressor | Supervised regression | Estimates the robot’s remaining operating life in minutes |
| 5 | anomaly_detector | Unsupervised (statistical) | Determines whether current sensor readings are significantly different from normal operation |

1. motor_health_clf

The motor health classifier predicts whether the robot motor is operating normally, under high load, overheated, or experiencing a fault. It uses motor current, motor temperature, robot speed, brush status, pump status, and battery current as its input features. It is a supervised Random Forest classification model because it is trained using synthetic sensor data with predetermined motor-health labels.

2. dirt_level_clf

The dirt level classifier predicts whether the floor condition is clean, moderately dirty, or dirty. It uses only the robot’s dirt_score, which ranges from 0 to 1, where a higher value represents a dirtier surface. It is a supervised Random Forest classification model trained using dirt scores with predefined dirt-level categories.

3. health_state_clf

The health state classifier predicts the overall condition of the robot as normal, warning, or critical. It uses nine derived features: motor temperature, estimated vibration, estimated rotational speed, electrical power, motor load percentage, motor current, estimated acoustic noise, estimated asset age, and a maintenance score based on the water level. It is a supervised Random Forest classification model trained using health labels generated from a calculated risk score.

4. rul_regressor

The remaining useful life regressor estimates how many minutes the robot can continue operating before maintenance, battery depletion, or component condition significantly limits its operation. It uses the same nine features as the health state classifier, including temperature, load, estimated vibration, battery-related values, asset age, and maintenance condition. It is a supervised Random Forest regression model because it produces a continuous numerical result rather than a category.

5. anomaly_detector

The anomaly detector identifies sensor readings that are unusually different from normal robot behaviour. It analyses motor current, motor temperature, robot speed, battery voltage, and battery current, and compares them with the learned mean and standard deviation of healthy operation. It is an unsupervised statistical model because it is trained only on normal-operation data and does not require labelled fault examples; a reading is classified as anomalous when any sensor differs from the normal mean by more than 4.5 standard deviations.

## 2. What-If Scenario Tests

The required screenshots have been captured, organised into `docs/evidence/`

**Scenario 1 — healthy robot:**

`Scenario1_Healthy_Robot.png`

The selected inputs were a motor current of 0.8 A, motor temperature of 40°C, robot speed of 0.2 m/s, battery state of charge of 90%, and water level of 80%. The brush was switched on, the pump was switched off, and the dirt score was 0.3.

The model predicted the motor condition as **NORMAL** with a confidence of **0.99**. The dirt level was predicted as **MODERATE** with a confidence of **0.72**, while the overall health state was predicted as **NORMAL** with a confidence of **0.9046**. The estimated remaining useful life was **108.8 minutes**. The anomaly detector returned a positive anomaly score of **3.8998**, so no anomaly was detected. The system recommendation was **“Normal operation — no action needed.”**

This result makes sense because the motor temperature and current are within the normal operating range, while the battery has a high state of charge. The moderate dirt prediction is also reasonable because the dirt score was exactly 0.3, which is the lower threshold for the MODERATE category. Overall, the robot appears healthy and capable of continuing operation for a relatively long period.

**Scenario 2 — Overheating motor**

`Scenario2_Overheating_Motor.png`

The selected inputs were a motor current of 3.6 A, motor temperature of 90°C, robot speed of 0.2 m/s, battery state of charge of 40%, and water level of 80%. The brush was switched on, the pump was switched off, and the dirt score remained at 0.3.

The model predicted the motor condition as **FAULT** with a confidence of **0.97**. The dirt level was predicted as **MODERATE** with a confidence of **0.72**. The overall health state was predicted as **WARNING** with a confidence of **0.555**, while the estimated remaining useful life decreased to **30.3 minutes**. The anomaly score was **-11.431**, so the system classified the readings as anomalous. The recommendation was **“Sensor anomaly detected — verify sensors and inspect robot.”**

This result is reasonable because both the motor temperature and motor current are far above normal operating values. In the labelling rules, a temperature above 70°C together with a current above 3.5 A is classified as a motor fault. The negative anomaly score also makes sense because these readings are very different from the learned pattern of normal robot operation. The much lower remaining useful life indicates that the severe motor condition could significantly reduce the robot’s safe operating time.

**Scenario 3 — Low battery and low water**

`Scenario3_LowBattery_LowWater.png`

The selected inputs were a battery state of charge of 15% and a water level of 5%. The other values used the default settings: motor current of 0.8 A, motor temperature of 40°C, robot speed of 0.2 m/s, battery current of 1.4 A, battery voltage of 11.5 V, brush on, pump off, and dirt score of 0.3.

The model predicted the motor condition as **NORMAL** with a confidence of **0.99**. The dirt level was predicted as **MODERATE** with a confidence of **0.72**. However, the overall health state was predicted as **WARNING** with a confidence of **0.5671**. The estimated remaining useful life was only **14.7 minutes**. The anomaly score was **3.8998**, so no anomaly was detected. The system recommendation was **“Schedule maintenance soon — monitor temperature and load.”**

This result is reasonable because the motor readings are still within a normal range, so the motor-health prediction remains NORMAL. However, the very low battery level and low water level reduce the robot’s expected operating time and worsen the overall health state. The low remaining useful life of 14.7 minutes is consistent with a robot that may soon need charging and servicing. The absence of an anomaly also makes sense because the anomaly detector mainly checks motor current, motor temperature, speed, battery voltage, and battery current rather than battery state of charge or water level.

## 3. Labelling Rules Assessment

The labelling rules are reasonable for a prototype because they use clear thresholds to separate normal operation, high load, overheating, and fault conditions. For example, the motor is labelled **OVERHEATED** when its temperature exceeds 70°C, while it is labelled **FAULT** when the temperature is above 70°C and the motor current is also above 3.5 A. The model also classifies the motor as **HIGH_LOAD** when the current is above 2.5 A, or above 1.5 A while the brush is running.

However, these thresholds should be validated using the actual motor specifications because different small cleaning robots may have different safe temperature and current limits. I would keep the same general structure but add an earlier warning range, such as a warning before the motor reaches the overheating threshold. I would also add hysteresis so that small sensor fluctuations near a threshold do not cause the predicted label to switch repeatedly between two states.

The dirt-level rules are simple and understandable, but they should be calibrated using real dirt sensor readings from different floor surfaces. The overall health-state thresholds are also reasonable for a prototype, although the risk-score weights and limits were created using synthetic data and should be tested on the physical robot before being used for important decisions.

## 4. Improvement Suggestions

1. Train and test the models using real robot telemetry. The current models are mainly trained using synthetically generated sensor values and labels. Real recorded data would include sensor noise, changing floor conditions, battery degradation, motor wear, and environmental effects, so the models would be more representative of actual robot operation.

2. Use confidence thresholds before acting on a prediction. The classifiers already return confidence values, but the system does not use a minimum confidence requirement before producing a recommendation. For example, Scenario 2 predicted the overall health state as WARNING with a confidence of only 0.555, so the system could mark this result as uncertain or request additional sensor readings before making an automatic decision.

3. Add continuous model monitoring. The system should store predictions, confidence values, anomaly scores, and confirmed maintenance outcomes over time. This would help detect sensor drift, changes in robot behaviour, and situations where the model performance begins to decrease.

4. Validate the thresholds and risk-score weights experimentally. Limits such as 70°C for overheating and 3.5 A for a fault should be compared with the actual motor datasheet and controlled hardware tests. The health-state risk formula should also be adjusted using real operating results so that serious motor faults are more consistently classified as critical conditions.

## 5. Overall Assessment

The AI layer is a strong prototype because it combines motor-health classification, dirt-level classification, overall health assessment, remaining useful life estimation, and anomaly detection in one service. It also provides confidence scores, recommendations, and a rule-based fallback, which makes the system easier to interpret and more reliable when trained model files are unavailable. However, the models are trained mainly on synthetic data, so their reported performance may not fully represent real robot behaviour. The AI layer should therefore be validated and recalibrated using physical robot telemetry before its predictions are used for automatic or safety-critical decisions.