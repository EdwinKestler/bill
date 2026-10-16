# T-Watch fork2checkbook app plan

Date: 2026-10-16

This is the bounded implementation plan for adding a LilyGO T-Watch 2020 V1
as a fork2checkbook device. The laptop remains the dock. The watch does not run
rgb-lib, hold a wallet mnemonic, host the note vault, run QVAC, access
Mutinynet, or confirm a spend.

Status: **reference inspected; port not implemented, built, flashed, or
physically accepted.** The already accepted WEMOS and TTGO LoRa32 profiles
remain the fallback demo hardware until every watch gate below passes.

## Deliberate minimal product scope

The watch image has only two user-facing functions:

1. a basic RTC-backed time/home screen; and
2. the fork2checkbook app.

There is no compatibility requirement for the reference firmware's other
apps or services. Exclude Gadgetbridge, notifications, music control, weather,
maps, GPS, Wi-Fi control, web server, FTP, MQTT, OTA, phone pairing, step BLE,
battery BLE, audio, and unrelated settings from the demo build. Retain only the
hardware/power code actually needed for display, touch, RTC, battery/charging,
sleep/wake, optional haptic feedback, SPIFFS, and the two-screen UI.

This reduction is intentional, not a temporary regression. It minimizes image
size and background work and lets fork2checkbook own NimBLE without competing with
legacy phone services. The unmodified reference build is used only once as a
hardware baseline before the minimal profile replaces it.

## Registered reference

| Item | Inspected value |
| --- | --- |
| Local tree | `/media/kestl/xwing/Old_documents/Documents/PlatformIO/Projects/My-TTGO-Watch` |
| Origin | `https://github.com/EdwinKestler/My-TTGO-Watch.git` |
| Upstream | `https://github.com/sharandac/My-TTGO-Watch.git` |
| Commit inspected | `a7eb49ead389e20d5e4d17cfcdb8b64e5d52d3d7` |
| Default target | PlatformIO `t-watch2020-v1`, board `ttgo-t-watch` |
| License | GPL-2.0 |
| Use in this project | Read-only hardware and application-framework reference |

Do not edit or flash from the reference tree without a new human request.
Submission changes belong in this public bill repository. If source is copied,
retain its notices and satisfy GPL-2.0 distribution obligations.

## Confirmed hardware and framework

| Capability | Reference implementation | fork2checkbook use |
| --- | --- | --- |
| MCU/storage | ESP32-D0WDQ6, 16 MB flash, PSRAM, SPIFFS | Opaque artifact staging and sidecars |
| Display | 240×240 ST7789, SPI, LVGL 7.11 | Amount, inventory state, next action, errors |
| Input | FT6336 capacitive touch, interrupt driven | Open app, arm/cancel one receive window |
| Power | AXP202 PMU and existing sleep/wake callbacks | Battery operation without corrupting transfers |
| Feedback | GPIO4 vibration motor | Short success/failure feedback only |
| BLE | NimBLE-Arduino 1.4.3; existing global server | Add the frozen RgbBill services under one BLE owner |
| App model | `app_autocall_function`, app tile, activate/hibernate callbacks | Register one `fork2checkbook` application |

The side button is the AXP202 power key, not a free ESP32 GPIO. The app must use
the touchscreen instead of assuming the current external TTP223/GPIO12 input.
GPIO12 is already the watch backlight enable and must not be repurposed.

## Fixed architecture

```text
Laptop dock                         Minimal T-Watch firmware
------------------------------      ---------------------------------
web/server.py + local QVAC          clock/home + fork2checkbook LVGL app
Bleak central                  <-->  frozen dock GATT peripheral
rgb-lib Wallet A/B                  frozen tap GATT central/peripheral
trusted one-shot note vault         ChunkProtocol + inventory v3
Mutinynet + confirmations            SPIFFS opaque capsule + sidecar
```

Only the right-hand physical-device adapter changes. The watch must remain
compatible with the current Python dock and with WEMOS/TTGO bills. No capsule,
claim secret, invoice, or consignment may use Wi-Fi, the watch web server, OTA,
Gadgetbridge, a phone, or a QR code as a hidden transport.

## Reuse map

Reuse from this repository without changing the wire contract:

- `lib/ChunkProtocol`: frame v1, CRC32, ordering, ACKs, and bounds;
- `lib/DockGatt`: dock service, inventory v3, durable dock staging;
- `lib/TapGatt`: sender/receiver FSM, metadata validation, RSSI gate, promotion,
  final-ACK deletion, and restart restoration;
- `include/config.h` and `docs/devs/gatt-contract.json`: canonical UUIDs and
  constants;
- existing native tests and Python Bleak acceptance tools.

Reuse from the watch reference:

- its board definition and T-Watch library initialization;
- only the LVGL primitives needed for a clock/home screen, fork2checkbook app, and
  touch callbacks;
- AXP202 display/power sequencing, wake handling, battery state, and haptic;
- the already-mounted SPIFFS instance and its filesystem conventions.

Reconcile instead of duplicating:

- **NimBLE ownership:** the reference firmware creates a global server for
  phone services. The minimal profile excludes those services and makes RGB
  Bill the sole `NimBLEDevice` owner. Never initialize a second stack.
- **Filesystem ownership:** create namespaced paths such as `/rgb-bill/…` and
  never format SPIFFS on a fork2checkbook error.
- **Power lifecycle:** block sleep during an active dock/tap session; resume
  normal watch power policy only after the transfer is durably complete or
  aborted.
- **Library generations:** the accepted bill firmware uses Arduino ESP32 BLE,
  while the watch uses NimBLE. Preserve the bytes and FSM, but provide a thin
  transport adapter rather than mixing both BLE libraries in one image.

