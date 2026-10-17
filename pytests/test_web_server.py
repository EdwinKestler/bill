from pathlib import Path

from web import server as web_server
from dock.chunk_protocol import FrameKind
from web.bearer_web import BearerWebError
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
    handle_bearer_load,
    handle_bearer_pass,
    handle_bearer_recover,
    handle_bearer_redeem,
    handle_chat,
    handle_confirm,
    handle_device_connect,
    handle_device_register,
    handle_device_scan,
    handle_import,
    handle_qvac,
    handle_retry_stage,
    handle_send_usdt,
    handle_receive_usdt,
)
from web.qvac_intent import QvacIntent


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


class FakeBearerService:
    def __init__(self, *, fail_confirm: bool = False, funding_ready: bool = True) -> None:
        self.fail_confirm = fail_confirm
        self.funding_ready = funding_ready
        self.load_calls = 0
        self.prepare_calls: list[bool] = []
        self.confirm_calls: list[tuple[str, str, str]] = []
        self.funding_confirm_calls: list[tuple[str, str, str]] = []
        self.btc_topup_confirm_calls: list[tuple[str, str, str]] = []

    def prepare_funding(self):
        if not self.funding_ready:
            return {
                "phase": "bearer-note-btc-topup-plan-ready",
                "note_id": "note-funded",
                "note_state": "BTC_TOPUP_PLANNED",
                "plan": {
                    "plan_id": "topup-123",
                    "note_id": "note-funded",
                    "destination_address": "tb1qnote",
                    "topup_amount_sat": 2_000,
                    "target_note_vanilla_sat": 2_000,
                    "note_vanilla_spendable_before": 0,
                    "source_vanilla_spendable_before": 50_000,
                    "fee_rate_sat_vb": 2,
                    "expiration_timestamp": 9_999_999_999,
                },
                "broadcast": False,
            }
        plan = {
            "plan_id": "fund-123",
            "note_id": "note-funded",
            "denomination_cents": 500,
            "asset_id": "rgb:usdt",
            "amount_base_units": 5_000_000,
            "source_spendable_before": 55_000_000,
            "recipient_id": "recipient-note",
            "witness_amount_sat": 1000,
            "fee_rate_sat_vb": 2,
            "min_confirmations": 1,
            "expiration_timestamp": 9_999_999_999,
            "recipient_invoice_sha256": "d" * 64,
        }
        return {
            "phase": "bearer-funding-plan-ready",
            "note_id": "note-funded",
            "note_state": "AWAITING_FUNDING",
            "funding_gate": (
                "READY_FOR_CONFIRMATION"
                if self.funding_ready
                else "BTC_PREFLIGHT_REQUIRED"
            ),
            "redemption_btc_preflight": {
                "address": "tb1qnote",
                "recommended_vanilla_target_sat": 2000,
                "ready": self.funding_ready,
            },
            "plan": plan,
            "broadcast": False,
        }

    def renew_funding(self, note_id):
        assert note_id == "note-funded"
        self.funding_ready = True
        return self.prepare_funding()

    def inspect_funding(self):
        return self.prepare_funding()

    def execute_funding(self, *, note_id, plan_id, confirmation_phrase):
        self.funding_confirm_calls.append((note_id, plan_id, confirmation_phrase))
        if confirmation_phrase != "CONFIRM fund-123":
            raise BearerWebError(
                "exact confirmation phrase is required",
                retryable=True,
                broadcast=False,
            )
        return {
            "phase": "live-funding-imported",
            "broadcast": True,
            "note_id": note_id,
            "plan_id": plan_id,
            "txid": "txid-funding",
        }

    def execute_btc_topup(self, *, note_id, plan_id, confirmation_phrase):
        self.btc_topup_confirm_calls.append(
            (note_id, plan_id, confirmation_phrase)
        )
        if confirmation_phrase != "CONFIRM topup-123":
            raise BearerWebError(
                "exact confirmation phrase is required",
                retryable=True,
                broadcast=False,
            )
        return {
            "phase": "live-note-btc-topup-broadcast",
            "broadcast": True,
            "note_id": note_id,
            "plan_id": plan_id,
            "txid": "a" * 64,
            "topup_amount_sat": 2_000,
        }

    def refresh_funding(self, note_id):
        assert note_id == "note-funded"
        return {
            "phase": "live-funding-settlement-refresh",
            "note_id": note_id,
            "txid": "txid-funding",
            "settled": True,
        }

    def load_note(self, note_id=None):
        self.load_calls += 1
        return {
            "phase": "bearer-loaded",
            "note_id": note_id or "note-123",
            "denomination_cents": 500,
            "artifact_bytes": 603,
            "artifact_sha256": "a" * 64,
            "ble_session_id": "0x01020304",
            "broadcast": False,
        }

    def pass_note(self):
        return {
            "phase": "offline-pass-ready",
            "broadcast": False,
            "offline": True,
            "instruction": "Press the empty receiving bill once.",
        }

    def prepare_redemption(self, *, receive_from_bill):
        self.prepare_calls.append(receive_from_bill)
        return {
            "phase": "bearer-redemption-plan-ready",
            "note_id": "note-123",
            "note_state": "CLAIM_PLANNED",
            "capsule_path": "/private/incoming.rgbn",
            "capsule_sha256": "a" * 64,
            "capsule_bytes": 603,
            "ble_session_id": "0x01020304" if receive_from_bill else None,
            "broadcast": False,
            "plan": {
                "plan_id": "redeem-123",
                "note_id": "note-123",
                "denomination_cents": 500,
                "asset_id": "rgb:usdt",
                "amount_base_units": 5_000_000,
                "recipient_id": "recipient-b",
                "witness_amount_sat": 1000,
                "fee_rate_sat_vb": 2,
                "min_confirmations": 1,
                "expiration_timestamp": 9999999999,
                "recipient_invoice_sha256": "b" * 64,
                "capsule_sha256": "a" * 64,
            },
        }

    def execute_redemption(self, *, note_id, plan_id, confirmation_phrase):
        self.confirm_calls.append((note_id, plan_id, confirmation_phrase))
        if confirmation_phrase != "CONFIRM redeem-123":
            raise BearerWebError(
                "exact confirmation phrase is required",
                retryable=True,
                broadcast=False,
            )
        if self.fail_confirm:
            raise BearerWebError(
                "send outcome requires recovery",
                retryable=False,
                broadcast=None,
                recovery_action="recover-bearer-redemption",
            )
        return {
            "phase": "live-redemption-imported",
            "broadcast": True,
            "note_id": note_id,
            "plan_id": plan_id,
            "txid": "txid-redeem",
            "consignment_sha256": "c" * 64,
        }

    def recover_redemption(self, note_id):
        return {
            "phase": "live-redemption-imported",
            "broadcast": True,
            "note_id": note_id,
            "txid": "txid-redeem",
        }

    def refresh_redemption(self, note_id):
        return {
            "phase": "live-redemption-settlement-refresh",
            "note_id": note_id,
            "txid": "txid-redeem",
            "settled": True,
        }


