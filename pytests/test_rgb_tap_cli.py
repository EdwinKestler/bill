from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.rgb_tap import _send_from_tap
from web.rgb.config import BillRole
from web.rgb.tap_flow import TapFlowError


class FakeFlow:
    def __init__(self, tmp_path: Path, *, stage_fails: bool = False) -> None:
        self.adapter = SimpleNamespace(
            settings=SimpleNamespace(role=BillRole.A),
            confirm_transfer=self._confirm,
        )
        self.confirmed = []
        self.executed = []
        self.stage_fails = stage_fails
        invoice = tmp_path / "invoice.rgb-invoice"
        invoice.write_bytes(b"rgb:invoice")
        self.prepared = SimpleNamespace(
            artifact=SimpleNamespace(path=invoice, sha256="invoice-hash"),
            received_session_id=0x12345678,
            plan=SimpleNamespace(
                plan_id="plan-123",
                asset_id="rgb:usdt",
                recipient_id="recipient",
                amount=200,
                balance_before=500,
                witness_amount_sat=1000,
                fee_rate=2,
                min_confirmations=1,
                expiration_timestamp=1900,
            ),
        )
        consignment = tmp_path / "consignment.rgbc"
        consignment.write_bytes(b"real-consignment")
        self.consignment = SimpleNamespace(
            txid="txid",
            batch_transfer_idx=7,
            path=consignment,
            size=len(b"real-consignment"),
            sha256="consignment-hash",
        )

    def receive_and_plan_invoice(self, **_kwargs):
        return self.prepared

    def _confirm(self, plan_id):
        self.confirmed.append(plan_id)

    def execute_confirmed_transfer(self, plan_id):
        self.executed.append(plan_id)
        return self.consignment

    def stage_consignment(self, _consignment):
        if self.stage_fails:
            raise RuntimeError("BLE unavailable")
        return SimpleNamespace(
            session_id=0x87654321,
            artifact=SimpleNamespace(size=16, sha256="consignment-hash"),
        )


def args() -> Namespace:
    return Namespace(
        address="30:AE:A4:4C:B1:6A",
        asset_id="rgb:usdt",
        amount=200,
        expires_seconds=900,
        invoice_file=None,
    )


def test_send_from_tap_mismatched_confirmation_never_broadcasts(
    tmp_path, monkeypatch
):
    flow = FakeFlow(tmp_path)
    monkeypatch.setattr("builtins.input", lambda _prompt: "no")

    with pytest.raises(TapFlowError, match="nothing was sent"):
        _send_from_tap(args(), flow)

    assert flow.confirmed == []
    assert flow.executed == []


def test_send_from_tap_reports_recovery_without_repeating_send(
    tmp_path, monkeypatch, capsys
):
    flow = FakeFlow(tmp_path, stage_fails=True)
    monkeypatch.setattr(
        "builtins.input", lambda _prompt: "CONFIRM plan-123"
    )

    with pytest.raises(SystemExit) as exc_info:
        _send_from_tap(args(), flow)

    assert exc_info.value.code == 2
    assert flow.confirmed == ["plan-123"]
    assert flow.executed == ["plan-123"]
    output = capsys.readouterr().out
    assert '"phase": "broadcast-complete"' in output
    assert '"phase": "consignment-stage-failed-after-broadcast"' in output
    assert '"retry_send": false' in output
    assert "dock.bill_dock chunk-send" in output
