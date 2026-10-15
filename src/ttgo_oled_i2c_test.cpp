#include <Arduino.h>
#include <Wire.h>

#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

// Isolated test for the replacement external four-wire I2C OLED.
// The external module has no reset lead, so GPIO16 is deliberately untouched.
// The ILI9341 TFT uses different pins and is deliberately not initialized by
// this isolated diagnostic.
namespace {
constexpr uint8_t OLED_SDA_PIN = 21;
constexpr uint8_t OLED_SCL_PIN = 22;
constexpr int8_t OLED_RESET_PIN = -1;
constexpr int16_t OLED_WIDTH = 128;
constexpr int16_t OLED_HEIGHT = 64;
constexpr uint32_t I2C_CLOCK_HZ = 100000;
constexpr uint32_t PHASE_DURATION_MS = 2000;

Adafruit_SSD1306 display(OLED_WIDTH, OLED_HEIGHT, &Wire, OLED_RESET_PIN);
uint8_t displayAddress = 0;
bool displayReady = false;
bool inverted = false;
uint32_t phaseChangedAt = 0;

uint8_t probeAddress(uint8_t address) {
  Wire.beginTransmission(address);
  return Wire.endTransmission();
}

void drawTestPattern() {
  display.clearDisplay();
  display.drawRect(0, 0, OLED_WIDTH, OLED_HEIGHT, SSD1306_WHITE);
  display.setTextColor(SSD1306_WHITE);
  display.setTextSize(2);
  display.setCursor(10, 8);
  display.print("TTGO OLED");
  display.setTextSize(1);
  display.setCursor(22, 34);
  display.print("SDA 21 SCL 22");
  display.setCursor(19, 49);
  display.printf("I2C 0x%02X PASS", displayAddress);
  display.display();
}
}  // namespace

void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.println();
  Serial.println("TTGO_OLED_I2C_TEST: external 128x64 SSD1306");
  Serial.println("TTGO_OLED_I2C_TEST: SDA=21 SCL=22 RESET=-1");
  Serial.println("TTGO_OLED_I2C_TEST: TFT is not initialized");

  Wire.begin(OLED_SDA_PIN, OLED_SCL_PIN);
  Wire.setClock(I2C_CLOCK_HZ);

  for (const uint8_t address : {uint8_t{0x3C}, uint8_t{0x3D}}) {
    const uint8_t error = probeAddress(address);
    Serial.printf("TTGO_OLED_I2C_TEST: probe_0x%02X=%s error=%u\n", address,
                  error == 0 ? "ACK" : "NO_ACK", error);
    if (error == 0 && displayAddress == 0) {
      displayAddress = address;
    }
  }

  if (displayAddress == 0) {
    Serial.println("TTGO_OLED_I2C_TEST: FAIL - no OLED at 0x3C or 0x3D");
    return;
  }

  displayReady = display.begin(SSD1306_SWITCHCAPVCC, displayAddress, false,
                               false);
  if (!displayReady) {
    Serial.printf("TTGO_OLED_I2C_TEST: FAIL - init at 0x%02X\n",
                  displayAddress);
    return;
  }

  drawTestPattern();
  phaseChangedAt = millis();
  Serial.printf("TTGO_OLED_I2C_TEST: PASS - visible test at 0x%02X\n",
                displayAddress);
}

void loop() {
  if (!displayReady) {
    delay(1000);
    return;
  }

  if (millis() - phaseChangedAt >= PHASE_DURATION_MS) {
    phaseChangedAt = millis();
    inverted = !inverted;
    display.invertDisplay(inverted);
    Serial.printf("TTGO_OLED_I2C_TEST: phase=%s\n",
                  inverted ? "INVERTED" : "NORMAL");
  }
  delay(10);
}
