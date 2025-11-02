#if defined(ESP32)
#include <WiFi.h>
#include <WebServer.h>
#include <ESP32Servo.h>
#elif defined(ESP8266)
#include <ESP8266WiFi.h>
#include <ESP8266WebServer.h>
#include <Servo.h>
#else
#error "This sketch requires an ESP8266 or ESP32 board."
#endif

#if defined(ESP8266)
constexpr uint8_t SERVO_PIN = D5;
constexpr uint8_t TRIG_PIN = D6;
constexpr uint8_t ECHO_PIN = D7;
#else
// LilyGO LoRa boards use GPIOs 25/26 for the radio, so default to 32/33 here.
constexpr uint8_t SERVO_PIN = 13;
constexpr uint8_t TRIG_PIN = 32;
constexpr uint8_t ECHO_PIN = 33;
#endif

constexpr int SERVO_MIN_DEG = 0;
constexpr int SERVO_MAX_DEG = 180;
constexpr int SERVO_OFFSET_DEG = 0;  // Adjust if the horn zero is misaligned (positive is clockwise).

constexpr uint8_t MIN_ANGLE_DEG = 45;
constexpr uint8_t MAX_ANGLE_DEG = 135;
constexpr uint8_t STEP_DEG = 3;
constexpr uint32_t SERVO_SETTLE_MS = 30;
constexpr uint32_t SAMPLE_PERIOD_MS = 60;
constexpr float MAX_DISTANCE_CM = 300.0f;
constexpr unsigned long PULSE_TIMEOUT_US = 25000;

constexpr bool RUN_AS_AP = true;
const char* const AP_SSID = "RadarScanner";
const char* const AP_PASSWORD = "scanradar";
const char* const WIFI_SSID = "YOUR_WIFI_SSID";
const char* const WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";

#if defined(ESP32)
WebServer server(80);
Servo radarServo;
#elif defined(ESP8266)
ESP8266WebServer server(80);
Servo radarServo;
#endif

float lastDistanceCm = -1.0f;
int lastAngleDeg = MIN_ANGLE_DEG;
unsigned long lastMeasurementMs = 0;

int currentAngleDeg = MIN_ANGLE_DEG;
int sweepDirection = 1;
bool waitingForServo = false;
unsigned long servoCommandMs = 0;
unsigned long lastStepMs = 0;

