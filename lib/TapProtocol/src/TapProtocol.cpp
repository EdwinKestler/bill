#include "TapProtocol.h"

namespace rgbbill::tap {
namespace {

uint32_t readLe32(const uint8_t* input) {
  return static_cast<uint32_t>(input[0]) |
         (static_cast<uint32_t>(input[1]) << 8U) |
         (static_cast<uint32_t>(input[2]) << 16U) |
         (static_cast<uint32_t>(input[3]) << 24U);
}

void writeLe32(uint8_t* output, uint32_t value) {
  output[0] = static_cast<uint8_t>(value & 0xFFU);
  output[1] = static_cast<uint8_t>((value >> 8U) & 0xFFU);
  output[2] = static_cast<uint8_t>((value >> 16U) & 0xFFU);
  output[3] = static_cast<uint8_t>((value >> 24U) & 0xFFU);
}

}  // namespace

bool encodeMetadata(const Metadata& metadata, uint8_t* output,
                    size_t capacity) {
  if (output == nullptr || capacity < METADATA_SIZE ||
      metadata.version != VERSION ||
      (metadata.state != ReadyState::kEmpty &&
       metadata.state != ReadyState::kReady)) {
    return false;
  }
  output[0] = metadata.version;
  output[1] = static_cast<uint8_t>(metadata.state);
  output[2] = metadata.kind;
  output[3] = 0;
  writeLe32(output + 4, metadata.sessionId);
  writeLe32(output + 8, metadata.size);
  writeLe32(output + 12, metadata.denominationCents);
  return true;
}

bool decodeMetadata(const uint8_t* encoded, size_t length,
                    Metadata& metadata) {
  if (encoded == nullptr ||
      (length != LEGACY_METADATA_SIZE && length != METADATA_SIZE) ||
      (encoded[0] != LEGACY_VERSION && encoded[0] != VERSION) ||
      (encoded[0] == LEGACY_VERSION && length != LEGACY_METADATA_SIZE) ||
      (encoded[0] == VERSION && length != METADATA_SIZE) || encoded[3] != 0 ||
      encoded[1] > 1) {
    return false;
  }
  metadata.version = encoded[0];
  metadata.state = static_cast<ReadyState>(encoded[1]);
  metadata.kind = encoded[2];
  metadata.sessionId = readLe32(encoded + 4);
  metadata.size = readLe32(encoded + 8);
  metadata.denominationCents =
      length == METADATA_SIZE ? readLe32(encoded + 12) : 0;
  return true;
}

Gate::Gate(int16_t rssiThresholdDbm, uint32_t debounceMs)
    : rssiThresholdDbm_(rssiThresholdDbm), debounceMs_(debounceMs) {}

void Gate::updateButton(bool rawPressed, uint32_t nowMs) {
  if (rawPressed != candidatePressed_) {
    candidatePressed_ = rawPressed;
    candidateSinceMs_ = nowMs;
    return;
  }
  if (stablePressed_ != candidatePressed_ &&
      nowMs - candidateSinceMs_ >= debounceMs_) {
    stablePressed_ = candidatePressed_;
    if (stablePressed_) {
      pressedEdgePending_ = true;
    }
  }
}

bool Gate::takePressedEdge() {
  const bool pending = pressedEdgePending_;
  pressedEdgePending_ = false;
  return pending;
}

bool Gate::rssiAllows(int rssiDbm) const {
  return rssiDbm >= rssiThresholdDbm_;
}

void OneShotArm::arm(uint32_t nowMs) {
  armed_ = true;
  armedAtMs_ = nowMs;
}

void OneShotArm::cancel() {
  armed_ = false;
  armedAtMs_ = 0;
}

bool OneShotArm::consume() {
  if (!armed_) {
    return false;
  }
  cancel();
  return true;
}

bool OneShotArm::expire(uint32_t nowMs) {
  if (!armed_ || nowMs - armedAtMs_ < windowMs_) {
    return false;
  }
  cancel();
  return true;
}

}  // namespace rgbbill::tap
