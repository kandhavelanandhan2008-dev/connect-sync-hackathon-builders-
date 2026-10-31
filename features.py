"""Builds the model's input vector from recent model steps.
Feature names come from feature_list.json, so changing the list needs no code change.
Rules match pandas: diff(), rolling(w, min_periods=1).mean()/std(ddof=1)/min()."""
import json, re
import numpy as np

PATTERN = re.compile(r"^(HR|O2Sat|Temp)(?:_(change)|_(mean|std|min)_(\d+))?$")
COLUMN = {"HR": "hr", "O2Sat": "spo2", "Temp": "temp"}


def load_feature_names(path):
    with open(path, encoding="utf-8") as f:
        names = json.load(f)["features"]
    for n in names:
        if not PATTERN.match(n):
            raise ValueError("Unsupported feature name: " + n)
    return names


def max_window(names):
    return max([2] + [int(PATTERN.match(n).group(4)) for n in names if PATTERN.match(n).group(4)])


def build_vector(names, rows):
    """rows: oldest to newest, each {'hr','spo2','temp'} (None = missing). Returns list of floats (nan = missing)."""
    out = []
    for n in names:
        sig, chg, stat, win = PATTERN.match(n).groups()
        col = COLUMN[sig]
        series = np.array([np.nan if r[col] is None else float(r[col]) for r in rows])
        if chg:
            v = series[-1] - series[-2] if len(series) >= 2 else np.nan
        elif not stat:
            v = series[-1] if len(series) else np.nan
        else:
            w = series[-int(win):]
            w = w[~np.isnan(w)]
            if not len(w):
                v = np.nan
            elif stat == "mean":
                v = w.mean()
            elif stat == "min":
                v = w.min()
            else:
                v = w.std(ddof=1) if len(w) > 1 else np.nan
        out.append(float(v))
    return out
