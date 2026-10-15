from __future__ import annotations

import pytest

from scripts.note_wallet_spike import run_fake_roundtrip
from web.rgb.note_spike import (
    NOTE_AMOUNT_BASE_UNITS,
    DisposableNoteSpike,
    FakeDisposableWalletBackend,
    NoteConfirmationRequired,
    NoteSpikeError,
    NoteState,
)


ASSET_ID = "rgb:synthetic-usdt"


def _spike():
    ids = iter(("note-1", "funding-plan", "redemption-plan"))
    backend = FakeDisposableWalletBackend(asset_id=ASSET_ID)
    spike = DisposableNoteSpike(
        backend,
        asset_id=ASSET_ID,
        clock=lambda: 1_000,
        id_factory=lambda: next(ids),
    )
    return spike, backend


def test_fake_roundtrip_requires_two_exact_one_use_confirmations():
    spike, backend = _spike()
    note_invoice = spike.prepare_note()
    funding = spike.plan_funding()

    assert note_invoice.transport_endpoints == ()
    with pytest.raises(NoteConfirmationRequired, match="exact confirmation"):
        spike.execute_confirmed(funding.plan_id, "yes")
    assert backend.send_calls == []

    funding_result = spike.execute_confirmed(
        funding.plan_id,
        funding.confirmation_phrase,
    )
    assert spike.state is NoteState.ACTIVE
    assert backend.wallets[spike.note_wallet_id] == NOTE_AMOUNT_BASE_UNITS
    assert backend.import_calls[0]["consignment_sha256"] == (
        funding_result.consignment_sha256
    )
    with pytest.raises(NoteConfirmationRequired, match="already-consumed"):
        spike.execute_confirmed(funding.plan_id, funding.confirmation_phrase)

    final_invoice = spike.create_final_invoice()
    redemption = spike.plan_redemption()
    assert final_invoice.transport_endpoints == ()
    redemption_result = spike.execute_confirmed(
        redemption.plan_id,
        redemption.confirmation_phrase,
    )

    assert spike.state is NoteState.REDEEMED
    assert backend.wallets[spike.note_wallet_id] == 0
    assert backend.wallets["wallet-a"] == 45_000_000
    assert backend.wallets["wallet-b"] == 55_000_000
    assert len(backend.send_calls) == 2
    replay = spike.replay()
    assert replay == {
        "status": "BOUNCED",
        "note_id": "note-1",
        "winning_txid": redemption_result.txid,
        "new_send": False,
    }
    assert len(backend.send_calls) == 2


def test_final_recipient_is_unknown_until_note_is_active():
    spike, _backend = _spike()
    spike.prepare_note()

    with pytest.raises(NoteSpikeError, match="requires active"):
        spike.create_final_invoice()


def test_backend_failure_consumes_plan_and_enters_ambiguous_state():
    class FailingBackend(FakeDisposableWalletBackend):
        def send_oob(self, **kwargs):
            self.send_calls.append(kwargs)
            raise RuntimeError("unknown fake backend outcome")

    ids = iter(("note-1", "funding-plan"))
    backend = FailingBackend(asset_id=ASSET_ID)
    spike = DisposableNoteSpike(
        backend,
        asset_id=ASSET_ID,
        clock=lambda: 1_000,
        id_factory=lambda: next(ids),
    )
    spike.prepare_note()
    plan = spike.plan_funding()

    with pytest.raises(RuntimeError, match="unknown fake backend outcome"):
        spike.execute_confirmed(plan.plan_id, plan.confirmation_phrase)
    assert spike.state is NoteState.AMBIGUOUS
    with pytest.raises(NoteConfirmationRequired, match="already-consumed"):
        spike.execute_confirmed(plan.plan_id, plan.confirmation_phrase)
    assert len(backend.send_calls) == 1


def test_cli_fake_roundtrip_labels_synthetic_boundary(capsys):
    def confirm(prompt: str) -> str:
        return prompt.split("'")[1]

    summary = run_fake_roundtrip(asset_id=ASSET_ID, input_fn=confirm)

    assert summary["mode"] == "fake-no-wallet-no-network-no-broadcast"
    assert summary["fake_rgb_transitions"] == 2
    assert summary["replay"]["status"] == "BOUNCED"
    output = capsys.readouterr().out
    assert "fake-no-wallet-no-network-no-broadcast" in output
    assert '"transport_endpoints": []' in output
    assert "mnemonic" not in output.lower()
    assert "claim_secret" not in output.lower()
