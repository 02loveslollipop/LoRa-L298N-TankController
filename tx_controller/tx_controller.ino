#include <Arduino.h>
#include <SPI.h>
#include <LoRa.h>
#include <WiFi.h>
#include <esp_system.h>
#include <WebServer.h>
#include "../common/ControlProtocol.h"
#include "LoRaBoards.h"

// ---------- Board selection: LilyGO T-Beam (ESP32) ----------
#if !defined(ESP32)
#error "This TX build targets the LilyGO T-Beam (ESP32)."
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

constexpr const char *kApSsid     = "TankController";
constexpr const char *kApPassword = "tank12345";

WebServer server(80);

uint8_t sequenceCounter = 0;
uint8_t currentLeftSpeed = 255;
uint8_t currentRightSpeed = 255;
String lastState = "STOP";

const char indexPage[] PROGMEM = R"rawliteral(
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Tank Controller TX</title>
  <style>
    body { font-family: sans-serif; margin: 0; padding: 2rem; background: #101820; color: #eee; }
    h1 { margin-top: 0; }
    button { width: 8rem; height: 3rem; margin: 0.5rem; font-size: 1rem; border: none; border-radius: 0.5rem; cursor: pointer; background: #ff7a18; color: #101820; }
    button.stop { background: #ff3b30; color: #fff; }
    #status { margin-top: 1.5rem; font-size: 1.1rem; }
    .pad { display: grid; grid-template-columns: repeat(3, 8.5rem); grid-template-rows: repeat(3, 3.5rem); gap: 0.5rem; justify-content: center; margin-top: 2rem; }
    .pad button { width: 100%; height: 100%; }
    .speeds { margin-top: 2rem; display: flex; gap: 1.5rem; justify-content: center; }
    .speeds label { display: flex; flex-direction: column; align-items: center; font-size: 0.9rem; }
    input[type=range] { width: 200px; }
    footer { margin-top: 3rem; font-size: 0.85rem; color: #aaa; text-align: center; }
  </style>
</head>
<body>
  <h1>T-Beam Tank Controller</h1>
  <p>Tap a button to send a command over LoRa. Commands are AES-256 encrypted.</p>
  <div class="pad">
    <div></div>
    <button data-cmd="forward">Forward</button>
    <div></div>
    <button data-cmd="left">Left</button>
    <button class="stop" data-cmd="stop">Stop</button>
    <button data-cmd="right">Right</button>
    <div></div>
    <button data-cmd="backward">Backward</button>
    <div></div>
  </div>
  <div class="speeds">
    <label>Left speed
      <input id="leftSpeed" type="range" min="0" max="255" value="255">
      <span id="leftValue">255</span>
    </label>
    <label>Right speed
      <input id="rightSpeed" type="range" min="0" max="255" value="255">
      <span id="rightValue">255</span>
    </label>
    <button data-cmd="speed" id="speedBtn">Set Speeds</button>
  </div>
  <div id="status">State: IDLE</div>
  <footer>Connect to the TankController Wi-Fi network (password: tank12345).</footer>
  <script>
    const statusEl = document.getElementById('status');
    const left = document.getElementById('leftSpeed');
    const right = document.getElementById('rightSpeed');
    const leftValue = document.getElementById('leftValue');
    const rightValue = document.getElementById('rightValue');

    function updateLabels() {
      leftValue.textContent = left.value;
      rightValue.textContent = right.value;
    }
    left.addEventListener('input', updateLabels);
    right.addEventListener('input', updateLabels);
    updateLabels();

    async function sendCommand(cmd) {
      statusEl.textContent = 'State: sending...';
      const params = new URLSearchParams({ action: cmd });
      if (cmd === 'speed') {
        params.set('left', left.value);
        params.set('right', right.value);
      }
      try {
        const res = await fetch('/cmd', { method: 'POST', body: params });
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();
        statusEl.textContent = `State: ${data.state}`;
      } catch (err) {
        statusEl.textContent = 'State: ERROR - ' + err.message;
      }
    }

    document.querySelectorAll('button[data-cmd]').forEach(btn => {
      btn.addEventListener('click', () => sendCommand(btn.dataset.cmd));
    });
    document.getElementById('speedBtn').addEventListener('click', () => sendCommand('speed'));
  </script>
</body>
</html>
)rawliteral";

TankControl::Command parseCommand(const String &action) {
  if (action == "forward") return TankControl::Command::Forward;
  if (action == "backward") return TankControl::Command::Backward;
  if (action == "left") return TankControl::Command::Left;
  if (action == "right") return TankControl::Command::Right;
  if (action == "speed") return TankControl::Command::SetSpeed;
  return TankControl::Command::Stop;
}

bool sendLoRaFrame(TankControl::Command cmd, uint8_t leftSpeed, uint8_t rightSpeed) {
  TankControl::ControlFrame frame;
  TankControl::initFrame(frame, cmd, leftSpeed, rightSpeed, sequenceCounter++);

  uint8_t encrypted[TankControl::kFrameSize];
  if (!TankControl::encryptFrame(frame, encrypted, sizeof(encrypted))) {
    Serial.println("Encrypt failed");
    return false;
  }

  LoRa.idle();
  LoRa.beginPacket();
  LoRa.write(encrypted, sizeof(encrypted));
  bool ok = LoRa.endPacket() == 1;
  LoRa.receive();

  if (ok) {
    Serial.print("TX -> cmd=");
    Serial.print(static_cast<int>(frame.command));
    Serial.print(" seq=");
    Serial.print(frame.sequence);
    Serial.print(" left=");
    Serial.print(frame.leftSpeed);
    Serial.print(" right=");
    Serial.println(frame.rightSpeed);
  } else {
    Serial.println("LoRa TX failed");
  }
  return ok;
}

void sendSpectrumTestBurst() {
  static constexpr size_t kBurstSize = 192;
  uint8_t payload[kBurstSize];
  for (size_t i = 0; i < kBurstSize; ++i) {
    payload[i] = static_cast<uint8_t>(random(0, 256));
  }

  Serial.println("Sending LoRa spectrum test burst...");
  LoRa.idle();
  LoRa.beginPacket();
  LoRa.write(payload, sizeof(payload));
  if (LoRa.endPacket() == 1) {
    Serial.print("Burst length: ");
    Serial.println(sizeof(payload));
  } else {
    Serial.println("Spectrum test burst failed to transmit");
  }
  LoRa.receive();
}

void handleWebRoot() {
  server.send_P(200, "text/html", indexPage);
}

void handleWebCommand() {
  if (!server.hasArg("action")) {
    server.send(400, "application/json", "{\"error\":\"missing action\"}");
    return;
  }

  String action = server.arg("action");
  action.toLowerCase();
  TankControl::Command cmd = parseCommand(action);
  bool ok = true;

  if (cmd == TankControl::Command::SetSpeed) {
    int left = server.hasArg("left") ? server.arg("left").toInt() : currentLeftSpeed;
    int right = server.hasArg("right") ? server.arg("right").toInt() : currentRightSpeed;
    left = constrain(left, 0, 255);
    right = constrain(right, 0, 255);
    currentLeftSpeed = static_cast<uint8_t>(left);
    currentRightSpeed = static_cast<uint8_t>(right);
    ok = sendLoRaFrame(cmd, currentLeftSpeed, currentRightSpeed);
    if (ok) {
      lastState = "SPEED";
    }
  } else {
    ok = sendLoRaFrame(cmd, currentLeftSpeed, currentRightSpeed);
    if (ok) {
      switch (cmd) {
        case TankControl::Command::Forward: lastState = "FORWARD"; break;
        case TankControl::Command::Backward: lastState = "BACKWARD"; break;
        case TankControl::Command::Left: lastState = "LEFT"; break;
        case TankControl::Command::Right: lastState = "RIGHT"; break;
        case TankControl::Command::Stop: lastState = "STOP"; break;
        default: break;
      }
    }
  }

  if (!ok) {
    server.send(500, "application/json", "{\"error\":\"lora tx failed\"}");
    return;
  }

  String body = "{\"state\":\"";
  body += lastState;
  body += "\"}";
  server.send(200, "application/json", body);
}

bool beginLoRa() {
  SPI.begin(RADIO_SCLK_PIN, RADIO_MISO_PIN, RADIO_MOSI_PIN, RADIO_CS_PIN);
  LoRa.setPins(RADIO_CS_PIN, RADIO_RST_PIN, RADIO_DIO0_PIN);

#ifdef RADIO_TCXO_ENABLE
  pinMode(RADIO_TCXO_ENABLE, OUTPUT);
  digitalWrite(RADIO_TCXO_ENABLE, HIGH);
#endif

  if (!LoRa.begin(CONFIG_RADIO_FREQ * 1000000)) {
    Serial.println("LoRa init failed. Check wiring.");
    return false;
  }

  LoRa.setTxPower(CONFIG_RADIO_OUTPUT_POWER);
  LoRa.setSignalBandwidth(CONFIG_RADIO_BW * 1000);
  LoRa.setSpreadingFactor(7);
  LoRa.setCodingRate4(5);
  LoRa.enableCrc();
  LoRa.receive();

  Serial.println("LoRa radio ready (TX).");
  return true;
}

void setup() {
  setupBoards(/*disable_u8g2=*/true);  // or false if you want the OLED splash
  delay(1500); // allow PMU rails to stabilize per LoRaBoards reference implementation
  while (!Serial) { delay(10); }

  Serial.println("\nT-Beam TX | LoRa Tank Controller");
  Serial.println("Hosting Wi-Fi AP + Web UI, relaying commands over AES-256 LoRa.");

  bool radioReady = beginLoRa();
  if (!radioReady) {
    Serial.println("LoRa setup failed; reboot after checking the radio module.");
  } else {
    randomSeed(esp_random());
    sendSpectrumTestBurst();
  }

  WiFi.mode(WIFI_AP);
  if (WiFi.softAP(kApSsid, kApPassword)) {
    Serial.print("SoftAP ready. SSID: ");
    Serial.print(kApSsid);
    Serial.print("  Password: ");
    Serial.println(kApPassword);
    Serial.print("AP IP address: ");
    Serial.println(WiFi.softAPIP());
  } else {
    Serial.println("Failed to start SoftAP.");
  }

  server.on("/", HTTP_GET, handleWebRoot);
  server.on("/cmd", HTTP_POST, handleWebCommand);
  server.onNotFound([]() {
    server.send(404, "application/json", "{\"error\":\"not found\"}");
  });
  server.begin();
  Serial.println("Web UI ready at http://" + WiFi.softAPIP().toString());
}

void loop() {
  server.handleClient();
}
