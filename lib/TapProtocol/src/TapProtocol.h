#pragma once

#include <cstddef>
#include <cstdint>

namespace rgbbill::tap {

constexpr uint8_t VERSION = 0x02;
constexpr uint8_t LEGACY_VERSION = 0x01;
constexpr size_t LEGACY_METADATA_SIZE = 12;
constexpr size_t METADATA_SIZE = 16;
constexpr int16_t DEFAULT_RSSI_THRESHOLD_DBM = -60;
constexpr uint32_t DEFAULT_BUTTON_DEBOUNCE_MS = 40;
constexpr uint32_t DEFAULT_ARM_WINDOW_MS = 15000;

enum class ReadyState : uint8_t {
  kEmpty = 0,
  kReady = 1,
};

enum class Control : uint8_t {
  kStart = 1,
  kCancel = 2,
};

struct Metadata {
  uint8_t version = VERSION;
  ReadyState state = ReadyState::kEmpty;
  uint8_t kind = 0;
  uint32_t sessionId = 0;
  uint32_t size = 0;
  uint32_t denominationCents = 0;
};

bool encodeMetadata(const Metadata& metadata, uint8_t* output,
                    size_t capacity);
bool decodeMetadata(const uint8_t* encoded, size_t length,
                    Metadata& metadata);

class Gate {
 public:
  explicit Gate(int16_t rssiThresholdDbm = DEFAULT_RSSI_THRESHOLD_DBM,
                uint32_t debounceMs = DEFAULT_BUTTON_DEBOUNCE_MS);

  void updateButton(bool rawPressed, uint32_t nowMs);
  bool buttonPressed() const { return stablePressed_; }
  bool takePressedEdge();
  bool rssiAllows(int rssiDbm) const;

 private:
  int16_t rssiThresholdDbm_;
  uint32_t debounceMs_;
  bool candidatePressed_ = false;
  bool stablePressed_ = false;
  bool pressedEdgePending_ = false;
  uint32_t candidateSinceMs_ = 0;
};

class OneShotArm {
 public:
  explicit OneShotArm(uint32_t windowMs = DEFAULT_ARM_WINDOW_MS)
      : windowMs_(windowMs) {}

  void arm(uint32_t nowMs);
  void cancel();
  bool consume();
  bool expire(uint32_t nowMs);
  bool armed() const { return armed_; }

 private:
  uint32_t windowMs_;
  bool armed_ = false;
  uint32_t armedAtMs_ = 0;
};

}  // namespace rgbbill::tap
