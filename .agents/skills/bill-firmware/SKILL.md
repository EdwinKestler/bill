---
name: bill-firmware
description: Build and change RGB cash-bill WEMOS LOLIN32 firmware with PlatformIO in VS Code. Use for platformio.ini, BillDisplay, DockGatt, TapGatt, BLE advertise, RSSI/button gate, OLED/LED, flashing. Triggers: firmware, ESP32, PlatformIO, GATT, /bill-firmware.
---

# Bill firmware

Project root: `ideas/bill/` (this PlatformIO project).

1. Read `docs/DESIGN.md` and `docs/PROTOCOL.md`.
2. Palimnex from hackathon root (`source-cache` skill). Search rgb-lib OOB
   consignment and existing bill GATT names before inventing new ones.
3. Build: `./install_platformio.sh` once, then `.venv-platformio/bin/pio run`
   (default env `esp32-bill`, board `lolin32`).
4. Keep `src/main.cpp` as composition. OLED lives in `lib/BillDisplay`; own
   BLE in `lib/DockGatt` then `lib/TapGatt`.
5. Match `include/config.h` UUIDs to `docs/devs/gatt-contract.json`.
6. BLE patterns: `/media/kestl/andor/github/waveshares3` (session FSM,
   write-with-response, notify, bonding). New UUIDs. No locker protocol.
7. Tap GATT: button **and** high RSSI. Chunk binary consignments; do not advertise them.
8. Mutinynet only. Do not flash unless a human asks.

Native FSM tests: `.venv-platformio/bin/pio test -e native`.

Serial: the plugged WEMOS LOLIN32 (OLED prototype) is CP2104
`/dev/serial/by-id/usb-Silicon_Labs_CP2104_USB_to_UART_Bridge_Controller_014BCF94-if00-port0`
(currently `/dev/ttyUSB1`). Chip `ESP32-D0WDQ6`, MAC `30:ae:a4:07:2d:2c`.
Use default env `esp32-bill` for product firmware and `oled-test` for the
standalone display diagnostic. Both target the LOLIN32; never use an ESP32-S3 image.
Do not flash unless a human asks. Probe: `pio device list` then esptool `chip_id`.
