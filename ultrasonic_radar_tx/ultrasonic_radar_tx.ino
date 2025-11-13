#if defined(ESP32)
#include <WiFi.h>
#include <ESP32Servo.h>
#include <TinyGPSPlus.h>
#elif defined(ESP8266)
#include <ESP8266WiFi.h>
#include <Servo.h>
#else
#error "This sketch requires an ESP8266 or ESP32 board."
#endif

#include <Wire.h>
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

#if defined(ESP32)
constexpr uint8_t HDC1080_SDA_PIN = 4;
constexpr uint8_t HDC1080_SCL_PIN = 23;
#endif
// Texas Instruments HDC1080 humidity/temp sensor (I2C)
constexpr uint8_t HDC1080_ADDR = 0x40;
constexpr unsigned long ENV_SAMPLE_PERIOD_MS = 2000;
constexpr unsigned long HDC1080_MEAS_DELAY_MS = 20;

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

bool envSensorInitialized = false;
bool envSensorHasSample = false;
float envLastTemperatureC = 0.0f;
float envLastHumidityPct = 0.0f;
unsigned long envLastSampleMs = 0;

#if defined(ESP32)
HardwareSerial SerialGPS(1);
TinyGPSPlus gps;
constexpr int GPS_RX_PIN = 34;
constexpr int GPS_TX_PIN = 12;
constexpr uint32_t GPS_BAUD_RATE = 9600;
constexpr unsigned long GPS_MAX_AGE_MS = 5000;
double gpsLastLat = 0.0;
double gpsLastLon = 0.0;
double gpsLastAlt = 0.0;
double gpsLastSpeedMps = 0.0;
double gpsLastHdop = 0.0;
uint8_t gpsLastSatellites = 0;
unsigned long gpsLastFixMs = 0;

void beginGps();
void pollGps();
bool gpsHasFix();
#endif

void connectToWifi();
void ensureWebsocket();
void publishRadarSample(int angleDeg, float distanceCm, bool valid);
float readDistanceCm();
void commandServo(int logicalAngle);
void updateSweep();
void beginEnvSensor();
void updateEnvSensor();
bool readHdc1080Sample(float& temperatureC, float& humidityPct);
bool readHdc1080Register(uint8_t reg, uint16_t& value);

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

#if defined(ESP32)
  beginGps();
#endif

  beginEnvSensor();
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
#if defined(ESP32)
  pollGps();
#endif

  if (WiFi.status() != WL_CONNECTED) {
    ensureWebsocket();  // ensures disconnect handling
    connectToWifi();
  } else {
    ensureWebsocket();
    radarSocket.poll();
  }

  updateEnvSensor();
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
  payload.reserve(220);
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
#if defined(ESP32)
  if (gpsHasFix()) {
    payload += ",\"gps\":{";
    payload += "\"lat\":"; payload += String(gpsLastLat, 6);
    payload += ",\"lon\":"; payload += String(gpsLastLon, 6);
    payload += ",\"alt_m\":"; payload += String(gpsLastAlt, 1);
    payload += ",\"speed_mps\":"; payload += String(gpsLastSpeedMps, 2);
    payload += ",\"hdop\":"; payload += String(gpsLastHdop, 1);
    payload += ",\"satellites\":"; payload += gpsLastSatellites;
    payload += ",\"fix_age_ms\":"; payload += (millis() - gpsLastFixMs);
    payload += "}";
  } else {
    payload += ",\"gps\":null";
  }
#endif
  payload += ",\"environment\":";
  if (envSensorHasSample) {
    payload += "{\"temperature_c\":";
    payload += String(envLastTemperatureC, 2);
    payload += ",\"humidity_pct\":";
    payload += String(envLastHumidityPct, 1);
    payload += "}";
  } else {
    payload += "null";
  }
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

void beginEnvSensor() {
#if defined(ESP32)
  Wire.begin(HDC1080_SDA_PIN, HDC1080_SCL_PIN);
#else
  Wire.begin();
#endif

  Wire.beginTransmission(HDC1080_ADDR);
  const bool found = (Wire.endTransmission() == 0);
  envSensorInitialized = found;
  if (found) {
    Serial.println("[HDC1080] Sensor detected");
  } else {
    Serial.println("[HDC1080] Sensor not found on I2C");
  }
}

void updateEnvSensor() {
  if (!envSensorInitialized) {
    return;
  }
  const unsigned long now = millis();
  if (envSensorHasSample && (now - envLastSampleMs) < ENV_SAMPLE_PERIOD_MS) {
    return;
  }

  float temperatureC = 0.0f;
  float humidityPct = 0.0f;
  if (readHdc1080Sample(temperatureC, humidityPct)) {
    envLastTemperatureC = temperatureC;
    envLastHumidityPct = humidityPct;
    envSensorHasSample = true;
  } else {
    Serial.println("[HDC1080] Failed to read sensor");
  }
  envLastSampleMs = now;
}

bool readHdc1080Sample(float& temperatureC, float& humidityPct) {
  uint16_t rawTemp = 0;
  uint16_t rawHumidity = 0;
  if (!readHdc1080Register(0x00, rawTemp)) {
    return false;
  }
  if (!readHdc1080Register(0x01, rawHumidity)) {
    return false;
  }

  temperatureC = (static_cast<float>(rawTemp) / 65536.0f) * 165.0f - 40.0f;
  humidityPct = (static_cast<float>(rawHumidity) / 65536.0f) * 100.0f;
  humidityPct = constrain(humidityPct, 0.0f, 100.0f);
  return true;
}

bool readHdc1080Register(uint8_t reg, uint16_t& value) {
  Wire.beginTransmission(HDC1080_ADDR);
  Wire.write(reg);
  if (Wire.endTransmission() != 0) {
    return false;
  }

  delay(HDC1080_MEAS_DELAY_MS);

  if (Wire.requestFrom(HDC1080_ADDR, static_cast<uint8_t>(2)) != 2) {
    while (Wire.available()) {
      Wire.read();
    }
    return false;
  }

  const uint8_t msb = Wire.read();
  const uint8_t lsb = Wire.read();
  value = (static_cast<uint16_t>(msb) << 8) | lsb;
  return true;
}

#if defined(ESP32)
void beginGps() {
  SerialGPS.begin(GPS_BAUD_RATE, SERIAL_8N1, GPS_RX_PIN, GPS_TX_PIN);
  Serial.println("[GPS] Serial initialized for TinyGPS++");
}

void pollGps() {
  bool sentenceCompleted = false;
  while (SerialGPS.available()) {
    sentenceCompleted |= gps.encode(SerialGPS.read());
  }

  if (!sentenceCompleted) {
    return;
  }

  const unsigned long now = millis();
  if (gps.location.isValid()) {
    gpsLastLat = gps.location.lat();
    gpsLastLon = gps.location.lng();
    gpsLastFixMs = now;
  }
  if (gps.altitude.isValid()) {
    gpsLastAlt = gps.altitude.meters();
  }
  if (gps.speed.isValid()) {
    gpsLastSpeedMps = gps.speed.mps();
  }
  if (gps.hdop.isValid()) {
    gpsLastHdop = gps.hdop.hdop();
  }
  if (gps.satellites.isValid()) {
    gpsLastSatellites = static_cast<uint8_t>(gps.satellites.value());
  }
}

bool gpsHasFix() {
  const unsigned long age = gps.location.isValid() ? gps.location.age() : GPS_MAX_AGE_MS + 1;
  return gps.location.isValid() && age <= GPS_MAX_AGE_MS;
}
#endif