class FakeQvacService:
    def __init__(self, intent: str = "LOAD_NOTE") -> None:
        self.intent = intent
        self.requests: list[str] = []

    def classify(self, text: str) -> QvacIntent:
        self.requests.append(text)
        amount = 500 if self.intent == "LOAD_NOTE" else None
        return QvacIntent(self.intent, amount, "local-test", 7, "cpu")


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
            "bearer": None,
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


def test_bearer_load_requires_empty_inventory_and_stages_existing_note():
    # B is a profile label, not a bearer authorization boundary.
    reset_state(role="B", cents=5500)
    service = FakeBearerService()
    empty = InventoryRegistry(
        {"direction": "empty", "kind": None, "denomination_cents": 0}
    )

    result = handle_bearer_load("note-123", service, empty)

    assert result["ok"] is True
    assert result["broadcast"] is False
    assert result["receipt"]["artifact_sha256"] == "a" * 64
    assert result["bill"]["bearer"]["phase"] == "loaded"
    assert service.load_calls == 1


def test_qvac_prepares_funding_but_cannot_confirm_it(tmp_path):
    reset_state(role="B", cents=5500)
    wallet = FakeWebService(tmp_path, role=BillRole.B)
    bearer = FakeBearerService()
    qvac = FakeQvacService()

    planned = handle_qvac(
        "prepare a five dollar note",
        qvac_service=qvac,
        bearer_service=bearer,
        wallet_service=wallet,
    )

    assert planned["ok"] is True
    assert planned["qvac"]["intent"] == "LOAD_NOTE"
    assert planned["pending"]["action"] == "bearer-funding"
    assert planned["pending"]["confirmation_phrase"] == "CONFIRM fund-123"
    assert bearer.funding_confirm_calls == []

    mismatch = handle_confirm(
        "fund-123",
        "yes",
        service=wallet,
        bearer_service=bearer,
    )
    assert mismatch["ok"] is False
    assert mismatch["broadcast"] is False
    assert bearer.funding_confirm_calls == [("note-funded", "fund-123", "yes")]

    confirmed = handle_confirm(
        "fund-123",
        "CONFIRM fund-123",
        service=wallet,
        bearer_service=bearer,
    )
    assert confirmed["ok"] is True
    assert confirmed["broadcast"] is True
    assert confirmed["receipt"]["action"] == "bearer-funding"
    assert _state["bearer"]["phase"] == "funding-imported"


