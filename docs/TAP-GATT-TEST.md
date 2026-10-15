# Tap GATT two-board acceptance

This test moves the inert 520-byte fixture between the WEMOS LOLIN32 and the
TTGO LoRa32 over bill-to-bill BLE. It does not invoke rgb-lib, spend funds, or
broadcast a transaction. The TTGO uses the external GPIO21/22 OLED profile.

Both boards use a momentary press of an active-high TTP223 digital touch module
on GPIO12. Either press arms a 15-second one-shot receive window, so release
immediately. Because GPIO12 is a flash-voltage strapping pin, keep both TTP223
modules released/LOW while resetting, powering up, or flashing their boards.
PlatformIO's `time` monitor filter is enabled for both profiles, and every
`bill_dock` CLI line includes a timezone-aware timestamp. Preserve those
prefixes when capturing evidence so events from all three terminals can be
ordered.

## Autonomous peer-RSSI diagnostic

If a receiver expires without connecting, use the isolated RSSI images before
repeating the transfer. They continuously advertise and scan at the same time;
no touch, dock command, staged artifact, or wallet is involved. This replaces
the main image temporarily and reboots each board, so any in-memory staged
metadata is lost and the fixture must be staged again after restoring the main
images.

Build and upload the two diagnostics:

```bash
.venv-platformio/bin/pio run -e wemos-tap-rssi-test -t upload
.venv-platformio/bin/pio run -e ttgo-tap-rssi-test -t upload
```

Then open one monitor per board:

```bash
.venv-platformio/bin/pio device monitor -e wemos-tap-rssi-test
.venv-platformio/bin/pio device monitor -e ttgo-tap-rssi-test
```

Each side reports one-second RSSI statistics for the other side, including
`QUALIFIES` at or above -60 dBm and `TOO_FAR` below it. `no peer seen in the
last 5s` distinguishes discovery failure from a weak peer. Restore the main
images after collecting both directions:

```bash
.venv-platformio/bin/pio run -e esp32-bill -t upload
.venv-platformio/bin/pio run -e ttgo-lora32-oled-test -t upload
```

The main firmware keeps duplicate advertisement reports throughout the
15-second arm window. A peer initially reported below threshold can therefore
qualify after the boards move closer; the first qualifying sample starts the
connection.

## 1. Build and flash

From `ideas/bill/`:

```bash
.venv-platformio/bin/pio run -e esp32-bill
.venv-platformio/bin/pio run -e ttgo-lora32-oled-test
.venv-platformio/bin/pio run -e esp32-bill -t upload
.venv-platformio/bin/pio run -e ttgo-lora32-oled-test -t upload
```

Open one serial monitor per board if desired. Expected WEMOS and TTGO boot
lines both include `press GPIO12 TTP223 once` with `RSSI >= -60 dBm`.

## 2. Identify addresses

```bash
.venv/bin/python -m dock.bill_dock scan --timeout 8
```

The known test addresses are WEMOS `30:AE:A4:07:2D:2E` and TTGO
`30:AE:A4:4C:B1:6A`; use the scan result if an address changes.

Confirm the new TTGO image reports `touch GPIO=12 active=HIGH`, then clear any
SPIFFS artifacts retained from earlier attempts:

```bash
.venv/bin/python -m dock.bill_dock state --address 30:AE:A4:07:2D:2E
.venv/bin/python -m dock.bill_dock state --address 30:AE:A4:4C:B1:6A
.venv/bin/python -m dock.bill_dock chunk-discard --address 30:AE:A4:07:2D:2E
.venv/bin/python -m dock.bill_dock chunk-discard --address 30:AE:A4:4C:B1:6A
```

## 3. WEMOS sender to TTGO receiver

Stage the fixture through the WEMOS dock service:

```bash
.venv/bin/python -m dock.bill_dock chunk-send \
  --address 30:AE:A4:07:2D:2E \
  --kind invoice \
  --input test/fixtures/chunk-smoke.payload
```

