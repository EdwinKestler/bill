# LilyGO TTGO LoRa32 V1.3 display + BLE test

## Isolated GPIO12 TTP223 digital test

Before changing the integrated tap input, use the `ttgo-touch-test` image to
read the TTP223 module's active-high digital output on GPIO12. This image does
not start BLE, LoRa, either display, SPI, or wallet code.

GPIO12 is not part of the board's SX1276 wiring, unlike GPIO27. However, GPIO12
is also the ESP32 MTDI boot-strapping pin: driving it high during reset selects
a 1.8 V flash supply instead of the normal 3.3 V setting and can prevent this
board from booting. Do not touch the TTP223 while powering up or resetting and
do not enable a latched/toggle mode that can leave its output high across a
reset.

Build, then upload only when ready to replace the current TTGO firmware:

```bash
.venv-platformio/bin/pio run -e ttgo-touch-test
.venv-platformio/bin/pio run -e ttgo-touch-test -t upload
.venv-platformio/bin/pio device monitor -e ttgo-touch-test
```

Expected output resembles:

```text
TOUCH_TEST: READY; touch and release the TTP223 pad
TOUCH_TEST: gpio12=LOW state=released
TOUCH_TEST: TOUCHED gpio12=HIGH
TOUCH_TEST: RELEASED gpio12=LOW
```

Wire the TTP223 as `VCC -> 3V3`, `GND -> GND`, and `OUT -> GPIO12`. Its onboard
LED changing proves that the sensor IC detects touch, but the serial transition
proves that `OUT`, the wiring, and the ESP32 input all work. If the LED changes
while serial remains `gpio12=LOW`, inspect the OUT wire and common ground.

## Active external OLED + touch profile

The active TTGO bill hardware replaces the known-dark onboard panel with a
four-wire 128x64 SSD1306-compatible OLED and uses an active-high digital touch
module instead of the BOOT button:

| Signal | TTGO GPIO |
| --- | ---: |
| OLED VCC | 3V3 |
| OLED GND | GND |
| OLED SDA | 21 |
| OLED SCL | 22 |
| OLED reset | not connected (`-1` in firmware) |
| TTP223 digital output | 12, active HIGH; keep released during reset |

LoRa is deliberately outside the RGB bill protocol. Build and, only when a
human requests it, upload the combined OLED/BLE/tap profile:

```bash
.venv-platformio/bin/pio run -e ttgo-lora32-oled-test
.venv-platformio/bin/pio run -e ttgo-lora32-oled-test -t upload
.venv-platformio/bin/pio device monitor -e ttgo-lora32-oled-test
```

Expected serial evidence includes:

```text
TTGO_TEST: OLED SDA=21 SCL=22 RESET=-1
TTGO_TEST: touch GPIO=12 active=HIGH input=TTP223
display: SSD1306 ready at 0x3C
TTGO_TEST: OLED PASS at 0x3C
tap: GATT ready; press GPIO12 TTP223 once near sender (RSSI >= -60 dBm)
```

A debounced touch arms reception for 15 seconds. Release immediately; the
accepted BLE session continues independently of the TTP223 output level. A
second touch cancels the armed window or active receive session.

The screen must visually show `RGB BILL` and `BLE READY` with no numeric amount
while its artifact inventory is empty. A complete invoice or consignment makes
the corresponding denomination and direction state appear.

The former ILI9341 build is retained only for rollback as
`ttgo-lora32-tft-legacy`; it is no longer the active TTGO bill profile.

## Legacy onboard OLED profile

This diagnostic is for the second bill prototype only. It does not initialize
the SX1276 LoRa radio, access a wallet, or move RGB assets.

## Verified hardware profile

- PlatformIO board: `ttgo-lora32-v1`
- USB: CP2102 serial `0001`
- Stable port:
  `/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0`
- ESP32-D0WDQ6 revision 1.0, MAC `30:AE:A4:4C:B1:68`, 26 MHz crystal
- OLED: 128x64 SSD1306-compatible I2C display
- OLED SDA: GPIO4
- OLED SCL: GPIO15
- OLED reset: GPIO16
- OLED address: probe `0x3C`, then `0x3D`

