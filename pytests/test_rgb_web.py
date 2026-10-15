from pathlib import Path
from types import SimpleNamespace

from dock.chunk_protocol import FrameKind
from web.rgb.adapter import ConsignmentArtifact
from web.rgb.backend import ReceiveIntent
from web.rgb.config import BillRole
from web.rgb.tap_flow import ReceivedArtifact, StagedArtifact, StoredArtifact
from web.rgb_web import RgbWebService


class FakeAdapter:
    def __init__(self, role: BillRole) -> None:
        self.settings = SimpleNamespace(role=role)
        self.confirmed = []
        self.closed = False

    def spendable_balance(self, _asset_id):
        return 60_000_000

    def confirm_transfer(self, plan_id):
        self.confirmed.append(plan_id)

    def close(self):
        self.closed = True

    def refresh_transfers(self):
        return {7: "settled"}


class RecoveryFlow:
    def __init__(self, tmp_path: Path, role: BillRole) -> None:
        self.adapter = FakeAdapter(role)
        self.create_invoice_calls = 0
        self.stage_artifact_calls = 0
        self.execute_calls = 0
        self.stage_consignment_calls = 0
        self.receive_calls = 0
        self.import_calls = 0
        invoice_path = tmp_path / "invoice.rgb-invoice"
        invoice_path.write_bytes(b"invoice")
        self.invoice = StoredArtifact(
            FrameKind.INVOICE,
            invoice_path,
            len(b"invoice"),
            "invoice-hash",
        )
        consignment_path = tmp_path / "consignment.rgbc"
        consignment_path.write_bytes(b"consignment")
        self.consignment = ConsignmentArtifact(
            "txid",
            7,
            consignment_path,
            len(b"consignment"),
            "consignment-hash",
        )
        self.stored_consignment = StoredArtifact(
            FrameKind.CONSIGNMENT,
            consignment_path,
            len(b"consignment"),
            "consignment-hash",
        )

    def create_invoice_artifact(self, **_kwargs):
        self.create_invoice_calls += 1
        return ReceiveIntent("invoice", "recipient", 1900, 4), self.invoice

    def stage_artifact(self, artifact, denomination_cents=0):
        self.stage_artifact_calls += 1
        if self.stage_artifact_calls == 1:
            raise RuntimeError("BLE unavailable")
        return StagedArtifact(artifact, 0x11111111)

    def execute_confirmed_transfer(self, plan_id):
        assert plan_id == "plan-123"
        self.execute_calls += 1
        return self.consignment

    def stage_consignment(self, _artifact, denomination_cents=0):
        self.stage_consignment_calls += 1
        if self.stage_consignment_calls == 1:
            raise RuntimeError("BLE unavailable")
        return StagedArtifact(self.stored_consignment, 0x22222222)

    def receive_consignment(self):
        self.receive_calls += 1
        return ReceivedArtifact(self.stored_consignment, 0x22222222)

    def import_consignment(self, _received):
        self.import_calls += 1
        if self.import_calls == 1:
            raise RuntimeError("indexer timeout")
        return {4: "waiting_confirmations"}


def test_invoice_stage_retry_reuses_same_native_invoice(tmp_path):
    flow = RecoveryFlow(tmp_path, BillRole.B)
    service = RgbWebService(flow, asset_id="rgb:usdt", asset_precision=6)

    first = service.stage_invoice(500)
    second = service.stage_invoice(500)

    assert first.staged is None
    assert second.staged is not None
    assert flow.create_invoice_calls == 1
    assert flow.stage_artifact_calls == 2
    assert first.artifact.path == second.artifact.path


def test_post_broadcast_retry_stages_same_consignment_without_resend(tmp_path):
    flow = RecoveryFlow(tmp_path, BillRole.A)
    service = RgbWebService(flow, asset_id="rgb:usdt", asset_precision=6)

    first = service.confirm_and_stage("plan-123", "CONFIRM plan-123")
    second = service.retry_consignment_stage()

    assert first.staged is None
    assert second.staged is not None
    assert first.consignment.path == second.consignment.path
    assert flow.execute_calls == 1
    assert flow.stage_consignment_calls == 2
    assert flow.adapter.confirmed == ["plan-123"]


def test_import_retry_reuses_received_artifact_without_second_ble_receive(tmp_path):
    flow = RecoveryFlow(tmp_path, BillRole.B)
    service = RgbWebService(flow, asset_id="rgb:usdt", asset_precision=6)

    first = service.receive_and_import()
    second = service.receive_and_import()

    assert first.updated_transfers is None
    assert second.updated_transfers == {4: "waiting_confirmations"}
    assert first.received.artifact.path == second.received.artifact.path
    assert flow.receive_calls == 1
    assert flow.import_calls == 2


def test_web_amount_conversion_uses_configured_asset_precision(tmp_path):
    flow = RecoveryFlow(tmp_path, BillRole.A)
    service = RgbWebService(flow, asset_id="rgb:usdt", asset_precision=6)

    assert service.amount_base_units(500) == 5_000_000
    assert service.cents_from_base_units(60_000_000) == 6000
    assert service.spendable_cents() == 6000
    assert service.refresh_settlement() == (6000, {7: "settled"})
