"""Keep frozen dock-core UUIDs in lockstep across all implementations."""

import json
from pathlib import Path

from dock import chunk_protocol

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "docs" / "devs" / "gatt-contract.json"
CONFIG = ROOT / "include" / "config.h"
DOCK = ROOT / "dock" / "bill_dock.py"
TAP_GATT = ROOT / "lib" / "TapGatt" / "src" / "TapGatt.cpp"
DOCK_GATT = ROOT / "lib" / "DockGatt" / "src" / "DockGatt.cpp"


def test_dock_service_uuid_matches():
    contract = CONTRACT.read_text(encoding="utf-8")
    config = CONFIG.read_text(encoding="utf-8")
    dock = DOCK.read_text(encoding="utf-8")
    uuid = "7c3e9a10-4b1e-4c8f-9d2a-00b111d0c001"
    assert uuid in contract
    assert uuid in config
    assert uuid in dock
    assert "RgbBill" in config
    assert "RgbBill" in CONTRACT.read_text(encoding="utf-8")


def test_identity_uuid_matches():
    contract = CONTRACT.read_text(encoding="utf-8")
    config = CONFIG.read_text(encoding="utf-8")
    dock = DOCK.read_text(encoding="utf-8")
    uuid = "7c3e9a10-4b1e-4c8f-9d2a-00b111d0c002"
    assert uuid in contract
    assert uuid in config
    assert uuid in dock


def test_all_frozen_dock_core_uuids_match():
    contract_text = CONTRACT.read_text(encoding="utf-8")
    contract = json.loads(contract_text)
    config = CONFIG.read_text(encoding="utf-8")
    dock = DOCK.read_text(encoding="utf-8")
    suffixes = range(1, 9)

    assert (
        contract["status"]
        == "dock-core-v1+artifact-inventory-v3+chunk-v1-explicit-bearer-extraction+tap-v3-build-verified"
    )
    for suffix in suffixes:
        uuid = f"7c3e9a10-4b1e-4c8f-9d2a-00b111d0c00{suffix}"
        assert uuid in contract_text
        assert uuid in config
        assert uuid in dock

    characteristics = contract["services"]["dock"]["characteristics"]
    assert characteristics["cmd"]["commands"] == [
        "diag:display:empty",
        "diag:chunk:echo",
        "artifact:prepare:<kind>:<denomination_cents>",
        "chunk:discard",
        "chunk:receive",
    ]
    assert characteristics["chunk_in"]["implemented"] is True
    assert characteristics["chunk_out"]["implemented"] is True
    assert characteristics["artifact_meta"]["encoding"] == (
        "artifact-inventory-v3-little-endian"
    )
    assert "3 recovery-blocked" in characteristics["artifact_meta"]["layout"]["1"]
    assert "4 bearer-held" in characteristics["artifact_meta"]["layout"]["1"]
    assert contract["chunk_v1"]["kinds"]["bearer_note"] == int(
        chunk_protocol.FrameKind.BEARER_NOTE
    )
    assert "constexpr uint8_t VERSION = 0x03" in config
    assert characteristics["chunk_in"]["max_transfer_bytes"] == 640 * 1024
    assert contract["chunk_v1"]["ack_status"]["accepted"] == 0
    assert contract["chunk_v1"]["ack_status"]["busy"] == 9
    assert (
        characteristics["chunk_in"]["max_transfer_bytes"]
        == chunk_protocol.MAX_TRANSFER_BYTES
    )
    assert (
        characteristics["chunk_in"]["default_payload_bytes"]
        == chunk_protocol.DEFAULT_PAYLOAD_BYTES
    )
    assert (
        characteristics["chunk_in"]["max_payload_bytes"]
        == chunk_protocol.MAX_PAYLOAD_BYTES
    )
    python_status = {
        (
            "accepted"
            if status is chunk_protocol.AckStatus.OK
            else status.name.lower()
        ): int(status)
        for status in chunk_protocol.AckStatus
    }
    assert contract["chunk_v1"]["ack_status"] == python_status


def test_tap_v1_uuids_and_gate_match_firmware():
    contract_text = CONTRACT.read_text(encoding="utf-8")
    contract = json.loads(contract_text)
    config = CONFIG.read_text(encoding="utf-8")
    tap_gatt = TAP_GATT.read_text(encoding="utf-8")

    for suffix in range(2, 7):
        uuid = f"7c3e9a10-4b1e-4c8f-9d2a-00b1117a000{suffix}"
        assert uuid in contract_text
        assert uuid in config

    tap = contract["services"]["tap"]
    assert tap["implemented"] is True
    assert tap["physical_acceptance"] is True
    assert tap["build_verified"] is True
    bearer = tap["bearer_v3_physical_acceptance_evidence"]
    assert bearer["artifact_kind"] == int(chunk_protocol.FrameKind.BEARER_NOTE)
    assert bearer["inventory_direction"] == 4
    assert bearer["hops"] == [
        "wemos-to-ttgo",
        "ttgo-to-wemos",
        "wemos-to-ttgo",
    ]
    assert bearer["restart_persistence"].startswith("ttgo-restored")
    assert bearer["final_digest_reread"] is False
    assert tap["previous_v1_physical_acceptance_evidence"]["fixture_bytes"] == 520
    assert (
        tap["previous_v1_physical_acceptance_evidence"]["sha256"]
        == "925a4bf7cdf591eea7e5b78975964aee5801417761474fe3588b385ba00bc014"
    )
    assert tap["previous_v1_physical_acceptance_evidence"]["advertising_recovered_without_reset"]
    assert tap["gate"]["mode"] == "debounced-rising-edge-one-shot"
    assert tap["gate"]["arm_window_ms"] == 15_000
    assert tap["gate"]["second_press"] == "cancel"
    assert tap["gate"]["release_after_press"] == "no-effect"
    assert tap["gate"]["rssi_min_dbm"] == -60
    assert (
        tap["gate"]["input"]["wemos"]
        == "GPIO12 active-high momentary TTP223 digital touch"
    )
    assert (
        tap["gate"]["input"]["ttgo_oled"]
        == "GPIO12 active-high momentary TTP223 digital touch"
    )
    wemos_hardware = config.split(
        "// WEMOS LOLIN32 V1.0.0 / ESP32-WROOM-32 prototype pin map.", 1
    )[1].split("constexpr uint8_t OLED_SDA_PIN", 1)[0]
    assert "TAP_BUTTON_PIN = 12" in wemos_hardware
    assert "TAP_BUTTON_MODE = INPUT" in wemos_hardware
    assert "TAP_BUTTON_ACTIVE_LEVEL = HIGH" in wemos_hardware
    assert 'TAP_INPUT_NAME[] = "TTP223"' in wemos_hardware
    assert tap["max_transfer_bytes"] == chunk_protocol.MAX_TRANSFER_BYTES
    assert "DEFAULT_RSSI_THRESHOLD_DBM" in tap_gatt
    assert "DEFAULT_ARM_WINDOW_MS" in tap_gatt
    assert "setAdvertisedDeviceCallbacks(&scanCallbacks_, true)" in tap_gatt


def test_tap_to_dock_role_transition_is_deferred_and_subscription_gated():
    dock_gatt = DOCK_GATT.read_text(encoding="utf-8")

    assert "ADVERTISING_RESTART_DELAY_MS" in dock_gatt
    assert "advertisingRestartPending_ = true" in dock_gatt
    assert "dock advertising restarted after BLE teardown" in dock_gatt
    assert "chunkOutCccd_->getNotifications()" in dock_gatt
    assert "dockSubscribed &&" in dock_gatt
