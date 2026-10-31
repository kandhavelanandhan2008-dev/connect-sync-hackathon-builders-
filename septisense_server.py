"""SeptiSense in one command: backend + dashboard + email alerts.

    python septisense_server.py

Then open http://localhost:8000 (the dashboard is served from here, so nothing else to set up).
Edit the EMAIL SETTINGS below, save, and restart. Keep your real password out of anything you share.
"""
import os

# ======================= EMAIL SETTINGS (edit these) =======================
SEND_EMAIL = False                      # change to True to send real emails to the doctor
DOCTOR_NAME = "Dr. On-call"
DOCTOR_EMAIL = "doctor@example.com"     # who receives the alerts
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = "your.address@gmail.com"    # the account that sends the alerts
SMTP_PASS = "xxxx xxxx xxxx xxxx"       # Gmail App Password (not your normal password)
# ===========================================================================
# ======================= SENSOR SETTINGS ===================================
TEMP_OFFSET_C = 0.0   # added to every temperature. MLX90614 skin temp is ~2 to 3 C below core: calibrate, then set e.g. 2.5
# ===========================================================================
# Gmail App Password: Google Account > Security > turn on 2-Step Verification >
# App passwords > create one named "SeptiSense" and paste the 16 characters above.

os.environ.setdefault("TEMP_OFFSET_C", str(TEMP_OFFSET_C))

if SEND_EMAIL:
    os.environ.setdefault("NOTIFY_CHANNELS", "log,email")
    os.environ.update(DOCTOR_NAME=DOCTOR_NAME, DOCTOR_EMAIL=DOCTOR_EMAIL, SMTP_HOST=SMTP_HOST,
                      SMTP_PORT=str(SMTP_PORT), SMTP_USER=SMTP_USER, SMTP_PASS=SMTP_PASS)
else:
    os.environ.setdefault("NOTIFY_CHANNELS", "log")

from flask import Response  # noqa: E402  (imports come after the settings on purpose)
from app import create_app  # noqa: E402
from config import HERE  # noqa: E402


def build_app(predictor=None):
    app = create_app(predictor=predictor)

    @app.get("/")
    def dashboard():
        with open(os.path.join(HERE, "septisense_dashboard_risk_score_alert.html"), encoding="utf-8") as f:
            html = f.read()
        # use the live backend on the same address instead of demo data
        html = html.replace("USE_MOCK: true", "USE_MOCK: false").replace('BASE_URL: "http://localhost:8000"', 'BASE_URL: ""')
        return Response(html, mimetype="text/html")

    return app


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    print(f"\nDashboard: http://localhost:{port}   |   email alerts: {'ON -> ' + DOCTOR_EMAIL if SEND_EMAIL else 'off (simulated only)'}\n")
    build_app().run(host="0.0.0.0", port=port, threaded=True)
