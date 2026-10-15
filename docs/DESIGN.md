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
| Bill A / Bill B | WEMOS LOLIN32 and LilyGO TTGO LoRa32 V1.3 / ESP32 | SSD1306 OLED, tap input, radio. **No** rgb-lib, **no** QVAC |
| Disposable note vault | Local trusted process for the selected demo | One fresh rgb-lib wallet N per note, claim hash, immutable plans, recovery journal |
| GATT-dock | laptop ↔ its bill | On-demand connection. Inventory, commands, status, denomination, opaque chunks |
| GATT-tap | bill ↔ bill | A press edge arms a bounded receiver window; high RSSI gates the peer. Carries invoice, consignment, or an opaque bearer capsule |

The ESP32 bills are not rgb-lib wallets. Wallet A and Wallet B each have their
own mnemonic/datadir on their role-scoped docks. The selected offline mode adds
one disposable note wallet N per note inside the trusted local vault. The bill
carries only an opaque bearer capsule; it never receives N's mnemonic or
datadir. Never open any datadir in two processes.

Each role-specific web dock registers one physical bill. Discovery requires
the frozen dock service UUID plus an RgbBill-family advertised name; a
read-only core-state connection verifies the target before its address is
saved. Every later connection reads the artifact inventory (empty, invoice,
or consignment; to-peer or to-dock) before selecting a transfer direction.
Transfers reconnect to that saved address on demand. Registration is
locked while a transfer or recovery boundary is active. This is prototype
device selection, not cryptographic device ownership authentication.

## Primary RGB mapping: offline bearer note

1. Wallet A funds fresh isolated note wallet N with exactly 5 USDT through a
   transport-free witness invoice and one exact confirmation.
2. After N settles, the vault creates a 603-byte bearer capsule containing a
   random claim capability and redacted funding evidence—never wallet keys.
3. Dock A loads the capsule onto a bill. Bills relay the same kind `0x04`
   artifact over BLE while docks and Internet are unavailable.
4. The final dock extracts and hashes the exact capsule. Only then does Wallet
   B create its fresh transport-free redemption invoice.
5. One separate exact confirmation authorizes N's one RGB send. Wallet B
   imports the exact retained consignment and becomes `REDEEMED` only after an
   exact txid/assignment/balance settlement check.

There are exactly two RGB transitions: Wallet A → N and N → Wallet B. The
offline bill-to-bill hops move the bearer capability but do not alter RGB
state. The vault retains N's keys, so this is trusted custody and copied
capsules are first-redemption-wins.

## Direct-mode fallback

The accepted browser flow remains available: Dock B creates a $5 invoice,
Bill B taps it to Bill A, Dock A confirms one send, Bill A taps the exact
consignment back, and Dock B imports it. Both modes require empty RGB
`transport_endpoints`; docks never exchange the payload over Wi‑Fi. The board
displays an amount only while a complete artifact is durable.

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
- Dock artifact inventory v3 is a 16-byte read-only characteristic. It makes
  connect-time direction selection deterministic and prevents blind
  CHUNK_OUT waits. Direction `recovery-blocked` prevents a retained DockGatt
  artifact or tap-storage orphan from being misreported as empty and blocks a
  second invoice until explicit operator recovery.
- Kind `0x04` is an opaque bearer-note capsule. Direction `bearer-held` means
  the complete capsule is durable and ready for another offline bill-to-bill
  hop. The receiving bill promotes it to its next tap-out slot; the sender
  deletes only after the successful final ACK. Firmware emits v3 while keeping
  inventory/tap metadata v1/v2 decode compatibility.
- A destination dock may subscribe to dock `CHUNK_OUT` while inventory is
  `bearer-held` to extract that same capsule for redemption. The bill keeps the
  file through the final dock ACK, then clears the bearer file and sidecar.
  Merely connecting or reading inventory never consumes the note.
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
- Second test bill: LilyGO TTGO LoRa32 V1.3-868. The active
  `ttgo-lora32-oled-test` profile uses a replacement external 128x64
  SSD1306-compatible display on SDA GPIO21 / SCL GPIO22 with no reset lead,
  plus the active-high TTP223 touch input on GPIO12. GPIO12 is also an ESP32
  flash-voltage strapping pin, so the sensor must not be touched or held high
  during reset. Its stable CP2102 USB path is kept separate from the WEMOS.
  The former ILI9341 build remains available only as
  `ttgo-lora32-tft-legacy`; the failed onboard OLED and older diagnostic
  profiles remain documented. See
  [TTGO-LORA32-V1.3-TEST.md](TTGO-LORA32-V1.3-TEST.md).

## Delivery status and Sunday priorities

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
   acceptance completed on 2026-10-15.**
6. Human-first inventory/tap metadata v2. **Implemented, flashed, and
   physically accepted on both boards with a settled $5 Mutinynet transfer on
   2026-10-15.**
7. Offline bearer-note mode. **Implemented and live accepted:** isolated note
   funding, 603-byte capsule, physical WEMOS → TTGO relay/restart, exact
   extraction, separately gated capacity, one-shot redemption, Wallet B
   settlement, and durable `REDEEMED` closure.
8. Integrate the accepted operator bearer flow into the web dock without
   weakening confirmation/recovery boundaries. **Not yet implemented.**
9. Connect local QVAC typed intent parsing to the accepted deterministic
   actions and capture a reproducible evaluation. **Not yet implemented and
   required for the final submission.**
10. Rehearse one non-technical three-minute live flow with understandable
   device/dock states and recovery messages. Add WDK only after the RGB + QVAC
   primary flow is stable; WDK is bonus, not a blocker.

## Web dock language

Python is the dock application: HTTP + static UI in `web/`, BLE in `dock/`,
rgb-lib-python in `web/rgb/`. That matches Bleak and the 0.3.0b7 wheels.

Rust rgb-lib stays optional under `web/rust/` if wheels fail. Do not run two
wallet processes on one datadir. QVAC is `tetherto-qvac-sdk` in `.venv`; the
desk UI is already a browser page.

## BLE reference (do not copy protocol)

`/media/kestl/andor/github/waveshares3`: ESP32-S3 reference only, PlatformIO, Bleak 3.0.2, frozen GATT JSON, write-with-response, notify, bonding, session FSM. Locker UUIDs, `0xA4`, barcodes, relays, and board pin maps stay there.

## Judging

Real RGB is proven by the two accepted Mutinynet transitions. QVAC stays on the
dock and remains an open integration gate. WDK is not integrated. The selected
bearer-note demo is explicitly trusted-vault custody; do not describe it as a
production self-custodial note.
