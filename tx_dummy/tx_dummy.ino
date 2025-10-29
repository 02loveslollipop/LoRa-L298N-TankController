#include <Arduino.h>

#if defined(ESP32)
#include <WiFi.h>
#elif defined(ESP8266)
#include <ESP8266WiFi.h>
#else
#error "Dummy RX currently supports ESP32/ESP8266 targets."
#endif

#include <WebSocketsClient.h>
#include <cstring>

#include "config.h"

namespace {

WebSocketsClient wsClient;
bool wsConnected = false;
unsigned long lastStatusPrint = 0;
unsigned long lastHeartbeat = 0;
constexpr uint32_t HEARTBEAT_INTERVAL = 5000; // Send status every 5 seconds

bool connectWiFi() {
  Serial.print("[INFO] Connecting to WiFi: ");
  Serial.println(CONFIG_WIFI_SSID);

  WiFi.mode(WIFI_STA);
  WiFi.begin(CONFIG_WIFI_SSID, CONFIG_WIFI_PASSWORD);

  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED &&
         millis() - start < CONFIG_WIFI_CONNECT_TIMEOUT_MS) {
    delay(250);
    Serial.print('.');
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("[INFO] Connected! IP: ");
    Serial.println(WiFi.localIP());
    return true;
  }

  Serial.println("[ERR] WiFi connection failed.");
  return false;
}

void onWebSocketEvent(WStype_t type, uint8_t *payload, size_t length) {
  switch (type) {
    case WStype_CONNECTED: {
      wsConnected = true;
      Serial.print("[INFO] WebSocket connected to: ");
      Serial.println(CONFIG_WS_PATH);
      // Send initial status to keep connection alive
      lastHeartbeat = millis();
      Serial.println("[TX] Sending initial status...");
      bool sent = wsClient.sendTXT("{\"type\":\"status\",\"state\":\"connected\",\"uptime\":0}");
      Serial.printf("[TX] Initial status sent: %s\n", sent ? "SUCCESS" : "FAILED");
      break;
    }
    case WStype_DISCONNECTED:
      wsConnected = false;
      Serial.println("[WARN] WebSocket disconnected; will retry.");
      break;
    case WStype_TEXT: {
      Serial.print("[RX] ");
      for (size_t i = 0; i < length; ++i) {
        Serial.print(static_cast<char>(payload[i]));
      }
      Serial.println();
      break;
    }
    case WStype_BIN:
      Serial.print("[RX] Binary payload (");
      Serial.print(length);
      Serial.println(" bytes)");
      break;
    case WStype_ERROR:
      Serial.println("[ERR] WebSocket error");
      break;
    case WStype_PING:
      Serial.println("[INFO] WebSocket ping");
      break;
    case WStype_PONG:
      Serial.println("[INFO] WebSocket pong");
      break;
    default:
      break;
  }
}

void connectWebSocket() {
  Serial.print("[INFO] Connecting to WebSocket: ");
  Serial.print(CONFIG_WS_HOST);
  Serial.print(':');
  Serial.print(CONFIG_WS_PORT);
  Serial.println(CONFIG_WS_PATH);

  if (CONFIG_WS_SECURE) {
    wsClient.beginSSL(CONFIG_WS_HOST, CONFIG_WS_PORT, CONFIG_WS_PATH);
  } else {
    wsClient.begin(CONFIG_WS_HOST, CONFIG_WS_PORT, CONFIG_WS_PATH);
  }
  wsClient.onEvent(onWebSocketEvent);
  if (CONFIG_WS_AUTH_HEADER && strlen(CONFIG_WS_AUTH_HEADER) > 0) {
    wsClient.setExtraHeaders(CONFIG_WS_AUTH_HEADER);
  }
  wsClient.setReconnectInterval(CONFIG_WS_RECONNECT_INTERVAL_MS);
  // Disable built-in heartbeat to avoid conflicts with our manual heartbeat
  // wsClient.enableHeartbeat(15000, 3000, 2);
}

}  // namespace

void setup() {
  Serial.begin(115200);
  while (!Serial) {
    delay(10);
  }

  Serial.println("\nDummy RX | WebSocket listener");
  Serial.println("Connects to configured host and logs incoming messages.");

  if (!connectWiFi()) {
    Serial.println("[FATAL] Unable to establish WiFi. Restarting in 5 seconds.");
    delay(5000);
    ESP.restart();
  }

  connectWebSocket();
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[WARN] WiFi lost; attempting reconnect.");
    if (!connectWiFi()) {
      Serial.println("[ERR] WiFi reconnect failed; will retry.");
      delay(1000);
      return;
    }
    connectWebSocket();
  }

  if (!wsConnected && WiFi.status() == WL_CONNECTED) {
    unsigned long now = millis();
    if (now - lastStatusPrint > CONFIG_WS_RECONNECT_INTERVAL_MS) {
      Serial.println("[INFO] Awaiting WebSocket connection...");
      lastStatusPrint = now;
    }
  }

  wsClient.loop();

  // Send periodic heartbeat to keep connection alive
  if (wsConnected && millis() - lastHeartbeat > HEARTBEAT_INTERVAL) {
    lastHeartbeat = millis();
    char msg[128];
    snprintf(msg, sizeof(msg), 
             "{\"type\":\"status\",\"state\":\"running\",\"uptime\":%lu,\"freeHeap\":%u}",
             millis() / 1000, ESP.getFreeHeap());
    Serial.printf("[TX] Sending heartbeat: %s\n", msg);
    bool sent = wsClient.sendTXT(msg);
    Serial.printf("[TX] Heartbeat sent: %s\n", sent ? "SUCCESS" : "FAILED");
  }
}
