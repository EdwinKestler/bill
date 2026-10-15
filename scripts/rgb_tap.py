"""Operator CLI for the live isolated-wallet RGB-over-BLE tap flow."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from dock.chunk_protocol import MAX_TRANSFER_BYTES
from web.rgb.config import RgbSettings, SettingsError
from web.rgb.runtime import open_adapter
from web.rgb.tap_flow import BillChunkGateway, TapFlowError, TapWalletFlow


def _record(phase: str, **values: Any) -> None:
    print(
        json.dumps(
            {
                "timestamp": datetime.now().astimezone().isoformat(
                    timespec="milliseconds"
                ),
                "phase": phase,
                **values,
            },
            indent=2,
        ),
        flush=True,
    )


def _address(value: str | None) -> str:
    selected = value or os.environ.get("BLE_DEVICE_ADDRESS", "")
    if not selected.strip():
        raise TapFlowError("--address or BLE_DEVICE_ADDRESS is required")
    return selected


def _flow(settings: RgbSettings, address: str, timeout: float) -> TapWalletFlow:
    if settings.max_consignment_bytes > MAX_TRANSFER_BYTES:
        raise SettingsError(
            "RGB_MAX_CONSIGNMENT_BYTES must be at most "
            f"{MAX_TRANSFER_BYTES} for the physical BLE path"
        )
    return TapWalletFlow(
        open_adapter(settings),
        BillChunkGateway(address, timeout=timeout),
    )


def _stage_invoice(args: argparse.Namespace, flow: TapWalletFlow) -> None:
    intent, artifact = flow.create_invoice_artifact(
        asset_id=args.asset_id,
        expires_in_seconds=args.expires_seconds,
    )
    _record(
        "invoice-created",
        role=flow.adapter.settings.role.value,
        asset_id=args.asset_id,
        expiration_timestamp=intent.expiration_timestamp,
        batch_transfer_idx=intent.batch_transfer_idx,
        transport_endpoints=[],
        artifact_path=str(artifact.path),
        artifact_bytes=artifact.size,
        artifact_sha256=artifact.sha256,
    )
    staged = flow.stage_artifact(artifact, args.denomination_cents)
    _record(
        "invoice-staged",
        ble_address=args.address,
        session_id=f"0x{staged.session_id:08x}",
        artifact_bytes=staged.artifact.size,
        artifact_sha256=staged.artifact.sha256,
    )


def _send_from_tap(args: argparse.Namespace, flow: TapWalletFlow) -> None:
    prepared = flow.receive_and_plan_invoice(
        expected_asset_id=args.asset_id,
        amount=args.amount,
        expires_in_seconds=args.expires_seconds,
        invoice_path=args.invoice_file,
    )
    plan = prepared.plan
    _record(
        "confirmation-required",
        role=flow.adapter.settings.role.value,
        invoice_path=str(prepared.artifact.path),
        invoice_sha256=prepared.artifact.sha256,
        invoice_session_id=(
            f"0x{prepared.received_session_id:08x}"
            if prepared.received_session_id is not None
            else None
        ),
        plan_id=plan.plan_id,
        asset_id=plan.asset_id,
        recipient_id=plan.recipient_id,
        transfer_amount_base_units=plan.amount,
        spendable_balance_before=plan.balance_before,
        witness_amount_sat=plan.witness_amount_sat,
        fee_rate_sat_vb=plan.fee_rate,
        min_confirmations=plan.min_confirmations,
        expiration_timestamp=plan.expiration_timestamp,
        donation=True,
        transport_endpoints=[],
        warning="confirmation will broadcast on Mutinynet",
    )
    expected = f"CONFIRM {plan.plan_id}"
    entered = input(f"Type exactly '{expected}' to broadcast: ")
    if entered != expected:
        raise TapFlowError(
            "confirmation did not match; nothing was sent; "
            f"invoice retained at {prepared.artifact.path}"
        )
    flow.adapter.confirm_transfer(plan.plan_id)
    consignment = flow.execute_confirmed_transfer(plan.plan_id)
    _record(
        "broadcast-complete",
        broadcast=True,
        txid=consignment.txid,
        batch_transfer_idx=consignment.batch_transfer_idx,
        consignment_path=str(consignment.path),
        consignment_bytes=consignment.size,
        consignment_sha256=consignment.sha256,
        warning="do not repeat the send if BLE staging fails",
    )
    try:
        staged = flow.stage_consignment(consignment, args.denomination_cents)
    except Exception as exc:
        recovery = shlex.join(
            [
                ".venv/bin/python",
                "-m",
                "dock.bill_dock",
                "chunk-send",
                "--address",
                args.address,
                "--kind",
                "consignment",
                "--input",
                str(consignment.path),
                "--denomination-cents",
                str(args.denomination_cents),
            ]
        )
        _record(
            "consignment-stage-failed-after-broadcast",
            txid=consignment.txid,
            error=f"{type(exc).__name__}: {exc}",
            consignment_path=str(consignment.path),
            consignment_sha256=consignment.sha256,
            recovery_command=recovery,
            retry_send=False,
        )
        raise SystemExit(2) from exc
    _record(
        "consignment-staged",
        txid=consignment.txid,
        ble_address=args.address,
        session_id=f"0x{staged.session_id:08x}",
        artifact_bytes=staged.artifact.size,
        artifact_sha256=staged.artifact.sha256,
    )


def _import_from_tap(args: argparse.Namespace, flow: TapWalletFlow) -> None:
    received = flow.receive_consignment()
    _record(
        "consignment-received",
        role=flow.adapter.settings.role.value,
        ble_address=args.address,
        session_id=f"0x{received.session_id:08x}",
        artifact_path=str(received.artifact.path),
        artifact_bytes=received.artifact.size,
        artifact_sha256=received.artifact.sha256,
    )
    try:
        updated = flow.import_consignment(received)
    except Exception as exc:
        _record(
            "consignment-import-failed",
            error=f"{type(exc).__name__}: {exc}",
            artifact_path=str(received.artifact.path),
            recovery_command=shlex.join(
                [
                    ".venv/bin/python",
                    "-m",
                    "scripts.rgb_wallet",
                    "import-consignment",
                    str(received.artifact.path),
                ]
            ),
        )
        raise SystemExit(3) from exc
    _record(
        "consignment-imported",
        updated_transfers={str(key): value for key, value in updated.items()},
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mutinynet RGB wallet artifacts over the accepted bill tap"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_ble_arguments(command: argparse.ArgumentParser) -> None:
        command.add_argument(
            "--address", help="BLE address of this dock's physical bill"
        )
        command.add_argument("--timeout", type=float, default=8.0)

    stage_invoice = subparsers.add_parser(
        "stage-invoice", help="Bill B: create and stage a real witness invoice"
    )
    add_ble_arguments(stage_invoice)
    stage_invoice.add_argument("--asset-id", required=True)
    stage_invoice.add_argument("--expires-seconds", type=int, default=3600)
    stage_invoice.add_argument("--denomination-cents", type=int, default=500)

    send = subparsers.add_parser(
        "send-from-tap",
        help="Bill A: receive/validate invoice, confirm send, and stage consignment",
    )
    add_ble_arguments(send)
    send.add_argument("--asset-id", required=True)
    send.add_argument("--amount", type=int)
    send.add_argument("--denomination-cents", type=int, default=500)
    send.add_argument("--expires-seconds", type=int, default=900)
    send.add_argument(
        "--invoice-file",
        type=Path,
        help="retry planning from a retained invoice without another tap",
    )

    import_from_tap = subparsers.add_parser(
        "import-from-tap",
        help="Bill B: receive and import the exact OOB consignment",
    )
    add_ble_arguments(import_from_tap)
    args = parser.parse_args()
    try:
        args.address = _address(args.address)
        settings = RgbSettings.from_env(require_credentials=True)
        flow = _flow(settings, args.address, args.timeout)
        try:
            if args.command == "stage-invoice":
                _stage_invoice(args, flow)
            elif args.command == "send-from-tap":
                _send_from_tap(args, flow)
            else:
                _import_from_tap(args, flow)
        finally:
            flow.adapter.close()
    except SystemExit:
        raise
    except Exception as exc:
        print(
            f"tap wallet command failed: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
