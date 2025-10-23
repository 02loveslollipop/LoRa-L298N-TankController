#pragma once

#include <Arduino.h>
#include <mbedtls/aes.h>

namespace TankControl {

constexpr uint8_t kMagic[4] = {'T', 'A', 'N', 'K'};
constexpr uint8_t kProtocolVersion = 1;
constexpr size_t kFrameSize = 16;

// AES-256-CBC shared secrets (replace in production).
const uint8_t kAesKey[32] = {
    0x51, 0x2A, 0xCE, 0x77, 0x48, 0x93, 0x11, 0xBA,
    0xE4, 0x7F, 0x8D, 0x2C, 0x90, 0x1B, 0x56, 0x3F,
    0x18, 0x24, 0xAB, 0xC3, 0x5D, 0x6E, 0x72, 0xF4,
    0x08, 0x9A, 0xD0, 0x42, 0x67, 0xB8, 0x1C, 0xE5};

const uint8_t kAesIv[16] = {
    0x44, 0x1E, 0xF9, 0xBC, 0x2A, 0x0D, 0x77, 0x63,
    0x9C, 0x53, 0x4B, 0x10, 0xAB, 0x88, 0xFE, 0x21};

enum class Command : uint8_t {
  Stop = 0,
  Forward = 1,
  Backward = 2,
  Left = 3,
  Right = 4,
  SetSpeed = 5
};

#pragma pack(push, 1)
struct ControlFrame {
  uint8_t magic[4];
  uint8_t version;
  uint8_t command;
  uint8_t leftSpeed;
  uint8_t rightSpeed;
  uint8_t sequence;
  uint8_t reserved[3];
  uint32_t crc32;
};
#pragma pack(pop)

inline uint32_t crc32(const uint8_t *data, size_t length) {
  uint32_t crc = 0xFFFFFFFFu;
  for (size_t i = 0; i < length; ++i) {
    crc ^= static_cast<uint32_t>(data[i]);
    for (uint8_t j = 0; j < 8; ++j) {
      uint32_t mask = -(crc & 1u);
      crc = (crc >> 1) ^ (0xEDB88320u & mask);
    }
  }
  return ~crc;
}

inline void initFrame(ControlFrame &frame, Command command,
                      uint8_t leftSpeed, uint8_t rightSpeed,
                      uint8_t sequence) {
  memcpy(frame.magic, kMagic, sizeof(kMagic));
  frame.version = kProtocolVersion;
  frame.command = static_cast<uint8_t>(command);
  frame.leftSpeed = leftSpeed;
  frame.rightSpeed = rightSpeed;
  frame.sequence = sequence;
  memset(frame.reserved, 0, sizeof(frame.reserved));
  frame.crc32 = crc32(reinterpret_cast<const uint8_t *>(&frame), 12);
}

inline bool encryptFrame(const ControlFrame &frame, uint8_t *outputBuffer,
                         size_t bufferLength) {
  if (!outputBuffer || bufferLength < kFrameSize) {
    return false;
  }

  uint8_t workBuffer[kFrameSize];
  memcpy(workBuffer, &frame, sizeof(ControlFrame));

  mbedtls_aes_context ctx;
  mbedtls_aes_init(&ctx);
  uint8_t iv[16];
  memcpy(iv, kAesIv, sizeof(iv));

  int err = mbedtls_aes_setkey_enc(&ctx, kAesKey, 256);
  if (err != 0) {
    mbedtls_aes_free(&ctx);
    return false;
  }

  err = mbedtls_aes_crypt_cbc(&ctx, MBEDTLS_AES_ENCRYPT, kFrameSize, iv,
                              workBuffer, outputBuffer);
  mbedtls_aes_free(&ctx);
  return err == 0;
}

inline bool decryptFrame(const uint8_t *inputBuffer, size_t bufferLength,
                         ControlFrame &frameOut) {
  if (!inputBuffer || bufferLength < kFrameSize) {
    return false;
  }

  uint8_t workBuffer[kFrameSize];
  memcpy(workBuffer, inputBuffer, kFrameSize);

  mbedtls_aes_context ctx;
  mbedtls_aes_init(&ctx);
  uint8_t iv[16];
  memcpy(iv, kAesIv, sizeof(iv));

  int err = mbedtls_aes_setkey_dec(&ctx, kAesKey, 256);
  if (err != 0) {
    mbedtls_aes_free(&ctx);
    return false;
  }

  err = mbedtls_aes_crypt_cbc(&ctx, MBEDTLS_AES_DECRYPT, kFrameSize, iv,
                              workBuffer, workBuffer);
  mbedtls_aes_free(&ctx);
  if (err != 0) {
    return false;
  }

  memcpy(&frameOut, workBuffer, sizeof(ControlFrame));

  if (memcmp(frameOut.magic, kMagic, sizeof(kMagic)) != 0) {
    return false;
  }
  if (frameOut.version != kProtocolVersion) {
    return false;
  }

  uint32_t expected = crc32(reinterpret_cast<const uint8_t *>(&frameOut), 12);
  return expected == frameOut.crc32;
}

inline Command commandFromFrame(const ControlFrame &frame) {
  switch (frame.command) {
    case static_cast<uint8_t>(Command::Stop): return Command::Stop;
    case static_cast<uint8_t>(Command::Forward): return Command::Forward;
    case static_cast<uint8_t>(Command::Backward): return Command::Backward;
    case static_cast<uint8_t>(Command::Left): return Command::Left;
    case static_cast<uint8_t>(Command::Right): return Command::Right;
    case static_cast<uint8_t>(Command::SetSpeed): return Command::SetSpeed;
    default: return Command::Stop;
  }
}

}  // namespace TankControl
