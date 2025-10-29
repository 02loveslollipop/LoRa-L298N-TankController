#include <Arduino.h>
#include <WiFi.h>
#include <ArduinoWebsockets.h>
#include <ArduinoJson.h>
#include <SPI.h>
#include <LoRa.h>
#include "config.h"
#include "../common/ControlProtocol.h"
#include "LoRaBoards.h"

#if !defined(ESP32)
#error "Current build targets the LilyGO T-Beam (ESP32)."
#endif

#ifndef CONFIG_RADIO_FREQ
#define CONFIG_RADIO_FREQ           910.0
#endif
#ifndef CONFIG_RADIO_OUTPUT_POWER
#define CONFIG_RADIO_OUTPUT_POWER   17
#endif
#ifndef CONFIG_RADIO_BW
#define CONFIG_RADIO_BW             125.0
#endif

// ----- Runtime State -------------------------------------------------
using namespace websockets;

WebsocketsClient wsClient;
bool wsConnected = false;
String currentState = "STOP";
uint8_t currentLeftSpeed = 0;
uint8_t currentRightSpeed = 0;
uint8_t sequenceCounter = 0;
uint32_t lastStatusAt = 0;
constexpr uint32_t kStatusIntervalMs = 5000;

// ----- Forward Declarations ------------------------------------------
void connectWiFi();
void beginWebSocket();
void handleWebsocketEvent(WebsocketsEvent event, String data);
void handleWebsocketMessage(WebsocketsMessage message);
void handleCommand(const char *json);
bool transmitLoRa(TankControl::Command cmd, uint8_t leftSpeed, uint8_t rightSpeed);
TankControl::Command mapCommand(const String &cmd);
bool publishStatus(bool force = false);
bool setupLoRa();

// ----- Setup / Loop --------------------------------------------------
void setup() {
    setupBoards(/*disable_u8g2=*/true);
    delay(1500);

    Serial.begin(115200);
    while (!Serial) { delay(10); }

    Serial.println();
    Serial.println("==============================================");
    Serial.println("WebSocket → LoRa Gateway");
    Serial.println("==============================================");

    if (!setupLoRa()) {
        Serial.println("[LoRa] Initialization failed. Halting.");
        while (true) { delay(1000); }
    }

    connectWiFi();
    beginWebSocket();
}

void loop() {
    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("[WiFi] Lost connection, attempting reconnect...");
        wsConnected = false;
        if (wsClient.available()) {
            wsClient.close();
        }
        connectWiFi();
        beginWebSocket();
        delay(500);
        return;
    }

    wsClient.poll();
    publishStatus();
    delay(5);
}

// ----- Wi-Fi & WebSocket ---------------------------------------------
void connectWiFi() {
    Serial.printf("[WiFi] Connecting to %s\n", WIFI_SSID);
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

    const uint32_t start = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - start < 30000) {
        Serial.print('.');
        delay(500);
    }

    if (WiFi.status() == WL_CONNECTED) {
        Serial.println();
        Serial.printf("[WiFi] Connected. IP=%s RSSI=%d dBm\n",
                      WiFi.localIP().toString().c_str(), WiFi.RSSI());
        return;
    }

    Serial.println("\n[WiFi] Failed to connect. Restarting...");
    delay(3000);
    ESP.restart();
}

void beginWebSocket() {
    if (wsClient.available()) {
        wsClient.close();
    }

    String uri = String("ws://") + WS_SERVER_HOST + ":" + WS_SERVER_PORT + "/ws/tank/" + TANK_ID;
    Serial.printf("[WS] Connecting to %s\n", uri.c_str());

    wsClient.onEvent(handleWebsocketEvent);
    wsClient.onMessage(handleWebsocketMessage);

    if (!wsClient.connect(uri)) {
        Serial.println("[WS] Connection attempt failed");
        wsConnected = false;
        return;
    }
}

void handleWebsocketEvent(WebsocketsEvent event, String data) {
    switch (event) {
        case WebsocketsEvent::ConnectionOpened:
            Serial.println("[WS] Event: connection opened");
            wsConnected = true;
            publishStatus(true);
            break;
        case WebsocketsEvent::ConnectionClosed:
            Serial.println("[WS] Event: connection closed");
            wsConnected = false;
            transmitLoRa(TankControl::Command::Stop, 0, 0);
            currentState = "STOP";
            break;
        case WebsocketsEvent::GotPing:
            Serial.println("[WS] Event: ping");
            break;
        case WebsocketsEvent::GotPong:
            Serial.println("[WS] Event: pong");
            break;
        default:
            if (data.length() > 0) {
                Serial.printf("[WS] Event %d data: %s\n",
                              static_cast<int>(event), data.c_str());
            }
            break;
    }
}

