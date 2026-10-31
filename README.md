# SeptiSense backend

Flask + SQLite service between the ESP32 node and the dashboard. Research prototype, not a clinical tool.

## Easiest way: one file
`python septisense_server.py`, then open http://localhost:8000. The dashboard is served by the backend, so there is nothing to edit.
For email alerts, edit the EMAIL SETTINGS block at the top of that file (set `SEND_EMAIL = True`, use a Gmail App Password).

## Run it (separate pieces)
```
pip install -r requirements.txt
python check_model.py          # confirms the .cbm loads and scores sensibly (do this first)
python app.py                  # serves http://localhost:8000
python simulate.py --scenario sepsis    # fake ESP32 (in a second terminal)
```
Open `septisense-dashboard.html`, set `USE_MOCK: false` and `BASE_URL` to the laptop's address
(use its LAN IP, not localhost, if the dashboard runs on another device). Tests: `python -m unittest discover -s tests`.

## Data flow
ESP32 `POST /api/telemetry` -> validate and store -> threshold alerts -> average readings into one
"model step" per `STEP_SECONDS` -> 22 features (`features.py`, driven by `feature_list.json`) ->
CatBoost -> calibrated risk + percentile band -> alert and doctor notification on a jump to HIGH.

## ESP32 payload (flexible)
The backend accepts JSON (any of hr/HR/bpm, spo2/SpO2/oxygen, temp/temperature/tempC), nested JSON, a JSON list, form values, a GET request like `/api/telemetry?hr=80&spo2=97&temp=36.9`, or text like `HR:80,SpO2:97,Temp:36.9`. Fahrenheit and -999 no-signal values are handled. See what it actually received at `/api/debug/payloads`.
Standard format:
`{"heart_rate": 82, "spo2": 97, "temperature": 36.9}` (optional: `timestamp`, `patient_id`,
`quality: {hr_valid, spo2_valid, temp_valid}`). If the ESP32 has no clock, leave out `timestamp`.

## Endpoints
`/api/latest`, `/api/history?minutes=60`, `/api/prediction`, `/api/alerts`, `/api/device-status`,
`/api/notifications`, `POST /api/notify/test`, `/api/alerts.csv`, `/api/readings.csv`, `/api/model-info`, `/api/health`.

## Notifications
Default is `NOTIFY_CHANNELS=log` (simulated, shown on the dashboard). For real messages set
`email` (SMTP), `sms` or `whatsapp` (Twilio) plus the variables in `.env.example`. Real sending is not tested.

## Things to know (put these in your write-up)
- **Weak model.** Held-out ROC-AUC 0.69, average precision 0.05 (base rate 0.019), precision 0.035 at threshold 0.5. Expect many false alarms.
- **Scores are not probabilities.** Training used balanced class weights, so healthy rows score about 0.3 to 0.5.
  `make_calibration.py` maps score to the observed held-out rate and to a percentile. Low, medium and high are the
  bottom 75%, next 20% and top 5% of held-out scores.
- **Time step mismatch.** Training rows were hourly. Live data is averaged into `STEP_SECONDS` steps (10 s demo default), so rolling windows cover minutes, not hours. Call this a demo substitution.
- **Temperature.** The MLX90614 reads surface temperature. Use `TEMP_OFFSET_C` and say it is not core temperature.
- **Confirm with the ML teammate:** how training handled a patient's first rows (this code uses pandas `min_periods=1`, std with ddof=1, and waits for `MIN_ROWS=3` steps) and what the 6 hour horizon means.
