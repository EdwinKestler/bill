# GATT contract

Rendered views of this contract are available as the
[GATT service map](diagrams/05-gatt-contract.png) and
[binary chunk-frame layout](diagrams/06-chunk-frame.png). Editable Mermaid
sources are indexed in [docs/diagrams/README.md](diagrams/README.md).

Dock core status: **frozen v1** after the 2026-10-09 hardware session that
advertised `RgbBill`, read `IDENTITY`, and reconnected without a reset. Tap
GATT and dock chunk transport status: **implemented and physically accepted
v1** in both directions as of 2026-10-11. `include/config.h` and
`docs/devs/gatt-contract.json` stay in lockstep with this document.

Device name: `RgbBill`.

## Dock service (`7c3e9a10-4b1e-4c8f-9d2a-00b111d0c001`)

Laptop is central. Bill is peripheral. One active transfer per connection.

| Name | UUID suffix | Properties | Payload |
| --- | --- | --- | --- |
| IDENTITY | `…c002` | Read | ASCII bill id (`bill-unprovisioned` until provisioned) |
| STATUS | `…c003` | Read, Notify | `idle` / `tap` / `pending` / `settled` / `error` |
| DENOMINATION | `…c004` | Read, Notify | ASCII integer cents, e.g. `500` for $5.00 |
| CMD | `…c005` | Write-with-response | UTF-8 command v1 |
| CHUNK_IN | `…c006` | Write-with-response | Binary frame v1, dock → bill |
| CHUNK_OUT | `…c007` | Notify | Binary frame v1, bill → dock |

Dock core v1 exposes one non-production command:
`diag:display:500:pending`. It sets `DENOMINATION` to ASCII `500`, sets
`STATUS` to ASCII `pending`, notifies subscribers, and asks the display to show
`$5.00 / PENDING`. It does not provision a bill, touch a wallet, construct or
broadcast a transaction, or survive a restart. Other command strings are
rejected. Production commands require a later contract revision.

Chunk transport adds two non-wallet commands. `diag:chunk:echo` arms a
one-shot, byte-exact echo of the next complete `CHUNK_IN` transfer through
`CHUNK_OUT`. `chunk:discard` deletes the staged transport artifact. Neither
command parses an RGB invoice, imports a consignment, calls a wallet, or
broadcasts a transaction.

`CHUNK_IN` accepts data frames from the dock and ACK frames for data sent by
the bill. `CHUNK_OUT` notifies an ACK for every accepted/rejected inbound data
frame and carries bill-originated data frames. Multi-byte integers are
little-endian:

| Field | Size | Meaning |
| --- | ---: | --- |
| version | 1 | `0x01` |
| kind | 1 | `0x01` invoice, `0x02` consignment, `0x03` ACK |
| session_id | 4 | Random per transfer session |
| sequence | 2 | Zero-based frame index |
| total | 2 | Total number of frames |
| payload_length | 2 | Payload bytes in this frame, maximum 200 |
| payload | 0–200 | Raw invoice, consignment, or ACK bytes |
| crc32 | 4 | CRC-32 over all preceding frame bytes |

Data payloads are 1–200 bytes. The dock defaults to 180 bytes, making the
largest normal frame 196 bytes under the firmware's requested ATT MTU of 247.
The receiver accepts only invoice (`0x01`) and consignment (`0x02`) data,
requires sequence zero first, enforces one stable kind/session/total tuple,
and appends only the exact next sequence. An exact retry of the immediately
previous frame is idempotently ACKed without being appended twice.

ACK (`0x03`) repeats the data frame's `session_id`, `sequence`, and `total`.
Its one-byte payload is:

| Value | Meaning |
| ---: | --- |
| `0x00` | accepted |
| `0x01` | malformed envelope or counters |
| `0x02` | unsupported version or kind |
| `0x03` | CRC mismatch |
| `0x04` | kind or session mismatch |
| `0x05` | sequence mismatch |
| `0x06` | total mismatch |
| `0x07` | transfer exceeds the receiver limit |
| `0x08` | staging-storage failure |
| `0x09` | receiver already holds a completed transfer |

The sender uses stop-and-wait: write/notify one frame, wait for its matching
successful ACK, then advance. Firmware retries a `CHUNK_OUT` notification up
to three times at one-second intervals. The dock relies on GATT
write-with-response for delivery to `CHUNK_IN` and fails closed on a missing or
negative ACK.

