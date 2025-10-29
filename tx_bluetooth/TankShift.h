#ifndef TANK_SHIFT_H
#define TANK_SHIFT_H

#include <Arduino.h>

class Tank {
public:
    Tank(uint8_t leftIn1, uint8_t leftIn2, uint8_t leftPwm,
         uint8_t rightIn1, uint8_t rightIn2, uint8_t rightPwm);

    void begin();
    void setRamp(uint8_t step, uint8_t interval);
    void setSpeed(uint8_t left, uint8_t right);
    void forward();
    void backward();
    void left();
    void right();
    void stop();
    void update();

private:
    uint8_t _leftIn1, _leftIn2, _leftPwm;
    uint8_t _rightIn1, _rightIn2, _rightPwm;

    int16_t _targetLeftSpeed = 0;
    int16_t _targetRightSpeed = 0;
    int16_t _currentLeftSpeed = 0;
    int16_t _currentRightSpeed = 0;

    uint8_t _rampStep = 10;
    uint8_t _rampInterval = 10;
    uint32_t _lastRampTime = 0;

    void driveLeft(int16_t speed);
    void driveRight(int16_t speed);
};

#endif // TANK_SHIFT_H
