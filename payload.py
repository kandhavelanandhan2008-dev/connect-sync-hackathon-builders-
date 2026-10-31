"""Turns whatever the electronics side sends into the standard reading dict.
Accepts: JSON object, JSON list (batch), nested JSON, form/query values (GET or POST),
plain text like 'HR:80,SpO2:97,Temp:36.9' or 'hr=80 spo2=97 temp=36.9', or just three numbers 'hr,spo2,temp'."""
import json, re

ALIASES = {
    "heart_rate": {"hr", "heartrate", "bpm", "pulse", "heartbeat", "pulserate"},
    "spo2": {"spo2", "o2sat", "o2", "oxygen", "sp02", "spo", "saturation", "oxygensaturation"},
    "temperature": {"temp", "temperature", "tempc", "bodytemp", "objecttemp", "objtemp", "tempobject", "tc", "celsius"},
    "temperature_f": {"tempf", "fahrenheit", "tf"},
    "timestamp": {"timestamp", "time", "ts", "datetime"},
    "patient_id": {"patientid", "patient", "pid", "deviceid", "id"},
}
LOOKUP = {a: k for k, names in ALIASES.items() for a in names}
SENTINELS = {-999, -1, 255}  # common "no signal" values from MAX30102 style sensors


def _key(k):
    return re.sub(r"[^a-z0-9]", "", str(k).lower())


def _flatten(d, out):
    for k, v in d.items():
        if isinstance(v, dict):
            _flatten(v, out)
        else:
            out.setdefault(_key(k), v)
    return out


def _from_text(text):
    pairs = re.findall(r"([A-Za-z_][A-Za-z0-9_ ]*?)\s*[:=]\s*(-?\d+(?:\.\d+)?)", text)
    if pairs:
        return {k.strip(): float(v) for k, v in pairs}
    nums = re.findall(r"-?\d+(?:\.\d+)?", text)
    if len(nums) == 3:  # assumed order: heart rate, SpO2, temperature
        return dict(zip(("hr", "spo2", "temp"), map(float, nums)))
    return {}


def standardize(raw):
    """raw: dict with any key spellings. Returns dict with heart_rate/spo2/temperature/timestamp/patient_id."""
    flat = _flatten(raw, {}) if isinstance(raw, dict) else {}
    out = {}
    for k, v in flat.items():
        std = LOOKUP.get(k)
        if std:
            out.setdefault(std, v)
    f = out.pop("temperature_f", None)
    if f is not None and "temperature" not in out:
        try:
            out["temperature"] = (float(f) - 32) * 5 / 9
        except (TypeError, ValueError):
            pass
    try:  # a body temperature above 45 can only be Fahrenheit
        if 90 <= float(out.get("temperature")) <= 115:
            out["temperature"] = (float(out["temperature"]) - 32) * 5 / 9
    except (TypeError, ValueError):
        pass
    for k in ("heart_rate", "spo2", "temperature"):
        try:
            if float(out.get(k)) in SENTINELS:
                out[k] = None
        except (TypeError, ValueError):
            pass
    return out


def parse_request(req):
    """Returns a list of raw dicts (one per reading) from a Flask request."""
    items = []
    body = req.get_data(as_text=True) or ""
    data = req.get_json(silent=True)
    if data is None and body.strip()[:1] in "{[":
        try:
            data = json.loads(body)
        except ValueError:
            data = None
    if isinstance(data, dict):
        for k in ("readings", "data_points", "batch"):
            if isinstance(data.get(k), list):
                data = data[k]
                break
    if isinstance(data, list):
        items = [d for d in data if isinstance(d, dict)]
    elif isinstance(data, dict):
        items = [data]
    elif req.form:
        items = [req.form.to_dict()]
    elif body.strip():
        t = _from_text(body)
        items = [t] if t else []
    if not items and req.args:
        items = [req.args.to_dict()]
    return items
