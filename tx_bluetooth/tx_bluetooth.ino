#include <Arduino.h>
#include <BluetoothSerial.h>
#include <SPI.h>
#include <LoRa.h>
#include "../common/ControlProtocol.h"
#include "LoRaBoards.h"

#if !defined(CONFIG_BT_ENABLED) || !defined(CONFIG_BLUEDROID_ENABLED)
#error Bluetooth is not enabled! Please run `make menuconfig` and enable it
#endif

#ifndef CONFIG_RADIO_FREQ
#define CONFIG_RADIO_FREQ           910.0
#endif
#ifndef CONFIG_RADIO_OUTPUT_POWER
#define CONFIG_RADIO_OUTPUT_POWER   17
#endif
#ifndef CONFIG_RADIO_BW
#define CONFIG_RADIO_BW             125.0
#endif

// ---------- Bluetooth Configuration ----------
BluetoothSerial SerialBT;
const char* BT_DEVICE_NAME = "ESP32_Tank";

// ---------- Control State ----------
uint8_t currentSpeed = 200; // Default speed (0-255)
String currentState = "STOP";
unsigned long lastCommandTime = 0;
constexpr uint32_t COMMAND_TIMEOUT = 2000; // 2 seconds

// ---------- LoRa TX State ----------
uint8_t sequenceCounter = 0;

// ---------- Function Declarations ----------
void handleBluetoothCommand(char cmd);
void printHelp();
void printStatus();
bool beginLoRa();
bool sendLoRaFrame(TankControl::Command cmd, uint8_t leftSpeed, uint8_t rightSpeed);
TankControl::Command parseCommand(char cmd);

void setup() {
    Serial.begin(115200);
    delay(500);
    
    Serial.println("\n\n==============================================");
    Serial.println("Bluetooth-to-LoRa Gateway");
    Serial.println("Bluetooth SPP → LoRa TX Bridge");
    Serial.println("==============================================\n");

    setupBoards(/*disable_u8g2=*/true);  // Initialize PMU for T-Beam
    delay(1500); // Allow PMU rails to stabilize

    // Initialize LoRa
    if (!beginLoRa()) {
        Serial.println("[LoRa] Setup failed - CANNOT FUNCTION WITHOUT LoRa!");
        while(1) { delay(1000); } // Halt - this device needs LoRa
    }

    // Initialize Bluetooth
    if (!SerialBT.begin(BT_DEVICE_NAME)) {
        Serial.println("[BT] Failed to initialize Bluetooth!");
        while(1) { delay(1000); }
    }
    
    Serial.printf("[BT] Bluetooth device '%s' is ready to pair\n", BT_DEVICE_NAME);
    Serial.println("[BT] Waiting for connection...");
    
    printHelp();
}

void loop() {
    // Handle Bluetooth commands
    if (SerialBT.available()) {
        char cmd = SerialBT.read();
        handleBluetoothCommand(cmd);
        lastCommandTime = millis();
    }

    // Safety timeout - stop if no command received for 2 seconds
    if (millis() - lastCommandTime > COMMAND_TIMEOUT && currentState != "STOP") {
        sendLoRaFrame(TankControl::Command::Stop, 0, 0);
        currentState = "STOP (TIMEOUT)";
        Serial.println("[SAFETY] Command timeout - sending STOP via LoRa");
        SerialBT.println("TIMEOUT: Stop command sent");
    }

    delay(10);
}