The LilyGO V1.3-868 branch calls the controller through an `SSD1306` library;
the board image is also labeled SSD1306. The Adafruit SSD1306 driver is used
for this test even if a seller listing calls the module SSD1308.
GPIO16 must be driven low for 50 ms and then high before the first I2C probe,
matching LilyGO's example; otherwise the controller may remain in reset and
neither address will acknowledge.

## Build, upload, and monitor

Build first:

```bash
cd /media/kestl/andor/github/rgbhackathon/ideas/bill
.venv-platformio/bin/pio run -e ttgo-lora32-test
```

When a human is ready to replace the firmware currently on the TTGO board:

```bash
.venv-platformio/bin/pio run -e ttgo-lora32-test -t upload
.venv-platformio/bin/pio device monitor -e ttgo-lora32-test
```

Do not use `esp32-bill` or `oled-test` for this port; those environments target
the separate WEMOS LOLIN32 on the CP2104 adapter.

## Expected result

The OLED should show `$0.00` and `BLE READY`. Serial should include:

```text
TTGO_TEST: OLED PASS at 0x3C
TTGO_TEST: BLE PASS - advertising as RgbBill-TTGO
TTGO_TEST: identity=bill-ttgo-v1.3-test
```

In LightBlue, connect to `RgbBill-TTGO`. Under service
`7c3e9a10-4b1e-4c8f-9d2a-00b111d0c001`, verify:

- `...c002` reads `bill-ttgo-v1.3-test`
- `...c003` reads `idle`
- `...c004` reads `0`

For the combined BLE-to-OLED test, write this UTF-8 string with response to
`...c005`:

```text
diag:display:empty
```

The display must change to `DISPLAY TEST` without a numeric amount;
`...c003` must read `idle` and `...c004` must read `0`. Disconnect and reconnect twice to verify that BLE
advertising resumes without pressing RESET.

The dock client can run the same test after selecting the TTGO's BLE address:

```bash
.venv/bin/python -m dock.bill_dock scan --timeout 8
.venv/bin/python -m dock.bill_dock state --address <TTGO_BLE_ADDRESS>
.venv/bin/python -m dock.bill_dock diagnostic --address <TTGO_BLE_ADDRESS>
```

After flashing a chunk-v1 build, validate `CHUNK_IN`, per-frame ACKs, and
`CHUNK_OUT` with the inert repository fixture:

```bash
.venv/bin/python -m dock.bill_dock chunk-loopback \
  --address 30:AE:A4:4C:B1:6A \
  --kind invoice \
  --input test/fixtures/chunk-smoke.payload
```

Success reports `loopback=ok`, `bytes=520`, and SHA-256
`925a4bf7cdf591eea7e5b78975964aee5801417761474fe3588b385ba00bc014`.
The fixture is opaque transport data and cannot invoke rgb-lib or authorize a
spend.

Hardware note: the tested TTGO unit's OLED controller ACKs and accepts the raw
all-pixels-on command, but its panel remains dark. Treat its OLED/flex or panel
power path as failed; BLE remains usable for chunk acceptance.

## Replacement external OLED test

Use the isolated diagnostic to verify the replacement four-wire 128x64
SSD1306-compatible OLED without starting BLE or the tap state machine:

| OLED lead | TTGO connection |
| --- | --- |
| VCC | 3V3 |
| GND | GND |
| SDA | GPIO21 |
| SCL | GPIO22 |

The external ILI9341 TFT may remain wired because this OLED bus no longer
shares its GPIO4 reset or GPIO15 chip-select pins; the diagnostic simply does
not initialize the TFT. The replacement OLED has no reset lead, so this test
uses `RESET=-1` and does not pulse GPIO16. It probes `0x3C` and `0x3D` at a
conservative 100 kHz.

Build first; this does not flash the board:

```bash
.venv-platformio/bin/pio run -e ttgo-oled-i2c-test
```

When ready to replace the current TTGO image:

```bash
.venv-platformio/bin/pio run -e ttgo-oled-i2c-test -t upload
.venv-platformio/bin/pio device monitor -e ttgo-oled-i2c-test
```

A working display shows `TTGO OLED`, `SDA 21 SCL 22`, and the responding I2C
address. It alternates normal and inverted output every two seconds. Expected
serial output includes:

