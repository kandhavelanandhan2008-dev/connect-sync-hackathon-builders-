import csv, io, json, os
from flask import Flask, Response, jsonify, request
from config import Config
from db import Db
from engine import Engine, iso
from notify import Notifier
from risk_model import RiskModel


def create_app(cfg=None, predictor=None, clock=None):
    cfg = cfg or Config()
    db = Db(cfg.db_path)
    model = RiskModel(cfg.model_path, cfg.calibration_path, cfg.medium_percentile, cfg.high_percentile, predictor)
    import time
    clock = clock or time.time
    notifier = Notifier(cfg, db, clock)
    eng = Engine(cfg, db, model, notifier, clock)
    app = Flask(__name__)
    app.engine = eng

    @app.after_request
    def cors(r):  # the dashboard runs from a different origin (file:// or another port)
        r.headers["Access-Control-Allow-Origin"] = "*"
        r.headers["Access-Control-Allow-Headers"] = "Content-Type"
        r.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
        return r

    pid = lambda: request.args.get("patient_id") or cfg.default_patient

    def reading_json(r):
        return {"timestamp": iso(r["ts"]), "heart_rate": r["hr"], "spo2": r["spo2"], "temperature": r["temp"],
                "quality": {"hr_valid": bool(r["hr_valid"]), "spo2_valid": bool(r["spo2_valid"]), "temp_valid": bool(r["temp_valid"])}}

    def csv_response(rows, header, name):
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(header)
        w.writerows(rows)
        return Response(buf.getvalue(), mimetype="text/csv", headers={"Content-Disposition": f"attachment; filename={name}"})

    @app.get("/api/health")
    def health():
        return {"ok": True}

    @app.post("/api/telemetry")
    @app.post("/sensor-data")  # same handler, so the ESP32 sketch works unchanged
    def telemetry():
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return {"error": "Send a JSON object"}, 400
        try:
            return eng.ingest(body), 201
        except ValueError as e:
            return {"error": str(e)}, 422

    @app.get("/api/latest")
    def latest():
        r = db.one("SELECT * FROM readings WHERE patient_id=? ORDER BY ts DESC, id DESC LIMIT 1", (pid(),))
        return (reading_json(r), 200) if r else ({"error": "No readings yet"}, 404)

    @app.get("/api/history")
    def history():
        mins = request.args.get("minutes", 60, type=float)
        last = db.one("SELECT MAX(ts) AS t FROM readings WHERE patient_id=?", (pid(),))["t"] or eng.clock()
        rows = db.all("SELECT * FROM readings WHERE patient_id=? AND ts>=? ORDER BY ts LIMIT 2000", (pid(), last - mins * 60))
        return {"readings": [reading_json(r) for r in rows]}

    @app.get("/api/prediction")
    def prediction():
        return eng.prediction(pid())

    def alert_rows():
        return db.all("SELECT * FROM alerts WHERE patient_id=? ORDER BY ts DESC LIMIT 500", (pid(),))

    @app.get("/api/alerts")
    def alerts():
        return {"alerts": [{"id": a["id"], "timestamp": iso(a["ts"]), "type": a["type"], "message": a["message"]} for a in alert_rows()[:50]]}

    @app.get("/api/alerts.csv")
    def alerts_csv():
        return csv_response([[iso(a["ts"]), a["patient_id"], a["type"], a["message"]] for a in alert_rows()],
                            ["timestamp", "patient_id", "type", "message"], f"alerts_{pid()}.csv")

    @app.get("/api/readings.csv")
    def readings_csv():
        rows = db.all("SELECT * FROM readings WHERE patient_id=? ORDER BY ts", (pid(),))
        return csv_response([[iso(r["ts"]), r["patient_id"], r["hr"], r["spo2"], r["temp"], r["hr_valid"], r["spo2_valid"], r["temp_valid"]] for r in rows],
                            ["timestamp", "patient_id", "heart_rate", "spo2", "temperature", "hr_valid", "spo2_valid", "temp_valid"], f"readings_{pid()}.csv")

    @app.get("/api/device-status")
    def device():
        return eng.device(pid())

    @app.get("/api/notifications")
    def notifications():
        rows = db.all("SELECT * FROM notifications ORDER BY ts DESC LIMIT 50")
        return {"notifications": [{"id": n["id"], "timestamp": iso(n["ts"]), "channel": n["channel"], "recipient": n["recipient"],
                                   "status": n["status"], "message": n["message"], "detail": n["detail"]} for n in rows]}

    @app.post("/api/notify/test")
    def notify_test():
        aid = db.run("INSERT INTO alerts(patient_id,ts,type,message) VALUES(?,?,?,?)", (pid(), eng.clock(), "manual", "Manual test notification"))
        notifier.notify(aid, f"SeptiSense test message for {pid()}: a clinician asked to send this notification.")
        return {"queued": True, "channels": cfg.notify_channels}, 202

    @app.get("/api/model-info")
    def model_info():
        with open(cfg.metrics_path, encoding="utf-8") as f:
            m = json.load(f)
        keys = ["model_name", "feature_count", "features", "split_method", "held_out_rows", "held_out_patients",
                "held_out_positive_prevalence", "held_out_ROC_AUC", "held_out_average_precision", "held_out_precision",
                "held_out_recall", "held_out_F1", "confusion_matrix", "rolling_window_note"]
        return {**{k: m[k] for k in keys if k in m}, "threshold_for_precision_recall_f1": 0.5,
                "live_step_seconds": cfg.step_seconds,
                "limitations": "Experimental research/demo model, not clinically validated. Raw scores are not probabilities; "
                               "risk bands use held-out score percentiles. Surface temperature is not core temperature."}

    return app


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), threaded=True)
