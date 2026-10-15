Laptop GATT central. From `ideas/bill/`:

```bash
.venv/bin/python -m dock.bill_dock scan --timeout 8
.venv/bin/python -m dock.bill_dock identity --timeout 8
.venv/bin/python -m dock.bill_dock state --timeout 8
.venv/bin/python -m dock.bill_dock diagnostic --timeout 8
.venv/bin/python -m dock.bill_dock chunk-loopback --address AA:BB:CC:DD:EE:FF --kind invoice --input PATH
```

`identity` connects without pairing, reads the ASCII `IDENTITY` characteristic,
and performs no GATT writes. Pass `--address AA:BB:CC:DD:EE:FF` to select one
bill explicitly. Chunks and rgb-lib send land here after the firmware contract
is frozen; the wallet-to-chunk handoff remains explicit for acceptance.

`state` reads `IDENTITY`, `STATUS`, `DENOMINATION`, and the artifact inventory.
`diagnostic` is the no-wallet hardware check: it writes only
`diag:display:empty`, verifies the state characteristics, and asks the display
to show `DISPLAY TEST` without inventing an amount. It cannot provision or
spend.

`chunk-send` stages the exact bytes of one RGB invoice or OOB consignment on
the bill. `chunk-receive` atomically writes a bill-originated artifact to the
dock. Both directions use ordered binary frames, CRC32, and per-frame ACKs.
The ESP32 currently accepts one artifact up to 640 KiB.

Before tap GATT is connected, validate both BLE directions with the safe
byte-exact echo:

```bash
.venv/bin/python -m dock.bill_dock chunk-loopback \
  --address AA:BB:CC:DD:EE:FF \
  --kind consignment \
  --input /path/to/consignment.rgbc
```

Use `chunk-discard --address ...` to remove staged dock and tap artifacts. These
commands move opaque bytes only; they never invoke rgb-lib or broadcast.

The repository includes a harmless multi-frame fixture for first hardware
acceptance:

```bash
.venv/bin/python -m dock.bill_dock chunk-loopback \
  --address AA:BB:CC:DD:EE:FF \
  --kind invoice \
  --input test/fixtures/chunk-smoke.payload
```
