#include "TankShift.h"

Tank::Tank(uint8_t serPin, uint8_t clkPin, uint8_t latchPin, uint8_t oePin,
           uint8_t L_IN1_mask, uint8_t L_IN2_mask,
           uint8_t R_IN1_mask, uint8_t R_IN2_mask)
: SER_(serPin), CLK_(clkPin), LATCH_(latchPin), OE_(oePin),
  L1_(L_IN1_mask), L2_(L_IN2_mask), R1_(R_IN1_mask), R2_(R_IN2_mask) {}

void Tank::begin() {
  pinMode(SER_, OUTPUT);
  pinMode(CLK_, OUTPUT);
  pinMode(LATCH_, OUTPUT);
  pinMode(OE_, OUTPUT);
  digitalWrite(SER_, LOW);
  digitalWrite(CLK_, LOW);
  digitalWrite(LATCH_, LOW);
  // 74HC595 OE is active LOW -> keep outputs enabled:
  digitalWrite(OE_, LOW);
  stop();
}

void Tank::writeRegister(uint8_t value) {
  // shift out MSB first (like your sample)
  uint8_t v = value;
  for (uint8_t i = 0; i < 8; ++i) { //Pass 8bit 
    digitalWrite(SER_, (v & 0x80) ? HIGH : LOW); //
    pulse_(CLK_);
    v <<= 1;
  }
  pulse_(LATCH_);
  reg_ = value;
}

void Tank::setDir_(int leftDir, int rightDir) {
  uint8_t v = 0;

  // Left motor pins
  if (leftDir > 0)      { v |= L1_; /* IN1=1 */              } // IN2 stays 0
  else if (leftDir < 0) { v |= L2_; /* IN2=1 */              } // IN1 stays 0
  // if 0 -> both 0 (coast/brake per shield wiring)

  // Right motor pins
  if (rightDir > 0)      { v |= R1_; }
  else if (rightDir < 0) { v |= R2_; }

  writeRegister(v);
}

void Tank::forward()  { setDir_(+1, +1); last_ = TankState::FORWARD;  }
void Tank::backward() { setDir_(-1, -1); last_ = TankState::BACKWARD; }
void Tank::left()     { setDir_(-1, +1); last_ = TankState::LEFT;     }
void Tank::right()    { setDir_(+1, -1); last_ = TankState::RIGHT;    }
void Tank::stop()     { setDir_( 0,  0); last_ = TankState::STOP;     }
