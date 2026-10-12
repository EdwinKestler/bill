"""Unit coverage for Bleak 3.x advertisement and identity handling."""

import asyncio
import re
from types import SimpleNamespace

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
    assert reads == [bill_dock.IDENTITY, bill_dock.STATUS, bill_dock.DENOMINATION]
    assert "status=idle  denomination=0" in capsys.readouterr().out


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
            values[bill_dock.STATUS] = b"pending"
            values[bill_dock.DENOMINATION] = b"500"

        async def read_gatt_char(self, uuid):
            return bytearray(values[uuid])

    monkeypatch.setattr(bill_dock, "_find_target", fake_find_target)
    monkeypatch.setattr(bill_dock, "BleakClient", FakeClient)

    assert asyncio.run(bill_dock.diagnostic(0.1)) == 0
    assert writes == [(bill_dock.CMD, bill_dock.DIAGNOSTIC_COMMAND, True)]
    assert "diagnostic=ok" in capsys.readouterr().out