const char INDEX_HTML[] PROGMEM = R"rawliteral(
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Ultrasonic Radar</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
:root { color-scheme: dark; }
body { margin:0; font-family: "Segoe UI", sans-serif; background:#010409; color:#e8f9ff; display:flex; flex-direction:column; align-items:center; min-height:100vh; }
header { text-align:center; padding:1.5rem 0 1rem 0; }
h1 { margin:0; font-size:1.75rem; }
#status { margin-top:0.25rem; font-size:0.95rem; opacity:0.75; }
#radar { background:#020b1b; border-radius:50%; width:min(90vw, 480px); height:auto; }
footer { margin:1rem 0 2rem 0; font-size:0.8rem; opacity:0.5; }
</style>
</head>
<body>
<header>
  <h1>Ultrasonic Radar</h1>
  <div id="status">Waiting for data...</div>
</header>
<canvas id="radar" width="480" height="480"></canvas>
<footer>HC-SR04 sweep on SG90 &mdash; ESP web radar</footer>
<script>
  const canvas = document.getElementById('radar');
  const ctx = canvas.getContext('2d');
  const statusEl = document.getElementById('status');
  const center = { x: canvas.width / 2, y: canvas.height / 2 };
  const radius = canvas.width / 2;
  const DISPLAY_MAX_CM = 120;
  const MIN_SWEEP_DEG = 0;
  const MAX_SWEEP_DEG = 180;
  let angleStepDeg = 3;
  let servoOffsetDeg = 0;
  let sweepCells = buildSweepBuffer(angleStepDeg);
  let maxDistance = DISPLAY_MAX_CM;
  let lastUpdateTs = 0;

  function buildSweepBuffer(stepDeg) {
    const slots = Math.floor((MAX_SWEEP_DEG - MIN_SWEEP_DEG) / stepDeg) + 1;
    return new Array(slots).fill(null);
  }

  function setAngleStep(stepDeg) {
    const clamped = clamp(Math.round(stepDeg), 1, 45);
    if (clamped === angleStepDeg) {
      return;
    }
    angleStepDeg = clamped;
    sweepCells = buildSweepBuffer(angleStepDeg);
  }

  function clamp(value, min, max) {
    return Math.min(Math.max(value, min), max);
  }

  function isFiniteNumber(value) {
    return typeof value === 'number' && isFinite(value);
  }

  function canvasRad(angleDeg) {
    return Math.PI - (angleDeg * Math.PI / 180);
  }

  function angleToIndex(angleDeg) {
    if (!isFiniteNumber(angleDeg)) {
      return 0;
    }
    const normalized = clamp(Math.round((angleDeg - MIN_SWEEP_DEG) / angleStepDeg), 0, sweepCells.length - 1);
    return normalized;
  }

  function recordMeasurement(snapshot) {
    if (!isFiniteNumber(snapshot.displayAngle)) {
      return;
    }
    const idx = angleToIndex(snapshot.displayAngle);
    if (!snapshot.valid) {
      sweepCells[idx] = null;
      return;
    }
    sweepCells[idx] = {
      angle: clamp(snapshot.displayAngle, MIN_SWEEP_DEG, MAX_SWEEP_DEG),
      distance: clamp(snapshot.distance, 0, maxDistance),
      timestamp: Date.now()
    };
  }

  function drawBackground() {
    ctx.fillStyle = '#020b1b';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.strokeStyle = '#0b3923';
    ctx.lineWidth = 2;
    const rings = 4;
    for (let i = 1; i <= rings; i++) {
      const ringRadius = radius * (i / rings);
      ctx.beginPath();
      ctx.arc(center.x, center.y, ringRadius, Math.PI, 0);
      ctx.stroke();
    }
    for (let deg = 0; deg <= 180; deg += 30) {
      const rad = canvasRad(deg);
      ctx.beginPath();
      ctx.moveTo(center.x, center.y);
      ctx.lineTo(center.x + Math.cos(rad) * radius, center.y - Math.sin(rad) * radius);
      ctx.stroke();
    }
  }

  function drawTrail() {
    const now = Date.now();
    const range = maxDistance > 0 ? maxDistance : 1;
    ctx.save();
    for (const entry of sweepCells) {
      if (!entry) {
        continue;
      }
      const halfStep = angleStepDeg / 2;
      const lower = clamp(entry.angle - halfStep, MIN_SWEEP_DEG, MAX_SWEEP_DEG);
      const upper = clamp(entry.angle + halfStep, MIN_SWEEP_DEG, MAX_SWEEP_DEG);
      if (upper <= lower) {
        continue;
      }
      const start = canvasRad(lower);
      const end = canvasRad(upper);
      const innerRadius = (entry.distance / range) * radius;
      const ageMs = now - entry.timestamp;
      const alpha = clamp(0.2 + (4000 - ageMs) / 8000, 0.2, 0.6);

      ctx.fillStyle = `rgba(13, 255, 148, ${alpha.toFixed(3)})`;
      ctx.beginPath();
      ctx.arc(center.x, center.y, radius, start, end, true);
      if (innerRadius > 2) {
        ctx.arc(center.x, center.y, innerRadius, end, start, false);
      } else {
        ctx.lineTo(center.x, center.y);
      }
      ctx.closePath();
      ctx.fill();
    }
    ctx.restore();
  }

  function drawSweep(angleDeg) {
    const rad = canvasRad(angleDeg);
    const gradient = ctx.createRadialGradient(center.x, center.y, radius * 0.1, center.x, center.y, radius);
    gradient.addColorStop(0, 'rgba(13, 255, 148, 0.2)');
    gradient.addColorStop(1, 'rgba(13, 255, 148, 0)');
    ctx.fillStyle = gradient;
    ctx.beginPath();
    ctx.moveTo(center.x, center.y);
    ctx.lineTo(center.x + Math.cos(rad) * radius, center.y - Math.sin(rad) * radius);
    ctx.arc(center.x, center.y, radius, rad, rad - 0.03, true);
    ctx.closePath();
    ctx.fill();

    ctx.strokeStyle = '#0dff94';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(center.x, center.y);
    ctx.lineTo(center.x + Math.cos(rad) * radius, center.y - Math.sin(rad) * radius);
    ctx.stroke();
  }

  function drawPing(angleDeg, distance) {
    const rad = canvasRad(angleDeg);
    const range = maxDistance > 0 ? maxDistance : 1;
    const normalized = clamp(distance / range, 0, 1);
    const pingRadius = normalized * radius;
    const x = center.x + Math.cos(rad) * pingRadius;
    const y = center.y - Math.sin(rad) * pingRadius;

    ctx.fillStyle = '#0dff94';
    ctx.beginPath();
    ctx.arc(x, y, 5, 0, 2 * Math.PI);
    ctx.fill();

    ctx.strokeStyle = 'rgba(13, 255, 148, 0.35)';
    ctx.beginPath();
    ctx.arc(center.x, center.y, pingRadius, rad - 0.05, rad + 0.05);
    ctx.stroke();
  }

  function render(snapshot) {
    recordMeasurement(snapshot);
    drawBackground();
    drawTrail();
    drawSweep(snapshot.displayAngle);
    if (snapshot.valid) {
      drawPing(snapshot.displayAngle, snapshot.distance);
      statusEl.textContent = `Angle: ${snapshot.physicalAngle.toFixed(0)} deg | Distance: ${snapshot.distance.toFixed(1)} cm`;
    } else {
      statusEl.textContent = `Angle: ${snapshot.physicalAngle.toFixed(0)} deg | Distance: ---`;
    }
  }

  async function poll() {
    try {
      const resp = await fetch('/scan');
      if (!resp.ok) {
        throw new Error('HTTP ' + resp.status);
      }
      const data = await resp.json();
      if (isFiniteNumber(data.max_distance_cm)) {
        maxDistance = clamp(data.max_distance_cm, 1, DISPLAY_MAX_CM);
      } else {
        maxDistance = DISPLAY_MAX_CM;
      }
      if (isFiniteNumber(data.step_deg)) {
        setAngleStep(data.step_deg);
      }
      if (isFiniteNumber(data.servo_offset_deg)) {
        servoOffsetDeg = data.servo_offset_deg;
      }
      const rawAngle = Number(data.angle);
      const logicalAngle = isFiniteNumber(rawAngle) ? rawAngle : 0;
      const physicalAngle = clamp(logicalAngle + servoOffsetDeg, MIN_SWEEP_DEG, MAX_SWEEP_DEG);
      const displayAngle = clamp(MAX_SWEEP_DEG - physicalAngle, MIN_SWEEP_DEG, MAX_SWEEP_DEG);
      const rawDistance = Number(data.distance_cm);
      const valid = Boolean(data.valid) && isFiniteNumber(rawDistance) && rawDistance >= 0;
      const distance = valid ? clamp(rawDistance, 0, DISPLAY_MAX_CM) : 0;
      render({ displayAngle, physicalAngle, distance, valid });
      lastUpdateTs = Date.now();
    } catch (error) {
      statusEl.textContent = 'Waiting for connection...';
    }
  }

  drawBackground();
  setInterval(poll, 150);
  setInterval(() => {
    if (Date.now() - lastUpdateTs > 2000) {
      statusEl.textContent = 'Waiting for data...';
    }
  }, 500);
</script>
</body>
</html>
)rawliteral";

