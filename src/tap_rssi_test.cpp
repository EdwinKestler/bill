#include <Arduino.h>
#include <BLEAdvertisedDevice.h>
#include <BLEDevice.h>
#include <TapProtocol.h>

#include <cstring>
#include <string>

#include "config.h"

namespace {
portMUX_TYPE statsMux = portMUX_INITIALIZER_UNLOCKED;
char peerName[32] = {};
char peerAddress[18] = {};
int lastRssi = -127;
int minRssi = 127;
int maxRssi = -127;
int32_t rssiSum = 0;
uint32_t samples = 0;

class PeerCallbacks : public BLEAdvertisedDeviceCallbacks {
 public:
  void onResult(BLEAdvertisedDevice device) override {
    if (!device.haveName() || !device.haveRSSI() ||
        device.getName().rfind("RgbBill", 0) != 0 ||
        device.getName() == BLE_DEVICE_NAME) {
      return;
    }

    const std::string name = device.getName();
    const std::string address = device.getAddress().toString();
    const int rssi = device.getRSSI();
    portENTER_CRITICAL(&statsMux);
    strncpy(peerName, name.c_str(), sizeof(peerName) - 1);
    peerName[sizeof(peerName) - 1] = '\0';
    strncpy(peerAddress, address.c_str(), sizeof(peerAddress) - 1);
    peerAddress[sizeof(peerAddress) - 1] = '\0';
    lastRssi = rssi;
    if (rssi < minRssi) {
      minRssi = rssi;
    }
    if (rssi > maxRssi) {
      maxRssi = rssi;
    }
    rssiSum += rssi;
    ++samples;
    portEXIT_CRITICAL(&statsMux);
  }
};

PeerCallbacks peerCallbacks;
uint32_t lastReportMs = 0;
uint32_t lastMissingReportMs = 0;
}  // namespace

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println();
  Serial.printf("TAP_RSSI_TEST: self=%s autonomous advertise+scan\n",
                BLE_DEVICE_NAME);

  BLEDevice::init(BLE_DEVICE_NAME);
  BLEAdvertising* advertising = BLEDevice::getAdvertising();
  advertising->addServiceUUID(BLE_UUIDs::DOCK_SERVICE);
  advertising->setScanResponse(true);
  advertising->start();

  BLEScan* scan = BLEDevice::getScan();
  scan->setAdvertisedDeviceCallbacks(&peerCallbacks, true);
  scan->setActiveScan(true);
  scan->setInterval(100);
  scan->setWindow(80);
  const bool started = scan->start(0, nullptr, false);
  Serial.printf("TAP_RSSI_TEST: scan=%s; peer prefix=RgbBill\n",
                started ? "STARTED" : "FAILED");
}

void loop() {
  const uint32_t now = millis();
  if (now - lastReportMs < 1000U) {
    delay(20);
    return;
  }
  lastReportMs = now;

  char name[sizeof(peerName)] = {};
  char address[sizeof(peerAddress)] = {};
  int last = -127;
  int minimum = 127;
  int maximum = -127;
  int32_t sum = 0;
  uint32_t count = 0;
  portENTER_CRITICAL(&statsMux);
  strncpy(name, peerName, sizeof(name) - 1);
  strncpy(address, peerAddress, sizeof(address) - 1);
  last = lastRssi;
  minimum = minRssi;
  maximum = maxRssi;
  sum = rssiSum;
  count = samples;
  minRssi = 127;
  maxRssi = -127;
  rssiSum = 0;
  samples = 0;
  portEXIT_CRITICAL(&statsMux);

  if (count > 0) {
    Serial.printf(
        "TAP_RSSI_TEST: peer=%s address=%s last=%d min=%d max=%d avg=%ld "
        "samples=%lu threshold=%d %s\n",
        name, address, last, minimum, maximum,
        static_cast<long>(sum / static_cast<int32_t>(count)),
        static_cast<unsigned long>(count),
        rgbbill::tap::DEFAULT_RSSI_THRESHOLD_DBM,
        last >= rgbbill::tap::DEFAULT_RSSI_THRESHOLD_DBM ? "QUALIFIES"
                                                         : "TOO_FAR");
    lastMissingReportMs = now;
  } else if (now - lastMissingReportMs >= 5000U) {
    Serial.println("TAP_RSSI_TEST: no peer seen in the last 5s");
    lastMissingReportMs = now;
  }
  delay(20);
}
