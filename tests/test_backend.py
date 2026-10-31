import os, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np, pandas as pd
import features as F
from config import Config
from app import create_app


class Clock:
    t = 1_800_000_000.0
    def __call__(self): return self.t


def make(predictor=lambda v: 0.4, **kw):
    cfg = Config(db_path=os.path.join(tempfile.mkdtemp(), "t.db"), notify_async=False, step_seconds=10, **kw)
    clock = Clock()
    app = create_app(cfg, predictor=predictor, clock=clock)
    return app, app.test_client(), clock, cfg


def post(c, clock, hr=80, spo2=97, temp=37.0, **extra):
    return c.post("/api/telemetry", json={"timestamp": clock.t, "heart_rate": hr, "spo2": spo2, "temperature": temp, **extra})


class FeatureTests(unittest.TestCase):
    def test_matches_pandas(self):
        names = F.load_feature_names(Config().feature_path)
        rng = np.random.default_rng(1)
        df = pd.DataFrame({"hr": rng.normal(85, 8, 20), "spo2": rng.normal(96, 2, 20), "temp": rng.normal(37, .4, 20)})
        rows = df.to_dict("records")
        for n in (5, 12, 20):  # includes warm-up lengths
            got = dict(zip(names, F.build_vector(names, rows[:n])))
            d = df.iloc[:n]
            exp = {"HR": d.hr.iloc[-1], "O2Sat": d.spo2.iloc[-1], "Temp": d.temp.iloc[-1],
                   "HR_change": d.hr.diff().iloc[-1], "O2Sat_change": d.spo2.diff().iloc[-1]}
            for sig, col in (("HR", "hr"), ("O2Sat", "spo2"), ("Temp", "temp")):
                for w in (3, 6, 12):
                    r = d[col].rolling(w, min_periods=1)
                    exp[f"{sig}_mean_{w}"], exp[f"{sig}_std_{w}"], exp[f"{sig}_min_{w}"] = r.mean().iloc[-1], r.std().iloc[-1], r.min().iloc[-1]
            for k, v in got.items():
                self.assertTrue(np.isclose(v, exp[k], equal_nan=True), (n, k, v, exp[k]))
        self.assertEqual(len(names), 22)


