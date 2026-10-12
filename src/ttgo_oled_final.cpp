#include <Arduino.h>
#include <Wire.h>

#include <SSD1306.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

// Final isolated reproduction for the older TTGO LoRa32 V1.3 vendor sketch.
// LoRa and BLE are deliberately excluded. The test uses the vendor's exact
// GPIO tuple and reset edge sequence, then renders through both libraries.
namespace {
constexpr uint8_t OLED_ADDRESS = 0x3C;
constexpr uint8_t OLED_SDA_PIN = 4;
constexpr uint8_t OLED_SCL_PIN = 15;
constexpr uint8_t OLED_RESET_PIN = 16;
constexpr uint32_t PHASE_DURATION_MS = 4000;

SSD1306 vendorDisplay(OLED_ADDRESS, OLED_SDA_PIN, OLED_SCL_PIN);
Adafruit_SSD1306 adafruitDisplay(128, 64, &Wire, -1);

bool vendorReady = false;
bool adafruitReady = false;

void pulseVendorReset() {
  // Match the vendor demo exactly: HIGH -> LOW -> HIGH, with 100 ms before
  // each edge. Adafruit does not pulse reset again because it is passed -1.
  pinMode(OLED_RESET_PIN, OUTPUT);
  digitalWrite(OLED_RESET_PIN, HIGH);
  delay(100);
  digitalWrite(OLED_RESET_PIN, LOW);
  delay(100);
  digitalWrite(OLED_RESET_PIN, HIGH);
}

uint8_t probe(uint8_t address) {
  Wire.beginTransmission(address);
  return Wire.endTransmission();
}

void showVendorPhase() {
  Serial.println("TTGO_OLED_FINAL: PHASE vendor ThingPulse SSD1306");
  vendorDisplay.clear();
  vendorDisplay.setTextAlignment(TEXT_ALIGN_CENTER);
  vendorDisplay.setFont(ArialMT_Plain_16);
  vendorDisplay.drawString(64, 0, "VENDOR DRIVER");
  vendorDisplay.drawString(64, 22, "SDA4 SCL15");
  vendorDisplay.drawString(64, 44, "RESET16");
  vendorDisplay.display();
}

void showAdafruitPhase() {
  Serial.println("TTGO_OLED_FINAL: PHASE Adafruit SSD1306");
  adafruitDisplay.clearDisplay();
  adafruitDisplay.drawRect(0, 0, 128, 64, SSD1306_WHITE);
  adafruitDisplay.setTextColor(SSD1306_WHITE);
  adafruitDisplay.setTextSize(1);
  adafruitDisplay.setCursor(19, 8);
  adafruitDisplay.print("ADAFRUIT DRIVER");
  adafruitDisplay.setTextSize(2);
  adafruitDisplay.setCursor(16, 27);
  adafruitDisplay.print("OLED TEST");
  adafruitDisplay.setTextSize(1);
  adafruitDisplay.setCursor(34, 51);
  adafruitDisplay.print("4 / 15 / 16");
  adafruitDisplay.display();
}
}  // namespace

void setup() {
  Serial.begin(115200);
  delay(100);
  Serial.println();
  Serial.println("TTGO_OLED_FINAL: vendor reset + two-library diagnostic");
  Serial.println("TTGO_OLED_FINAL: SDA=4 SCL=15 RESET=16 ADDR=0x3C");

  pulseVendorReset();

  Wire.begin(OLED_SDA_PIN, OLED_SCL_PIN);
  Wire.setClock(400000);
  const uint8_t result3c = probe(0x3C);
  const uint8_t result3d = probe(0x3D);
  Serial.printf("TTGO_OLED_FINAL: probe_0x3C=%s error=%u\n",
                result3c == 0 ? "ACK" : "NO_ACK", result3c);
  Serial.printf("TTGO_OLED_FINAL: probe_0x3D=%s error=%u\n",
                result3d == 0 ? "ACK" : "NO_ACK", result3d);

  vendorReady = vendorDisplay.init();
  vendorDisplay.flipScreenVertically();
  Serial.printf("TTGO_OLED_FINAL: vendor_init=%s\n",
                vendorReady ? "PASS" : "FAIL");
  if (vendorReady) {
    showVendorPhase();
    delay(PHASE_DURATION_MS);
  }

  // Reproduce the hardware reset before the independent Adafruit init. Wire
  // remains on GPIO4/15 and begin(..., false, false) neither remaps it nor
  // performs another reset pulse.
  pulseVendorReset();
  adafruitReady = adafruitDisplay.begin(
      SSD1306_SWITCHCAPVCC, OLED_ADDRESS, false, false);
  Serial.printf("TTGO_OLED_FINAL: adafruit_init=%s\n",
                adafruitReady ? "PASS" : "FAIL");
  if (adafruitReady) {
    showAdafruitPhase();
  }

  if (!vendorReady && !adafruitReady) {
    Serial.println("TTGO_OLED_FINAL: STOP - neither driver initialized");
  }
}

void loop() {
  if (!vendorReady && !adafruitReady) {
    delay(1000);
    return;
  }

  static uint32_t changedAt = millis();
  static bool vendorPhase = true;  // Setup finishes on the Adafruit phase.
  if (millis() - changedAt < PHASE_DURATION_MS) {
    delay(10);
    return;
  }

  changedAt = millis();
  if (vendorPhase && vendorReady) {
    showVendorPhase();
  } else if (adafruitReady) {
    showAdafruitPhase();
  }
  vendorPhase = !vendorPhase;
}
