#include <Arduino.h>
#include <BillDisplay.h>

namespace {
BillDisplay billDisplay;
uint32_t frame = 0;
}  // namespace

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println();
  Serial.println("OLED_TEST: WEMOS LOLIN32 + SSD1306 128x64");
  if (!billDisplay.begin()) {
    Serial.println("OLED_TEST: FAIL");
    return;
  }

  Serial.printf("OLED_TEST: PASS - SSD1306 initialized at 0x%02X\n",
                billDisplay.address());
  billDisplay.showAmount(500, "OLED TEST 0");
}

void loop() {
  if (!billDisplay.available()) {
    delay(1000);
    return;
  }

  ++frame;
  char status[24];
  snprintf(status, sizeof(status), "OLED TEST %lu",
           static_cast<unsigned long>(frame));
  billDisplay.showAmount(500, status);
  delay(250);
}
