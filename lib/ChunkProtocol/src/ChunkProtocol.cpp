#include "ChunkProtocol.h"

namespace rgbbill::chunk {
namespace {

uint16_t readLe16(const uint8_t* input) {
  return static_cast<uint16_t>(input[0]) |
         (static_cast<uint16_t>(input[1]) << 8U);
}

uint32_t readLe32(const uint8_t* input) {
  return static_cast<uint32_t>(input[0]) |
         (static_cast<uint32_t>(input[1]) << 8U) |
         (static_cast<uint32_t>(input[2]) << 16U) |
         (static_cast<uint32_t>(input[3]) << 24U);
}

void writeLe16(uint8_t* output, uint16_t value) {
  output[0] = static_cast<uint8_t>(value & 0xFFU);
  output[1] = static_cast<uint8_t>((value >> 8U) & 0xFFU);
}

void writeLe32(uint8_t* output, uint32_t value) {
  output[0] = static_cast<uint8_t>(value & 0xFFU);
  output[1] = static_cast<uint8_t>((value >> 8U) & 0xFFU);
  output[2] = static_cast<uint8_t>((value >> 16U) & 0xFFU);
  output[3] = static_cast<uint8_t>((value >> 24U) & 0xFFU);
}

bool supportedKind(uint8_t rawKind) {
  return rawKind == static_cast<uint8_t>(Kind::kInvoice) ||
         rawKind == static_cast<uint8_t>(Kind::kConsignment) ||
         rawKind == static_cast<uint8_t>(Kind::kAck);
}

}  // namespace

uint32_t crc32(const uint8_t* data, size_t length) {
  uint32_t crc = 0xFFFFFFFFU;
  for (size_t index = 0; index < length; ++index) {
    crc ^= data[index];
    for (uint8_t bit = 0; bit < 8; ++bit) {
      const uint32_t mask = 0U - (crc & 1U);
      crc = (crc >> 1U) ^ (0xEDB88320U & mask);
    }
  }
  return ~crc;
}

bool encodeFrame(Kind kind, uint32_t sessionId, uint16_t sequence,
                 uint16_t total, const uint8_t* payload,
                 uint16_t payloadLength, uint8_t* output,
                 size_t outputCapacity, size_t& outputLength) {
  outputLength = 0;
  const size_t required = HEADER_SIZE + payloadLength + CRC_SIZE;
  if (output == nullptr || outputCapacity < required ||
      payloadLength > MAX_PAYLOAD_SIZE ||
      (payloadLength > 0 && payload == nullptr)) {
    return false;
  }

  output[0] = VERSION;
  output[1] = static_cast<uint8_t>(kind);
  writeLe32(output + 2, sessionId);
  writeLe16(output + 6, sequence);
  writeLe16(output + 8, total);
  writeLe16(output + 10, payloadLength);
  for (uint16_t index = 0; index < payloadLength; ++index) {
    output[HEADER_SIZE + index] = payload[index];
  }
  writeLe32(output + HEADER_SIZE + payloadLength,
            crc32(output, HEADER_SIZE + payloadLength));
  outputLength = required;
  return true;
}

Result decodeFrame(const uint8_t* encoded, size_t encodedLength,
                   FrameView& frame) {
  if (encoded == nullptr || encodedLength < HEADER_SIZE + CRC_SIZE) {
    return Result::kMalformed;
  }

  const uint16_t payloadLength = readLe16(encoded + 10);
  if (payloadLength > MAX_PAYLOAD_SIZE ||
      encodedLength != HEADER_SIZE + payloadLength + CRC_SIZE) {
    return Result::kMalformed;
  }

  const uint32_t expectedCrc =
      readLe32(encoded + HEADER_SIZE + payloadLength);
  if (crc32(encoded, HEADER_SIZE + payloadLength) != expectedCrc) {
    return Result::kCrcMismatch;
  }
  if (encoded[0] != VERSION || !supportedKind(encoded[1])) {
    return Result::kUnsupported;
  }

  frame.version = encoded[0];
  frame.kind = static_cast<Kind>(encoded[1]);
  frame.sessionId = readLe32(encoded + 2);
  frame.sequence = readLe16(encoded + 6);
  frame.total = readLe16(encoded + 8);
  frame.payloadLength = payloadLength;
  frame.payload = encoded + HEADER_SIZE;
  return Result::kOk;
}

ReceiveSession::ReceiveSession(size_t maxTransferBytes)
    : maxTransferBytes_(maxTransferBytes) {}

Result ReceiveSession::accept(const FrameView& frame) {
  if (frame.kind != Kind::kInvoice && frame.kind != Kind::kConsignment) {
    return Result::kUnsupported;
  }
  if (frame.total == 0 || frame.sequence >= frame.total ||
      frame.payloadLength == 0 || frame.payload == nullptr) {
    return Result::kMalformed;
  }
  if (complete_) {
    return Result::kBusy;
  }

  if (!active_) {
    if (frame.sequence != 0) {
      return Result::kSequenceMismatch;
    }
    active_ = true;
    kind_ = frame.kind;
    sessionId_ = frame.sessionId;
    total_ = frame.total;
  } else {
    if (frame.sessionId != sessionId_ || frame.kind != kind_) {
      return Result::kSessionMismatch;
    }
    if (frame.total != total_) {
      return Result::kTotalMismatch;
    }
  }

  if (frame.sequence != nextSequence_) {
    return Result::kSequenceMismatch;
  }
  if (frame.payloadLength > maxTransferBytes_ - bytesReceived_) {
    return Result::kTooLarge;
  }

  bytesReceived_ += frame.payloadLength;
  ++nextSequence_;
  complete_ = nextSequence_ == total_;
  return Result::kOk;
}

void ReceiveSession::reset() {
  active_ = false;
  complete_ = false;
  kind_ = Kind::kInvoice;
  sessionId_ = 0;
  total_ = 0;
  nextSequence_ = 0;
  bytesReceived_ = 0;
}

}  // namespace rgbbill::chunk
