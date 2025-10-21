#pragma once
#include <Arduino.h>

enum class TankState { STOP, FORWARD, BACKWARD, LEFT, RIGHT };

class Tank {
public:
  // Map each half-H bridge: IN1, IN2, PWM (ENA/ENB).
  Tank(uint8_t leftIn1, uint8_t leftIn2, uint8_t leftPwm,
       uint8_t rightIn1, uint8_t rightIn2, uint8_t rightPwm);

  void begin();
  void forward();   // both motors forward
  void backward();  // both motors backward
  void left();      // spin left: left back, right forward
  void right();     // spin right: left forward, right back
  void stop();      // disable both motors (coast)

  void setSpeed(uint8_t leftSpeed, uint8_t rightSpeed); // Max PWM (0-255)
  uint8_t leftSpeed()  const { return maxLeftSpeed_; }
  uint8_t rightSpeed() const { return maxRightSpeed_; }
  void setRamp(uint8_t step, uint16_t intervalMs);      // ramp resolution
  void update();                                        // call every loop tick
  TankState state() const { return last_; }

private:
  void setDir_(int leftDir, int rightDir); // -1 back, 0 stop, +1 forward
  void apply_();
  void drive_(uint8_t in1, uint8_t in2, uint8_t pwmPin, int command) const;
  int stepToward_(int current, int target) const;

  uint8_t leftIn1_, leftIn2_, leftPwm_;
  uint8_t rightIn1_, rightIn2_, rightPwm_;

  int targetLeftDir_ = 0;
  int targetRightDir_ = 0;
  int targetLeftCommand_ = 0;   // -255..255
  int targetRightCommand_ = 0;  // -255..255
  int currentLeftCommand_ = 0;  // -255..255
  int currentRightCommand_ = 0; // -255..255

  uint8_t maxLeftSpeed_ = 255;
  uint8_t maxRightSpeed_ = 255;
  uint8_t rampStep_ = 8;
  uint16_t rampIntervalMs_ = 15;
  unsigned long lastUpdateMs_ = 0;

  TankState last_ = TankState::STOP;
};
