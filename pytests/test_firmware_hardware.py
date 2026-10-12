from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_production_firmware_targets_verified_lolin32():
    platformio = (ROOT / "platformio.ini").read_text(encoding="utf-8")

    assert "default_envs = esp32-bill" in platformio
    assert "[env:esp32-bill]" in platformio
    assert "board = lolin32" in platformio
    assert "freenove_esp32_s3_wroom" not in platformio
    assert "usb-Silicon_Labs_CP2104_USB_to_UART_Bridge_Controller_014BCF94" in platformio


def test_production_uses_three_megabyte_no_ota_partition():
    platformio = (ROOT / "platformio.ini").read_text(encoding="utf-8")
    partitions = (ROOT / "partitions.csv").read_text(encoding="utf-8")

    assert "board_build.partitions = partitions.csv" in platformio
    assert "app0,     app,  factory, 0x10000, 0x300000" in partitions
    assert "ota_0" not in partitions
    assert "ota_1" not in partitions


def test_main_and_oled_test_share_verified_display_driver():
    config = (ROOT / "include" / "config.h").read_text(encoding="utf-8")
    main = (ROOT / "src" / "main.cpp").read_text(encoding="utf-8")
    oled_test = (ROOT / "src" / "oled_test.cpp").read_text(encoding="utf-8")

    assert "OLED_SDA_PIN = 21" in config
    assert "OLED_SCL_PIN = 22" in config
    assert "OLED_WIDTH = 128" in config
    assert "OLED_HEIGHT = 64" in config
    assert '#include <BillDisplay.h>' in main
    assert '#include <BillDisplay.h>' in oled_test
    assert 'billDisplay.showAmount(0, "BLE READY")' in main


def test_ttgo_lora32_v13_has_isolated_oled_ble_environment():
    platformio = (ROOT / "platformio.ini").read_text(encoding="utf-8")
    config = (ROOT / "include" / "config.h").read_text(encoding="utf-8")
    ttgo_test = (ROOT / "src" / "ttgo_lora32_test.cpp").read_text(
        encoding="utf-8"
    )

    assert "[env:ttgo-lora32-test]" in platformio
    assert "board = ttgo-lora32-v1" in platformio
    assert "RGB_BILL_TTGO_LORA32_V13=1" in platformio
    assert "usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001" in platformio
    assert "OLED_SDA_PIN = 4" in config
    assert "OLED_SCL_PIN = 15" in config
    assert "OLED_RESET_PIN = 16" in config
    assert 'BLE_DEVICE_NAME[] = "RgbBill-TTGO"' in config
    assert '#include <BillDisplay.h>' in ttgo_test
    assert '#include <DockGatt.h>' in ttgo_test


def test_ttgo_external_ili9341_and_touch_profile_is_isolated():
    platformio = (ROOT / "platformio.ini").read_text(encoding="utf-8")
    config = (ROOT / "include" / "config.h").read_text(encoding="utf-8")
    ttgo_test = (ROOT / "src" / "ttgo_lora32_test.cpp").read_text(
        encoding="utf-8"
    )
    display = (
        ROOT / "lib" / "TftBillDisplay" / "src" / "TftBillDisplay.cpp"
    ).read_text(encoding="utf-8")

    assert "[env:ttgo-lora32-tft-test]" in platformio
    assert "RGB_BILL_TTGO_TFT_ILI9341=1" in platformio
    assert "Adafruit ILI9341@^1.6.2" in platformio
    assert "TAP_BUTTON_PIN = 12" in config
    assert "TAP_BUTTON_ACTIVE_LEVEL = HIGH" in config
    assert 'TAP_INPUT_NAME[] = "TTP223"' in config
    assert "TFT_BACKLIGHT_PIN = 32" in config
    assert "TFT_SCK_PIN = 18" in config
    assert "TFT_MOSI_PIN = 23" in config
    assert "TFT_DC_PIN = 2" in config
    assert "TFT_RESET_PIN = 4" in config
    assert "TFT_CS_PIN = 15" in config
    assert '#include <TftBillDisplay.h>' in ttgo_test
    assert "SPI.begin(TFT_SCK_PIN, -1, TFT_MOSI_PIN, TFT_CS_PIN)" in display
    assert "pinMode(TFT_BACKLIGHT_PIN, INPUT)" in display
    assert "digitalWrite(TFT_BACKLIGHT_PIN, HIGH)" not in display


def test_ttgo_oled_reset_is_released_before_i2c_probe():
    display = (
        ROOT / "lib" / "BillDisplay" / "src" / "BillDisplay.cpp"
    ).read_text(encoding="utf-8")

    reset_low = display.index("digitalWrite(OLED_RESET_PIN, LOW)")
    reset_high = display.index("digitalWrite(OLED_RESET_PIN, HIGH)")
    probe = display.index("if (probeAddress(OLED_ADDRESS_PRIMARY))")
    assert reset_low < reset_high < probe
    assert "delay(50)" in display[reset_low:reset_high]
    assert "SSD1306_SWITCHCAPVCC, address_, false, false" in display


