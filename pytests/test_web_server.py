from pathlib import Path

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
    _state,
    handle_cancel,
    handle_chat,
    handle_confirm,
    handle_import,
    handle_retry_stage,
)


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
