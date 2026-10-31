SEPTISENSE 22-FEATURE MODEL

Main model: septisense_main_22_feature.cbm
Features: feature_list.json
Evaluation metrics: metrics.json
Training settings: model_config.json
Held-out predictions: held_out_test_predictions.csv
Feature importance: feature_importance.csv

Metrics are calculated on a patient-level held-out split.
Precision, recall, F1 and confusion matrix use probability threshold 0.5.
Average precision is reported separately from ROC-AUC.

Integration requirements:
Supply the 22 numeric features in the exact order in feature_list.json.
Keep feature units and preprocessing consistent with training.

Limitations:
This is an experimental research/demo model, not a clinically validated
sepsis diagnostic tool. The source training data and physical sensor data
may differ in measurement method and units. MLX90614 surface temperature
should not automatically be treated as core body temperature.
Rolling windows use recorded rows, not guaranteed elapsed hours if data
has gaps. A live system needs prior readings for rolling features.
