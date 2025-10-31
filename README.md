## Introduction

This project provides a complete **IoT tank control system** combining embedded hardware control with cloud-based orchestration. The architecture spans from low-level motor control on **ESP32/ESP8266** platforms using dual **L298N** H-bridges, through **LoRa wireless communication** with **AES-256-CBC encryption**, up to cloud services for real-time command distribution and telemetry streaming.

The system uses **Redis Streams** as the event backbone, enabling multiple services to coordinate tank control, telemetry broadcasting, and web-based monitoring through a modern microservices architecture deployed on **AWS Elastic Beanstalk**.

---

## System Architecture

### Hardware Layer (RX - Tank Receiver)
- **ESP32/ESP8266** microcontroller running the tank firmware
- **L298N Dual H-Bridge** for motor control with PWM speed regulation
- **LoRa transceiver** (SX1276/SX1278) for long-range wireless communication
- **TankShift** C++ library providing smooth motor ramping and tank-style movement
- **AES-256-CBC encryption** for secure command reception
- Connects to WiFi and establishes **WebSocket** connection to Control Broker

### Communication Layer (TX - LoRa Gateway)
- **LoRa Transmitter** device with physical controls or web interface
- **AES-256-CBC encryption** matching receiver configuration
- Optional standalone operation or integration with cloud services
- Provides REST endpoint (`/cmd`) for remote command injection

### Cloud Services Layer

#### Control Broker Service
**WebSocket Gateway** managing real-time tank connections:
- Maintains persistent WebSocket connections with tank devices
- Receives commands from Redis `tank_commands` stream
- Routes commands to appropriate tank via WebSocket
- Publishes tank status updates to Redis `tank_status` stream
- Handles connection lifecycle (registration, heartbeat, disconnection)
- Deployed on AWS Elastic Beanstalk

#### Visual Controller Service
**Web UI and REST Gateway** for human operators:
- Provides interactive browser-based controller interface
- REST API for command submission (`POST /command/{tank_id}`)
- Writes commands to Redis `tank_commands` stream
- Subscribes to Redis `tank_status` stream for telemetry
- WebSocket endpoint (`/ws/ui/{tank_id}`) for real-time UI updates
- Deployed on AWS Elastic Beanstalk

