#include "TankShift.h"

Tank::Tank(uint8_t leftIn1, uint8_t leftIn2, uint8_t leftPwm,
           uint8_t rightIn1, uint8_t rightIn2, uint8_t rightPwm)
    : leftIn1_(leftIn1), leftIn2_(leftIn2), leftPwm_(leftPwm),
      rightIn1_(rightIn1), rightIn2_(rightIn2), rightPwm_(rightPwm) {}

void Tank::begin() {
  pinMode(leftIn1_, OUTPUT);
  pinMode(leftIn2_, OUTPUT);
  pinMode(leftPwm_, OUTPUT);
  pinMode(rightIn1_, OUTPUT);
  pinMode(rightIn2_, OUTPUT);
  pinMode(rightPwm_, OUTPUT);

  // Ensure all lines start low to keep the motors idle.
  digitalWrite(leftIn1_, LOW);
  digitalWrite(leftIn2_, LOW);
  analogWrite(leftPwm_, 0);
  digitalWrite(rightIn1_, LOW);
  digitalWrite(rightIn2_, LOW);
  analogWrite(rightPwm_, 0);

  currentLeftCommand_ = 0;
  currentRightCommand_ = 0;
  targetLeftCommand_ = 0;
  targetRightCommand_ = 0;
  targetLeftDir_ = 0;
  targetRightDir_ = 0;
  lastUpdateMs_ = millis();
  stop();
}

void Tank::setSpeed(uint8_t leftSpeed, uint8_t rightSpeed) {
  maxLeftSpeed_ = constrain(leftSpeed, static_cast<uint8_t>(0), static_cast<uint8_t>(255));
  maxRightSpeed_ = constrain(rightSpeed, static_cast<uint8_t>(0), static_cast<uint8_t>(255));
  targetLeftCommand_ = targetLeftDir_ * static_cast<int>(maxLeftSpeed_);
  targetRightCommand_ = targetRightDir_ * static_cast<int>(maxRightSpeed_);
  lastUpdateMs_ = millis() - rampIntervalMs_;
}

void Tank::setDir_(int leftDir, int rightDir) {
  targetLeftDir_ = constrain(leftDir, -1, 1);
  targetRightDir_ = constrain(rightDir, -1, 1);
  targetLeftCommand_ = targetLeftDir_ * static_cast<int>(maxLeftSpeed_);
  targetRightCommand_ = targetRightDir_ * static_cast<int>(maxRightSpeed_);
  lastUpdateMs_ = millis() - rampIntervalMs_;
}

void Tank::apply_() {
  drive_(leftIn1_, leftIn2_, leftPwm_, currentLeftCommand_);
  drive_(rightIn1_, rightIn2_, rightPwm_, currentRightCommand_);
}

void Tank::drive_(uint8_t in1, uint8_t in2, uint8_t pwmPin, int command) const {
  if (command > 0) {
    digitalWrite(in1, HIGH);
    digitalWrite(in2, LOW);
  } else if (command < 0) {
    digitalWrite(in1, LOW);
    digitalWrite(in2, HIGH);
  } else {
    digitalWrite(in1, LOW);
    digitalWrite(in2, LOW);
  }

  uint8_t pwm = static_cast<uint8_t>(abs(command));
  analogWrite(pwmPin, pwm);
}

void Tank::forward() {
  setDir_(+1, +1);
  last_ = TankState::FORWARD;
}

void Tank::backward() {
  setDir_(-1, -1);
  last_ = TankState::BACKWARD;
}

void Tank::left() {
  setDir_(-1, +1);
  last_ = TankState::LEFT;
}

void Tank::right() {
  setDir_(+1, -1);
  last_ = TankState::RIGHT;
}

void Tank::stop() {
  setDir_(0, 0);
  last_ = TankState::STOP;
}

void Tank::setRamp(uint8_t step, uint16_t intervalMs) {
  rampStep_ = step == 0 ? 1 : step;
  rampIntervalMs_ = intervalMs == 0 ? 1 : intervalMs;
  lastUpdateMs_ = millis() - rampIntervalMs_;
}

void Tank::update() {
  unsigned long now = millis();
  if (now - lastUpdateMs_ < rampIntervalMs_) {
    return;
  }
  lastUpdateMs_ = now;

  int nextLeft = stepToward_(currentLeftCommand_, targetLeftCommand_);
  int nextRight = stepToward_(currentRightCommand_, targetRightCommand_);

  if (nextLeft == currentLeftCommand_ && nextRight == currentRightCommand_) {
    return;
  }

  currentLeftCommand_ = nextLeft;
  currentRightCommand_ = nextRight;
  apply_();
}

int Tank::stepToward_(int current, int target) const {
  if (current == target) {
    return current;
  }

  int step = static_cast<int>(rampStep_);

  if (target == 0) {
    if (current > 0) {
      current -= step;
      if (current < 0) {
        current = 0;
      }
    } else {
      current += step;
      if (current > 0) {
        current = 0;
      }
    }
    return current;
  }

  if (target > 0) {
    if (current < 0) {
      current += step;
      if (current > 0) {
        current = 0;
      }
      return current;
    }
    current += step;
    if (current > target) {
      current = target;
    }
    return current;
  }

  // target < 0
  if (current > 0) {
    current -= step;
    if (current < 0) {
      current = 0;
    }
    return current;
  }
  current -= step;
  if (current < target) {
    current = target;
  }
  return current;
}
