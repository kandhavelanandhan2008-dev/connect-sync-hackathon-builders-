# Electronics guide for SeptiSense (give this to the hardware teammate)

## What the ESP32 must do
1. Read heart rate, SpO2 and temperature.
2. Every 2 to 10 seconds, send ONE HTTP request to the laptop:
   `POST http://<LAPTOP-IP>:8000/api/telemetry`, header `Content-Type: application/json`, body:
   ```
   {"patient_id":"P001","heart_rate":82,"spo2":97,"temperature":36.9,
    "quality":{"hr_valid":true,"spo2_valid":true,"temp_valid":true}}
   ```
3. A reply of **201** means it was stored. 400 means the backend could not read the body, 422 means no valid value.

Rules:
- Do not send a timestamp (an ESP32 has no real clock). The backend stamps the arrival time.
- Temperature in degrees Celsius. (Fahrenheit is auto-converted, but avoid it.)
- If a sensor has no signal (finger off), send `-999` for that value and `false` in its quality flag. Never send 0.
- The dashboard shows "Device offline" if nothing arrives for 10 s, so send at least every 10 s.
- The backend also accepts other formats (text like `HR:82,SpO2:97,Temp:36.9`, or a GET link
  `/api/telemetry?hr=82&spo2=97&temp=36.9`), so use whatever is easiest. Check what it received at
  `http://<LAPTOP-IP>:8000/api/debug/payloads`.

## Network setup (most common hackathon failure)
- ESP32 and laptop must be on the SAME network, and the address must be the laptop's IPv4 address
  (`ipconfig` on Windows), never `localhost`.
- **Venue Wi-Fi often blocks devices from talking to each other.** Use a phone hotspot (or the laptop's own
  hotspot) for both the ESP32 and the laptop. Ask the backend person to test first.
- Windows Firewall: when Python first runs, click "Allow access" for private networks.
- Test before using the ESP32: open `http://<LAPTOP-IP>:8000/api/health` in a phone browser on the same network.
  It should show `{"ok": true}`.

## Temperature: important
The MLX90614 measures SKIN surface temperature (typically 33 to 35 C on the forehead or wrist, lower than core).
The model and the alert limits think in core temperature (about 37 C normal, 38.5 C fever). If you send raw skin
temperature, the fever alert will almost never fire and the model sees a "cold" patient.
- Measure a few people with a normal thermometer and compare with the sensor, then agree on an offset
  (for example +2.5 C).
- The backend person sets it in `septisense_server.py` (`TEMP_OFFSET_C = 2.5`). Do not also add it in firmware.
- Say in the write-up: "temperature is surface temperature with a calibration offset, not core temperature".

## SpO2 and heart rate
- Keep the finger still and covered, with steady light pressure. Movement and ambient light cause bad values.
- MAX30102 values are for demonstration, not medical grade.
- If an ECG board is also used later, tell the backend person: ECG-derived heart rate would be preferred when its
  signal is good (planned, not built yet).

## Test checklist
1. Backend running, `/api/health` opens from a phone.
2. ESP32 serial monitor shows `server replied 201`.
3. `/api/debug/payloads` shows the ESP32's messages as "1 stored".
4. Dashboard values move when you warm the temperature sensor or move the finger.
5. Unplug the ESP32: after 10 s the dashboard shows "Device offline".

## Optional extras (only if time)
- Local alert: buzzer or LED when HR is above 120, SpO2 below 92, or temperature above 38.5 (the brief mentions local alerts).
- Offline buffer: store readings while Wi-Fi is down and send them when it returns (the backend accepts a JSON list).
- A "finger detected" LED so the user knows when a measurement is valid.