void handleWebsocketMessage(WebsocketsMessage message) {
    if (message.isText()) {
        const String &payload = message.data();
        Serial.printf("[WS] <<< %s\n", payload.c_str());
        handleCommand(payload.c_str());
    } else if (message.isBinary()) {
        Serial.printf("[WS] <<< binary (%u bytes)\n",
                      static_cast<unsigned>(message.length()));
    }
}

// ----- Command Handling ----------------------------------------------
void handleCommand(const char *json) {
    StaticJsonDocument<256> doc;
    DeserializationError err = deserializeJson(doc, json);
    if (err) {
        Serial.printf("[CMD] JSON parse error: %s\n", err.c_str());
        return;
    }

    const char *cmdField = doc["command"];
    if (!cmdField) {
        Serial.println("[CMD] Missing command field");
        return;
    }

    uint8_t left = doc["leftSpeed"] | currentLeftSpeed;
    uint8_t right = doc["rightSpeed"] | currentRightSpeed;

    String normalized = cmdField;
    normalized.toLowerCase();

    TankControl::Command cmd = mapCommand(normalized);
    if (!transmitLoRa(cmd, left, right)) {
        Serial.println("[LoRa] Transmission failed");
        return;
    }

    if (normalized == "setspeed") {
        currentLeftSpeed = left;
        currentRightSpeed = right;
    } else if (normalized == "stop") {
        currentLeftSpeed = currentRightSpeed = 0;
    }
    currentState = normalized;

    publishStatus(true);
}

TankControl::Command mapCommand(const String &cmd) {
    if (cmd == "forward") return TankControl::Command::Forward;
    if (cmd == "backward") return TankControl::Command::Backward;
    if (cmd == "left") return TankControl::Command::Left;
    if (cmd == "right") return TankControl::Command::Right;
    if (cmd == "setspeed") return TankControl::Command::SetSpeed;
    return TankControl::Command::Stop;
}

bool transmitLoRa(TankControl::Command cmd, uint8_t leftSpeed, uint8_t rightSpeed) {
    TankControl::ControlFrame frame;
    TankControl::initFrame(frame, cmd, leftSpeed, rightSpeed, sequenceCounter++);

    uint8_t buffer[TankControl::kFrameSize];
    if (!TankControl::encryptFrame(frame, buffer, sizeof(buffer))) {
        Serial.println("[LoRa] encryptFrame failed");
        return false;
    }

    LoRa.idle();
    LoRa.beginPacket();
    LoRa.write(buffer, sizeof(buffer));
    bool ok = LoRa.endPacket() == 1;
    LoRa.receive();

    if (ok) {
        Serial.printf("[LoRa] >>> cmd=%d seq=%u L=%u R=%u\n",
                      static_cast<int>(frame.command),
                      frame.sequence,
                      frame.leftSpeed,
                      frame.rightSpeed);
    }
    return ok;
}

// ----- Status Reporting ----------------------------------------------
bool publishStatus(bool force) {
    if (!wsConnected || !wsClient.available()) {
        return false;
    }

    uint32_t now = millis();
    if (!force && (now - lastStatusAt) < kStatusIntervalMs) {
        return false;
    }
    lastStatusAt = now;

    StaticJsonDocument<256> doc;
    doc["type"] = "status";
    doc["tankId"] = TANK_ID;
    doc["state"] = currentState;
    doc["leftSpeed"] = currentLeftSpeed;
    doc["rightSpeed"] = currentRightSpeed;
    doc["wifiRssi"] = WiFi.RSSI();
    doc["uptime"] = now / 1000;
    doc["freeHeap"] = ESP.getFreeHeap();

    String out;
    serializeJson(doc, out);
    bool sent = wsClient.send(out);
    Serial.printf("[STATUS] %s (%s)\n", out.c_str(), sent ? "sent" : "failed");
    return sent;
}

// ----- LoRa -----------------------------------------------------------
bool setupLoRa() {
    SPI.begin(RADIO_SCLK_PIN, RADIO_MISO_PIN, RADIO_MOSI_PIN, RADIO_CS_PIN);
    LoRa.setPins(RADIO_CS_PIN, RADIO_RST_PIN, RADIO_DIO0_PIN);

#ifdef RADIO_TCXO_ENABLE
    pinMode(RADIO_TCXO_ENABLE, OUTPUT);
    digitalWrite(RADIO_TCXO_ENABLE, HIGH);
#endif

    if (!LoRa.begin(CONFIG_RADIO_FREQ * 1000000)) {
        Serial.println("[LoRa] begin() failed");
        return false;
    }

    LoRa.setTxPower(CONFIG_RADIO_OUTPUT_POWER);
    LoRa.setSignalBandwidth(CONFIG_RADIO_BW * 1000);
    LoRa.setSpreadingFactor(7);
    LoRa.setCodingRate4(5);
    LoRa.enableCrc();
    LoRa.receive();

    Serial.println("[LoRa] Radio ready");
    return true;
}
