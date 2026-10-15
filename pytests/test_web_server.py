from pathlib import Path

from web import server as web_server
from dock.chunk_protocol import FrameKind
from web.rgb.adapter import ConsignmentArtifact, TransferPlan
from web.rgb.backend import ParsedInvoice
from web.rgb.config import BillRole
from web.rgb.tap_flow import (
    InvoiceTransferPlan,
    ReceivedArtifact,
    StagedArtifact,
    StoredArtifact,
)
from web.rgb_web import ImportOutcome, InvoiceStageOutcome, RgbWebError, SendStageOutcome
from web.server import (
    MODE,
    _startup_error_message,
    _state,
    handle_cancel,
    handle_chat,
    handle_confirm,
    handle_device_connect,
    handle_device_register,
    handle_device_scan,
    handle_import,
    handle_retry_stage,
    handle_send_usdt,
    handle_receive_usdt,
)


class FakeDeviceRegistry:
    def __init__(self):
        self.address = None
        self.guard_result = None

    def scan(self, timeout):
        assert timeout == 5
        return [
            {
                "address": "AA:01",
                "name": "RgbBill",
                "rssi": -42,
                "service_uuid": "service",
                "registered": False,
            }
        ]

    def connect(self, address):
        return {
            "connected": True,
            "address": address,
            "identity": "bill-picked",
        }

    def active_address(self):
        return self.address

    def register(self, address, *, guard):
        self.guard_result = guard()
        if not self.guard_result:
            from web.device_registry import DeviceRegistryError

            raise DeviceRegistryError(
                "finish or recover the current transfer before changing bills",
                retryable=False,
            )
        self.address = address
        return self.snapshot()

    def snapshot(self):
        record = (
            {
                "address": self.address,
                "identity": "bill-picked",
            }
            if self.address
            else None
        )
        return {
            "registered": record is not None,
            "active_address": self.address,
            "device": record,
        }


class InventoryRegistry:
    def __init__(self, artifact):
        self.artifact = artifact

    def connect(self, _address=None):
        return {
            "connected": True,
            "address": "AA:01",
            "identity": "bill-picked",
            "artifact": self.artifact,
        }


class FakeWebService:
    def __init__(
        self,
        tmp_path: Path,
        *,
        role: BillRole,
        stage_send_fails: bool = False,
    ) -> None:
        self.role = role
        self.stage_send_fails = stage_send_fails
        self.confirm_calls = 0
        self.retry_calls = 0
        invoice_path = tmp_path / "invoice.rgb-invoice"
        invoice_path.write_bytes(b"rgb:invoice")
        invoice_artifact = StoredArtifact(
            FrameKind.INVOICE,
            invoice_path,
            len(b"rgb:invoice"),
            "invoice-hash",
        )
        plan = TransferPlan(
            plan_id="plan-123",
            asset_id="rgb:usdt",
            recipient_id="recipient",
            amount=5_000_000,
            balance_before=60_000_000,
            witness_amount_sat=1000,
            fee_rate=2,
            min_confirmations=1,
            expiration_timestamp=1900,
        )
        parsed = ParsedInvoice(
            invoice="rgb:invoice",
            recipient_id="recipient",
            asset_id="rgb:usdt",
            expiration_timestamp=1900,
            transport_endpoints=(),
            unknown_query_params={},
        )
        self.prepared = InvoiceTransferPlan(
            parsed,
            invoice_artifact,
            0x11111111,
            plan,
        )
        consignment_path = tmp_path / "consignment.rgbc"
        consignment_path.write_bytes(b"real-consignment")
        self.consignment = ConsignmentArtifact(
            "txid",
            7,
            consignment_path,
            len(b"real-consignment"),
            "consignment-hash",
        )
        self.staged_consignment = StagedArtifact(
            StoredArtifact(
                FrameKind.CONSIGNMENT,
                consignment_path,
                len(b"real-consignment"),
                "consignment-hash",
            ),
            0x22222222,
        )
        self.received = ReceivedArtifact(self.staged_consignment.artifact, 0x22222222)

    def cents_from_base_units(self, amount):
        return amount // 10_000

    def plan_transfer(self, cents):
        assert self.role is BillRole.A
        assert cents == 500
        return self.prepared

    def confirm_and_stage(self, plan_id, phrase):
        assert plan_id == "plan-123"
        if phrase != "CONFIRM plan-123":
            raise RgbWebError(
                "confirmation phrase did not match; nothing was sent",
                retryable=True,
                broadcast=False,
            )
        self.confirm_calls += 1
        if self.stage_send_fails:
            return SendStageOutcome(
                self.consignment,
                None,
                "RuntimeError: BLE unavailable",
            )
        return SendStageOutcome(self.consignment, self.staged_consignment)

    def retry_consignment_stage(self):
        self.retry_calls += 1
        return SendStageOutcome(self.consignment, self.staged_consignment)

    def stage_invoice(self, cents):
        assert self.role is BillRole.B
        assert cents == 500
        return InvoiceStageOutcome(
            cents,
            self.prepared.artifact,
            1900,
            4,
            StagedArtifact(self.prepared.artifact, 0x11111111),
        )

    def receive_and_import(self):
        assert self.role is BillRole.B
        return ImportOutcome(
            self.received,
            {4: "waiting_confirmations"},
        )

    def refresh_settlement(self):
        return 6000 if self.role is BillRole.A else 4000, {7: "settled"}


