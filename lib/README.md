Firmware libraries. `BillDisplay/` owns the shared SSD1306 display driver.
`DockGatt/` owns the dock peripheral, including disconnect/session boundaries
and automatic advertising restart. `ChunkProtocol/` owns the portable binary
frame codec and ordered receive-session rules; `DockGatt/` stages completed
artifacts in SPIFFS and drives stop-and-wait ACKs. `TapProtocol/` owns the
portable tap metadata and button/RSSI gate. `TapGatt/` owns deterministic
bill-to-bill sender/receiver roles and reuses chunk-v1 for opaque artifacts.
Do not copy locker protocol code from `/media/kestl/andor/github/waveshares3`.
