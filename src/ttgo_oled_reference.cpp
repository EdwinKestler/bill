#include <Arduino.h>
#include <Wire.h>

// LilyGO's V1.3-868 sketch includes this legacy ThingPulse header and creates
// the display with the same address and pin tuple below.
#include <SSD1306.h>

namespace {
constexpr uint8_t OLED_ADDRESS = 0x3C;
constexpr uint8_t OLED_SDA_PIN_REF = 4;
constexpr uint8_t OLED_SCL_PIN_REF = 15;
constexpr uint8_t OLED_RESET_PIN_REF = 16;

SSD1306 display(OLED_ADDRESS, OLED_SDA_PIN_REF, OLED_SCL_PIN_REF);
}  // namespace

void setup() {
  // Match the manufacturer example exactly: release the OLED from reset
  // before calling display.init().
  pinMode(OLED_RESET_PIN_REF, OUTPUT);
  digitalWrite(OLED_RESET_PIN_REF, LOW);
  delay(50);
  digitalWrite(OLED_RESET_PIN_REF, HIGH);

  Serial.begin(115200);
  delay(100);
  Serial.println();
  Serial.println("TTGO_OLED_REFERENCE: LilyGO V1.3 ThingPulse test");
  Serial.println("TTGO_OLED_REFERENCE: SDA=4 SCL=15 RESET=16 ADDR=0x3C");

  const bool initialized = display.init();
  display.flipScreenVertically();
  display.clear();
  display.setTextAlignment(TEXT_ALIGN_CENTER);
  display.setFont(ArialMT_Plain_16);
  display.drawString(64, 0, "LILYGO V1.3");
  display.drawString(64, 22, "OLED TEST");
  display.drawString(64, 44, initialized ? "INIT PASS" : "INIT FAIL");
  display.display();

  Wire.beginTransmission(OLED_ADDRESS);
  const uint8_t i2cResult = Wire.endTransmission();
  Serial.printf("TTGO_OLED_REFERENCE: init=%s i2c_0x3C=%s error=%u\n",
                initialized ? "PASS" : "FAIL", i2cResult == 0 ? "ACK" : "NO_ACK",
                i2cResult);
}

void loop() { delay(1000); }
