#include <Arduino.h>
#include <SPI.h>
#include <LoRa.h>
#include "TankShift.h"
#include "../common/ControlProtocol.h"
#include "LoRaBoards.h"

#if !defined(ESP32)
#error "Current RX build targets the LilyGO T-Beam (ESP32)."
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

// ---------- L298N Half-H bridge pin mapping for LilyGO T-Beam ----------
// Avoid LoRa DIO lines (GPIO32/33) which are wired to the SX1276 module.
constexpr uint8_t LEFT_IN1  = 22;
constexpr uint8_t LEFT_IN2  = 21;
constexpr uint8_t LEFT_PWM  = 25;  // DAC/PWM capable (ENA)
constexpr uint8_t RIGHT_IN1 = 15;
constexpr uint8_t RIGHT_IN2 = 13;
constexpr uint8_t RIGHT_PWM = 14;  // PWM capable (ENB)

Tank Tank(LEFT_IN1, LEFT_IN2, LEFT_PWM, RIGHT_IN1, RIGHT_IN2, RIGHT_PWM);

// Simple ANSI arrow-key parser (serial fallback)
int escStage = 0; // 0=normal, 1=ESC, 2='['

uint8_t expectedSequence = 0;
bool hasSequence = false;
unsigned long lastFrameTimestamp = 0;

TankControl::ControlFrame lastFrame{};

void logState(const char *label) {
  Serial.print(label);
  Serial.print(" | cmd=");
  Serial.print(static_cast<int>(lastFrame.command));
  Serial.print(" seq=");
  Serial.print(lastFrame.sequence);
  Serial.print(" left=");
  Serial.print(lastFrame.leftSpeed);
  Serial.print(" right=");
  Serial.println(lastFrame.rightSpeed);
}

void handleKey(int c) {
  if (escStage == 0) {
    if (c == 0x1B) { escStage = 1; return; }  // ESC
    if (c == ' ')  { Tank.stop(); Serial.println("STOP"); return; }
    // WASD fallback
    if (c == 'w' || c == 'W') { Tank.forward();  Serial.println("FORWARD"); }
    if (c == 's' || c == 'S') { Tank.backward(); Serial.println("BACKWARD"); }
    if (c == 'a' || c == 'A') { Tank.left();     Serial.println("LEFT"); }
    if (c == 'd' || c == 'D') { Tank.right();    Serial.println("RIGHT"); }
    return;
  }
  if (escStage == 1) {
    escStage = (c == '[') ? 2 : 0;
    return;
  }
  if (escStage == 2) {
    switch (c) {
      case 'A': Tank.forward();  Serial.println("FORWARD");  break; // Up
      case 'B': Tank.backward(); Serial.println("BACKWARD"); break; // Down
      case 'C': Tank.right();    Serial.println("RIGHT");    break; // Right
      case 'D': Tank.left();     Serial.println("LEFT");     break; // Left
      default: break;
    }
    escStage = 0;
  }
}

void applyCommand(const TankControl::ControlFrame &frame) {
  lastFrame = frame;
  lastFrameTimestamp = millis();
  Tank.setSpeed(frame.leftSpeed, frame.rightSpeed);

  switch (TankControl::commandFromFrame(frame)) {
    case TankControl::Command::Stop:
      Tank.stop();
      logState("LoRa -> STOP");
      break;
    case TankControl::Command::Forward:
      Tank.forward();
      logState("LoRa -> FORWARD");
      break;
    case TankControl::Command::Backward:
      Tank.backward();
      logState("LoRa -> BACKWARD");
      break;
    case TankControl::Command::Left:
      Tank.left();
      logState("LoRa -> LEFT");
      break;
    case TankControl::Command::Right:
      Tank.right();
      logState("LoRa -> RIGHT");
      break;
    case TankControl::Command::SetSpeed:
      logState("LoRa -> SPEED");
      break;
    default:
      Tank.stop();
      logState("LoRa -> STOP");
      break;
  }
}

void handleLoRa() {
  int packetSize = LoRa.parsePacket();
  if (packetSize <= 0) {
    return;
  }

  uint8_t buffer[TankControl::kFrameSize];
  int len = min(packetSize, static_cast<int>(sizeof(buffer)));
  for (int i = 0; i < len; ++i) {
    buffer[i] = static_cast<uint8_t>(LoRa.read());
  }
  while (LoRa.available()) {
    LoRa.read();
  }

  if (len != static_cast<int>(TankControl::kFrameSize)) {
    Serial.println("LoRa packet discarded: unexpected length");
    return;
  }

  TankControl::ControlFrame frame;
  if (!TankControl::decryptFrame(buffer, TankControl::kFrameSize, frame)) {
    Serial.println("LoRa packet discarded: decrypt/CRC failed");
    return;
  }

  if (hasSequence && frame.sequence == expectedSequence) {
    Serial.println("LoRa packet ignored: duplicate sequence");
    return;
  }

  expectedSequence = frame.sequence;
  hasSequence = true;
  applyCommand(frame);
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

  Serial.println("LoRa radio ready.");
  return true;
}

void setup() {
  setupBoards(/*disable_u8g2=*/true);  // or false if you want the OLED splash
  delay(1500); // allow PMU rails to stabilize before accessing peripherals
  Serial.begin(115200);
  while (!Serial) { delay(10); }
  Serial.println("\nT-Beam RX | L298N Tank Controller");
  Serial.println("LoRa listener + PWM ramp drivetrain");
  Serial.println("Serial fallback: Arrow keys = move, Space = stop.");

  Tank.begin();
  Tank.setRamp(10, 10); // step size, interval ms
  Tank.stop();

  if (!beginLoRa()) {
    Serial.println("LoRa setup failed; continuing with serial-only control.");
  }
}

void loop() {
  while (Serial.available()) {
    int c = Serial.read();
    handleKey(c);
    if (c == 'f' || c == 'F') { Tank.forward(); Serial.println("FORWARD"); }
    if (c == 'b' || c == 'B') { Tank.backward(); Serial.println("BACKWARD"); }
    if (c == 'l' || c == 'L') { Tank.left(); Serial.println("LEFT"); }
    if (c == 'r' || c == 'R') { Tank.right(); Serial.println("RIGHT"); }
    if (c == ' ')            { Tank.stop(); Serial.println("STOP"); }
  }
  handleLoRa();
  Tank.update();
  delay(5); // keep the ramp timing predictable
}
