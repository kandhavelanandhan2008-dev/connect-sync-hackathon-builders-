
"""Ingest pipeline: validate -> store -> threshold alerts
-> average into model steps -> features -> model -> risk alert.
"""

import time
from datetime import datetime, timezone

import features as F

RANGES = {
    "hr": (20, 250),
    "spo2": (50, 100),
    "temp": (30, 43)
}


def iso(ts):
    return (
        datetime.fromtimestamp(ts, timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def parse_ts(v, fallback):
    """Handle ESP32 timestamps, falling back to server time."""
    try:
        if isinstance(v, (int, float)):
            return (
                v / 1000 if v > 1e12
                else v if v > 1e9
                else fallback
            )

        if isinstance(v, str) and v:
            return datetime.fromisoformat(
                v.replace("Z", "+00:00")
            ).timestamp()

    except ValueError:
        pass

    return fallback


def num(v):
    try:
        x = float(v)
        return x if x == x else None
    except (TypeError, ValueError):
        return None


class Engine:

    def __init__(self, cfg, db, model, notifier, clock=time.time):
        self.cfg = cfg
        self.db = db
        self.model = model
        self.notifier = notifier
        self.clock = clock

        self.names = F.load_feature_names(cfg.feature_path)
        self.keep = F.max_window(self.names)

        self.rows = {}
        self.bucket = {}
        self.cool = {}
        self.level = {}
        self.last_seen = {}

        # Tracks whether each patient's risk threshold is active.
        self.risk_alert_active = set()

    # ---- state ----

    def _rows(self, pid):
        if pid not in self.rows:
            got = self.db.all(
                """
                SELECT hr, spo2, temp
                FROM steps
                WHERE patient_id=?
                ORDER BY ts DESC
                LIMIT ?
                """,
                (pid, self.keep)
            )

            self.rows[pid] = list(reversed(got))

        return self.rows[pid]

    def _cooled(self, key, seconds):
        now = self.clock()

        if now - self.cool.get(key, -1e18) < seconds:
            return False

        self.cool[key] = now
        return True

    # ---- ingest ----

    def ingest(self, p):
        c = self.cfg
        now = self.clock()

        pid = str(p.get("patient_id") or c.default_patient)
        ts = parse_ts(p.get("timestamp"), now)

        q = p.get("quality") or {}

        def first(*keys):
            for k in keys:
                if p.get(k) is not None:
                    return p[k]
            return None

        vals = {
            "hr": num(first("heart_rate", "hr", "bpm")),
            "spo2": num(first("spo2", "SpO2")),
            "temp": num(
                first(
                    "temperature",
                    "temp",
                    "temperature_filtered",
                    "temperature_raw"
                )
            )
        }

        q = dict(q)

        for k, field in (
            ("hr", "heart_rate_quality"),
            ("spo2", "spo2_quality"),
            ("temp", "temperature_quality")
        ):
            if str(p.get(field, "")).upper() == "INVALID":
                q[k + "_valid"] = False

        if vals["temp"] is not None:
            vals["temp"] += c.temp_offset_c

        ok = {}

        for k, (lo, hi) in RANGES.items():
            ok[k] = (
                vals[k] is not None
                and lo <= vals[k] <= hi
                and q.get(k + "_valid", True) is not False
            )

        if not any(ok.values()):
            raise ValueError("No valid measurement in payload")

        self.db.run(
            """
            INSERT INTO readings(
                patient_id, ts, hr, spo2, temp,
                hr_valid, spo2_valid, temp_valid
            )
            VALUES(?,?,?,?,?,?,?,?)
            """,
            (
                pid, ts,
                vals["hr"], vals["spo2"], vals["temp"],
                ok["hr"], ok["spo2"], ok["temp"]
            )
        )

        self.last_seen[pid] = now

        self._threshold_alerts(pid, ts, vals, ok)
        self._add_to_step(pid, ts, vals, ok)

        return {
            "stored": True,
            "patient_id": pid,
            "timestamp": iso(ts),
            "valid": ok
        }

    # ---- sensor threshold alerts ----

    def _threshold_alerts(self, pid, ts, v, ok):
        c = self.cfg

        rules = [
            (
                "hr",
                ok["hr"] and v["hr"] > c.hr_high,
                f"Heart rate {(v['hr'] or 0):.0f} bpm is above {c.hr_high:g}"
            ),
            (
                "spo2",
                ok["spo2"] and v["spo2"] < c.spo2_low,
                f"SpO2 {(v['spo2'] or 0):.0f}% is below {c.spo2_low:g}"
            ),
            (
                "temp",
                ok["temp"] and v["temp"] > c.temp_high,
                f"Temperature {(v['temp'] or 0):.1f} C is above {c.temp_high:g}"
            )
        ]

        for k, hit, msg in rules:
            if hit and self._cooled(
                (pid, "th_" + k),
                c.alert_cooldown_s
            ):
                self._raise(
                    pid,
                    ts,
                    "threshold",
                    msg,
                    (pid, "th_" + k)
                )

    # ---- save alerts ----

    def _raise(self, pid, ts, kind, msg, notify_key):
        aid = self.db.run(
            """
            INSERT INTO alerts(patient_id, ts, type, message)
            VALUES(?,?,?,?)
            """,
            (pid, ts, kind, msg)
        )

        if self._cooled(
            ("notify",) + notify_key,
            self.cfg.notify_cooldown_s
        ):
            self.notifier.notify(
                aid,
                f"SeptiSense alert for {pid}: {msg}. "
                "Research prototype, not a diagnosis."
            )

    # ---- model steps ----

    def _add_to_step(self, pid, ts, v, ok):
        b = self.bucket.get(pid)

        if b and ts - b["start"] >= self.cfg.step_seconds:
            self._close_step(pid, b)
            b = None

        if not b:
            b = self.bucket[pid] = {
                "start": ts,
                "end": ts,
                "hr": [],
                "spo2": [],
                "temp": []
            }

        b["end"] = ts

        for k in ("hr", "spo2", "temp"):
            if ok[k]:
                b[k].append(v[k])

    def _close_step(self, pid, b):
        mean = lambda xs: sum(xs) / len(xs) if xs else None

        row = {
            k: mean(b[k])
            for k in ("hr", "spo2", "temp")
        }

        rows = self._rows(pid)
        rows.append(row)

        del rows[:-self.keep]

        self.db.run(
            """
            INSERT INTO steps(patient_id, ts, hr, spo2, temp)
            VALUES(?,?,?,?,?)
            """,
            (
                pid,
                b["end"],
                row["hr"],
                row["spo2"],
                row["temp"]
            )
        )

        self._predict(pid, b["end"])

    # ---- risk prediction and alerts ----

    def _predict(self, pid, ts):
        """
        Calculate the CatBoost raw score, interpret it,
        save the prediction and log one alert per
        threshold-crossing period.
        """

        # 1. Get recent model steps
        rows = self._rows(pid)

        # 2. Build the feature vector using features.py
        vector = F.build_vector(self.names, rows)

        # 3. Calculate raw CatBoost score
        score = self.model.score(vector)

        # 4. Interpret the score for dashboard display
        prob, pct, level = self.model.interpret(score)

        self.level[pid] = level

        # 5. Save prediction to SQLite
        self.db.run(
    """
    INSERT INTO predictions(
        patient_id,
        ts,
        raw_score,
        probability,
        percentile,
        level,
        rows_used
    )
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """,
            (
                pid,
                ts,
                score,
                prob,
                pct,
                level,
                len(rows)
            )
        )

        # 6. Log an alert when raw score reaches threshold
        if score >= self.cfg.risk_alert_threshold:

            if pid not in self.risk_alert_active:

                self._raise(
                    pid,
                    ts,
                    "high_risk",
                    (
                        f"Raw model score {score:.2f} reached "
                        f"the alert threshold "
                        f"{self.cfg.risk_alert_threshold:.2f}"
                    ),
                    (pid, "risk")
                )

                self.risk_alert_active.add(pid)

        else:
            # Reset after score falls below threshold
            self.risk_alert_active.discard(pid)

    # ---- API payloads ----

    def prediction(self, pid):
        c = self.cfg

        base = {
            "patient_id": pid,
            "horizon_hours": c.horizon_hours,
            "model_name": "SeptiSense respiration-free CatBoost",
            "feature_count": len(self.names),
            "rows_needed": c.min_rows,
            "step_seconds": c.step_seconds
        }

        r = self.db.one(
            """
            SELECT *
            FROM predictions
            WHERE patient_id=?
            ORDER BY ts DESC
            LIMIT 1
            """,
            (pid,)
        )

        if not r:
            return {
                **base,
                "status": "warming_up",
                "timestamp": iso(self.clock()),
                "risk_probability": None,
                "rows_collected": len(self._rows(pid))
            }

        return {
            **base,
            "status": "ok",
            "timestamp": iso(r["ts"]),
            "risk_probability": round(r["probability"], 4),
            "risk_score": round(r["raw_score"], 4),
            "risk_percentile": round(r["percentile"], 3),
            "risk_level": r["level"],
            "rows_collected": r["rows_used"]
        }

    def device(self, pid):
        t = self.last_seen.get(pid)

        if t is None:
            r = self.db.one(
                "SELECT MAX(ts) AS t FROM readings WHERE patient_id=?",
                (pid,)
            )
            t = r["t"] if r and r["t"] else None

        if t is None:
            return {
                "online": False,
                "last_seen": iso(0)
            }

        return {
            "online": self.clock() - t <= self.cfg.offline_after_s,
            "last_seen": iso(t)
        }
