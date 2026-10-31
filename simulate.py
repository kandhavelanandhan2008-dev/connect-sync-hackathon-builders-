
import argparse
import random
import time
import requests

ap = argparse.ArgumentParser()
ap.add_argument("--url", default="http://localhost:8000")
ap.add_argument("--interval", type=float, default=2.0)
ap.add_argument("--phase-seconds", type=float, default=30.0)
ap.add_argument("--threshold", type=float, default=0.77)
a = ap.parse_args()

print("SeptiSense alternating synthetic-data simulator")
print("Backend:", a.url)
print("Raw-score threshold:", a.threshold)

session_start = time.time()

while True:
    elapsed = time.time() - session_start

    # Alternate between low and high synthetic input phases
    phase_number = int(elapsed // a.phase_seconds)
    high_phase = phase_number % 2 == 1

    if high_phase:
        scenario = "HIGH-INPUT"
        hr = random.randint(110, 125)
        spo2 = random.randint(90, 94)
        temperature = round(random.uniform(38.5, 39.0), 1)
    else:
        scenario = "LOW-INPUT"
        hr = random.randint(75, 85)
        spo2 = random.randint(97, 99)
        temperature = round(random.uniform(36.5, 37.0), 1)

    body = {
        "timestamp": time.time(),
        "heart_rate": hr,
        "spo2": spo2,
        "temperature": temperature
    }

    try:
        response = requests.post(
            a.url + "/api/telemetry",
            json=body,
            timeout=5
        )
        response.raise_for_status()

        # Allow backend time to process the latest reading
        time.sleep(0.5)

        prediction_response = requests.get(
            a.url + "/api/prediction",
            timeout=5
        )
        prediction_response.raise_for_status()

        prediction = prediction_response.json()
        score = prediction.get("risk_score")

        print(
            f"\n{scenario} | "
            f"HR={hr} | SpO2={spo2} | Temp={temperature}"
        )

        if score is None:
            print("Raw score not found in prediction response.")
        else:
            score = float(score)
            alert = score >= a.threshold

            print(f"Raw score: {score:.4f}")
            print(f"Threshold: {a.threshold:.2f}")
            print("Threshold reached:", "YES" if alert else "NO")

    except requests.RequestException as error:
        print("API error:", error)

    time.sleep(a.interval)
