"""One-off: turn held_out_test_predictions.csv into model/calibration.json.
The model was trained with class weights, so its raw score is NOT a probability (healthy rows score ~0.3-0.5).
This maps raw score -> observed sepsis rate (isotonic regression) and -> percentile on held-out data.
Usage: python make_calibration.py path/to/held_out_test_predictions.csv"""
import json, sys
import numpy as np, pandas as pd
from sklearn.isotonic import IsotonicRegression

d = pd.read_csv(sys.argv[1])
s, y = d["predicted_probability"].to_numpy(), d["actual_SepsisLabel"].to_numpy()
iso = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1).fit(s, y)
qs = np.linspace(0, 1, 201)
knots = np.quantile(s, qs)
cal = {"score_knots": [round(float(v), 6) for v in knots],
       "percentile_knots": [round(float(v), 4) for v in qs],
       "probability_knots": [round(float(v), 6) for v in iso.predict(knots)],
       "held_out_rows": int(len(d)), "held_out_prevalence": float(y.mean())}
json.dump(cal, open("model/calibration.json", "w"))
print("wrote model/calibration.json; prevalence", round(float(y.mean()), 4))
