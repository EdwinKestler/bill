#include "BillDisplay.h"

#include <Arduino.h>
#include <Wire.h>

#include "config.h"

BillDisplay::BillDisplay()
    : display_(OLED_WIDTH, OLED_HEIGHT, &Wire, OLED_RESET_PIN) {}

bool BillDisplay::probeAddress(uint8_t address) {
  Wire.beginTransmission(address);
  return Wire.endTransmission() == 0;
}

bool BillDisplay::begin() {
  Serial.printf("display: I2C SDA=%u SCL=%u\n", OLED_SDA_PIN, OLED_SCL_PIN);

  // LilyGO's TTGO LoRa32 V1.3 reference holds the onboard OLED in reset on
  // GPIO16, then releases it before initializing or probing I2C. Probing first
  // cannot succeed while the controller is still held in reset. The WEMOS
  // profile uses -1 and skips this board-specific step.
  if (OLED_RESET_PIN >= 0) {
    Serial.printf("display: reset GPIO=%d\n", OLED_RESET_PIN);
    pinMode(OLED_RESET_PIN, OUTPUT);
    digitalWrite(OLED_RESET_PIN, LOW);
    delay(50);
    digitalWrite(OLED_RESET_PIN, HIGH);
    delay(10);
  }

  Wire.begin(OLED_SDA_PIN, OLED_SCL_PIN);
  Wire.setClock(400000);

  if (probeAddress(OLED_ADDRESS_PRIMARY)) {
    address_ = OLED_ADDRESS_PRIMARY;
  } else if (probeAddress(OLED_ADDRESS_SECONDARY)) {
    address_ = OLED_ADDRESS_SECONDARY;
  } else {
    Serial.println("display: no SSD1306 found at 0x3C or 0x3D");
    return false;
  }

  // Wire is already configured with the LOLIN32 pins, so prevent the library
  // from reinitializing the peripheral with board defaults.
  // Reset was performed above, before the address probe. Do not pulse it a
  // second time inside Adafruit_SSD1306::begin().
  if (!display_.begin(SSD1306_SWITCHCAPVCC, address_, false, false)) {
    Serial.printf("display: SSD1306 init failed at 0x%02X\n", address_);
    address_ = 0;
    return false;
  }

  available_ = true;
  display_.clearDisplay();
  display_.display();
  Serial.printf("display: SSD1306 ready at 0x%02X\n", address_);
  return true;
}

void BillDisplay::showAmount(uint32_t cents, const char* status) {
  if (!available_) {
    return;
  }

  char amount[20];
  snprintf(amount, sizeof(amount), "$%lu.%02lu",
           static_cast<unsigned long>(cents / 100),
           static_cast<unsigned long>(cents % 100));

  display_.clearDisplay();
  display_.drawRect(0, 0, OLED_WIDTH, OLED_HEIGHT, SSD1306_WHITE);
  display_.setTextColor(SSD1306_WHITE);

  display_.setTextSize(1);
  display_.setCursor(40, 5);
  display_.print("RGB BILL");

  if (cents > 0) {
    display_.setTextSize(2);
    int16_t x1 = 0;
    int16_t y1 = 0;
    uint16_t width = 0;
    uint16_t height = 0;
    display_.getTextBounds(amount, 0, 0, &x1, &y1, &width, &height);
    display_.setCursor((OLED_WIDTH - width) / 2, 24);
    display_.print(amount);
  }

  display_.setTextSize(1);
  display_.setCursor(5, 52);
  display_.print(status == nullptr ? "" : status);
  display_.display();
}
