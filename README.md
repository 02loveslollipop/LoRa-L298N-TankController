## Introduction

This project ships with a lightweight Arduino C++ helper (`TankShift`) that drives a dual **L298N** H-bridge. Each motor is controlled with two direction inputs and a single enable pin (ENA / ENB). The library wraps those lines behind a tank-style API, adds PWM speed control, and ramps between states for smooth transitions on **ESP8266** and **ESP32** platforms.

The system uses **LoRa wireless communication** for long-range control, with **AES-256-CBC encryption** ensuring secure command transmission between transmitter and receiver. A shared protocol library (`ControlProtocol.h`) standardizes the communication format across all nodes.


---

## Features

### Secure Communication
- **AES-256-CBC Encryption**: All LoRa commands are encrypted to prevent unauthorized access
- **CRC32 Validation**: Ensures data integrity across wireless transmission
- **Sequence Tracking**: Prevents replay attacks and duplicate command processing
- **Magic Header & Version Control**: Validates protocol compatibility

### LoRa Wireless Control
- **Long-Range Operation**: Control your tank from hundreds of meters away
- **Low Latency**: Fast command execution for responsive control

### 🔧 Shared Protocol Library
The `ControlProtocol.h` header provides a standardized communication framework:
- **Platform-Independent**: Works across ESP8266, ESP32, and probably other Arduino-compatible boards
- **Compact Frame Format**: 16-byte encrypted packets minimize bandwidth
- **Command Set**: Stop, Forward, Backward, Left, Right, SetSpeed
- **Easy Integration**: Include once, use everywhere

---

## Core Components

### L298N Dual H-Bridge

![L298N Pinout](https://arduinoyard.com/wp-content/uploads/2025/02/l298n_motordriver_pinout_bb.png)

The **L298N** exposes two identical H bridges. Each side needs:

- `IN1` / `IN2` / `IN3` / `IN4`  to choose direction
- `ENx` to gate power (HIGH = run, LOW = stop) (can be PWM modulated for speed control)

The helper class toggles those pins directly and drives the enable lines with PWM, ramping between targets so direction changes feel smooth.

### LoRa Transceiver Module
Supports common LoRa modules (SX1276/SX1278-based):
- **Frequency**: 433 MHz, 868 MHz, or 915 MHz depending on region
- **Spread Factor**: Configurable for range vs. speed tradeoff
- **Bandwidth**: Adjustable based on interference environment
- **Output Power**: Configurable transmission power

---

### Encryption Details
- **Algorithm**: AES-256 in CBC mode
- **Key Size**: 256-bit (32 bytes)
- **IV Size**: 128-bit (16 bytes)
- **Block Size**: 16 bytes (matches frame size)

---

## Pinout & Connections

### Motor Controller (Receiver)

| Signal                      | L298N Pin | ESP8266 Pin | ESP32 (LilyGO) Pin |
|-----------------------------|-----------|-------------|--------------------|
| Motor A PWM                 | ENA       | D7          | 25                 |
| Motor A Direction control 1 | IN1       | D2          | 22                 |
| Motor A Direction control 2 | IN2       | D1          | 21                 |
| Motor B PWM                 | ENB       | D8          | 14                 |
| Motor B Direction control 1 | IN3       | D5          | 13                 |
| Motor B Direction control 2 | IN4       | D6          | 15                 |

### LoRa Module Connections

| LoRa Pin | ESP8266 Pin | ESP32 Pin | Description    |
|----------|-------------|-----------|----------------|
| SCK      | D5 (GPIO14) | GPIO18    | SPI Clock      |
| MISO     | D6 (GPIO12) | GPIO19    | SPI Data In    |
| MOSI     | D7 (GPIO13) | GPIO23    | SPI Data Out   |
| NSS/CS   | D8 (GPIO15) | GPIO5     | Chip Select    |
| RST      | D0 (GPIO16) | GPIO14    | Reset          |
| DIO0     | D1 (GPIO5)  | GPIO26    | Interrupt Pin  |

Power the logic side with 5 V, feed the motor supply (7–12 V typical) to `VCC`/`VIN`, and keep grounds common between the driver and the MCU.

---

## Network Setup

On boot the receiver firmware creates a SoftAP named `TankController` (password `tank12345`). Once connected, browse to `http://192.168.4.1` to access the on-board controller page with both manual controls and LoRa status indicators.

The transmitter can operate standalone with physical controls or provide its own web interface for command input. The receiver also exposes a REST ENDPOINT at `/cmd` where to remotely control the device.

---

## Dependencies

- **Arduino LoRa library** by Sandeep Mistry
- **mbedTLS** (included with ESP8266/ESP32 cores)
- **ESP8266WiFi** or **WiFi** (ESP32) for web interface
- **TankShift** motor control library (included)

---

## Getting Started

1. Install required libraries via Arduino Library Manager
2. Update encryption keys in `common/ControlProtocol.h`
3. Configure LoRa frequency and parameters for your region
4. Flash receiver sketch to tank controller
5. Flash transmitter sketch to remote control
6. Power up both devices and test range
7. Fine-tune motor ramping and speed limits as needed
