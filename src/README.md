PlatformIO firmware entries. `main.cpp` composes `BillDisplay` and `DockGatt`.
`oled_test.cpp` is the standalone display diagnostic. BLE ownership and
callbacks stay in `lib/DockGatt`. `ttgo_lora32_test.cpp` is the isolated
OLED + dock-core BLE diagnostic for the second LilyGO TTGO LoRa32 V1.3 bill.
`ttgo_oled_reference.cpp` is the minimal manufacturer-library comparison.
Both product entry points call `DockGatt::poll()` to advance outbound chunk
notifications and enforce ACK/session timeouts.
