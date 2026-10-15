"""Unit coverage for Bleak 3.x advertisement and identity handling."""

import asyncio
import re
from types import SimpleNamespace

import pytest

from dock import bill_dock


def _sighting():
    device = SimpleNamespace(name="RgbBill", address="30:AE:A4:07:2D:2E")
    advertisement = SimpleNamespace(
        local_name="RgbBill",
        service_uuids=[bill_dock.DOCK_SERVICE],
        rssi=-53,
    )
    return device, advertisement


def test_scan_uses_bleak_3_advertisement_data(monkeypatch, capsys):
    device, advertisement = _sighting()
    calls = []

    class FakeScanner:
        @staticmethod
        async def discover(**kwargs):
            calls.append(kwargs)
            return {device.address: (device, advertisement)}

    monkeypatch.setattr(bill_dock, "BleakScanner", FakeScanner)

    assert asyncio.run(bill_dock.scan(0.1)) == 0
    output = capsys.readouterr().out
    assert re.match(
        r"^\[\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}[+-]\d{2}:\d{2}\] ",
        output,
    )
    assert "30:AE:A4:07:2D:2E" in output
    assert "rssi=-53" in output
    assert calls[0]["return_adv"] is True
    assert calls[0]["service_uuids"] == [bill_dock.DOCK_SERVICE]


def test_picker_requires_service_uuid_and_rgbill_name(monkeypatch):
    sightings = [
        (
            SimpleNamespace(name="RgbBill", address="name-only"),
            SimpleNamespace(local_name="RgbBill", service_uuids=[], rssi=-20),
        ),
        (
            SimpleNamespace(name="Other", address="wrong-name"),
            SimpleNamespace(
                local_name="Other",
                service_uuids=[bill_dock.DOCK_SERVICE],
                rssi=-30,
            ),
        ),
        (
            SimpleNamespace(name="RgbBill-TTGO", address="ttgo"),
            SimpleNamespace(
                local_name="RgbBill-TTGO",
                service_uuids=[bill_dock.DOCK_SERVICE.upper()],
                rssi=-55,
            ),
        ),
        (
            SimpleNamespace(name="RgbBill", address="wemos"),
            SimpleNamespace(
                local_name="RgbBill",
                service_uuids=[bill_dock.DOCK_SERVICE],
                rssi=-42,
            ),
        ),
    ]

    async def fake_discover(_timeout):
        return sightings

    monkeypatch.setattr(bill_dock, "_discover", fake_discover)

    candidates = asyncio.run(bill_dock.discover_bill_candidates(0.1))

    assert [candidate.address for candidate in candidates] == ["wemos", "ttgo"]
    assert candidates[0].rssi == -42


def test_identity_reads_expected_characteristic(monkeypatch, capsys):
    device, advertisement = _sighting()
    reads = []

    async def fake_discover(_timeout):
        return [(device, advertisement)]

    class FakeClient:
        def __init__(self, selected_device, timeout):
            assert selected_device is device
            assert timeout == 0.1

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        async def read_gatt_char(self, uuid):
            reads.append(uuid)
            return bytearray(b"bill-unprovisioned")

    monkeypatch.setattr(bill_dock, "_discover", fake_discover)
    monkeypatch.setattr(bill_dock, "BleakClient", FakeClient)

    assert asyncio.run(bill_dock.identity(0.1)) == 0
    assert reads == [bill_dock.IDENTITY]
    assert "identity=bill-unprovisioned" in capsys.readouterr().out