def test_qvac_prepares_issuer_funded_btc_topup_without_using_faucet(tmp_path):
    reset_state(role="B", cents=5500)
    wallet = FakeWebService(tmp_path, role=BillRole.B)
    bearer = FakeBearerService(funding_ready=False)

    result = handle_qvac(
        "make a note for five dollars",
        qvac_service=FakeQvacService(),
        bearer_service=bearer,
        wallet_service=wallet,
    )

    assert result["ok"] is True
    assert result["pending"]["action"] == "bearer-note-btc-topup"
    assert result["pending"]["topup_amount_sat"] == 2_000
    assert result["pending"]["destination_address"] == "tb1qnote"
    assert "replaces the faucet step" in result["reply"]
    assert bearer.btc_topup_confirm_calls == []

    confirmed = handle_confirm(
        "topup-123",
        "CONFIRM topup-123",
        service=wallet,
        bearer_service=bearer,
    )
    assert confirmed["ok"] is True
    assert confirmed["receipt"]["action"] == "bearer-note-btc-topup"
    assert _state["bearer"]["phase"] == "btc-topup-waiting"


def test_qvac_inspect_recovers_durable_note_after_server_state_loss(tmp_path):
    reset_state(role="B", cents=5500)
    wallet = FakeWebService(tmp_path, role=BillRole.B)
    bearer = FakeBearerService(funding_ready=False)

    result = handle_qvac(
        "check my note",
        qvac_service=FakeQvacService("INSPECT_NOTE"),
        bearer_service=bearer,
        wallet_service=wallet,
    )

    assert result["ok"] is True
    assert result["qvac"]["intent"] == "INSPECT_NOTE"
    assert result["pending"]["action"] == "bearer-note-btc-topup"
    assert _state["bearer"]["note_id"] == "note-funded"


def test_load_click_refreshes_funding_then_loads_note():
    reset_state(role="B", cents=5000)
    _state["bearer"] = {
        "step": 1,
        "phase": "funding-imported",
        "offline": False,
        "note_id": "note-funded",
    }
    service = FakeBearerService()
    empty = InventoryRegistry(
        {"direction": "empty", "kind": None, "denomination_cents": 0}
    )

    result = handle_bearer_load(None, service, empty)

    assert result["ok"] is True
    assert result["receipt"]["note_id"] == "note-funded"
    assert service.load_calls == 1
    assert result["bill"]["bearer"]["phase"] == "loaded"

    occupied = InventoryRegistry(
        {
            "direction": "to-peer",
            "kind": int(FrameKind.BEARER_NOTE),
            "denomination_cents": 500,
        }
    )
    rejected = handle_bearer_load("note-123", service, occupied)
    assert rejected["ok"] is False
    assert service.load_calls == 1


def test_bearer_pass_only_reports_offline_physical_action():
    reset_state(role="A", cents=5500)
    service = FakeBearerService()
    held = InventoryRegistry(
        {
            "direction": "to-peer",
            "kind": int(FrameKind.BEARER_NOTE),
            "denomination_cents": 500,
        }
    )

    result = handle_bearer_pass(service, held)

    assert result["ok"] is True
    assert result["offline"] is True
    assert result["broadcast"] is False
    assert "Press the empty" in result["reply"]


