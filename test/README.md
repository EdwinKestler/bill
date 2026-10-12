Native (host) tests: `../.venv-platformio/bin/pio test -e native`.

Arduino-independent FSMs (session, chunk reassembly, RSSI gate) belong here.
Do not put BLE-stack tests in `native` until they compile without the IDF.

`fixtures/chunk-smoke.payload` is an inert multi-frame payload for the physical
`chunk-loopback` command. It is deliberately not an RGB invoice or
consignment and cannot authorize or trigger a wallet operation.
