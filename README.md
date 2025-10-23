## 📌 Introduction

This project ships with a lightweight Arduino C++ helper (`TankShift`) that drives a dual **L298N** module in half-H configuration. Each motor is controlled with two direction inputs and a single enable pin (ENA / ENB). The library wraps those lines behind a tank-style API, adds PWM speed control, and ramps between states for smooth transitions on an **ESP8266** or **ESP32**.

The example sketch (`tank.ino`) listens to serial input (WASD or arrow keys) and translates the commands into forward, reverse, spin-left, spin-right, or stop actions.

---

## ⚙️ Core Components

### L298N Dual H-Bridge
The **L298N** exposes two identical half-H bridges. Each side needs:

- `INx1` / `INx2` to choose direction
- `ENx` to gate power (HIGH = run, LOW = stop)

The helper class toggles those pins directly and drives the enable lines with PWM, ramping between targets so direction changes feel smooth.

---

## Usage & Code Logic

- Call `Tank.begin()` once to set the pin modes and stop both motors.
- Use `.forward()`, `.backward()`, `.left()`, `.right()`, or `.stop()` to command the chassis.
- `setSpeed(left, right)` defines the PWM ceiling (0–255) for each side.
- `setRamp(step, intervalMs)` tunes how aggressively the PWM ramps between targets. Smaller steps or larger intervals yield gentler transitions.
- `Tank.update()` must be called regularly (e.g. each `loop()` pass) so the ramp logic can advance.
- The sketch exposes both serial controls and a lightweight Wi-Fi web UI; connect to the board's access point to steer it from a browser.

---

## 🔌 Pinout & Connections

Example wiring for a NodeMCU-style ESP8266 (adjust to match your board):

| Signal | L298N Pin | ESP8266 Pin | GPIO | Notes |
| ------ | --------- | ----------- | ---- | ----- |
| ENA    | ENA       | D7          | 25   | Tie HIGH for full speed or PWM this pin |
| IN1    | IN1       | D2          | 22   | Left motor direction A |
| IN2    | IN2       | D1          | 21   | Left motor direction B |
| ENB    | ENB       | D8          | 14   | PWM capable; ensure the board keeps GPIO15 LOW at boot |
| IN3    | IN3       | D5          | 13   | Right motor direction A |
| IN4    | IN4       | D6          | 15   | Right motor direction B |

Power the logic side with 5 V, feed the motor supply (7–12 V typical) to `VCC`/`VIN`, and keep grounds common between the driver and the MCU.

On boot the firmware creates a SoftAP named `TankController` (password `tank12345`). Once connected, browse to `http://192.168.4.1` to access the on-board controller page.

---

## ✅ Summary

You now have a browser- and serial-controllable half-H bridge driver tailored to the ubiquitous L298N board. The `TankShift` class keeps the API focused on movement semantics while smoothing transitions with PWM ramps. Customize the pin mapping and ramp settings to suit your chassis.