```text
TTGO_OLED_I2C_TEST: SDA=21 SCL=22 RESET=-1
TTGO_OLED_I2C_TEST: probe_0x3C=ACK error=0
TTGO_OLED_I2C_TEST: PASS - visible test at 0x3C
TTGO_OLED_I2C_TEST: phase=INVERTED
TTGO_OLED_I2C_TEST: phase=NORMAL
```

An ACK proves an I2C controller responded; the alternating image remains the
required visual proof that the replacement panel itself works.

## Current T3 V1.3 pin-map A/B test

LilyGo's current
[`T3_V1_3_SX1276` documentation](https://github.com/Xinyuan-LilyGO/LilyGo-LoRa-Series/blob/master/docs/en/t3_v13_sx1276/t3_v13_sx1276.md)
and example utilities define the OLED as SDA GPIO21, SCL GPIO22, address
`0x3C`, with `OLED_RST` unused.
That differs from the earlier 4/15/16 profile above. The alternate environment
changes only those OLED pins and preserves the accepted BLE/chunk firmware:

```bash
.venv-platformio/bin/pio run -e ttgo-lora32-oled21-test -t upload
.venv-platformio/bin/pio device monitor -e ttgo-lora32-oled21-test
```

Expected serial evidence is:

```text
display: I2C SDA=21 SCL=22
display: SSD1306 ready at 0x3C
TTGO_TEST: OLED PASS at 0x3C
```

This profile represents LilyGo's `OLED_RST UNUSED_PIN` as `-1`. It must not
pulse GPIO0, which is an ESP32 boot-strapping pin. If serial instead reports
`no SSD1306 found`, the attached unit uses the earlier 4/15/16 I2C route.

## Manufacturer-library comparison

If the combined test remains blank, stop the serial monitor with `Ctrl+C` and
flash the OLED-only reproduction of LilyGO's sketch:

```bash
.venv-platformio/bin/pio run -e ttgo-oled-reference -t upload
.venv-platformio/bin/pio device monitor -e ttgo-oled-reference
```

This image uses ThingPulse's legacy-compatible `SSD1306` class with exactly
`SSD1306 display(0x3c, 4, 15)`, the GPIO16 reset pulse, and
`flipScreenVertically()`. It excludes BLE and LoRa. A working display shows
`LILYGO V1.3 / OLED TEST / INIT PASS`; serial separately reports whether
address `0x3C` acknowledged.

If serial reports `i2c_0x3C=NO_ACK`, the alternate driver cannot communicate
with the panel either. That points to failed OLED hardware, a different board
revision/pin map, or an electrical fault rather than the RGB bill firmware.

## Final raw-controller test

If both library tests report an I2C ACK but the panel remains black, flash the
no-library diagnostic:

```bash
.venv-platformio/bin/pio run -e ttgo-oled-raw -t upload
.venv-platformio/bin/pio device monitor -e ttgo-oled-raw
```

It performs a hardware reset, enables the internal charge pump with raw I2C
commands, and cycles every four seconds through controller-forced all pixels
on, RAM solid on, inverse empty RAM, checkerboard, and display off. In
particular, phase 1 uses command `0xA5`, which forces the panel on independently
of display RAM, fonts, geometry, and column offsets.

If phase 1 remains physically black while serial reports `probe=ACK`,
`raw_init=PASS`, and `phase_write=PASS`, replace or electrically repair the
OLED/board. Trying another framebuffer library or SH1106 column offset will not
explain a failure of the controller-forced all-pixels mode.

## Final vendor-reset and Adafruit comparison

The `ttgo-oled-final` environment is the last software A/B test for the
GPIO4/15/16 variant. It reproduces the vendor demo's exact GPIO16 reset pulse
(`HIGH` for 100 ms, `LOW` for 100 ms, then `HIGH`), initializes the vendor's
ThingPulse `SSD1306` driver at `0x3C`, then resets and initializes Adafruit
SSD1306 on the same bus. BLE and LoRa are excluded.

```bash
.venv-platformio/bin/pio run -e ttgo-oled-final -t upload
.venv-platformio/bin/pio device monitor -e ttgo-oled-final
```

The panel should alternate every four seconds between `VENDOR DRIVER` and
`ADAFRUIT DRIVER`. Serial reports the probes and both initialization results.
If `0x3C` ACKs and both drivers report `PASS` while every phase remains dark,
the test closes the software investigation: repair or replace the OLED/flex or
its panel-power path.
