# LoRa Tank Control Protocol

This document describes the over-the-air communication standard used between the **TX controller node** and the **RX drive node**.

## Radio Parameters

- **Frequency:** 902-915 MHz
- **Bandwidth:** 125 kHz
- **Spreading Factor:** 7
- **Coding Rate:** 4/5
- **Transmit Power:** 17 dBm
- **CRC:** Enabled at the LoRa PHY layer

These settings are applied to both nodes in `setup()` via the `LoRa` Arduino library. Any change must be mirrored on TX and RX.

## Frame Layout

Each command is encapsulated in a single 16-byte control frame before encryption. The frame is little-endian and packed without padding.

| Offset | Size | Field        | Description                                   |
| ------ | ---- | ------------ | --------------------------------------------- |
| 0      | 4    | `magic`      | ASCII `"TANK"` to identify valid frames       |
| 4      | 1    | `version`    | Protocol version, currently `0x01`            |
| 5      | 1    | `command`    | See command table below                       |
| 6      | 1    | `leftSpeed`  | Desired left motor PWM ceiling (0-255)        |
| 7      | 1    | `rightSpeed` | Desired right motor PWM ceiling (0-255)       |
| 8      | 1    | `sequence`   | Monotonic counter to suppress replays         |
| 9      | 3    | `reserved`   | Kept for future use                           |
| 12     | 4    | `crc32`      | CRC-32 (IEEE 802.3) of bytes 0-11             |

### Command Table

| Value | Meaning              | Notes                                |
| ----- | -------------------- | ------------------------------------ |
| 0x00  | `Stop`               | Immediately ramps both motors to idle|
| 0x01  | `Forward`            | Ramp both motors forward             |
| 0x02  | `Backward`           | Ramp both motors reverse             |
| 0x03  | `Left`               | Left motor reverse, right forward    |
| 0x04  | `Right`              | Left forward, right reverse          |
| 0x05  | `SetSpeed`           | Update PWM ceilings only             |

## Security

- **Cipher:** AES-256-CBC (mbedTLS implementation on ESP32)
- **Key Size:** 32 bytes
- **IV:** 16 bytes (static, shared) – rotate in production deployments.
- **Padding:** Not required because the frame size is exactly 16 bytes.
- **Integrity:** Verified with CRC-32 after decryption.
- **Replay Mitigation:** The RX node ignores frames whose sequence number equals the last accepted value.

## Workflow Summary

1. TX node collects a command (web UI, local input, exposed API).
2. Populate a `ControlFrame`, compute CRC-32, and increment the sequence counter.
3. Encrypt the frame with AES-256-CBC and transmit it via LoRa.
4. RX node receives a packet, decrypts it, validates magic/version/CRC/sequence, and then dispatches the command to the drivetrain.