float readDistanceCm();
void handleRoot();
void handleScan();
void updateSweep();
void commandServo(int logicalAngle);

void setup() {
  Serial.begin(115200);
  delay(100);

  pinMode(TRIG_PIN, OUTPUT);
  digitalWrite(TRIG_PIN, LOW);
  pinMode(ECHO_PIN, INPUT);

#if defined(ESP32)
  radarServo.attach(SERVO_PIN, 500, 2400);
#else
  radarServo.attach(SERVO_PIN);
#endif
  commandServo(currentAngleDeg);
  waitingForServo = true;
  servoCommandMs = millis();

  if (RUN_AS_AP) {
    WiFi.mode(WIFI_AP);
    WiFi.softAP(AP_SSID, AP_PASSWORD);
    Serial.print("Access point SSID: ");
    Serial.println(AP_SSID);
    Serial.print("AP IP address: ");
    Serial.println(WiFi.softAPIP());
  } else {
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    Serial.print("Connecting to ");
    Serial.println(WIFI_SSID);
    const unsigned long connectStart = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - connectStart < 20000) {
      delay(250);
      Serial.print(".");
    }
    if (WiFi.status() == WL_CONNECTED) {
      Serial.println("\nWi-Fi connected");
      Serial.print("IP address: ");
      Serial.println(WiFi.localIP());
    } else {
      Serial.println("\nWi-Fi connect failed, starting access point");
      WiFi.mode(WIFI_AP);
      WiFi.softAP(AP_SSID, AP_PASSWORD);
      Serial.print("AP IP address: ");
      Serial.println(WiFi.softAPIP());
    }
  }

  server.on("/", handleRoot);
  server.on("/scan", handleScan);
  server.onNotFound([]() {
    server.send(404, "text/plain", "Not found");
  });
  server.begin();
  Serial.println("HTTP server started");
}

