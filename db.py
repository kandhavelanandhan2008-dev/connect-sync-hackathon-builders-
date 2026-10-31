import sqlite3, threading

SCHEMA = """
CREATE TABLE IF NOT EXISTS readings(id INTEGER PRIMARY KEY, patient_id TEXT, ts REAL, hr REAL, spo2 REAL, temp REAL,
  hr_valid INTEGER, spo2_valid INTEGER, temp_valid INTEGER);
CREATE INDEX IF NOT EXISTS ix_readings ON readings(patient_id, ts);
CREATE TABLE IF NOT EXISTS steps(id INTEGER PRIMARY KEY, patient_id TEXT, ts REAL, hr REAL, spo2 REAL, temp REAL);
CREATE TABLE IF NOT EXISTS predictions(id INTEGER PRIMARY KEY, patient_id TEXT, ts REAL, raw_score REAL, probability REAL,
  percentile REAL, level TEXT, rows_used INTEGER);
CREATE TABLE IF NOT EXISTS alerts(id INTEGER PRIMARY KEY, patient_id TEXT, ts REAL, type TEXT, message TEXT);
CREATE TABLE IF NOT EXISTS notifications(id INTEGER PRIMARY KEY, ts REAL, alert_id INTEGER, channel TEXT, recipient TEXT,
  status TEXT, message TEXT, detail TEXT);
"""


class Db:
    def __init__(self, path):
        self.lock = threading.Lock()
        self.con = sqlite3.connect(path, check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        with self.lock:
            self.con.executescript(SCHEMA)

    def run(self, sql, args=()):
        with self.lock:
            cur = self.con.execute(sql, args)
            self.con.commit()
            return cur.lastrowid

    def all(self, sql, args=()):
        with self.lock:
            return [dict(r) for r in self.con.execute(sql, args).fetchall()]

    def one(self, sql, args=()):
        rows = self.all(sql, args)
        return rows[0] if rows else None