def test_bearer_redeem_extracts_then_stops_at_exact_confirmation():
    # A may be the previously unknown final wallet for a note issued elsewhere.
    reset_state(role="A", cents=4500)
    service = FakeBearerService()
    held = InventoryRegistry(
        {
            "direction": "bearer-held",
            "kind": int(FrameKind.BEARER_NOTE),
            "denomination_cents": 500,
        }
    )

    planned = handle_bearer_redeem(service, held)

    assert planned["ok"] is True
    assert planned["broadcast"] is False
    assert service.prepare_calls == [True]
    assert planned["pending"]["action"] == "bearer-redemption"
    assert planned["pending"]["confirmation_phrase"] == "CONFIRM redeem-123"
    mismatch = handle_confirm(
        "redeem-123", "approve", bearer_service=service
    )
    assert mismatch["ok"] is False
    assert mismatch["broadcast"] is False
    assert _state["pending"]["id"] == "redeem-123"

    confirmed = handle_confirm(
        "redeem-123", "CONFIRM redeem-123", bearer_service=service
    )
    assert confirmed["ok"] is True
    assert confirmed["broadcast"] is True
    assert confirmed["receipt"]["txid"] == "txid-redeem"
    assert confirmed["retry_send"] is False


def test_bearer_confirmation_failure_enters_no_resend_recovery():
    reset_state(role="B", cents=4500)
    service = FakeBearerService(fail_confirm=True)
    held = InventoryRegistry(
        {
            "direction": "bearer-held",
            "kind": int(FrameKind.BEARER_NOTE),
            "denomination_cents": 500,
        }
    )
    handle_bearer_redeem(service, held)

    failed = handle_confirm(
        "redeem-123", "CONFIRM redeem-123", bearer_service=service
    )

    assert failed["ok"] is False
    assert failed["broadcast"] is None
    assert failed["recovery"]["action"] == "recover-bearer-redemption"
    assert failed["recovery"]["retry_send"] is False
    assert _state["pending"] is None

    recovered = handle_bearer_recover("note-123", service)
    assert recovered["ok"] is True
    assert recovered["retry_send"] is False


def test_bearer_empty_bill_reuses_retained_extraction_for_plan():
    reset_state(role="B", cents=4500)
    service = FakeBearerService()
    empty = InventoryRegistry(
        {"direction": "empty", "kind": None, "denomination_cents": 0}
    )

    planned = handle_bearer_redeem(service, empty)

    assert planned["ok"] is True
    assert service.prepare_calls == [False]
    assert planned["receipt"]["ble_session_id"] is None


def test_bearer_durable_plan_cannot_be_cancelled_as_ephemeral():
    reset_state(role="B", cents=4500)
    _state["pending"] = {
        "id": "redeem-123",
        "action": "bearer-redemption",
    }

    result = handle_cancel("redeem-123")

    assert result["ok"] is False
    assert result["broadcast"] is False
    assert _state["pending"]["id"] == "redeem-123"


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
        settings = type(
            "StartupSettings",
            (),
            {
                "wallet_label": "Owner wallet A",
                "master_fingerprint": "a1b2c3d4",
            },
        )()

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

    class StartupQvac:
        model_name = "local-test"
        ready = True

        def __init__(self):
            self.started = False
            self.closed = False

        def start_background(self):
            self.started = True

        def close(self):
            self.closed = True

    registry = StartupRegistry()
    service = StartupService()
    qvac = StartupQvac()
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
        web_server.BearerWebService,
        "from_env",
        classmethod(lambda _cls, _service: object()),
    )
    monkeypatch.setattr(
        web_server.QvacIntentService,
        "from_env",
        classmethod(lambda _cls: qvac),
    )
    monkeypatch.setattr(
        web_server,
        "ThreadingHTTPServer",
        lambda _binding, _handler: fake_server,
    )

    web_server.main()

    assert _state["identity"] == "bill-saved"
    assert _state["wallet"] == {
        "label": "Owner wallet A",
        "role": "A",
        "network": "Mutinynet",
        "master_fingerprint": "a1b2c3d4",
        "asset_id": "rgb:usdt",
        "purpose": "Issues or redeems whole-value bearer notes",
        "bearer_target": (
            "Unknown until redemption; issuance funds a fresh disposable note wallet"
        ),
        "profile_setting": "RGB_DATA_DIR_A",
        "restart_required_to_switch": True,
    }
    assert service.closed is True
    assert qvac.started is True
    assert qvac.closed is True
    assert fake_server.closed is True


def test_startup_429_message_does_not_echo_remote_html():
    message = _startup_error_message(
        RuntimeError("status: 429 <html>Too Many Requests</html>")
    )

    assert "HTTP 429" in message
    assert "<html>" not in message
