import json
import numpy as np


class RiskModel:
    """Wraps the CatBoost model plus the calibration table built from the held-out predictions.
    predictor: optional callable(list_of_22_floats) -> raw score, used by tests."""

    def __init__(self, model_path, calibration_path, medium_pct, high_pct, predictor=None):
        with open(calibration_path, encoding="utf-8") as f:
            self.cal = json.load(f)
        self.medium_pct, self.high_pct = medium_pct, high_pct
        if predictor is not None:
            self._predict = predictor
        else:
            from catboost import CatBoostClassifier  # imported here so tests do not need it
            m = CatBoostClassifier()
            m.load_model(model_path)
            self._predict = lambda vec: float(m.predict_proba(np.array([vec], dtype=float))[0, 1])

    def score(self, vec):
        return float(self._predict(vec))

    def interpret(self, score):
        c = self.cal
        prob = float(np.interp(score, c["score_knots"], c["probability_knots"]))
        pct = float(np.interp(score, c["score_knots"], c["percentile_knots"]))
        level = "high" if pct >= self.high_pct else "medium" if pct >= self.medium_pct else "low"
        return prob, pct, level
