"""Run this once on your laptop: confirms the .cbm loads, takes 22 features, and returns sensible scores."""
import json
from catboost import CatBoostClassifier
import features as F
from config import Config

c = Config()
m = CatBoostClassifier()
m.load_model(c.model_path)
names = F.load_feature_names(c.feature_path)
print("Model feature count:", m.feature_names_ and len(m.feature_names_), "| JSON feature count:", len(names))
if m.feature_names_ and list(m.feature_names_) != names and not all(str(n).isdigit() for n in m.feature_names_):
    print("WARNING: feature order in the model differs from feature_list.json")
healthy = [{"hr": 72 + i % 3, "spo2": 98, "temp": 36.8} for i in range(12)]
sick = [{"hr": 95 + 3 * i, "spo2": 96 - i * .5, "temp": 37.5 + .15 * i} for i in range(12)]
for label, rows in (("healthy-looking", healthy), ("deteriorating", sick)):
    print(label, "raw score:", round(float(m.predict_proba([F.build_vector(names, rows)])[0, 1]), 3))
print("Both scores should be between 0 and 1 and the deteriorating one is usually higher. Training scores were never clinically validated.")