void handleBluetoothCommand(char cmd) {
    // Convert to uppercase for consistency
    cmd = toupper(cmd);

    TankControl::Command loraCmd;
    bool sendCommand = false;

    switch (cmd) {
        // Movement commands
        case 'W':
        case 'F':
        case '8':  // Numpad 8
            loraCmd = TankControl::Command::Forward;
            currentState = "FORWARD";
            sendCommand = true;
            Serial.println("[BT] FORWARD");
            SerialBT.println("FORWARD");
            break;

        case 'S':
        case 'B':
        case '2':  // Numpad 2
            loraCmd = TankControl::Command::Backward;
            currentState = "BACKWARD";
            sendCommand = true;
            Serial.println("[BT] BACKWARD");
            SerialBT.println("BACKWARD");
            break;

        case 'A':
        case 'L':
        case '4':  // Numpad 4
            loraCmd = TankControl::Command::Left;
            currentState = "LEFT";
            sendCommand = true;
            Serial.println("[BT] LEFT");
            SerialBT.println("LEFT");
            break;

        case 'D':
        case 'R':
        case '6':  // Numpad 6
            loraCmd = TankControl::Command::Right;
            currentState = "RIGHT";
            sendCommand = true;
            Serial.println("[BT] RIGHT");
            SerialBT.println("RIGHT");
            break;

        case 'X':
        case ' ':
        case '5':  // Numpad 5
            loraCmd = TankControl::Command::Stop;
            currentState = "STOP";
            sendCommand = true;
            Serial.println("[BT] STOP");
            SerialBT.println("STOP");
            break;

        // Speed control
        case '+':
        case '=':
            currentSpeed = min(255, currentSpeed + 25);
            Serial.printf("[BT] Speed increased to %d\n", currentSpeed);
            SerialBT.printf("Speed: %d\n", currentSpeed);
            // Don't send LoRa command, just update local state
            break;

        case '-':
        case '_':
            currentSpeed = max(0, currentSpeed - 25);
            Serial.printf("[BT] Speed decreased to %d\n", currentSpeed);
            SerialBT.printf("Speed: %d\n", currentSpeed);
            // Don't send LoRa command, just update local state
            break;

        // Speed presets
        case '1':
            currentSpeed = 100;
            Serial.println("[BT] Speed set to SLOW (100)");
            SerialBT.println("Speed: SLOW (100)");
            break;

        case '3':
            currentSpeed = 200;
            Serial.println("[BT] Speed set to MEDIUM (200)");
            SerialBT.println("Speed: MEDIUM (200)");
            break;

        case '9':
            currentSpeed = 255;
            Serial.println("[BT] Speed set to FAST (255)");
            SerialBT.println("Speed: FAST (255)");
            break;

        // Info commands
        case 'H':
        case '?':
            printHelp();
            break;

        case 'I':
            printStatus();
            break;

        // Ignore newlines and carriage returns
        case '\n':
        case '\r':
            break;

        // Unknown command
        default:
            Serial.printf("[BT] Unknown command: '%c' (0x%02X)\n", cmd, cmd);
            SerialBT.println("Unknown command. Send 'H' for help.");
            break;
    }

    // Send LoRa command if needed
    if (sendCommand) {
        bool success = sendLoRaFrame(loraCmd, currentSpeed, currentSpeed);
        if (!success) {
            SerialBT.println("ERROR: LoRa transmission failed!");
        }
    }
}

void printHelp() {
    const char* help = R"(
========================================
Bluetooth-to-LoRa Gateway - Commands
========================================

Movement (sends LoRa commands):
  W/F/8 - Forward
  S/B/2 - Backward
  A/L/4 - Left
  D/R/6 - Right
  X/ /5 - Stop

Speed Control:
  +/=   - Increase speed (+25)
  -/_   - Decrease speed (-25)
  1     - Slow (100)
  3     - Medium (200)
  9     - Fast (255)

Info:
  H/?   - Show this help
  I     - Show gateway status

========================================
This device transmits commands via LoRa
to the robot receiver (rx_driver)
========================================
)";
    
    Serial.println(help);
    SerialBT.println(help);
}

void printStatus() {
    char status[200];
    snprintf(status, sizeof(status),
             "\n--- Gateway Status ---\n"
             "State: %s\n"
             "Speed: %d/255\n"
             "Sequence: %d\n"
             "Uptime: %lu s\n"
             "Free Heap: %u bytes\n"
             "---------------------\n",
             currentState.c_str(),
             currentSpeed,
             sequenceCounter,
             millis() / 1000,
             ESP.getFreeHeap());
    
    Serial.print(status);
    SerialBT.print(status);
}

bool beginLoRa() {
    Serial.println("[LoRa] Initializing radio...");
    
    SPI.begin(RADIO_SCLK_PIN, RADIO_MISO_PIN, RADIO_MOSI_PIN);
    LoRa.setPins(RADIO_CS_PIN, RADIO_RST_PIN, RADIO_DIO0_PIN);

    if (!LoRa.begin(CONFIG_RADIO_FREQ * 1000000)) {
        Serial.println("[LoRa] Failed to initialize!");
        return false;
    }

    LoRa.setTxPower(CONFIG_RADIO_OUTPUT_POWER);
    LoRa.setSignalBandwidth(CONFIG_RADIO_BW * 1000);
    LoRa.setSpreadingFactor(7);
    LoRa.setCodingRate4(5);
    LoRa.enableCrc();
    LoRa.receive();

    Serial.println("[LoRa] Radio ready for transmission.");
    return true;
}

bool sendLoRaFrame(TankControl::Command cmd, uint8_t leftSpeed, uint8_t rightSpeed) {
    TankControl::ControlFrame frame;
    TankControl::initFrame(frame, cmd, leftSpeed, rightSpeed, sequenceCounter++);

    uint8_t encrypted[TankControl::kFrameSize];
    if (!TankControl::encryptFrame(frame, encrypted, sizeof(encrypted))) {
        Serial.println("[LoRa] Encryption failed");
        return false;
    }

    LoRa.idle();
    LoRa.beginPacket();
    LoRa.write(encrypted, sizeof(encrypted));
    bool ok = LoRa.endPacket() == 1;
    LoRa.receive();

    if (ok) {
        Serial.printf("[LoRa] >>> TX: cmd=%d seq=%d L=%d R=%d\n", 
                     static_cast<int>(frame.command), frame.sequence, 
                     frame.leftSpeed, frame.rightSpeed);
    } else {
        Serial.println("[LoRa] TX FAILED!");
    }

    return ok;
}
