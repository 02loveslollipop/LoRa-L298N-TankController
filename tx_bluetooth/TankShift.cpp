#include "TankShift.h"

Tank::Tank(uint8_t leftIn1, uint8_t leftIn2, uint8_t leftPwm,
           uint8_t rightIn1, uint8_t rightIn2, uint8_t rightPwm)
    : _leftIn1(leftIn1), _leftIn2(leftIn2), _leftPwm(leftPwm),
      _rightIn1(rightIn1), _rightIn2(rightIn2), _rightPwm(rightPwm) {
}

void Tank::begin() {
    pinMode(_leftIn1, OUTPUT);
    pinMode(_leftIn2, OUTPUT);
    pinMode(_leftPwm, OUTPUT);
    pinMode(_rightIn1, OUTPUT);
    pinMode(_rightIn2, OUTPUT);
    pinMode(_rightPwm, OUTPUT);

    stop();
}

void Tank::setRamp(uint8_t step, uint8_t interval) {
    _rampStep = step;
    _rampInterval = interval;
}

void Tank::setSpeed(uint8_t left, uint8_t right) {
    int16_t newLeft = left;
    int16_t newRight = right;
    
    // Preserve direction, update magnitude
    if (_targetLeftSpeed < 0) newLeft = -newLeft;
    if (_targetRightSpeed < 0) newRight = -newRight;
    
    _targetLeftSpeed = newLeft;
    _targetRightSpeed = newRight;
}

void Tank::forward() {
    _targetLeftSpeed = abs(_targetLeftSpeed);
    _targetRightSpeed = abs(_targetRightSpeed);
}

void Tank::backward() {
    _targetLeftSpeed = -abs(_targetLeftSpeed);
    _targetRightSpeed = -abs(_targetRightSpeed);
}

void Tank::left() {
    _targetLeftSpeed = -abs(_targetLeftSpeed);
    _targetRightSpeed = abs(_targetRightSpeed);
}

void Tank::right() {
    _targetLeftSpeed = abs(_targetLeftSpeed);
    _targetRightSpeed = -abs(_targetRightSpeed);
}

void Tank::stop() {
    _targetLeftSpeed = 0;
    _targetRightSpeed = 0;
}

void Tank::update() {
    uint32_t now = millis();
    if (now - _lastRampTime < _rampInterval) {
        return;
    }
    _lastRampTime = now;

    // Ramp left motor
    if (_currentLeftSpeed < _targetLeftSpeed) {
        _currentLeftSpeed = min((int16_t)(_currentLeftSpeed + _rampStep), _targetLeftSpeed);
    } else if (_currentLeftSpeed > _targetLeftSpeed) {
        _currentLeftSpeed = max((int16_t)(_currentLeftSpeed - _rampStep), _targetLeftSpeed);
    }

    // Ramp right motor
    if (_currentRightSpeed < _targetRightSpeed) {
        _currentRightSpeed = min((int16_t)(_currentRightSpeed + _rampStep), _targetRightSpeed);
    } else if (_currentRightSpeed > _targetRightSpeed) {
        _currentRightSpeed = max((int16_t)(_currentRightSpeed - _rampStep), _targetRightSpeed);
    }

    driveLeft(_currentLeftSpeed);
    driveRight(_currentRightSpeed);
}

void Tank::driveLeft(int16_t speed) {
    if (speed > 0) {
        digitalWrite(_leftIn1, HIGH);
        digitalWrite(_leftIn2, LOW);
        analogWrite(_leftPwm, speed);
    } else if (speed < 0) {
        digitalWrite(_leftIn1, LOW);
        digitalWrite(_leftIn2, HIGH);
        analogWrite(_leftPwm, -speed);
    } else {
        digitalWrite(_leftIn1, LOW);
        digitalWrite(_leftIn2, LOW);
        analogWrite(_leftPwm, 0);
    }
}

void Tank::driveRight(int16_t speed) {
    if (speed > 0) {
        digitalWrite(_rightIn1, HIGH);
        digitalWrite(_rightIn2, LOW);
        analogWrite(_rightPwm, speed);
    } else if (speed < 0) {
        digitalWrite(_rightIn1, LOW);
        digitalWrite(_rightIn2, HIGH);
        analogWrite(_rightPwm, -speed);
    } else {
        digitalWrite(_rightIn1, LOW);
        digitalWrite(_rightIn2, LOW);
        analogWrite(_rightPwm, 0);
    }
}