## Human-facing watch flow

| Inventory | Watch screen | Only primary action |
| --- | --- | --- |
| Empty | `EMPTY` / `Ready to receive` | **Receive note** |
| Receiver armed | `TAP READY` / countdown | **Cancel** |
| Bearer held | `$5.00` / `NOTE` / `Tap to pass or dock to redeem` | **Pass note** |
| Sending | `SENDING` / peer and progress | No repeated action |
| Recovery blocked | `RECOVERY` / `Use your dock` | No tap transfer |
| Transfer succeeded | `NOTE RECEIVED` or `NOTE SENT` + short vibration | Return to inventory state |
| Transfer failed | Plain error + next safe action + distinct vibration | Retry only from stable inventory |

The amount is artifact denomination, never a wallet balance. **Pass note** must
not start an uncontrolled permanent scan: it exposes the stored artifact as a
sender and tells the human to arm the empty receiving device. **Receive note**
arms one bounded 15-second central scan. The selected BLE session continues
after the finger is released.

## Tomorrow's phased implementation

### W0 — Freeze and reproduce the watch baseline

1. Record the physical watch model and compare it to T-Watch 2020 V1.
2. Build unmodified reference commit `a7eb49ea` with `t-watch2020-v1`.
3. Record firmware size, partition layout, free SPIFFS, free heap/PSRAM, and
   stable USB by-id path.
4. Flash only after explicit human authorization; prove display, touch,
   battery/charging, sleep/wake, and current BLE behavior.

Gate: the unmodified baseline builds and the physical hardware matches the
documented V1. We do not require its app catalog or phone integrations to work.
If the hardware does not match, stop and identify the exact watch revision.

### W1 — Build the minimal clock + fork2checkbook shell

1. Add a watch-specific PlatformIO environment/profile in this repository.
2. Compile only the basic RTC clock/home screen, fork2checkbook app, required LVGL
   and hardware drivers, and shared protocol code. Exclude every unrelated app
   and network/phone service at the build boundary.
3. Open the `fork2checkbook` screen from the clock/home screen and provide a clear
   route back to the clock.
4. Render the inventory states above from an in-memory fake inventory.
5. Map touch to one-shot arm/cancel and use short haptic feedback.

Gate: clean build with no wallet, network, GATT, or storage behavior; UI is
usable on 240×240, the RTC time remains visible, and power-key wake/sleep still
works. No unrelated app or service is linked into the image.

### W2 — Port storage and the portable protocol core

1. Compile the existing `ChunkProtocol` against the watch profile.
2. Add a namespaced SPIFFS store and atomic artifact/sidecar promotion.
3. Restore empty, bearer-held, and recovery-blocked states after reboot.
4. Reuse the same 640 KiB logical cap only if measured free storage supports
   it; otherwise set and document a smaller device limit still well above the
   live 603-byte capsule and expected consignments.

Gate: native protocol tests remain green; watch reboot preserves a fixture and
its inventory metadata byte-for-byte; no format-on-error path exists.

### W3 — Reconcile BLE and expose the frozen dock contract

1. Initialize NimBLE once under fork2checkbook ownership and create the existing
   dock service UUID and characteristics. Do not compile the reference
   Gadgetbridge, device-info, battery, or step BLE services.
2. Port `DockGatt` through a narrow NimBLE adapter; keep inventory v3 and chunk
   bytes unchanged.
3. Verify the unchanged Python dock can scan, connect, read identity/inventory,
   stage kind `0x04`, extract it, and compare SHA-256.
4. Confirm Wi-Fi, web, OTA, and companion transports are absent from the build,
   not merely switched off for the acceptance run.

Gate: Python dock loopback and 603-byte bearer fixture round-trip exactly,
including restart restoration and explicit discard recovery.

### W4 — Port the tap FSM

1. Port `TapGatt` through the same NimBLE owner for both peripheral sender and
   bounded central receiver roles.
2. Connect **Receive note** to one rising-edge event, 15-second arm window,
   second-action cancel, and RSSI threshold `-60 dBm`.
3. Keep sender data until final ACK; promote receiver data atomically.
4. Suspend sleep during the session and restore it afterward.

Gate: WEMOS → watch, watch → TTGO, and watch → WEMOS fixture transfers are
byte-exact; sender becomes empty only after final ACK; interrupted transfers
retain a safe recoverable copy.

### W5 — Live capsule and demo acceptance

1. Use a non-secret synthetic kind `0x04` fixture first.
2. Load an authorized active 603-byte live capsule from the laptop dock.
3. Disconnect/gate dock networking and relay through the watch.
4. Reboot the watch and verify restored `$5.00 / NOTE` state.
5. Extract at the destination dock and compare the exact expected SHA-256
   before any redemption plan is created.
6. Run the existing immutable confirmation/no-resend redemption flow unchanged.

Gate: one complete evidence bundle records serial timestamps, addresses/RSSI,
artifact sizes and hashes, reboot persistence, dock actions, txid, and final
Wallet B settlement. Never print the capsule or claim secret.

## Stop conditions and fallback

Stop the watch port and use the accepted WEMOS/TTGO pair if any of these remains
unresolved near the demo: wrong hardware revision, unstable baseline, an
unintended second BLE owner/service set, storage corruption/formatting risk,
sleep during transfer, payload incompatibility, unexplained sender deletion,
or inability to reproduce the exact capsule hash after reboot.

The watch is an experience upgrade, not permission to risk the settled RGB
flow. A partial watch UI may be shown as future work, but it must not be
described as a working bearer device until W5 passes physically.
