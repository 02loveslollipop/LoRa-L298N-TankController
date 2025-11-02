#if defined(ESP32)
#include <WiFi.h>
#include <ESP32Servo.h>
#elif defined(ESP8266)
#include <ESP8266WiFi.h>
#include <Servo.h>
#else
#error "This sketch requires an ESP8266 or ESP32 board."
#endif

#include <ArduinoWebsockets.h>

using namespace websockets;

#if defined(ESP8266)
constexpr uint8_t SERVO_PIN = D5;
constexpr uint8_t TRIG_PIN = D6;
constexpr uint8_t ECHO_PIN = D7;
#else
constexpr uint8_t SERVO_PIN = 13;
constexpr uint8_t TRIG_PIN = 32;
constexpr uint8_t ECHO_PIN = 33;
#endif

constexpr int SERVO_MIN_DEG = 0;
constexpr int SERVO_MAX_DEG = 180;
constexpr int SERVO_OFFSET_DEG = 0;

constexpr uint8_t MIN_ANGLE_DEG = 15;
constexpr uint8_t MAX_ANGLE_DEG = 165;
constexpr uint8_t STEP_DEG = 3;
constexpr uint32_t SERVO_SETTLE_MS = 30;
constexpr uint32_t SAMPLE_PERIOD_MS = 60;
constexpr float MAX_DISTANCE_CM = 300.0f;
constexpr unsigned long PULSE_TIMEOUT_US = 25000;

// Wi-Fi and radar broker configuration
const char* WIFI_SSID = "UPBWiFi";
const char* WIFI_PASSWORD = "";
const char* RADAR_SOURCE_ID = "tank_001";
// Control broker public endpoint (set to your deployment host)
const char* RADAR_SERVER_HOST = "ws.nene.02labs.me";
const uint16_t RADAR_SERVER_PORT = 80;
String radarWsPath = String("/ws/radar/source/") + RADAR_SOURCE_ID;

constexpr unsigned long WIFI_RETRY_MS = 5000;
constexpr unsigned long WS_RETRY_MS = 5000;

Servo radarServo;
WebsocketsClient radarSocket;

float lastDistanceCm = -1.0f;
int lastAngleDeg = MIN_ANGLE_DEG;
unsigned long lastMeasurementMs = 0;

int currentAngleDeg = MIN_ANGLE_DEG;
int sweepDirection = 1;
bool waitingForServo = false;
unsigned long servoCommandMs = 0;
unsigned long lastStepMs = 0;

unsigned long lastWifiAttempt = 0;
unsigned long lastWsAttempt = 0;

void connectToWifi();
void ensureWebsocket();
void publishRadarSample(int angleDeg, float distanceCm, bool valid);
float readDistanceCm();
void commandServo(int logicalAngle);
void updateSweep();

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

  connectToWifi();

  radarSocket.onEvent([](WebsocketsEvent event, String data) {
    switch (event) {
      case WebsocketsEvent::ConnectionOpened:
        Serial.println("[WS] Radar broker connected");
        break;
      case WebsocketsEvent::ConnectionClosed:
        Serial.println("[WS] Radar broker connection closed");
        break;
      case WebsocketsEvent::GotPing:
        Serial.println("[WS] Received ping");
        break;
      case WebsocketsEvent::GotPong:
        Serial.println("[WS] Received pong");
        break;
    }
  });
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    ensureWebsocket();  // ensures disconnect handling
    connectToWifi();
  } else {
    ensureWebsocket();
    radarSocket.poll();
  }

  updateSweep();
}

void connectToWifi() {
  if (WiFi.status() == WL_CONNECTED) {
    return;
  }

  const unsigned long now = millis();
  if (now - lastWifiAttempt < WIFI_RETRY_MS) {
    return;
  }
  lastWifiAttempt = now;

  Serial.printf("[WIFI] Connecting to %s...\n", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  uint8_t attempt = 0;
  while (WiFi.status() != WL_CONNECTED && attempt < 40) {
    delay(250);
    Serial.print(".");
    attempt++;
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("[WIFI] Connected, IP: %s\n", WiFi.localIP().toString().c_str());
    lastWsAttempt = 0;  // trigger immediate WS connect
  } else {
    Serial.println("[WIFI] Connection failed");
  }
}

void ensureWebsocket() {
  if (radarSocket.available()) {
    return;
  }
  const unsigned long now = millis();
  if (now - lastWsAttempt < WS_RETRY_MS) {
    return;
  }
  lastWsAttempt = now;

  if (WiFi.status() != WL_CONNECTED) {
    return;
  }

  Serial.printf("[WS] Connecting to ws://%s:%u%s\n",
                RADAR_SERVER_HOST,
                RADAR_SERVER_PORT,
                radarWsPath.c_str());

  if (radarSocket.connect(RADAR_SERVER_HOST, RADAR_SERVER_PORT, radarWsPath.c_str())) {
    String hello = "{\"type\":\"hello\",\"sourceId\":\"";
    hello += RADAR_SOURCE_ID;
    hello += "\",\"firmware\":\"ultrasonic_radar_tx\"}";
    radarSocket.send(hello);
  } else {
    Serial.println("[WS] Connection attempt failed");
  }
}

void publishRadarSample(int angleDeg, float distanceCm, bool valid) {
  if (!radarSocket.available()) {
    return;
  }
  String payload;
  payload.reserve(160);
  payload += "{\"angle\":";
  payload += angleDeg;
  payload += ",\"distance_cm\":";
  if (valid) {
    payload += String(distanceCm, 1);
  } else {
    payload += "-1";
  }
  payload += ",\"valid\":";
  payload += valid ? "true" : "false";
  payload += ",\"sourceId\":\"";
  payload += RADAR_SOURCE_ID;
  payload += "\",\"timestamp_ms\":";
  payload += millis();
  payload += "}";

  if (!radarSocket.send(payload)) {
    Serial.println("[WS] Failed to send radar payload");
  } else {
    Serial.printf("[WS] -> %s\n", payload.c_str());
  }
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

    const bool valid = distance >= 0.0f;
    publishRadarSample(lastAngleDeg, distance, valid);
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
