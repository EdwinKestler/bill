#include <Arduino.h>
#include <Wire.h>

namespace {
constexpr uint8_t OLED_ADDRESS = 0x3C;
constexpr uint8_t OLED_SDA_PIN = 4;
constexpr uint8_t OLED_SCL_PIN = 15;
constexpr uint8_t OLED_RESET_PIN = 16;
constexpr uint32_t PHASE_DURATION_MS = 4000;
bool controllerReady = false;

enum class Phase : uint8_t {
  kControllerAllOn,
  kRamSolidOn,
  kInverseEmptyRam,
  kCheckerboard,
  kDisplayOff,
  kCount,
};

bool sendCommand(uint8_t command) {
  Wire.beginTransmission(OLED_ADDRESS);
  Wire.write(0x00);  // Control byte: following byte is a command.
  Wire.write(command);
  return Wire.endTransmission() == 0;
}

bool sendCommand(uint8_t command, uint8_t argument) {
  Wire.beginTransmission(OLED_ADDRESS);
  Wire.write(0x00);
  Wire.write(command);
  Wire.write(argument);
  return Wire.endTransmission() == 0;
}

bool sendCommand(uint8_t command, uint8_t firstArgument,
                 uint8_t secondArgument) {
  Wire.beginTransmission(OLED_ADDRESS);
  Wire.write(0x00);
  Wire.write(command);
  Wire.write(firstArgument);
  Wire.write(secondArgument);
  return Wire.endTransmission() == 0;
}

bool initializeController() {
  // SSD1306 128x64 initialization, issued without a display library.
  return sendCommand(0xAE) &&       // Display off.
         sendCommand(0xD5, 0x80) && // Clock divide ratio.
         sendCommand(0xA8, 0x3F) && // Multiplex: 64 rows.
         sendCommand(0xD3, 0x00) && // Display offset.
         sendCommand(0x40) &&       // Start line 0.
         sendCommand(0x8D, 0x14) && // Internal charge pump on.
         sendCommand(0x20, 0x00) && // Horizontal addressing mode.
         sendCommand(0xA1) &&       // Segment remap.
         sendCommand(0xC8) &&       // COM scan direction remap.
         sendCommand(0xDA, 0x12) && // COM pins for 128x64.
         sendCommand(0x81, 0xCF) && // Contrast.
         sendCommand(0xD9, 0xF1) && // Pre-charge period.
         sendCommand(0xDB, 0x40) && // VCOMH deselect level.
         sendCommand(0x2E) &&       // Stop scrolling.
         sendCommand(0xA4) &&       // Display follows RAM.
         sendCommand(0xA6) &&       // Normal display.
         sendCommand(0xAF);         // Display on.
}

bool setFullWindow() {
  return sendCommand(0x21, 0x00, 0x7F) &&
         sendCommand(0x22, 0x00, 0x07);
}

bool fillRam(uint8_t evenByte, uint8_t oddByte) {
  if (!setFullWindow()) {
    return false;
  }

  for (uint16_t offset = 0; offset < 1024; offset += 16) {
    Wire.beginTransmission(OLED_ADDRESS);
    Wire.write(0x40);  // Control byte: following bytes are display data.
    for (uint8_t index = 0; index < 16; ++index) {
      Wire.write(((offset + index) & 1U) == 0U ? evenByte : oddByte);
    }
    if (Wire.endTransmission() != 0) {
      return false;
    }
  }
  return true;
}

bool showPhase(Phase phase) {
  bool ok = sendCommand(0xAF);  // Ensure the panel is enabled first.

  switch (phase) {
    case Phase::kControllerAllOn:
      Serial.println("TTGO_OLED_RAW: PHASE 1/5 controller ALL PIXELS ON (0xA5)");
      // This ignores display RAM completely. It is the decisive panel test.
      return ok && sendCommand(0xA6) && sendCommand(0xA5);
    case Phase::kRamSolidOn:
      Serial.println("TTGO_OLED_RAW: PHASE 2/5 RAM SOLID ON (0xFF)");
      return ok && sendCommand(0xA4) && sendCommand(0xA6) &&
             fillRam(0xFF, 0xFF);
    case Phase::kInverseEmptyRam:
      Serial.println("TTGO_OLED_RAW: PHASE 3/5 INVERSE EMPTY RAM");
      return ok && sendCommand(0xA4) && fillRam(0x00, 0x00) &&
             sendCommand(0xA7);
    case Phase::kCheckerboard:
      Serial.println("TTGO_OLED_RAW: PHASE 4/5 CHECKERBOARD");
      return ok && sendCommand(0xA4) && sendCommand(0xA6) &&
             fillRam(0xAA, 0x55);
    case Phase::kDisplayOff:
      Serial.println("TTGO_OLED_RAW: PHASE 5/5 DISPLAY OFF (0xAE)");
      return ok && sendCommand(0xAE);
    case Phase::kCount:
      break;
  }
  return false;
}
}  // namespace

void setup() {
  Serial.begin(115200);
  delay(100);
  Serial.println();
  Serial.println("TTGO_OLED_RAW: no-library final panel diagnostic");
  Serial.println("TTGO_OLED_RAW: SDA=4 SCL=15 RESET=16 ADDR=0x3C");

  pinMode(OLED_RESET_PIN, OUTPUT);
  digitalWrite(OLED_RESET_PIN, LOW);
  delay(50);
  digitalWrite(OLED_RESET_PIN, HIGH);
  delay(50);

  Wire.begin(OLED_SDA_PIN, OLED_SCL_PIN);
  Wire.setClock(100000);
  Wire.beginTransmission(OLED_ADDRESS);
  const uint8_t probeResult = Wire.endTransmission();
  Serial.printf("TTGO_OLED_RAW: probe=%s error=%u\n",
                probeResult == 0 ? "ACK" : "NO_ACK", probeResult);

  const bool initialized = probeResult == 0 && initializeController();
  Serial.printf("TTGO_OLED_RAW: raw_init=%s\n",
                initialized ? "PASS" : "FAIL");
  if (!initialized) {
    Serial.println("TTGO_OLED_RAW: STOP - controller did not accept commands");
    return;
  }

  controllerReady = true;
  const bool phaseOk = showPhase(Phase::kControllerAllOn);
  Serial.printf("TTGO_OLED_RAW: phase_write=%s\n", phaseOk ? "PASS" : "FAIL");
}

void loop() {
  static uint32_t changedAt = millis();
  static Phase phase = Phase::kControllerAllOn;

  if (!controllerReady) {
    delay(1000);
    return;
  }

  if (millis() - changedAt < PHASE_DURATION_MS) {
    delay(10);
    return;
  }

  const uint8_t next = (static_cast<uint8_t>(phase) + 1U) %
                       static_cast<uint8_t>(Phase::kCount);
  phase = static_cast<Phase>(next);
  changedAt = millis();
  const bool phaseOk = showPhase(phase);
  Serial.printf("TTGO_OLED_RAW: phase_write=%s\n", phaseOk ? "PASS" : "FAIL");
}
