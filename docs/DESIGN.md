# RGB cash bill — design

Rendered architecture, sequence, state, protocol, hardware, and trust diagrams
are indexed in [docs/diagrams/README.md](diagrams/README.md). Their editable
Mermaid sources live beside the PNGs under `docs/diagrams/src/`.

Physical USDT notes. The dock exposes two explicit human actions: **Send
USDT** and **Receive USDT**. Tap two bills once when instructed. No QR, no
phone app, and no guessing whether the bill should be read or written.

## Roles

| Piece | Where | Job |
| --- | --- | --- |
| Dock A / Dock B | Two laptops | Python web desk (`web/`, :8788), Bleak GATT (`dock/`), rgb-lib-python, QVAC voice, Mutinynet broadcast |
| Bill A / Bill B | WEMOS LOLIN32 and LilyGO TTGO LoRa32 V1.3 / ESP32 | SSD1306 OLED or external ILI9341 TFT, tap input, radio. **No** rgb-lib, **no** QVAC |
| GATT-dock | laptop ↔ its bill | On-demand connection. Inventory, commands, status, denomination, opaque chunks |
| GATT-tap | bill ↔ bill | A press edge arms a bounded receiver window; high RSSI gates the peer. Carries invoice + consignment |

Each bill is its own rgb-lib wallet (own mnemonic, own datadir). The dock
mounts that wallet for the transfer, then the only copy of the stash is the
bill’s pairing to that dock. Never open the same datadir in two processes.

Each role-specific web dock registers one physical bill. Discovery requires
the frozen dock service UUID plus an RgbBill-family advertised name; a
read-only core-state connection verifies the target before its address is
saved. Every later connection reads the artifact inventory (empty, invoice,
or consignment; to-peer or to-dock) before selecting a transfer direction.
Transfers reconnect to that saved address on demand. Registration is
locked while a transfer or recovery boundary is active. This is prototype
device selection, not cryptographic device ownership authentication.

## RGB mapping

1. Dock B **Receive USDT** creates a $5 witness invoice and loads Bill B.
2. Tap moves the invoice B→A; Dock A **Send USDT** reads it and presents the
   exact confirmation gate.
3. After the one authorized Mutinynet broadcast, tap moves the exact
   consignment A→B; Dock B **Receive USDT** reads and imports it.
4. Empty `transport_endpoints`. Use rgb-lib out-of-band consignment receive. Docks do not exchange the packet over Wi‑Fi.
5. The board display shows an amount only while a complete invoice or
   consignment is physically stored. Empty inventory displays no amount.

The dock adapter enforces this as two isolated processes, not one process with
two wallet objects. Bill B creates the witness invoice. Bill A reads its full
spendable asset balance, presents an immutable plan, consumes a one-use human
confirmation, and calls rgb-lib with `donation=true` and empty transport
endpoints. The generated consignment bytes leave the dock only through the
out-of-band chunk path. Bill B imports those bytes with
`provide_out_of_band_consignment`. An ambiguous send is never automatically
retried because it may already have broadcast.

On-chain rgb-lib, not RLN. Lightning is a channel, not a note.

## Radio

- GATT-dock: Arduino `BLEDevice` **peripheral** on the bill, Bleak **central** on the laptop. Same shape as `/media/kestl/andor/github/waveshares3` (patterns only).
- GATT-dock chunk v1 is implemented: CRC32, ordered stop-and-wait frames,
  per-frame ACKs, and one opaque SPIFFS-staged artifact up to 640 KiB. Its
  diagnostic echo validates both directions without invoking a wallet.
- Dock artifact inventory v1 is a 16-byte read-only characteristic. It makes
  connect-time direction selection deterministic and prevents blind
  CHUNK_OUT waits.
- GATT-tap: the bill holding the staged artifact stays **peripheral/sender**;
  one debounced tap on the empty bill arms a 15-second **central/receiver**
  window. The operator may release immediately. The receiver connects only if
  RSSI ≥ −60 dBm and validates tap metadata before START; the accepted BLE
  session then continues independently of the input level. A second press
  cancels. It reuses 180-byte chunk-v1 payloads and CRC32. Advertising PDUs
  never carry invoice or consignment bytes.
- Session timeout on the dock link is minutes (pending confirmation ~30 s), not 60 s.

## Bill hardware

- Board: WEMOS LOLIN32 V1.0.0 (`board = lolin32`), ESP32-D0WDQ6, 4 MB flash.
- Flash layout: one 3 MiB factory application, no OTA slot, 896 KiB SPIFFS,
  and 64 KiB coredump. USB flashing is the update path for the prototype.
- Display: 128x64 SSD1306 over I2C, SDA GPIO21, SCL GPIO22, address probed at `0x3C` then `0x3D`.
- Tap input: active-high TTP223 digital output on GPIO12. GPIO12 is an ESP32
  flash-voltage strapping pin, so keep the sensor released/LOW during power-up,
  reset, and flashing.
- The production `esp32-bill` and diagnostic `oled-test` environments use the
  stable CP2104 USB by-id path. Do not upload an ESP32-S3 image to this board.
- Second test bill: LilyGO TTGO LoRa32 V1.3-868. The isolated
  `ttgo-lora32-tft-test` profile uses an external 240x320 ILI9341 in landscape
  mode (SCK 18, MOSI 23, D/C 2, reset 4, CS 15) and an active-high digital
  TTP223 touch input on GPIO12. GPIO12 is also an ESP32 flash-voltage strapping
  pin, so the sensor must not be touched or held high during reset. Its stable CP2102
  USB path is kept separate from the WEMOS. LoRa remains disabled because the
  TFT reuses radio-board pins. The failed onboard OLED and its legacy diagnostic
  profiles remain documented. See
  [TTGO-LORA32-V1.3-TEST.md](TTGO-LORA32-V1.3-TEST.md).

## Weekend order

1. Two rgb-lib wallets, witness + OOB consignment over USB serial, docks drive OLEDs/LEDs.
2. Replace the cable with dock GATT chunks. **Implemented and physically
   accepted on both boards.**
3. Tap GATT + RSSI/button v1. **Implemented and physically accepted in both
   directions with byte-exact 520-byte invoice/consignment fixtures.**
4. Replace fixtures with real isolated-wallet artifacts. **Bridge implemented
   and live accepted with a confirmed 20 USDT Mutinynet transfer on
   2026-10-11.**
5. Integrate the accepted flow into `python -m web.server`. **Implemented with
   exact typed confirmation and no-resend recovery; browser-driven physical
   acceptance remains.**
6. Connect QVAC “print a five” intent parsing to the accepted web action.
7. Human-first inventory/tap metadata v2. **Implemented and build-verified;
   physical acceptance is pending a two-board flash.**

## Web dock language

Python is the dock application: HTTP + static UI in `web/`, BLE in `dock/`,
rgb-lib-python in `web/rgb/`. That matches Bleak and the 0.3.0b7 wheels.

Rust rgb-lib stays optional under `web/rust/` if wheels fail. Do not run two
wallet processes on one datadir. QVAC is `tetherto-qvac-sdk` in `.venv`; the
desk UI is already a browser page.

## BLE reference (do not copy protocol)

`/media/kestl/andor/github/waveshares3`: ESP32-S3 reference only, PlatformIO, Bleak 3.0.2, frozen GATT JSON, write-with-response, notify, bonding, session FSM. Locker UUIDs, `0xA4`, barcodes, relays, and board pin maps stay there.

## Judging

Track 2 self-custodial dollars, cash UX. QVAC stays on the dock (criterion 2). Real Mutinynet tx on tap (criterion 1).
