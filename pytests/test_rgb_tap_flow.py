from pathlib import Path

from dock.chunk_protocol import FrameKind
from web.rgb.adapter import RgbBillAdapter
from web.rgb.backend import BackendSendResult, ParsedInvoice, ReceiveIntent
from web.rgb.config import BillRole, RgbSettings
from web.rgb.tap_flow import TapArtifactStore, TapWalletFlow


class FakeBackend:
    def __init__(self, tmp_path: Path, *, balance: int = 500) -> None:
        self.balance = balance
        self.consignment = tmp_path / "native-consignment.rgbc"
        self.consignment.write_bytes(b"real-rgb-consignment")
        self.send_calls = []
        self.imported = []

    def spendable_balance(self, _asset_id):
        return self.balance

    def witness_receive(self, asset_id, expiration_timestamp, min_confirmations):
        assert asset_id == "rgb:usdt"
        assert min_confirmations == 1
        return ReceiveIntent("rgb:invoice", "recipient", expiration_timestamp, 4)

    def parse_invoice(self, invoice):
        return ParsedInvoice(
            invoice=invoice,
            recipient_id="recipient",
            asset_id="rgb:usdt",
            expiration_timestamp=1900,
            transport_endpoints=(),
            unknown_query_params={},
        )

    def send_donation(self, **kwargs):
        self.send_calls.append(kwargs)
        return BackendSendResult("txid", 7, self.consignment)

    def import_consignment(self, path):
        self.imported.append(path.read_bytes())
        return {4: "waitingconfirmations"}

    def close(self):
        pass


class FakeGateway:
    def __init__(self, inbound: dict[FrameKind, bytes] | None = None) -> None:
        self.inbound = inbound or {}
        self.staged = []
        self.next_session = 0x12345678

    def stage(self, kind, path):
        self.staged.append((kind, path.read_bytes()))
        return self.next_session

    def receive(self, kind, output):
        payload = self.inbound[kind]
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(payload)
        return self.next_session, len(payload)


def settings(tmp_path: Path, role: BillRole) -> RgbSettings:
    return RgbSettings(
        role=role,
        data_dir=tmp_path / f"bill-{role.value.lower()}",
        peer_data_dir=tmp_path / f"bill-{'b' if role is BillRole.A else 'a'}",
        inbox_dir=tmp_path / f"inbox-{role.value.lower()}",
        electrum_url="https://mutinynet.com/api",
    )


def flow(tmp_path: Path, role: BillRole, gateway: FakeGateway):
    backend = FakeBackend(tmp_path)
    adapter = RgbBillAdapter(settings(tmp_path, role), backend, clock=lambda: 1000)
    return (
        TapWalletFlow(
            adapter,
            gateway,
            store=TapArtifactStore(tmp_path / f"artifacts-{role.value.lower()}"),
        ),
        backend,
    )


def test_bill_b_stages_exact_native_invoice_bytes(tmp_path):
    gateway = FakeGateway()
    tap, _backend = flow(tmp_path, BillRole.B, gateway)

    result = tap.create_and_stage_invoice(
        asset_id="rgb:usdt", expires_in_seconds=900
    )

    assert gateway.staged == [(FrameKind.INVOICE, b"rgb:invoice")]
    assert result.staged.artifact.path.read_bytes() == b"rgb:invoice"
    assert result.staged.session_id == 0x12345678


def test_bill_a_receives_invoice_confirms_once_and_stages_consignment(tmp_path):
    gateway = FakeGateway({FrameKind.INVOICE: b"rgb:invoice"})
    tap, backend = flow(tmp_path, BillRole.A, gateway)

    prepared = tap.receive_and_plan_invoice(
        expected_asset_id="rgb:usdt",
        amount=200,
        expires_in_seconds=900,
    )
    tap.adapter.confirm_transfer(prepared.plan.plan_id)
    consignment = tap.execute_confirmed_transfer(prepared.plan.plan_id)
    staged = tap.stage_consignment(consignment)

    assert prepared.received_session_id == 0x12345678
    assert prepared.plan.amount == 200
    assert len(backend.send_calls) == 1
    assert gateway.staged == [
        (FrameKind.CONSIGNMENT, b"real-rgb-consignment")
    ]
    assert staged.artifact.sha256 == consignment.sha256


def test_bill_b_receives_and_imports_exact_consignment_bytes(tmp_path):
    gateway = FakeGateway(
        {FrameKind.CONSIGNMENT: b"real-rgb-consignment"}
    )
    tap, backend = flow(tmp_path, BillRole.B, gateway)

    received = tap.receive_consignment()
    updated = tap.import_consignment(received)

    assert received.session_id == 0x12345678
    assert backend.imported == [b"real-rgb-consignment"]
    assert updated == {4: "waitingconfirmations"}
