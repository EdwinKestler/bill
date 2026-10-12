#include <Arduino.h>
#include <BillDisplay.h>
#include <DockGatt.h>
#include <TapGatt.h>
#include "config.h"

namespace {
BillDisplay billDisplay;
DockGatt dockGatt;
TapGatt tapGatt;
uint32_t displayedCents = 0;
}

void setup() {
  Serial.begin(115200);
  pinMode(LED_STATUS_PIN, OUTPUT);
  digitalWrite(LED_STATUS_PIN, LOW);

  if (billDisplay.begin()) {
    billDisplay.showAmount(0, "STARTING");
  }

  dockGatt.begin();
  tapGatt.begin(dockGatt.server());

  billDisplay.showAmount(0, "BLE READY");
}

void loop() {
  dockGatt.poll();
  tapGatt.poll();

  if (dockGatt.takeTapDiscardRequest()) {
    tapGatt.discardStaged();
  }

  if (tapGatt.canStageOutbound()) {
    DockGatt::InboundTransfer transfer;
    if (dockGatt.moveInboundTransfer(transfer, TapGatt::OUTBOUND_PATH) &&
        !tapGatt.stageOutbound(transfer.kind, transfer.sessionId,
                               transfer.size, transfer.path)) {
      Serial.println("bill: tap handoff failed after dock artifact move");
    }
  }

  TapGatt::InboundTransfer tapped;
  if (tapGatt.peekInboundTransfer(tapped)) {
    dockGatt.queueOutboundTransfer(tapped.kind, tapped.sessionId, tapped.path,
                                   true);
  }

  uint32_t cents = 0;
  char status[16];
  if (dockGatt.takeDisplayUpdate(cents, status, sizeof(status))) {
    displayedCents = cents;
    billDisplay.showAmount(cents, status);
  }
  if (tapGatt.takeStatusUpdate(status, sizeof(status))) {
    billDisplay.showAmount(displayedCents, status);
  }
  delay(20);
}
