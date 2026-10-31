/*
  SeptiSense ESP32 example sketch (NOT tested on hardware: treat it as a starting point).

  Sensors assumed:
    MAX30102 / MAX30105 (heart rate + SpO2)  -> library "SparkFun MAX3010x"
    MLX90614 (non-contact temperature)        -> library "Adafruit MLX90614"
  Wiring: both sensors on the same I2C pins (ESP32 default SDA=21, SCL=22), 3.3 V and GND.

  What it does: every ~5 s it measures, then POSTs JSON to the laptop backend:
    {"patient_id":"P001","heart_rate":82,"spo2":97,"temperature":36.9,
     "quality":{"hr_valid":true,"spo2_valid":true,"temp_valid":true}}
  No timestamp is sent; the backend uses the time it receives the reading.
*/
#include <WiFi.h>
#include <HTTPClient.h>
#include <Wire.h>
#include <Adafruit_MLX90614.h>
#include "MAX30105.h"
#include "spo2_algorithm.h"

// ---------- EDIT THESE ----------
const char* WIFI_SSID = "YOUR_WIFI_OR_PHONE_HOTSPOT";
const char* WIFI_PASS = "YOUR_PASSWORD";
const char* SERVER_URL = "http://192.168.1.23:8000/api/telemetry";  // laptop IPv4 address, NOT localhost
const char* PATIENT_ID = "P001";
// --------------------------------

Adafruit_MLX90614 mlx;
MAX30105 pm;
const int N = 100;               // 100 samples at ~25 samples/s = 4 s per measurement
uint32_t irBuf[N], redBuf[N];

void connectWifi() {
  if (WiFi.status() == WL_CONNECTED) return;
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  unsigned long t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < 15000) delay(300);
}

void setup() {
  Serial.begin(115200);
  Wire.begin();
  if (!mlx.begin()) Serial.println("MLX90614 not found");
  if (!pm.begin(Wire, I2C_SPEED_FAST)) Serial.println("MAX30102 not found");
  pm.setup(60, 4, 2, 100, 411, 4096);  // brightness, averaging, red+IR, sample rate, pulse width, ADC range
  connectWifi();
}

void loop() {
  // 1) heart rate + SpO2 (finger must be on the sensor)
  for (int i = 0; i < N; i++) {
    while (!pm.available()) pm.check();
    redBuf[i] = pm.getRed();
    irBuf[i] = pm.getIR();
    pm.nextSample();
  }
  int32_t spo2 = -999, hr = -999;
  int8_t okS = 0, okH = 0;
  maxim_heart_rate_and_oxygen_saturation(irBuf, N, redBuf, &spo2, &okS, &hr, &okH);
  bool finger = irBuf[N - 1] > 50000;          // no finger -> weak IR signal
  bool spo2Ok = okS && finger, hrOk = okH && finger;
  if (!spo2Ok) spo2 = -999;
  if (!hrOk) hr = -999;

  // 2) temperature (surface). Calibrate it: see ELECTRONICS_GUIDE.md
  float t = mlx.readObjectTempC();
  bool tOk = !isnan(t) && t > 20 && t < 45;
  if (!tOk) t = -999;

  // 3) send
  char body[220];
  snprintf(body, sizeof(body),
    "{\"patient_id\":\"%s\",\"heart_rate\":%ld,\"spo2\":%ld,\"temperature\":%.1f,"
    "\"quality\":{\"hr_valid\":%s,\"spo2_valid\":%s,\"temp_valid\":%s}}",
    PATIENT_ID, (long)hr, (long)spo2, t,
    hrOk ? "true" : "false", spo2Ok ? "true" : "false", tOk ? "true" : "false");
  Serial.println(body);

  connectWifi();
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    http.setTimeout(3000);
    http.begin(SERVER_URL);
    http.addHeader("Content-Type", "application/json");
    int code = http.POST((uint8_t*)body, strlen(body));
    Serial.printf("server replied %d\n", code);   // 201 = stored
    http.end();
  } else {
    Serial.println("no Wi-Fi, reading skipped");
  }
  delay(1000);   // total cycle is about 5 s
}
