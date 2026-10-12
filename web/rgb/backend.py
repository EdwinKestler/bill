"""Small backend surface used by the policy adapter and offline fakes."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Protocol


@dataclass(frozen=True)
class ReceiveIntent:
    invoice: str
    recipient_id: str
    expiration_timestamp: int
    batch_transfer_idx: int


@dataclass(frozen=True)
class BackendSendResult:
    txid: str
    batch_transfer_idx: int
    consignment_path: Path


@dataclass(frozen=True)
class ParsedInvoice:
    invoice: str
    recipient_id: str
    asset_id: str | None
    expiration_timestamp: int | None
    transport_endpoints: tuple[str, ...]
    unknown_query_params: Mapping[str, str]


class RgbBackend(Protocol):
    """Operations that touch one already-open rgb-lib wallet."""

    def spendable_balance(self, asset_id: str) -> int: ...

    def witness_receive(
        self,
        asset_id: str | None,
        expiration_timestamp: int,
        min_confirmations: int,
    ) -> ReceiveIntent: ...

    def parse_invoice(self, invoice: str) -> ParsedInvoice: ...

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
    ) -> BackendSendResult: ...

    def import_consignment(self, consignment_path: Path) -> Mapping[int, str]: ...

    def refresh(self) -> Mapping[int, str]: ...

    def close(self) -> None: ...