void loop() {
  server.handleClient();
#if defined(ESP8266)
  yield();
#endif
  updateSweep();
}

void handleRoot() {
  server.send_P(200, "text/html", INDEX_HTML);
}

void handleScan() {
  String payload;
  payload.reserve(200);
  payload += "{\"angle\":";
  payload += lastAngleDeg;
  payload += ",\"distance_cm\":";
  if (lastDistanceCm >= 0.0f) {
    payload += String(lastDistanceCm, 1);
    payload += ",\"valid\":true";
  } else {
    payload += "-1";
    payload += ",\"valid\":false";
  }
  payload += ",\"max_distance_cm\":";
  payload += String(MAX_DISTANCE_CM, 1);
  payload += ",\"servo_offset_deg\":";
  payload += SERVO_OFFSET_DEG;
  payload += ",\"step_deg\":";
  payload += STEP_DEG;
  payload += ",\"timestamp_ms\":";
  payload += lastMeasurementMs;
  payload += "}";
  server.send(200, "application/json", payload);
}

float readDistanceCm() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);

  const unsigned long duration = pulseIn(ECHO_PIN, HIGH, PULSE_TIMEOUT_US);
  if (duration == 0) {
    return -1.0f;
  }

  const float distance = (duration * 0.0343f) * 0.5f;
  if (distance < 1.0f || distance > MAX_DISTANCE_CM) {
    return -1.0f;
  }
  return distance;
}

void commandServo(int logicalAngle) {
  const int physical = constrain(logicalAngle + SERVO_OFFSET_DEG, SERVO_MIN_DEG, SERVO_MAX_DEG);
  radarServo.write(physical);
}

void updateSweep() {
  const unsigned long now = millis();
  if (waitingForServo) {
    if (now - servoCommandMs < SERVO_SETTLE_MS) {
      return;
    }
    const float distance = readDistanceCm();
    lastDistanceCm = distance;
    lastAngleDeg = currentAngleDeg;
    lastMeasurementMs = now;
    waitingForServo = false;
    lastStepMs = now;
    return;
  }

  if (now - lastStepMs < SAMPLE_PERIOD_MS) {
    return;
  }

  int nextAngle = currentAngleDeg + (sweepDirection * STEP_DEG);
  if (nextAngle > MAX_ANGLE_DEG) {
    nextAngle = MAX_ANGLE_DEG;
    sweepDirection = -1;
  } else if (nextAngle < MIN_ANGLE_DEG) {
    nextAngle = MIN_ANGLE_DEG;
    sweepDirection = 1;
  }

  if (nextAngle == currentAngleDeg) {
    nextAngle += sweepDirection * STEP_DEG;
  }

  nextAngle = constrain(nextAngle, MIN_ANGLE_DEG, MAX_ANGLE_DEG);
  if (nextAngle != currentAngleDeg) {
    currentAngleDeg = nextAngle;
    commandServo(currentAngleDeg);
    servoCommandMs = now;
    waitingForServo = true;
  }
}
