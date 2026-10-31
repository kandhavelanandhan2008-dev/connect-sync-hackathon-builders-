"""Doctor / nurse notifications. 'log' only records a simulated message (safe for demos).
'email' uses SMTP; 'sms' and 'whatsapp' use the Twilio REST API. Real channels need credentials in .env."""
import smtplib, threading
from email.message import EmailMessage
import requests


class Notifier:
    def __init__(self, cfg, db, clock):
        self.cfg, self.db, self.clock, self.last = cfg, db, clock, {}

    def _record(self, alert_id, channel, recipient, status, message, detail=""):
        self.db.run("INSERT INTO notifications(ts,alert_id,channel,recipient,status,message,detail) VALUES(?,?,?,?,?,?,?)",
                    (self.clock(), alert_id, channel, recipient, status, message, detail))

    def _send(self, channel, alert_id, text):
        c = self.cfg
        try:
            if channel == "log":
                self._record(alert_id, "log", c.doctor_name, "simulated", text, "No real message was sent")
            elif channel == "email":
                if not (c.smtp_host and c.doctor_email):
                    return self._record(alert_id, "email", c.doctor_email, "skipped", text, "SMTP_HOST or DOCTOR_EMAIL not set")
                m = EmailMessage()
                m["Subject"], m["From"], m["To"] = "SeptiSense alert", c.smtp_user or "septisense@localhost", c.doctor_email
                m.set_content(text)
                with smtplib.SMTP(c.smtp_host, c.smtp_port, timeout=10) as s:
                    s.starttls()
                    if c.smtp_user:
                        s.login(c.smtp_user, c.smtp_pass)
                    s.send_message(m)
                self._record(alert_id, "email", c.doctor_email, "sent", text)
            elif channel in ("sms", "whatsapp"):
                if not (c.twilio_sid and c.twilio_token and c.doctor_phone):
                    return self._record(alert_id, channel, c.doctor_phone, "skipped", text, "Twilio credentials or DOCTOR_PHONE not set")
                wa = channel == "whatsapp"
                data = {"To": ("whatsapp:" if wa else "") + c.doctor_phone,
                        "From": c.twilio_whatsapp_from if wa else c.twilio_from, "Body": text}
                r = requests.post(f"https://api.twilio.com/2010-04-01/Accounts/{c.twilio_sid}/Messages.json",
                                  data=data, auth=(c.twilio_sid, c.twilio_token), timeout=10)
                self._record(alert_id, channel, c.doctor_phone, "sent" if r.ok else "failed", text, "" if r.ok else r.text[:200])
            else:
                self._record(alert_id, channel, "", "skipped", text, "Unknown channel")
        except Exception as e:  # a failed notification must never break data ingest
            self._record(alert_id, channel, "", "failed", text, str(e)[:200])

    def notify(self, alert_id, text):
        """Sends to every configured channel. Rate limiting is done by the engine."""
        for ch in self.cfg.notify_channels:
            if self.cfg.notify_async:
                threading.Thread(target=self._send, args=(ch, alert_id, text), daemon=True).start()
            else:
                self._send(ch, alert_id, text)
