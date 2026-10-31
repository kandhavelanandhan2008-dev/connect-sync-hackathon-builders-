"""All settings come from environment variables, so nothing is hard-coded."""
import os
from dataclasses import dataclass, field

HERE = os.path.dirname(os.path.abspath(__file__))
env = os.environ.get


@dataclass
class Config:
    db_path: str = env("DB_PATH", os.path.join(HERE, "septisense.db"))
    model_path: str = env("MODEL_PATH", os.path.join(HERE, "model", "septisense_main_22_feature.cbm"))
    feature_path: str = env("FEATURE_PATH", os.path.join(HERE, "model", "feature_list.json"))
    calibration_path: str = env("CALIBRATION_PATH", os.path.join(HERE, "model", "calibration.json"))
    metrics_path: str = env("METRICS_PATH", os.path.join(HERE, "model", "metrics.json"))
    default_patient: str = env("PATIENT_ID", "P001")

    # The model was trained on one row per hour. The sensor sends a reading every few seconds,
    # so readings are averaged into one "model step" per STEP_SECONDS. 10 s is a demo setting;
    # use 3600 for a real hourly pipeline. Rolling windows (3, 6, 12) count steps.
    step_seconds: float = float(env("STEP_SECONDS", "10"))
    min_rows: int = int(env("MIN_ROWS", "3"))            # steps needed before the first prediction
    horizon_hours: int = int(env("HORIZON_HOURS", "6"))  # confirm with whoever trained the model
    temp_offset_c: float = float(env("TEMP_OFFSET_C", "0"))  # surface (MLX90614) vs core calibration

    offline_after_s: float = float(env("OFFLINE_AFTER_S", "10"))

    # Alert rules (same defaults as the dashboard)
    hr_high: float = float(env("TH_HR_HIGH", "120"))
    spo2_low: float = float(env("TH_SPO2_LOW", "92"))
    temp_high: float = float(env("TH_TEMP_HIGH", "38.5"))

    # ML model risk alert threshold
    risk_alert_threshold: float = float(env("RISK_ALERT_THRESHOLD", "0.77"))

    alert_cooldown_s: float = float(env("ALERT_COOLDOWN_S", "60"))
    risk_alert_cooldown_s: float = float(env("RISK_ALERT_COOLDOWN_S", "300"))

    

    # Risk bands are percentiles of the held-out score distribution (see make_calibration.py)
    medium_percentile: float = float(env("MEDIUM_PERCENTILE", "0.75"))
    high_percentile: float = float(env("HIGH_PERCENTILE", "0.95"))

    # Doctor / nurse notifications. "log" only records a simulated message.
    notify_channels: list = field(default_factory=lambda: [c.strip() for c in env("NOTIFY_CHANNELS", "log").split(",") if c.strip()])
    notify_cooldown_s: float = float(env("NOTIFY_COOLDOWN_S", "300"))
    notify_async: bool = env("NOTIFY_ASYNC", "1") == "1"
    doctor_name: str = env("DOCTOR_NAME", "Dr. On-call")
    doctor_email: str = env("DOCTOR_EMAIL", "")
    doctor_phone: str = env("DOCTOR_PHONE", "")           # E.164, e.g. +919876543210
    smtp_host: str = env("SMTP_HOST", "")
    smtp_port: int = int(env("SMTP_PORT", "587"))
    smtp_user: str = env("SMTP_USER", "")
    smtp_pass: str = env("SMTP_PASS", "")
    twilio_sid: str = env("TWILIO_SID", "")
    twilio_token: str = env("TWILIO_TOKEN", "")
    twilio_from: str = env("TWILIO_FROM", "")             # SMS number
    twilio_whatsapp_from: str = env("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")  # Twilio sandbox