#### Event Streamer (Redis Streams)
**Distributed message backbone** using **AWS ElastiCache (Valkey)**:
- `tank_commands` stream: Command queue from UI to tanks
- `tank_status` stream: Telemetry flow from tanks to monitoring clients
- Provides durability, ordering, and fan-out capabilities
- Enables decoupled service communication
- TLS encryption (rediss://) for secure data transport

### Data Flow

```
[Tank Device (RX)] ←→ WebSocket ←→ [Control Broker] ←→ Redis Streams ←→ [Visual Controller] ←→ HTTP/WS ←→ [Browser UI]
         ↑                                                       ↑
    LoRa (encrypted)                                    Commands/Telemetry
         ↑                                                       ↓
  [LoRa Transmitter (TX)]                              [Redis Streams (Valkey)]
```

**Command Path**: Browser → Visual Controller → Redis `tank_commands` → Control Broker → WebSocket → Tank Device  
**Telemetry Path**: Tank Device → WebSocket → Control Broker → Redis `tank_status` → Visual Controller → Browser


---

## Features

### Hardware Control
- **Dual Motor Control**: Independent PWM speed regulation (0-255) per motor
- **Smooth Transitions**: Configurable ramping between speed changes
- **Tank-Style Movement**: Forward, backward, pivot left/right, gradual turns
- **TankShift Library**: Platform-independent C++ API for ESP8266/ESP32

### Secure Communication
- **AES-256-CBC Encryption**: All LoRa commands encrypted end-to-end
- **CRC32 Validation**: Ensures data integrity across wireless transmission
- **Sequence Tracking**: Prevents replay attacks and duplicate command processing
- **Magic Header & Version Control**: Validates protocol compatibility
- **TLS/SSL**: Secure Redis connections (rediss://) for cloud communication

### LoRa Wireless Control
- **Long-Range Operation**: Control tanks from hundreds of meters away
- **Low Latency**: Fast command execution for responsive control
- **Frequency Options**: 433 MHz, 868 MHz, or 915 MHz regional support
- **Adjustable Parameters**: Configurable spread factor, bandwidth, and transmit power

### Cloud Architecture
- **Microservices Design**: Decoupled Control Broker and Visual Controller services
- **Redis Streams**: Durable, ordered message queues with fan-out capabilities
- **WebSocket Gateway**: Real-time bidirectional communication with hardware
- **REST API**: Simple HTTP interface for command submission
- **Elastic Beanstalk Deployment**: Auto-scaling, load balancing, health monitoring
- **AWS ElastiCache (Valkey)**: Managed Redis-compatible event backbone

### 🔧 Shared Protocol Library
The `ControlProtocol.h` header provides a standardized communication framework:
- **Platform-Independent**: Works across ESP8266, ESP32, and Arduino-compatible boards
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

### Tank Receiver (RX) Configuration
On boot, the receiver firmware:
1. Creates a SoftAP named `TankController` (password `tank12345`)
2. Starts web server at `http://192.168.4.1` with manual control interface
3. Connects to configured WiFi network (if credentials provided)
4. Establishes WebSocket connection to Control Broker service
5. Registers tank ID and begins heartbeat transmission
6. Exposes REST endpoint at `/cmd` for local command injection

### Control Broker Service
WebSocket gateway deployed on AWS Elastic Beanstalk:
- Listens for tank WebSocket connections on `/ws/tank/{tank_id}`
- Accepts radar sensor feeds on `/ws/radar/source/{source_id}` and rebroadcasts to `/ws/radar/listener`
- Subscribes to Redis `tank_commands` stream
- Routes commands to connected tanks
- Publishes telemetry to Redis `tank_status` stream
- Stores radar sweeps to Redis `tank_radar` stream for downstream consumers
- Health check endpoint at `/health`
- Environment variables: `REDIS_URL`, `REDIS_COMMAND_STREAM`, `REDIS_STATUS_STREAM`, `REDIS_STATUS_MAXLEN`, `REDIS_RADAR_STREAM`, `REDIS_RADAR_MAXLEN`

### Visual Controller Service
Web UI service deployed on AWS Elastic Beanstalk:
- Provides browser interface at `/controller/{tank_id}`
- REST API at `POST /command/{tank_id}` for command submission
- WebSocket endpoint at `/ws/ui/{tank_id}` for real-time telemetry
- Publishes commands to Redis `tank_commands` stream
- Subscribes to Redis `tank_status` stream
- Environment variables: `REDIS_URL`, `REDIS_COMMAND_STREAM`, `REDIS_STATUS_STREAM`

### Redis Event Backbone
AWS ElastiCache (Valkey) provides:
- Stream-based message queuing
- Automatic message TTL and stream trimming
- TLS-encrypted connections (rediss://)
- High availability and durability
- Consumer groups for scalability
- Streams in use: `tank_commands`, `tank_status`, `tank_radar`

---

## Deployment

### Hardware Setup
1. Install required Arduino libraries via Library Manager
2. Update encryption keys in `common/ControlProtocol.h`
3. Configure LoRa frequency and parameters for your region
4. Flash receiver sketch to ESP32/ESP8266 on tank
5. Flash transmitter sketch to remote LoRa controller
6. Configure WiFi credentials in receiver firmware
7. Test WebSocket connection to Control Broker

### Cloud Services Setup
1. Create AWS ElastiCache (Valkey) instance with TLS enabled
2. Package services using `package.ps1` script
3. Deploy `control-broker-*.zip` to Elastic Beanstalk environment
4. Deploy `visual-controller-*.zip` to separate Elastic Beanstalk environment
5. Configure `REDIS_URL` environment variable with `rediss://` connection string
6. Verify health endpoints respond correctly
7. Test end-to-end command flow from browser to tank

---

## Dependencies

### Hardware (Arduino/PlatformIO)
- **Arduino LoRa library** by Sandeep Mistry
- **mbedTLS** (included with ESP8266/ESP32 cores)
- **ESP8266WiFi** or **WiFi** (ESP32) for network connectivity
- **WebSocketsClient** for Control Broker connection
- **TankShift** motor control library (included)
- **ArduinoJson** for command parsing

### Cloud Services (Python)
- **FastAPI** - Async web framework
- **redis.asyncio** - Async Redis client
- **pydantic** - Data validation
- **uvicorn** - ASGI server
- **python-dotenv** - Environment configuration

---

## Getting Started

### Quick Start (Hardware)
1. Install Arduino dependencies
2. Update `ControlProtocol.h` with encryption keys
3. Configure WiFi credentials in receiver firmware
4. Set Control Broker WebSocket URL in firmware
5. Flash firmware to devices
6. Power up and verify WebSocket connection

### Quick Start (Cloud)
1. Set up AWS ElastiCache (Valkey) with TLS
2. Run `.\package.ps1` to create deployment packages
3. Deploy both services to Elastic Beanstalk
4. Configure `REDIS_URL` environment variables
5. Access Visual Controller web interface
6. Test command transmission to connected tanks
