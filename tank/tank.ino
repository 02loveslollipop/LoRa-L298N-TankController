#include <Arduino.h>
#include "TankShift.h"

// ---------- L298N Half-H bridge pin mapping (adjust for your wiring) ----------
// Left motor (ENA, IN1, IN2)
constexpr uint8_t LEFT_IN1 = 4;   // D2 on NodeMCU
constexpr uint8_t LEFT_IN2 = 5;   // D1 on NodeMCU
constexpr uint8_t LEFT_PWM = 13;  // D7 on NodeMCU (ENA) -> HIGH = run

// Right motor (ENB, IN3, IN4)
constexpr uint8_t RIGHT_IN1 = 14;  // D5 on NodeMCU
constexpr uint8_t RIGHT_IN2 = 12;  // D6 on NodeMCU
constexpr uint8_t RIGHT_PWM = 15;  // D8 on NodeMCU (ENB) -> PWM capable

Tank Tank(LEFT_IN1, LEFT_IN2, LEFT_PWM, RIGHT_IN1, RIGHT_IN2, RIGHT_PWM);

// Simple ANSI arrow-key parser
int escStage = 0;  // 0=normal, 1=ESC, 2='['

void handleKey(int c) {
  if (escStage == 0) {
    if (c == 0x1B) {
      escStage = 1;
      return;
    }  // ESC
    if (c == ' ') {
      Tank.stop();
      Serial.println("STOP");
      return;
    }
    // WASD fallback
    if (c == 'w' || c == 'W') {
      Tank.forward();
      Serial.println("FORWARD");
    }
    if (c == 's' || c == 'S') {
      Tank.backward();
      Serial.println("BACKWARD");
    }
    if (c == 'a' || c == 'A') {
      Tank.left();
      Serial.println("LEFT");
    }
    if (c == 'd' || c == 'D') {
      Tank.right();
      Serial.println("RIGHT");
    }
    return;
  }
  if (escStage == 1) {
    escStage = (c == '[') ? 2 : 0;
    return;
  }
  if (escStage == 2) {
    switch (c) {
      case 'A':
        Tank.forward();
        Serial.println("FORWARD");
        break;  // Up
      case 'B':
        Tank.backward();
        Serial.println("BACKWARD");
        break;  // Down
      case 'C':
        Tank.right();
        Serial.println("RIGHT");
        break;  // Right
      case 'D':
        Tank.left();
        Serial.println("LEFT");
        break;  // Left
      default: break;
    }
    escStage = 0;
  }
}

void setup() {
  Serial.begin(115200);
  while (!Serial) {}
  Serial.println("\nESP32/ESP8266 + L298N Half-H Bridge - Tank Test");
  Serial.println("Arrow keys = move, Space = stop, WASD also works.");
  Serial.println("PWM ramp enables smooth transitions between states.");

  Tank.begin();
  Tank.setRamp(10, 10);  // step size, interval ms
  Tank.forward();
  Serial.println("Starting forward...");
}

void loop() {
  while (Serial.available()) {
    handleKey(Serial.read());
  }
  Tank.update();
  delay(5);  // keep the ramp timing predictable
}
