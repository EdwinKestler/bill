"""Pinned rgb-lib 0.3.0b7 bridge. Importing this module does not open a wallet."""

from __future__ import annotations

import importlib
import importlib.metadata
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping

from .backend import BackendSendResult, ParsedInvoice, ReceiveIntent
from .config import RgbSettings, SettingsError
from .lock import WalletProcessLock


class RgbLibUnavailable(RuntimeError):
    """The pinned native wheel is missing or does not match the expected API."""


def _enum_name(value: object) -> str:
    name = getattr(value, "name", None)
    if isinstance(name, str):
        return name.lower()
    return str(value).split(".")[-1].lower()


class RgbLibBackend:
    """Own one native wallet, one Online handle, and its process lock."""

    def __init__(
        self,
        *,
        rgb_lib: ModuleType,
        wallet: Any,
        online: Any,
        process_lock: WalletProcessLock,
    ) -> None:
        self._rgb = rgb_lib
        self._wallet = wallet
        self._online = online
        self._process_lock = process_lock

    @classmethod
    def open(cls, settings: RgbSettings) -> RgbLibBackend:
        backend = cls.load_offline(settings)
        try:
            online_options = backend._rgb.OnlineOptions(
                indexer_url=settings.electrum_url,
                skip_consistency_check=False,
                vanilla_sync_lookback=20,
            )
            backend._online = backend._wallet.go_online(online_options)
        except Exception:
            backend.close()
            raise
        return backend

    @classmethod
    def load_offline(cls, settings: RgbSettings) -> RgbLibBackend:
        """Load one locked wallet without contacting an indexer."""

        if settings.master_fingerprint is None:
            raise SettingsError("active bill master fingerprint is not configured")
        mnemonic = settings.read_mnemonic()
        try:
            rgb_lib = importlib.import_module("rgb_lib")
        except ImportError as exc:
            raise RgbLibUnavailable(
                "install the pinned wheel with: .venv/bin/pip install -r requirements-rgb.txt"
            ) from exc
        try:
            installed_version = importlib.metadata.version("rgb-lib")
        except importlib.metadata.PackageNotFoundError as exc:
            raise RgbLibUnavailable("cannot verify installed rgb-lib version") from exc
        if installed_version != "0.3.0b7":
            raise RgbLibUnavailable(
                f"rgb-lib 0.3.0b7 is required; found {installed_version}"
            )

        process_lock = WalletProcessLock(settings.data_dir)
        process_lock.acquire()
        try:
            wallet = rgb_lib.Wallet.load(
                str(settings.data_dir),
                settings.master_fingerprint,
                mnemonic,
            )
            wallet_data = wallet.get_wallet_data()
            if wallet_data.bitcoin_network != rgb_lib.BitcoinNetwork.SIGNET_CUSTOM:
                raise RgbLibUnavailable("wallet network is not Mutinynet/custom signet")
        except Exception:
            process_lock.release()
            raise
        return cls(
            rgb_lib=rgb_lib,
            wallet=wallet,
            online=None,
            process_lock=process_lock,
        )

    def spendable_balance(self, asset_id: str) -> int:
        return int(self._wallet.get_asset_balance(asset_id).spendable)

    def witness_receive(
        self,
        asset_id: str | None,
        expiration_timestamp: int,
        min_confirmations: int,
    ) -> ReceiveIntent:
        data = self._wallet.witness_receive(
            asset_id,
            self._rgb.Assignment.ANY(),
            expiration_timestamp,
            [],
            min_confirmations,
        )
        return ReceiveIntent(
            invoice=data.invoice,
            recipient_id=data.recipient_id,
            expiration_timestamp=int(data.expiration_timestamp),
            batch_transfer_idx=int(data.batch_transfer_idx),
        )

    def parse_invoice(self, invoice: str) -> ParsedInvoice:
        try:
            parsed = self._rgb.Invoice(invoice)
            data = parsed.invoice_data()
        except Exception as exc:
            raise RgbLibUnavailable("received payload is not a valid RGB invoice") from exc
        if data.network != self._rgb.BitcoinNetwork.SIGNET_CUSTOM:
            raise RgbLibUnavailable("received RGB invoice is not Mutinynet/custom signet")
        return ParsedInvoice(
            invoice=parsed.invoice_string(),
            recipient_id=data.recipient_id,
            asset_id=data.asset_id,
            expiration_timestamp=(
                int(data.expiration_timestamp)
                if data.expiration_timestamp is not None
                else None
            ),
            transport_endpoints=tuple(data.transport_endpoints),
            unknown_query_params=dict(data.unknown_query_params),
        )

    def send_donation(
        self,
        *,
        asset_id: str,
        recipient_id: str,
        amount: int,
        witness_amount_sat: int,
        fee_rate: int,
        min_confirmations: int,
        expiration_timestamp: int,
    ) -> BackendSendResult:
        recipient = self._rgb.Recipient(
            recipient_id=recipient_id,
            witness_data=self._rgb.WitnessData(
                amount_sat=witness_amount_sat,
                blinding=None,
            ),
            assignment=self._rgb.Assignment.FUNGIBLE(amount),
            transport_endpoints=[],
        )
        result = self._wallet.send(
            self._online,
            {asset_id: [recipient]},
            True,
            fee_rate,
            min_confirmations,
            expiration_timestamp,
        )
        transfers = self._wallet.list_transfers(asset_id)
        paths = {
            Path(transfer.consignment_path)
            for transfer in transfers
            if transfer.txid == result.txid
            and transfer.consignment_path
            and _enum_name(transfer.kind) == "send"
        }
        if len(paths) != 1:
            raise RgbLibUnavailable(
                "rgb-lib did not return exactly one send consignment path"
            )
        return BackendSendResult(
            txid=result.txid,
            batch_transfer_idx=int(result.batch_transfer_idx),
            consignment_path=paths.pop(),
        )

    def import_consignment(self, consignment_path: Path) -> Mapping[int, str]:
        refreshed = self._wallet.provide_out_of_band_consignment(
            self._online,
            str(consignment_path),
            [],
        )
        return {
            int(batch_idx): _enum_name(value.updated_status)
            for batch_idx, value in refreshed.items()
        }

    def refresh(self) -> Mapping[int, str]:
        refreshed = self._wallet.refresh(self._online, None, [], False)
        return {
            int(batch_idx): _enum_name(value.updated_status)
            for batch_idx, value in refreshed.items()
            if value.updated_status is not None
        }

    def close(self) -> None:
        self._wallet = None
        self._online = None
        self._process_lock.release()
