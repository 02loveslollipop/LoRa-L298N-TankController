#pragma once
#include <Arduino.h>

enum class TankState { STOP, FORWARD, BACKWARD, LEFT, RIGHT };

class Tank {
public:
  // 74HC595 pins (ESP32 GPIOs)
  Tank(uint8_t serPin, uint8_t clkPin, uint8_t latchPin, uint8_t oePin,
       // bit masks for the 74HC595 output lines -> L293D inputs
       uint8_t L_IN1_mask = 0b00000001, 
       uint8_t L_IN2_mask = 0b00000010,
       uint8_t R_IN1_mask = 0b00000100,
       uint8_t R_IN2_mask = 0b00001000);

  void begin();
  void forward();   // both forward
  void backward();  // both backward
  void left();      // spin left: left back, right fwd
  void right();     // spin right: left fwd, right back
  void stop();      // all low

  TankState state() const { return last_; }

  // For debugging / customization
  void writeRegister(uint8_t value);
  uint8_t currentRegister() const { return reg_; }

private:
  uint8_t SER_, CLK_, LATCH_, OE_;
  uint8_t L1_, L2_, R1_, R2_;
  volatile uint8_t reg_ = 0;     // shadow of 74HC595 outputs
  TankState last_ = TankState::STOP;

  inline void pulse_(uint8_t pin) {
    digitalWrite(pin, HIGH); delayMicroseconds(2);
    digitalWrite(pin, LOW);  delayMicroseconds(2);
  }

  void setDir_(int leftDir, int rightDir);
  // leftDir/rightDir: -1 back, 0 stop, +1 forward
};