def test_state_reads_frozen_core_characteristics(monkeypatch, capsys):
    device, _advertisement = _sighting()
    reads = []
    values = {
        bill_dock.IDENTITY: b"bill-unprovisioned",
        bill_dock.STATUS: b"idle",
        bill_dock.DENOMINATION: b"0",
        bill_dock.ARTIFACT_META: bytes([1]) + bytes(15),
    }

    async def fake_find_target(_timeout, _address=None):
        return device

    class FakeClient:
        def __init__(self, selected_device, timeout):
            assert selected_device is device
            assert timeout == 0.1

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        async def read_gatt_char(self, uuid):
            reads.append(uuid)
            return bytearray(values[uuid])

    monkeypatch.setattr(bill_dock, "_find_target", fake_find_target)
    monkeypatch.setattr(bill_dock, "BleakClient", FakeClient)

    assert asyncio.run(bill_dock.state(0.1)) == 0
    assert reads == [
        bill_dock.IDENTITY,
        bill_dock.STATUS,
        bill_dock.DENOMINATION,
        bill_dock.ARTIFACT_META,
    ]
    assert "status=idle  denomination=0" in capsys.readouterr().out


def test_artifact_inventory_decodes_direction_kind_and_amount():
    raw = (
        bytes([1, 2, int(bill_dock.FrameKind.CONSIGNMENT), 0])
        + (0x12345678).to_bytes(4, "little")
        + (12496).to_bytes(4, "little")
        + (500).to_bytes(4, "little")
    )

    artifact = bill_dock.decode_artifact_metadata(raw)

    assert artifact.direction == "to-dock"
    assert artifact.kind is bill_dock.FrameKind.CONSIGNMENT
    assert artifact.session_id == 0x12345678
    assert artifact.size == 12496
    assert artifact.denomination_cents == 500


def test_artifact_inventory_v2_decodes_known_blocked_artifact():
    raw = (
        bytes([2, 3, int(bill_dock.FrameKind.INVOICE), 0])
        + (0xFDB1D99B).to_bytes(4, "little")
        + (210).to_bytes(4, "little")
        + (500).to_bytes(4, "little")
    )

    artifact = bill_dock.decode_artifact_metadata(raw)

    assert artifact.direction == "blocked"
    assert artifact.kind is bill_dock.FrameKind.INVOICE
    assert artifact.session_id == 0xFDB1D99B
    assert artifact.size == 210
    assert artifact.denomination_cents == 500


def test_artifact_inventory_v2_decodes_unknown_orphan_as_blocked():
    artifact = bill_dock.decode_artifact_metadata(bytes([2, 3]) + bytes(14))

    assert artifact.direction == "blocked"
    assert artifact.kind is None
    assert artifact.session_id == 0
    assert artifact.size == 0
    assert artifact.denomination_cents == 0


def test_artifact_inventory_v1_rejects_blocked_direction():
    raw = bytes([1, 3]) + bytes(14)

    with pytest.raises(ValueError, match="direction"):
        bill_dock.decode_artifact_metadata(raw)


def test_artifact_inventory_rejects_nonempty_empty_state():
    raw = bytes([1, 0, 1, 0]) + bytes(12)

    with pytest.raises(ValueError, match="empty bill"):
        bill_dock.decode_artifact_metadata(raw)


def test_diagnostic_is_fixed_write_with_response(monkeypatch, capsys):
    device, _advertisement = _sighting()
    writes = []
    values = {
        bill_dock.IDENTITY: b"bill-unprovisioned",
        bill_dock.STATUS: b"idle",
        bill_dock.DENOMINATION: b"0",
    }

    async def fake_find_target(_timeout, _address=None):
        return device

    class FakeClient:
        def __init__(self, selected_device, timeout):
            assert selected_device is device

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        async def write_gatt_char(self, uuid, payload, response):
            writes.append((uuid, bytes(payload), response))
            values[bill_dock.STATUS] = b"idle"
            values[bill_dock.DENOMINATION] = b"0"

        async def read_gatt_char(self, uuid):
            return bytearray(values[uuid])

    monkeypatch.setattr(bill_dock, "_find_target", fake_find_target)
    monkeypatch.setattr(bill_dock, "BleakClient", FakeClient)

    assert asyncio.run(bill_dock.diagnostic(0.1)) == 0
    assert writes == [(bill_dock.CMD, bill_dock.DIAGNOSTIC_COMMAND, True)]
    assert "diagnostic=ok" in capsys.readouterr().out
