"""Run the network-free M1 disposable RGB note-wallet experiment."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from typing import Callable

from web.rgb.note_spike import (
    NOTE_AMOUNT_BASE_UNITS,
    DisposableNoteSpike,
    FakeDisposableWalletBackend,
    FakeTransitionResult,
    NoteSpikeError,
    NoteTransferPlan,
)


DEFAULT_FAKE_ASSET_ID = "rgb:synthetic-usdt"


def _emit(value: dict[str, object]) -> None:
    print(json.dumps(value, indent=2))


def _plan_payload(plan: NoteTransferPlan) -> dict[str, object]:
    payload = asdict(plan)
    payload["kind"] = plan.kind.value
    payload["confirmation_required"] = plan.confirmation_phrase
    return payload


def _result_payload(result: FakeTransitionResult) -> dict[str, object]:
    return {
        "txid": result.txid,
        "consignment_bytes": len(result.consignment),
        "consignment_sha256": result.consignment_sha256,
    }


def run_fake_roundtrip(
    *,
    asset_id: str = DEFAULT_FAKE_ASSET_ID,
    input_fn: Callable[[str], str] = input,
) -> dict[str, object]:
    backend = FakeDisposableWalletBackend(asset_id=asset_id)
    spike = DisposableNoteSpike(backend, asset_id=asset_id)

    note_invoice = spike.prepare_note()
    _emit(
        {
            "mode": "fake-no-wallet-no-network-no-broadcast",
            "phase": "note-prepared",
            "note_id": spike.note_id,
            "invoice_sha256": note_invoice.sha256,
            "transport_endpoints": list(note_invoice.transport_endpoints),
            "amount_base_units": NOTE_AMOUNT_BASE_UNITS,
        }
    )
    funding_plan = spike.plan_funding()
    _emit({"phase": "funding-confirmation-required", "plan": _plan_payload(funding_plan)})
    funding_phrase = input_fn(
        f"Type exactly '{funding_plan.confirmation_phrase}' to execute the fake funding: "
    )
    funding = spike.execute_confirmed(funding_plan.plan_id, funding_phrase)
    _emit({"phase": "fake-funding-complete", **_result_payload(funding)})

    final_invoice = spike.create_final_invoice()
    _emit(
        {
            "phase": "final-invoice-created-after-activation",
            "invoice_sha256": final_invoice.sha256,
            "transport_endpoints": list(final_invoice.transport_endpoints),
        }
    )
    redemption_plan = spike.plan_redemption()
    _emit(
        {
            "phase": "redemption-confirmation-required",
            "plan": _plan_payload(redemption_plan),
        }
    )
    redemption_phrase = input_fn(
        f"Type exactly '{redemption_plan.confirmation_phrase}' to execute the fake redemption: "
    )
    redemption = spike.execute_confirmed(
        redemption_plan.plan_id,
        redemption_phrase,
    )
    _emit({"phase": "fake-redemption-complete", **_result_payload(redemption)})

    replay = spike.replay()
    summary = {
        "mode": "fake-no-wallet-no-network-no-broadcast",
        "phase": "fake-roundtrip-complete",
        "state": spike.state.value,
        "fake_rgb_transitions": len(backend.send_calls),
        "funding_txid": funding.txid,
        "redemption_txid": redemption.txid,
        "replay": replay,
        "wallet_balances": dict(backend.wallets),
    }
    _emit(summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="M1 fake disposable-wallet round trip; never opens rgb-lib"
    )
    parser.add_argument("command", choices=["fake-roundtrip"])
    parser.add_argument("--asset-id", default=DEFAULT_FAKE_ASSET_ID)
    args = parser.parse_args()
    try:
        run_fake_roundtrip(asset_id=args.asset_id)
    except NoteSpikeError as exc:
        print(f"note spike failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