def reset_state(*, role: str, cents: int) -> None:
    _state.update(
        {
            "role": role,
            "identity": "bill-test",
            "status": "idle",
            "cents": cents,
            "pending": None,
            "receipts": [],
            "recovery": None,
            "mode": MODE,
            "settlement": "settled",
            "asset_id": "rgb:usdt",
            "asset_precision": 6,
            "expected_receive_cents": None,
        }
    )


def test_bill_a_requires_exact_phrase_before_one_live_send(tmp_path):
    reset_state(role="A", cents=6000)
    service = FakeWebService(tmp_path, role=BillRole.A)

    chat = handle_chat("bill for $5", service)

    assert chat["pending"]["confirmation_phrase"] == "CONFIRM plan-123"
    assert chat["pending"]["transport_endpoints"] == []
    mismatch = handle_confirm("plan-123", "approve", service)
    assert mismatch["ok"] is False
    assert mismatch["broadcast"] is False
    assert _state["pending"]["id"] == "plan-123"
    assert service.confirm_calls == 0

    result = handle_confirm("plan-123", "CONFIRM plan-123", service)

    assert result["ok"] is True
    assert result["completed"] is True
    assert result["receipt"]["txid"] == "txid"
    assert result["receipt"]["ble_session_id"] == "0x22222222"
    assert result["receipt"]["retry_send"] is False
    assert result["bill"]["cents"] == 5500
    assert service.confirm_calls == 1


def test_post_broadcast_stage_failure_uses_recovery_not_second_send(tmp_path):
    reset_state(role="A", cents=6000)
    service = FakeWebService(
        tmp_path,
        role=BillRole.A,
        stage_send_fails=True,
    )
    pending = handle_chat("bill for $5", service)["pending"]

    result = handle_confirm(
        pending["id"],
        pending["confirmation_phrase"],
        service,
    )

    assert result["ok"] is True
    assert result["completed"] is False
    assert result["broadcast"] is True
    assert result["retry_send"] is False
    assert result["recovery"]["endpoint"] == "/api/rgb/retry-stage"
    assert _state["pending"] is None
    assert service.confirm_calls == 1

    retry = handle_retry_stage(service)

    assert retry["ok"] is True
    assert retry["retry_send"] is False
    assert service.retry_calls == 1
    assert service.confirm_calls == 1


def test_bill_b_stages_invoice_and_imports_received_consignment(tmp_path):
    reset_state(role="B", cents=4000)
    service = FakeWebService(tmp_path, role=BillRole.B)

    staged = handle_chat("prepare bill for $5", service)

    assert staged["ok"] is True
    assert staged["receipt"]["ble_session_id"] == "0x11111111"
    assert staged["receipt"]["transport_endpoints"] == []
    imported = handle_import(service)
    assert imported["ok"] is True
    assert imported["receipt"]["artifact_sha256"] == "consignment-hash"
    assert imported["receipt"]["updated_transfers"] == {
        "4": "waiting_confirmations"
    }
    assert imported["bill"]["cents"] == 4500
    assert imported["bill"]["settlement"] == "waiting-confirmations"


def test_non_five_dollar_amount_is_not_confirmable(tmp_path):
    reset_state(role="A", cents=6000)
    service = FakeWebService(tmp_path, role=BillRole.A)

    result = handle_chat("bill for $10", service)

    assert result["pending"] is None
    assert result["broadcast"] is False
    assert "$5.00" in result["reply"]
    assert service.confirm_calls == 0


def test_cancel_discards_web_plan_without_confirmation_or_broadcast(tmp_path):
    reset_state(role="A", cents=6000)
    service = FakeWebService(tmp_path, role=BillRole.A)
    pending = handle_chat("bill for $5", service)["pending"]

    result = handle_cancel(pending["id"])

    assert result["ok"] is True
    assert result["broadcast"] is False
    assert result["bill"]["pending"] is None
    assert service.confirm_calls == 0


def test_status_refreshes_through_same_live_wallet_service(tmp_path):
    reset_state(role="A", cents=5500)
    service = FakeWebService(tmp_path, role=BillRole.A)

    result = handle_chat("what is the balance status?", service)

    assert result["ok"] is True
    assert "$60.00" in result["reply"]
    assert "settled" in result["reply"]
    assert _state["cents"] == 6000


def test_device_scan_connect_and_register_update_selected_identity():
    reset_state(role="A", cents=6000)
    registry = FakeDeviceRegistry()

    scanned = handle_device_scan(5, registry)
    connected = handle_device_connect("AA:01", registry)
    registered = handle_device_register("AA:01", registry)

    assert scanned["ok"] is True
    assert scanned["devices"][0]["address"] == "AA:01"
    assert connected["ok"] is True
    assert registered["ok"] is True
    assert registered["device"]["active_address"] == "AA:01"
    assert registry.guard_result is True
    assert _state["identity"] == "bill-picked"


