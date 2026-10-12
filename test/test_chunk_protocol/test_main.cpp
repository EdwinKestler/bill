#include <ChunkProtocol.h>
#include <unity.h>

#include <array>
#include <cstdint>

using rgbbill::chunk::FrameView;
using rgbbill::chunk::Kind;
using rgbbill::chunk::ReceiveSession;
using rgbbill::chunk::Result;

namespace {

void test_frame_round_trip_and_known_crc() {
  const std::array<uint8_t, 9> known = {'1', '2', '3', '4', '5',
                                         '6', '7', '8', '9'};
  TEST_ASSERT_EQUAL_HEX32(0xCBF43926U,
                          rgbbill::chunk::crc32(known.data(), known.size()));

  const std::array<uint8_t, 4> payload = {0x00, 0x11, 0xFE, 0xFF};
  std::array<uint8_t, rgbbill::chunk::MAX_FRAME_SIZE> encoded{};
  size_t encodedLength = 0;
  TEST_ASSERT_TRUE(rgbbill::chunk::encodeFrame(
      Kind::kConsignment, 0x78563412U, 2, 4, payload.data(), payload.size(),
      encoded.data(), encoded.size(), encodedLength));

  FrameView decoded;
  TEST_ASSERT_EQUAL_UINT8(
      static_cast<uint8_t>(Result::kOk),
      static_cast<uint8_t>(rgbbill::chunk::decodeFrame(
          encoded.data(), encodedLength, decoded)));
  TEST_ASSERT_EQUAL_UINT8(static_cast<uint8_t>(Kind::kConsignment),
                          static_cast<uint8_t>(decoded.kind));
  TEST_ASSERT_EQUAL_HEX32(0x78563412U, decoded.sessionId);
  TEST_ASSERT_EQUAL_UINT16(2, decoded.sequence);
  TEST_ASSERT_EQUAL_UINT16(4, decoded.total);
  TEST_ASSERT_EQUAL_UINT16(payload.size(), decoded.payloadLength);
  TEST_ASSERT_EQUAL_UINT8_ARRAY(payload.data(), decoded.payload, payload.size());
}

void test_crc_corruption_is_rejected() {
  const std::array<uint8_t, 2> payload = {0xAA, 0x55};
  std::array<uint8_t, rgbbill::chunk::MAX_FRAME_SIZE> encoded{};
  size_t encodedLength = 0;
  TEST_ASSERT_TRUE(rgbbill::chunk::encodeFrame(
      Kind::kInvoice, 7, 0, 1, payload.data(), payload.size(), encoded.data(),
      encoded.size(), encodedLength));
  encoded[rgbbill::chunk::HEADER_SIZE] ^= 0x01;

  FrameView decoded;
  TEST_ASSERT_EQUAL_UINT8(
      static_cast<uint8_t>(Result::kCrcMismatch),
      static_cast<uint8_t>(rgbbill::chunk::decodeFrame(
          encoded.data(), encodedLength, decoded)));
}

FrameView frame(Kind kind, uint32_t session, uint16_t sequence,
                uint16_t total, const uint8_t* payload, uint16_t length) {
  FrameView value;
  value.version = rgbbill::chunk::VERSION;
  value.kind = kind;
  value.sessionId = session;
  value.sequence = sequence;
  value.total = total;
  value.payload = payload;
  value.payloadLength = length;
  return value;
}

void test_receive_session_requires_order_and_matching_metadata() {
  const std::array<uint8_t, 2> payload = {1, 2};
  ReceiveSession session(16);

  TEST_ASSERT_EQUAL_UINT8(
      static_cast<uint8_t>(Result::kSequenceMismatch),
      static_cast<uint8_t>(session.accept(
          frame(Kind::kInvoice, 9, 1, 2, payload.data(), payload.size()))));
  TEST_ASSERT_EQUAL_UINT8(
      static_cast<uint8_t>(Result::kOk),
      static_cast<uint8_t>(session.accept(
          frame(Kind::kInvoice, 9, 0, 2, payload.data(), payload.size()))));
  TEST_ASSERT_EQUAL_UINT8(
      static_cast<uint8_t>(Result::kSessionMismatch),
      static_cast<uint8_t>(session.accept(
          frame(Kind::kInvoice, 10, 1, 2, payload.data(), payload.size()))));
  TEST_ASSERT_EQUAL_UINT8(
      static_cast<uint8_t>(Result::kTotalMismatch),
      static_cast<uint8_t>(session.accept(
          frame(Kind::kInvoice, 9, 1, 3, payload.data(), payload.size()))));
  TEST_ASSERT_EQUAL_UINT8(
      static_cast<uint8_t>(Result::kOk),
      static_cast<uint8_t>(session.accept(
          frame(Kind::kInvoice, 9, 1, 2, payload.data(), payload.size()))));
  TEST_ASSERT_TRUE(session.complete());
  TEST_ASSERT_EQUAL_UINT32(4, session.bytesReceived());
  TEST_ASSERT_EQUAL_UINT8(
      static_cast<uint8_t>(Result::kBusy),
      static_cast<uint8_t>(session.accept(
          frame(Kind::kInvoice, 9, 1, 2, payload.data(), payload.size()))));
}

void test_receive_session_enforces_total_size_limit() {
  const std::array<uint8_t, 3> payload = {1, 2, 3};
  ReceiveSession session(5);
  TEST_ASSERT_EQUAL_UINT8(
      static_cast<uint8_t>(Result::kOk),
      static_cast<uint8_t>(session.accept(
          frame(Kind::kConsignment, 42, 0, 2, payload.data(), payload.size()))));
  TEST_ASSERT_EQUAL_UINT8(
      static_cast<uint8_t>(Result::kTooLarge),
      static_cast<uint8_t>(session.accept(
          frame(Kind::kConsignment, 42, 1, 2, payload.data(), payload.size()))));
  TEST_ASSERT_FALSE(session.complete());
}

}  // namespace

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_frame_round_trip_and_known_crc);
  RUN_TEST(test_crc_corruption_is_rejected);
  RUN_TEST(test_receive_session_requires_order_and_matching_metadata);
  RUN_TEST(test_receive_session_enforces_total_size_limit);
  return UNITY_END();
}
