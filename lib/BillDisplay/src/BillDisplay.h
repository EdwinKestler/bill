#pragma once

#include <Adafruit_SSD1306.h>
#include <cstdint>

class BillDisplay {
 public:
  BillDisplay();

  // Probes the two common SSD1306 addresses and initializes the display.
  // Failure is non-fatal so the bill can keep advertising over BLE.
  bool begin();
  void showAmount(uint32_t cents, const char* status);

  bool available() const { return available_; }
  uint8_t address() const { return address_; }

 private:
  bool probeAddress(uint8_t address);

  Adafruit_SSD1306 display_;
  uint8_t address_ = 0;
  bool available_ = false;
};
