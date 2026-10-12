#pragma once

#include <Adafruit_ILI9341.h>
#include <cstdint>

class TftBillDisplay {
 public:
  TftBillDisplay();

  // Initializes the write-only SPI display. ILI9341 has no reliable device-ID
  // probe on this wiring, so begin() confirms only that initialization ran.
  bool begin();
  void showAmount(uint32_t cents, const char* status);

  bool available() const { return available_; }

 private:
  Adafruit_ILI9341 display_;
  bool available_ = false;
};