def test_production_environment_excludes_ttgo_diagnostic_entry():
    platformio = (ROOT / "platformio.ini").read_text(encoding="utf-8")
    production = platformio.split("[env:esp32-bill]", 1)[1].split(
        "[env:oled-test]", 1
    )[0]

    assert "-<ttgo_lora32_test.cpp>" in production
    assert "-<ttgo_oled_reference.cpp>" in production
    assert "-<ttgo_touch_test.cpp>" in production


def test_ttgo_gpio12_ttp223_digital_diagnostic_is_isolated():
    platformio = (ROOT / "platformio.ini").read_text(encoding="utf-8")
    source = (ROOT / "src" / "ttgo_touch_test.cpp").read_text(
        encoding="utf-8"
    )

    assert "[env:ttgo-touch-test]" in platformio
    assert "+<ttgo_touch_test.cpp>" in platformio
    assert "TOUCH_GPIO = 12" in source
    assert "TOUCH_ACTIVE_LEVEL = HIGH" in source
    assert "never drive it HIGH at reset" in source
    assert "pinMode(TOUCH_GPIO, INPUT)" in source
    assert "digitalRead(TOUCH_GPIO)" in source
    assert "touchRead(TOUCH_GPIO)" not in source


def test_ttgo_reference_environment_matches_lilygo_oled_sketch():
    platformio = (ROOT / "platformio.ini").read_text(encoding="utf-8")
    source = (ROOT / "src" / "ttgo_oled_reference.cpp").read_text(
        encoding="utf-8"
    )

    assert "[env:ttgo-oled-reference]" in platformio
    assert "ESP8266 and ESP32 OLED driver for SSD1306 displays@4.6.2" in platformio
    assert (
        "SSD1306 display(OLED_ADDRESS, OLED_SDA_PIN_REF, OLED_SCL_PIN_REF)"
        in source
    )
    assert "OLED_ADDRESS = 0x3C" in source
    assert "OLED_SDA_PIN_REF = 4" in source
    assert "OLED_SCL_PIN_REF = 15" in source
    assert "OLED_RESET_PIN_REF = 16" in source
    assert "display.flipScreenVertically()" in source


def test_dock_gatt_defers_advertising_restart_until_disconnect_teardown():
    main = (ROOT / "src" / "main.cpp").read_text(encoding="utf-8")
    dock_header = (ROOT / "lib" / "DockGatt" / "src" / "DockGatt.h").read_text(
        encoding="utf-8"
    )
    dock_source = (ROOT / "lib" / "DockGatt" / "src" / "DockGatt.cpp").read_text(
        encoding="utf-8"
    )

    assert "DockGatt dockGatt" in main
    assert "dockGatt.begin()" in main
    assert "onDisconnect(BLEServer* server) override" in dock_header
    assert "server_->setCallbacks(&callbacks_)" in dock_source
    assert "advertisingRestartPending_ = true" in dock_source
    assert "ADVERTISING_RESTART_DELAY_MS" in dock_source
    assert "BLEDevice::getAdvertising()->start()" in dock_source
    assert "dock advertising restarted after BLE teardown" in dock_source


def test_dock_gatt_exposes_state_and_fixed_diagnostic():
    dock_source = (ROOT / "lib" / "DockGatt" / "src" / "DockGatt.cpp").read_text(
        encoding="utf-8"
    )

    assert "BLE_UUIDs::STATUS" in dock_source
    assert "BLE_UUIDs::DENOMINATION" in dock_source
    assert "BLE_UUIDs::CMD" in dock_source
    assert "BLECharacteristic::PROPERTY_NOTIFY" in dock_source
    assert 'command == "diag:display:500:pending"' in dock_source
    assert 'setState(500, "pending", "PENDING")' in dock_source


def test_dock_gatt_exposes_chunk_fsm_and_polls_it():
    main = (ROOT / "src" / "main.cpp").read_text(encoding="utf-8")
    dock_source = (ROOT / "lib" / "DockGatt" / "src" / "DockGatt.cpp").read_text(
        encoding="utf-8"
    )

    assert "BLE_UUIDs::CHUNK_IN" in dock_source
    assert "BLE_UUIDs::CHUNK_OUT" in dock_source
    assert "BLEDevice::setMTU(247)" in dock_source
    assert "MAX_TRANSFER_BYTES = 640U * 1024U" in dock_source
    assert 'command == "diag:chunk:echo"' in dock_source
    assert 'command == "chunk:discard"' in dock_source
    assert "dockGatt.poll()" in main