class ApiTests(unittest.TestCase):
    def feed(self, c, clock, n, **kw):
        for _ in range(n):
            self.assertEqual(post(c, clock, **kw).status_code, 201)
            clock.t += 4

    def test_warmup_then_prediction(self):
        app, c, clock, cfg = make()
        self.assertEqual(c.get("/api/latest").status_code, 404)
        self.feed(c, clock, 3)
        self.assertEqual(c.get("/api/prediction").get_json()["status"], "warming_up")
        self.feed(c, clock, 30)
        p = c.get("/api/prediction").get_json()
        self.assertEqual(p["status"], "ok")
        self.assertEqual(p["feature_count"], 22)
        self.assertIn(p["risk_level"], ("low", "medium", "high"))
        self.assertTrue(0 <= p["risk_probability"] <= 1)
        self.assertGreater(len(c.get("/api/history?minutes=60").get_json()["readings"]), 20)

    def test_levels_and_high_alert_notifies_once(self):
        scores = iter([0.4] * 3 + [0.8] * 50)
        app, c, clock, cfg = make(predictor=lambda v: next(scores))
        self.feed(c, clock, 40)
        self.assertEqual(c.get("/api/prediction").get_json()["risk_level"], "high")
        al = c.get("/api/alerts").get_json()["alerts"]
        self.assertEqual([a["type"] for a in al].count("high_risk"), 1)
        n = c.get("/api/notifications").get_json()["notifications"]
        self.assertEqual(len(n), 1)
        self.assertEqual(n[0]["status"], "simulated")

    def test_threshold_alert_cooldown_and_csv(self):
        app, c, clock, cfg = make()
        self.feed(c, clock, 5, hr=150)
        al = c.get("/api/alerts").get_json()["alerts"]
        self.assertEqual(len(al), 1)  # 60 s cooldown: only the first of 5 readings
        self.assertIn("Heart rate 150", al[0]["message"])
        csv_text = c.get("/api/alerts.csv").get_data(as_text=True)
        self.assertTrue(csv_text.startswith("timestamp,patient_id,type,message"))
        self.assertIn("threshold", csv_text)
        self.assertIn("heart_rate", c.get("/api/readings.csv").get_data(as_text=True))

    def test_flexible_payload_formats(self):
        app, c, clock, cfg = make()
        ok = lambda r: self.assertIn(r.status_code, (200, 201), r.get_data(as_text=True))
        ok(c.post("/api/telemetry", json={"HR": 80, "SpO2": 97, "Temp": 36.9}))
        ok(c.post("/api/telemetry", json={"data": {"bpm": 81, "oxygen": 96, "tempC": 37.1}}))
        ok(c.post("/api/telemetry", data="HR:82,SpO2:98,Temp:37.0"))
        ok(c.post("/api/telemetry", data="hr=83 spo2=97 temp=37.2"))
        ok(c.post("/api/telemetry", data="84,96,37.3", content_type="text/plain"))
        ok(c.get("/api/telemetry?hr=85&spo2=97&temp=37.4"))
        ok(c.post("/api/telemetry", data={"heart_rate": 86, "spo2": 97, "temperature": 98.6}))  # Fahrenheit
        r = c.post("/api/telemetry", json=[{"hr": 70, "spo2": 98, "temp": 36.5}, {"hr": 71, "spo2": 98, "temp": 36.6}])
        self.assertEqual(r.get_json()["stored"], 2)
        ok(c.post("/api/telemetry", json={"hr": -999, "spo2": 97, "temp": 36.8}))  # no-signal sentinel
        self.assertFalse(c.get("/api/latest").get_json()["quality"]["hr_valid"])
        self.assertEqual(c.post("/api/telemetry", data="hello").status_code, 400)
        self.assertEqual(len(c.get("/api/history?minutes=60").get_json()["readings"]), 10)
        self.assertIn("unreadable", c.get("/api/debug/payloads").get_data(as_text=True))
        temps = [r["temperature"] for r in c.get("/api/history").get_json()["readings"]]
        self.assertAlmostEqual(temps[6], 37.0, places=1)  # 98.6 F converted

    def test_validation_and_quality(self):
        app, c, clock, cfg = make()
        self.assertEqual(c.post("/api/telemetry", data="x").status_code, 400)  # unreadable
        self.assertEqual(c.post("/api/telemetry", json={"heart_rate": "abc"}).status_code, 422)
        post(c, clock, hr=400)  # impossible HR is stored but flagged invalid, no alert
        r = c.get("/api/latest").get_json()
        self.assertFalse(r["quality"]["hr_valid"])
        self.assertTrue(r["quality"]["spo2_valid"])
        self.assertEqual(c.get("/api/alerts").get_json()["alerts"], [])

    def test_device_status(self):
        app, c, clock, cfg = make()
        self.assertFalse(c.get("/api/device-status").get_json()["online"])
        post(c, clock)
        self.assertTrue(c.get("/api/device-status").get_json()["online"])
        clock.t += 30
        self.assertFalse(c.get("/api/device-status").get_json()["online"])

    def test_restart_restores_rows_and_manual_notify_and_info(self):
        app, c, clock, cfg = make()
        self.feed(c, clock, 40)
        app2 = create_app(cfg, predictor=lambda v: 0.4, clock=clock)
        self.assertEqual(len(app2.engine._rows("P001")), 12)
        self.assertEqual(app2.test_client().post("/api/notify/test").status_code, 202)
        self.assertEqual(len(c.get("/api/notifications").get_json()["notifications"]), 1)
        info = c.get("/api/model-info").get_json()
        self.assertAlmostEqual(info["held_out_ROC_AUC"], 0.692, places=3)
        self.assertEqual(c.options("/api/telemetry").headers["Access-Control-Allow-Origin"], "*")


if __name__ == "__main__":
    unittest.main()
