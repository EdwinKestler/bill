#include <TapProtocol.h>
#include <unity.h>

#include <array>

namespace {

void test_metadata_round_trip() {
  rgbbill::tap::Metadata input;
  input.state = rgbbill::tap::ReadyState::kReady;
  input.kind = 2;
  input.sessionId = 0x78563412U;
  input.size = 655360U;
  input.denominationCents = 500U;
  std::array<uint8_t, rgbbill::tap::METADATA_SIZE> encoded{};
  TEST_ASSERT_TRUE(rgbbill::tap::encodeMetadata(input, encoded.data(),
                                                encoded.size()));
  rgbbill::tap::Metadata decoded;
  TEST_ASSERT_TRUE(rgbbill::tap::decodeMetadata(encoded.data(), encoded.size(),
                                                decoded));
  TEST_ASSERT_EQUAL_UINT8(1, static_cast<uint8_t>(decoded.state));
  TEST_ASSERT_EQUAL_UINT8(2, decoded.kind);
  TEST_ASSERT_EQUAL_HEX32(0x78563412U, decoded.sessionId);
  TEST_ASSERT_EQUAL_UINT32(655360U, decoded.size);
  TEST_ASSERT_EQUAL_UINT32(500U, decoded.denominationCents);
}

void test_metadata_decodes_legacy_v1_without_denomination() {
  std::array<uint8_t, rgbbill::tap::LEGACY_METADATA_SIZE> encoded{};
  encoded[0] = rgbbill::tap::LEGACY_VERSION;
  encoded[1] = 1;
  encoded[2] = 1;
  encoded[4] = 0x12;
  encoded[8] = 0x34;
  rgbbill::tap::Metadata decoded;
  TEST_ASSERT_TRUE(rgbbill::tap::decodeMetadata(encoded.data(), encoded.size(),
                                                decoded));
  TEST_ASSERT_EQUAL_UINT8(1, decoded.kind);
  TEST_ASSERT_EQUAL_UINT32(0x12U, decoded.sessionId);
  TEST_ASSERT_EQUAL_UINT32(0x34U, decoded.size);
  TEST_ASSERT_EQUAL_UINT32(0U, decoded.denominationCents);
}

void test_metadata_rejects_bad_version_and_reserved_byte() {
  std::array<uint8_t, rgbbill::tap::METADATA_SIZE> encoded{};
  encoded[0] = 3;
  rgbbill::tap::Metadata decoded;
  TEST_ASSERT_FALSE(rgbbill::tap::decodeMetadata(encoded.data(), encoded.size(),
                                                 decoded));
  encoded[0] = rgbbill::tap::VERSION;
  encoded[3] = 1;
  TEST_ASSERT_FALSE(rgbbill::tap::decodeMetadata(encoded.data(), encoded.size(),
                                                 decoded));
}

void test_gate_emits_one_edge_per_debounced_press() {
  rgbbill::tap::Gate gate(rgbbill::tap::DEFAULT_RSSI_THRESHOLD_DBM, 40);
  gate.updateButton(true, 100);
  TEST_ASSERT_FALSE(gate.takePressedEdge());
  gate.updateButton(true, 139);
  TEST_ASSERT_FALSE(gate.takePressedEdge());
  gate.updateButton(true, 140);
  TEST_ASSERT_TRUE(gate.takePressedEdge());
  TEST_ASSERT_FALSE(gate.takePressedEdge());

  gate.updateButton(false, 200);
  gate.updateButton(false, 240);
  TEST_ASSERT_FALSE(gate.takePressedEdge());

  gate.updateButton(true, 300);
  gate.updateButton(true, 340);
  TEST_ASSERT_TRUE(gate.takePressedEdge());
  TEST_ASSERT_FALSE(gate.takePressedEdge());
}

void test_gate_applies_rssi_independently_of_button_level() {
  rgbbill::tap::Gate gate;
  TEST_ASSERT_TRUE(gate.rssiAllows(-60));
  TEST_ASSERT_FALSE(gate.rssiAllows(-61));

  gate.updateButton(true, 100);
  gate.updateButton(true, 140);
  TEST_ASSERT_TRUE(gate.takePressedEdge());
  gate.updateButton(false, 200);
  gate.updateButton(false, 240);
  TEST_ASSERT_FALSE(gate.buttonPressed());
  TEST_ASSERT_TRUE(gate.rssiAllows(-30));
}

void test_one_shot_arm_consumes_or_expires_once() {
  rgbbill::tap::OneShotArm arm(15000);
  TEST_ASSERT_FALSE(arm.armed());
  TEST_ASSERT_FALSE(arm.consume());

  arm.arm(100);
  TEST_ASSERT_TRUE(arm.armed());
  TEST_ASSERT_FALSE(arm.expire(15099));
  TEST_ASSERT_TRUE(arm.consume());
  TEST_ASSERT_FALSE(arm.armed());
  TEST_ASSERT_FALSE(arm.consume());

  arm.arm(200);
  TEST_ASSERT_TRUE(arm.expire(15200));
  TEST_ASSERT_FALSE(arm.armed());
  TEST_ASSERT_FALSE(arm.expire(15201));
}

void test_one_shot_arm_timeout_is_millis_wrap_safe() {
  rgbbill::tap::OneShotArm arm(20);
  arm.arm(0xFFFFFFF5U);
  TEST_ASSERT_FALSE(arm.expire(8));
  TEST_ASSERT_TRUE(arm.expire(9));
}

}  // namespace

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_metadata_round_trip);
  RUN_TEST(test_metadata_rejects_bad_version_and_reserved_byte);
  RUN_TEST(test_metadata_decodes_legacy_v1_without_denomination);
  RUN_TEST(test_gate_emits_one_edge_per_debounced_press);
  RUN_TEST(test_gate_applies_rssi_independently_of_button_level);
  RUN_TEST(test_one_shot_arm_consumes_or_expires_once);
  RUN_TEST(test_one_shot_arm_timeout_is_millis_wrap_safe);
  return UNITY_END();
}
