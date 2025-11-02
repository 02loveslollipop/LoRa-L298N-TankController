#ifndef CONFIG_H
#define CONFIG_H

// ---------- WiFi Configuration ----------
#define WIFI_SSID           "UPBWiFi"
#define WIFI_PASSWORD       ""

// ---------- WebSocket Server Configuration ----------
#define WS_SERVER_HOST      "ws.nene.02labs.me"
#define WS_SERVER_PORT      80
#define TANK_ID             "tank_001"

// If using local testing:
// #define WS_SERVER_HOST      "192.168.1.100"
// #define WS_SERVER_PORT      8000

// For WSS (secure WebSocket), use port 443 and modify webSocket.begin() to use SSL

// ---------- Safety Configuration ----------
#define WATCHDOG_TIMEOUT_MS 2000    // Emergency stop after 2 seconds
#define STATUS_INTERVAL_MS  5000    // Send status every 5 seconds

// ---------- Motor Configuration ----------
#define DEFAULT_SPEED       200     // 0-255
#define RAMP_STEP           10      // PWM units per update
#define RAMP_INTERVAL_MS    10      // Update every 10ms

#endif // CONFIG_H