Place the boards on the same bench. Tap the GPIO12 TTP223 on the TTGO once and
release it. Its serial terminal must report
`tap: receiver armed for 15s; release input`, followed by the qualifying peer
and receive milestones without another touch. Expected sender milestones are
`tap: staged outbound`, `tap: sender started`, and `tap: sender complete`.

Wait for the TTGO to report
`bill: dock advertising restarted after BLE teardown`, then pull the received
bytes from the TTGO and compare them. This delayed restart is part of the
central-to-peripheral role transition; do not reset the receiver:

```bash
.venv/bin/python -m dock.bill_dock chunk-receive \
  --address 30:AE:A4:4C:B1:6A \
  --kind invoice \
  --output /tmp/wemos-to-ttgo.payload
cmp test/fixtures/chunk-smoke.payload /tmp/wemos-to-ttgo.payload
sha256sum test/fixtures/chunk-smoke.payload /tmp/wemos-to-ttgo.payload
```

`cmp` must produce no output and both hashes must match.

Clear both staging slots before reversing direction:

```bash
.venv/bin/python -m dock.bill_dock chunk-discard --address 30:AE:A4:07:2D:2E
.venv/bin/python -m dock.bill_dock chunk-discard --address 30:AE:A4:4C:B1:6A
```

## 4. Reverse direction

Repeat with TTGO as sender and WEMOS as receiver, changing `--kind` to
`consignment`. Touch and release the GPIO12 TTP223 once on the WEMOS to arm its
receiver:

```bash
.venv/bin/python -m dock.bill_dock chunk-send \
  --address 30:AE:A4:4C:B1:6A \
  --kind consignment \
  --input test/fixtures/chunk-smoke.payload

.venv/bin/python -m dock.bill_dock chunk-receive \
  --address 30:AE:A4:07:2D:2E \
  --kind consignment \
  --output /tmp/ttgo-to-wemos.payload

cmp test/fixtures/chunk-smoke.payload /tmp/ttgo-to-wemos.payload
sha256sum test/fixtures/chunk-smoke.payload /tmp/ttgo-to-wemos.payload
```

Both directions must report 520 bytes and SHA-256
`925a4bf7cdf591eea7e5b78975964aee5801417761474fe3588b385ba00bc014`.
Finish by running `chunk-discard` against both addresses once more.

## Accepted hardware evidence — 2026-10-11

Both physical directions passed with the inert fixture and no receiver reset:

- WEMOS → TTGO, invoice session `f7e494c0`: 520 bytes retrieved through the
  TTGO dock service; `cmp` was clean and SHA-256 matched the source fixture.
- TTGO → WEMOS, consignment session `d959a1ae`: the WEMOS qualified the TTGO
  at −49 dBm, received 520 bytes, resumed advertising after BLE teardown, and
  returned a byte-identical payload through its dock service.
- Both senders reported `tap: sender complete`; both receivers reported
  `tap: receive complete`; both receivers became discoverable again without a
  reset.

This test accepts the opaque GATT-dock → GATT-tap → GATT-dock transport. By
itself it does not prove live rgb-lib invoice parsing, OOB consignment import,
or Mutinynet settlement. Those separate live acceptance results are recorded
in [LIVE-EVIDENCE.md](LIVE-EVIDENCE.md); they must not be inferred from this
fixture test alone.

## Failure behavior

- RSSI below -60 dBm: no connection is attempted.
  Serial reports the observed peer address and RSSI as `below threshold`.
- Releasing the tap input after the press: no effect on the armed window or
  active transfer.
- No qualifying peer within 15 seconds: receiver disarms automatically.
- A second press while armed or receiving: receiver cancels and disarms.
- Disconnect or missing ACK: sender aborts the session but keeps the staged
  artifact for another controlled attempt.
- Invalid service or metadata: receiver disconnects without creating a ready
  artifact.
