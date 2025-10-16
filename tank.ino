#include <Arduino.h>
#include "TankShift.h"

// ---------- 74HC595 <-> ESP32 pins (use your wiring) ----------
constexpr uint8_t kSER   = 21; // data
constexpr uint8_t kCLK   = 19; // shift clock
constexpr uint8_t kLATCH = 23; // latch
constexpr uint8_t kOE    = 18; // output enable (active LOW)
// ---------- Bit mapping (adjust if needed) ----------
constexpr uint8_t L_IN1 = 0b00000001; // left motor IN1
constexpr uint8_t L_IN2 = 0b00000010; // left motor IN2
constexpr uint8_t R_IN1 = 0b00000100; // right motor IN1
constexpr uint8_t R_IN2 = 0b00001000; // right motor IN2

Tank Tank(kSER, kCLK, kLATCH, kOE, L_IN1, L_IN2, R_IN1, R_IN2);

// Simple ANSI arrow-key parser
int escStage = 0; // 0=normal, 1=ESC, 2='['

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

void setup() {
  Serial.begin(115200);
  while (!Serial) {}
  Serial.println("\nESP32 + L293D Shield (74HC595) - Tank Test");
  Serial.println("Arrow keys = move, Space = stop, WASD also works.");
  Serial.println("OE is active-LOW; keeping it LOW enables outputs.");

  Tank.begin();
  Tank.stop();
}

void loop() {
  while (Serial.available()) {
    handleKey(Serial.read());
  }
}
