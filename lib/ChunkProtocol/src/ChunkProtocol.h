#pragma once

#include <cstddef>
#include <cstdint>

namespace rgbbill::chunk {

constexpr uint8_t VERSION = 0x01;
constexpr size_t HEADER_SIZE = 12;
constexpr size_t CRC_SIZE = 4;
constexpr size_t MAX_PAYLOAD_SIZE = 200;
constexpr size_t MAX_FRAME_SIZE = HEADER_SIZE + MAX_PAYLOAD_SIZE + CRC_SIZE;

enum class Kind : uint8_t {
  kInvoice = 0x01,
  kConsignment = 0x02,
  kAck = 0x03,
};

// These values are also carried as the single ACK payload byte.
enum class Result : uint8_t {
  kOk = 0x00,
  kMalformed = 0x01,
  kUnsupported = 0x02,
  kCrcMismatch = 0x03,
  kSessionMismatch = 0x04,
  kSequenceMismatch = 0x05,
  kTotalMismatch = 0x06,
  kTooLarge = 0x07,
  kStorageFailure = 0x08,
  kBusy = 0x09,
};

struct FrameView {
  uint8_t version = 0;
  Kind kind = Kind::kInvoice;
  uint32_t sessionId = 0;
  uint16_t sequence = 0;
  uint16_t total = 0;
  uint16_t payloadLength = 0;
  const uint8_t* payload = nullptr;
};

uint32_t crc32(const uint8_t* data, size_t length);

bool encodeFrame(Kind kind, uint32_t sessionId, uint16_t sequence,
                 uint16_t total, const uint8_t* payload,
                 uint16_t payloadLength, uint8_t* output,
                 size_t outputCapacity, size_t& outputLength);

Result decodeFrame(const uint8_t* encoded, size_t encodedLength,
                   FrameView& frame);

class ReceiveSession {
 public:
  explicit ReceiveSession(size_t maxTransferBytes);

  Result accept(const FrameView& frame);
  void reset();

  bool active() const { return active_; }
  bool complete() const { return complete_; }
  Kind kind() const { return kind_; }
  uint32_t sessionId() const { return sessionId_; }
  uint16_t total() const { return total_; }
  uint16_t nextSequence() const { return nextSequence_; }
  size_t bytesReceived() const { return bytesReceived_; }

 private:
  size_t maxTransferBytes_;
  bool active_ = false;
  bool complete_ = false;
  Kind kind_ = Kind::kInvoice;
  uint32_t sessionId_ = 0;
  uint16_t total_ = 0;
  uint16_t nextSequence_ = 0;
  size_t bytesReceived_ = 0;
};

}  // namespace rgbbill::chunk
