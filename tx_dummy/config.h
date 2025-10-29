#pragma once

// WiFi configuration
constexpr const char *CONFIG_WIFI_SSID = "UPBWiFi";
constexpr const char *CONFIG_WIFI_PASSWORD = "";

// Soft AP fallback (activated if STA connection fails)
constexpr const char *CONFIG_AP_SSID = "TankDummy";
constexpr const char *CONFIG_AP_PASSWORD = "changeme123";
constexpr uint32_t CONFIG_WIFI_CONNECT_TIMEOUT_MS = 15000;

// WebSocket endpoint for tank connections
constexpr const char *CONFIG_WS_HOST = "controllserver-env.eba-erumaege.us-east-1.elasticbeanstalk.com";
constexpr uint16_t CONFIG_WS_PORT = 80;
constexpr const char *CONFIG_WS_PATH = "/ws/tank/dummy";
constexpr bool CONFIG_WS_SECURE = false;

// Optional Authorization header (format: "Authorization: Bearer TOKEN")
constexpr const char *CONFIG_WS_AUTH_HEADER = "";

constexpr uint32_t CONFIG_WS_RECONNECT_INTERVAL_MS = 5000;
