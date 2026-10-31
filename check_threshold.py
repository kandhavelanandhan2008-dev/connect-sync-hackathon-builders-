
from config import Config
from risk_model import RiskModel

c = Config()

model = RiskModel(
    c.model_path,
    c.calibration_path,
    c.medium_percentile,
    c.high_percentile
)

threshold = c.risk_alert_threshold

print("\n===== SEPTISENSE RAW SCORE THRESHOLD CHECK =====")
print(f"Configured raw score threshold: {threshold:.2f}")

print("\nTesting model interpretation:\n")

for score in [i / 100 for i in range(0, 101, 5)]:
    prob, pct, level = model.interpret(score)

    alert = score >= threshold

    print(
        f"Raw Score: {score:.2f} | "
        f"Probability: {prob:.4f} | "
        f"Percentile: {pct:.2%} | "
        f"Level: {level.upper()} | "
        f"Alert: {'YES' if alert else 'NO'}"
    )

print("\n===== EXACT RAW SCORE THRESHOLD TEST =====")

for score in [0.75, 0.76, 0.77, 0.78, 0.80]:
    alert = score >= threshold

    print(
        f"Raw Score: {score:.2f} | "
        f"Threshold: {threshold:.2f} | "
        f"Alert: {'YES' if alert else 'NO'}"
    )

print("\n===== TEST COMPLETE =====")
