#include "TftBillDisplay.h"

#include <Arduino.h>
#include <SPI.h>

#include "config.h"

namespace {
constexpr uint32_t TFT_SPI_FREQUENCY_HZ = 20000000;
constexpr uint8_t TFT_ROTATION = 1;
}  // namespace

TftBillDisplay::TftBillDisplay()
    : display_(&SPI, TFT_DC_PIN, TFT_CS_PIN, TFT_RESET_PIN) {}

bool TftBillDisplay::begin() {
  Serial.printf("display: SPI ILI9341 SCK=%u MOSI=%u DC=%u RESET=%u CS=%u\n",
                TFT_SCK_PIN, TFT_MOSI_PIN, TFT_DC_PIN, TFT_RESET_PIN,
                TFT_CS_PIN);

  // Do not source an unknown TFT backlight load from an ESP32 GPIO. Many
  // ILI9341 breakouts expose LED as the backlight power input, not as a logic
  // enable. Power it from 3V3 or use a transistor after checking the module.
  pinMode(TFT_BACKLIGHT_PIN, INPUT);
  Serial.printf(
      "display: GPIO%u backlight is NOT driven; TFT LED must be safely powered\n",
      TFT_BACKLIGHT_PIN);
  SPI.begin(TFT_SCK_PIN, -1, TFT_MOSI_PIN, TFT_CS_PIN);
  display_.begin(TFT_SPI_FREQUENCY_HZ);
  display_.setRotation(TFT_ROTATION);
  display_.fillScreen(ILI9341_BLACK);
  available_ = true;
  Serial.println("display: ILI9341 ready 320x240 rotation=1 SPI=20MHz");
  return true;
}

void TftBillDisplay::showAmount(uint32_t cents, const char* status) {
  if (!available_) {
    return;
  }

  char amount[20];
  snprintf(amount, sizeof(amount), "$%lu.%02lu",
           static_cast<unsigned long>(cents / 100),
           static_cast<unsigned long>(cents % 100));

  display_.fillScreen(ILI9341_BLACK);
  display_.drawRect(0, 0, display_.width(), display_.height(), ILI9341_CYAN);
  display_.drawRect(4, 4, display_.width() - 8, display_.height() - 8,
                    ILI9341_BLUE);

  display_.setTextWrap(false);
  display_.setTextColor(ILI9341_CYAN, ILI9341_BLACK);
  display_.setTextSize(3);
  display_.setCursor(82, 28);
  display_.print("RGB BILL");

  if (cents > 0) {
    int16_t x1 = 0;
    int16_t y1 = 0;
    uint16_t width = 0;
    uint16_t height = 0;
    display_.setTextColor(ILI9341_WHITE, ILI9341_BLACK);
    display_.setTextSize(6);
    display_.getTextBounds(amount, 0, 0, &x1, &y1, &width, &height);
    display_.setCursor((display_.width() - width) / 2, 92);
    display_.print(amount);
  }

  display_.fillRect(5, 186, display_.width() - 10, 48, ILI9341_NAVY);
  display_.setTextColor(ILI9341_YELLOW, ILI9341_NAVY);
  display_.setTextSize(3);
  display_.setCursor(16, 198);
  display_.print(status == nullptr ? "" : status);
}