The current ESP32 staging limit is 655360 bytes (640 KiB), leaving filesystem
metadata and garbage-collection headroom in the 896 KiB SPIFFS partition. One
completed opaque artifact may be staged at a time. Complete artifacts survive
a dock disconnect for the future tap layer;
incomplete sessions are deleted on disconnect or after the five-minute
session timeout. `chunk:discard` explicitly frees dock and tap staging slots.

This layer transports exact opaque invoice and consignment bytes only. It does
not prove that the payload is valid RGB data. The existing wallet adapter is
still the authority that creates invoices and imports received OOB
consignments.

## Tap service (`7c3e9a10-4b1e-4c8f-9d2a-00b1117a0002`)

Bill–bill only. The bill holding a staged artifact is always the BLE
peripheral/sender. A bill with no staged artifact becomes central/receiver
when a debounced rising press edge arms a one-shot 15-second discovery window.
Both the WEMOS prototype and TTGO TFT profile use an active-high digital TTP223
touch module on GPIO12. The input may be released immediately: release does
not cancel scanning or an accepted BLE session. This removes central/central
races and the need to hold either input.
The receiver considers only advertisements whose name begins with `RgbBill`,
requires RSSI >= -60 dBm, and consumes the one-shot authorization when it
attempts the first qualifying connection. Duplicate advertisement reports are
kept during the arm window so a peer first observed below the threshold may
qualify on a later, stronger RSSI sample. It then validates the tap service and
metadata before requesting bytes. Success, connection/session failure, or the
15-second pre-connection timeout leaves the receiver disarmed. A second press
explicitly cancels an armed window or active receive session.

| Name | UUID suffix | Properties | Payload |
| --- | --- | --- | --- |
| META | `…0003` | Read | 12-byte tap metadata v1 |
| CONTROL | `…0004` | Write-with-response | `0x01` START, `0x02` CANCEL |
| CHUNK_IN | `…0005` | Write-with-response | chunk-v1 ACK, receiver → sender |
| CHUNK_OUT | `…0006` | Notify | chunk-v1 data, sender → receiver |

Tap metadata is little-endian:

| Field | Size | Meaning |
| --- | ---: | --- |
| version | 1 | `0x01` |
| state | 1 | `0x00` empty, `0x01` artifact ready |
| kind | 1 | chunk-v1 invoice `0x01` or consignment `0x02`; zero if empty |
| reserved | 1 | Must be zero |
| session_id | 4 | Same session identifier carried by every chunk frame |
| size | 4 | Exact artifact byte count, maximum 655360 |

`CHUNK_OUT` and `CHUNK_IN` reuse the dock service's binary chunk-v1 envelope,
CRC32, strict ordering, exact duplicate ACK behavior, and stop-and-wait retry
rules. The sender keeps `/tap-out.ready` after cancellation, disconnect, or
timeout, and removes it only after the matching successful final ACK. The
receiver writes `/tap-in.part`, atomically promotes it to `/tap-in.ready`, and
then makes it available through dock `CHUNK_OUT`. No RGB parsing occurs on the
ESP32.

After the receiver disconnects its tap client, dock advertising is restarted
from the main loop after a short BLE-stack teardown delay rather than directly
inside the disconnect callback. A bill-to-bill connection is not treated as a
dock retrieval session: the received artifact is queued to dock `CHUNK_OUT`
only after the laptop has enabled that characteristic's notification CCCD.

The v1 discovery advertisement remains the frozen dock advertisement so it
continues to fit one legacy 31-byte PDU. Tap discovery uses the `RgbBill*`
name and validates the tap service after connection; no invoice, consignment,
amount, or session metadata is placed in advertising data.

Security: dock link may request bonding (`ENC_NO_MITM`) like the Waveshare
gateway. Tap link is short-lived; Mutinynet demo may stay unauthenticated.
Mainnet would need a pairing story.

Both current bill profiles sample the TTP223 output on GPIO12 as an active-high
digital input. GPIO12 is also the ESP32 MTDI flash-voltage strap, so each
TTP223 must remain released/LOW during power-up, reset, and flashing. Do not
configure either module for a latched mode that could retain a HIGH output
across reset.
