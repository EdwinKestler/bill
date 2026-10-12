#include <Arduino.h>

// Isolated TTP223 digital-output diagnostic for the LilyGO TTGO LoRa32 V1.x.
// GPIO12 is not used by the onboard SX1276. It is also the MTDI flash-voltage
// strapping pin, so do not touch the sensor or otherwise drive its output HIGH
// during reset. BLE, LoRa, OLED, and TFT stay off for this test.

namespace {
constexpr uint8_t TOUCH_GPIO = 12;
constexpr uint8_t TOUCH_ACTIVE_LEVEL = HIGH;
constexpr uint16_t DEBOUNCE_MS = 60;
constexpr uint16_t REPORT_INTERVAL_MS = 250;

bool stableTouched = false;
bool candidateTouched = false;
uint32_t candidateSinceMs = 0;
uint32_t lastReportMs = 0;

void reportTransition(bool touched, uint8_t level) {
  Serial.printf("TOUCH_TEST: %s gpio12=%s\n",
                touched ? "TOUCHED" : "RELEASED",
                level == HIGH ? "HIGH" : "LOW");
}
}  // namespace

void setup() {
  pinMode(TOUCH_GPIO, INPUT);
  Serial.begin(115200);
  delay(750);
  Serial.println();
  Serial.println("TOUCH_TEST: TTGO LoRa32 TTP223 digital diagnostic");
  Serial.println("TOUCH_TEST: TTP223 OUT -> GPIO12; active=HIGH");
  Serial.println("TOUCH_TEST: GPIO12 is a boot strap; never drive it HIGH at reset");
  Serial.println("TOUCH_TEST: READY; touch and release the TTP223 pad");
}

void loop() {
  const uint8_t level = digitalRead(TOUCH_GPIO);
  const uint32_t now = millis();
  const bool observedTouched = level == TOUCH_ACTIVE_LEVEL;

  if (observedTouched != candidateTouched) {
    candidateTouched = observedTouched;
    candidateSinceMs = now;
  }

  if (candidateTouched != stableTouched &&
      now - candidateSinceMs >= DEBOUNCE_MS) {
    stableTouched = candidateTouched;
    reportTransition(stableTouched, level);
  }

  if (now - lastReportMs >= REPORT_INTERVAL_MS) {
    lastReportMs = now;
    Serial.printf("TOUCH_TEST: gpio12=%s state=%s\n",
                  level == HIGH ? "HIGH" : "LOW",
                  stableTouched ? "TOUCHED" : "released");
  }

  delay(10);
}
