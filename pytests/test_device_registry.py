import json
import stat

import pytest

from dock.bill_dock import DOCK_SERVICE, BillCandidate, BillState
from web.device_registry import DeviceRegistry, DeviceRegistryError
from web.rgb.config import BillRole


def candidate(address: str, name: str = "RgbBill", rssi: int = -45):
    return BillCandidate(address=address, name=name, rssi=rssi)


def reader_for(states):
    async def reader(_timeout, address):
        if address not in states:
            raise RuntimeError("bill unavailable")
        return states[address]

    return reader


def discoverer_for(devices):
    async def discoverer(_timeout):
        return list(devices)

    return discoverer


def test_register_persists_one_verified_bill_and_reloads(tmp_path):
    first = candidate("AA:01")
    second = candidate("AA:02", "RgbBill-TTGO", -50)
    states = {
        "AA:01": BillState("AA:01", "bill-one", "idle", 0),
        "AA:02": BillState("AA:02", "bill-two", "pending", 500),
    }
    path = tmp_path / "registration.json"
    registry = DeviceRegistry(
        BillRole.A,
        path,
        discoverer=discoverer_for([first, second]),
        reader=reader_for(states),
    )

    scanned = registry.scan(1)
    assert [item["address"] for item in scanned] == ["AA:01", "AA:02"]
    saved = registry.register("AA:01")

    assert saved["active_address"] == "AA:01"
    assert saved["device"]["identity"] == "bill-one"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["service_uuid"] == DOCK_SERVICE
    assert payload["role"] == "A"

    registry.scan(1)
    replaced = registry.register("AA:02")
    assert replaced["active_address"] == "AA:02"
    assert json.loads(path.read_text(encoding="utf-8"))["address"] == "AA:02"

    reloaded = DeviceRegistry(
        BillRole.A,
        path,
        discoverer=discoverer_for([]),
        reader=reader_for(states),
    )
    assert reloaded.active_address() == "AA:02"
    assert reloaded.snapshot()["device"]["identity"] == "bill-two"


def test_register_rejects_unscanned_address_and_closed_guard(tmp_path):
    allowed = candidate("AA:01")
    registry = DeviceRegistry(
        BillRole.B,
        tmp_path / "registration.json",
        discoverer=discoverer_for([allowed]),
        reader=reader_for(
            {"AA:01": BillState("AA:01", "bill-one", "idle", 0)}
        ),
    )
    registry.scan(1)

    with pytest.raises(DeviceRegistryError, match="latest authorized scan"):
        registry.register("AA:99")
    with pytest.raises(DeviceRegistryError, match="current transfer"):
        registry.register("AA:01", guard=lambda: False)

    assert not (tmp_path / "registration.json").exists()


def test_environment_fallback_can_connect_without_registration_scan(tmp_path):
    registry = DeviceRegistry(
        BillRole.A,
        tmp_path / "registration.json",
        fallback_address="AA:FALLBACK",
        discoverer=discoverer_for([]),
        reader=reader_for(
            {
                "AA:FALLBACK": BillState(
                    "AA:FALLBACK", "bill-existing", "idle", 500
                )
            }
        ),
    )

    connected = registry.connect()

    assert connected["identity"] == "bill-existing"
    assert registry.snapshot()["source"] == "environment"
    assert registry.snapshot()["registered"] is False