def test_device_registration_is_blocked_during_transfer():
    reset_state(role="A", cents=6000)
    _state["status"] = "invoice-staged"
    registry = FakeDeviceRegistry()

    result = handle_device_register("AA:01", registry)

    assert result["ok"] is False
    assert result["retryable"] is False
    assert "current transfer" in result["error"]
    assert registry.address is None
    assert registry.guard_result is False


def test_send_usdt_requires_received_invoice_before_planning(tmp_path):
    reset_state(role="A", cents=6000)
    service = FakeWebService(tmp_path, role=BillRole.A)
    empty = InventoryRegistry(
        {
            "direction": "empty",
            "kind": None,
            "denomination_cents": 0,
        }
    )

    rejected = handle_send_usdt(500, service, empty)

    assert rejected["ok"] is False
    assert "no received invoice" in rejected["error"]
    assert _state["pending"] is None


def test_send_usdt_inventory_selects_invoice_read_and_confirmation(tmp_path):
    reset_state(role="A", cents=6000)
    service = FakeWebService(tmp_path, role=BillRole.A)
    invoice = InventoryRegistry(
        {
            "direction": "to-dock",
            "kind": int(FrameKind.INVOICE),
            "denomination_cents": 500,
        }
    )

    result = handle_send_usdt(500, service, invoice)

    assert result["ok"] is True
    assert result["pending"]["confirmation_phrase"] == "CONFIRM plan-123"


def test_send_usdt_blocked_inventory_fails_before_wallet_plan(tmp_path):
    reset_state(role="A", cents=5500)
    service = FakeWebService(tmp_path, role=BillRole.A)
    blocked = InventoryRegistry(
        {
            "direction": "blocked",
            "kind": int(FrameKind.INVOICE),
            "denomination_cents": 500,
        }
    )

    result = handle_send_usdt(500, service, blocked)

    assert result["ok"] is False
    assert result["broadcast"] is False
    assert "storage recovery is required" in result["error"]
    assert "Do not create or send another artifact" in result["error"]
    assert _state["pending"] is None


def test_receive_usdt_empty_inventory_stages_invoice(tmp_path):
    reset_state(role="B", cents=4000)
    service = FakeWebService(tmp_path, role=BillRole.B)
    empty = InventoryRegistry(
        {
            "direction": "empty",
            "kind": None,
            "denomination_cents": 0,
        }
    )

    result = handle_receive_usdt(500, service, empty)

    assert result["ok"] is True
    assert result["receipt"]["action"] == "invoice-stage"


def test_receive_usdt_blocked_inventory_does_not_create_second_invoice(tmp_path):
    reset_state(role="B", cents=4500)
    service = FakeWebService(tmp_path, role=BillRole.B)
    blocked = InventoryRegistry(
        {
            "direction": "blocked",
            "kind": int(FrameKind.INVOICE),
            "denomination_cents": 500,
        }
    )

    def unexpected_stage(_cents):
        raise AssertionError("blocked inventory must not create another invoice")

    service.stage_invoice = unexpected_stage
    result = handle_receive_usdt(500, service, blocked)

    assert result["ok"] is False
    assert result["broadcast"] is False
    assert "storage recovery is required" in result["error"]
    assert _state["pending"] is None


def test_main_loads_registration_without_startup_ble_connect(monkeypatch):
    class StartupRegistry:
        timeout = 8.0

        def snapshot(self):
            return {
                "device": {
                    "address": "AA:01",
                    "identity": "bill-saved",
                }
            }

    class StartupService:
        role = BillRole.A
        asset_id = "rgb:usdt"
        asset_precision = 6

        def __init__(self):
            self.closed = False

        def spendable_cents(self):
            return 5500

        def close(self):
            self.closed = True

    class FakeServer:
        def __init__(self, _binding, _handler):
            self.closed = False

        def serve_forever(self):
            raise KeyboardInterrupt

        def server_close(self):
            self.closed = True

    registry = StartupRegistry()
    service = StartupService()
    fake_server = FakeServer(None, None)
    monkeypatch.setattr(
        web_server.DeviceRegistry,
        "from_env",
        classmethod(lambda _cls, _role: registry),
    )
    monkeypatch.setattr(
        web_server.RgbWebService,
        "from_env",
        classmethod(lambda _cls, *, gateway: service),
    )
    monkeypatch.setattr(
        web_server,
        "ThreadingHTTPServer",
        lambda _binding, _handler: fake_server,
    )

    web_server.main()

    assert _state["identity"] == "bill-saved"
    assert service.closed is True
    assert fake_server.closed is True


def test_startup_429_message_does_not_echo_remote_html():
    message = _startup_error_message(
        RuntimeError("status: 429 <html>Too Many Requests</html>")
    )

    assert "HTTP 429" in message
    assert "<html>" not in message
