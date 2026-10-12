"""Role and confirmation policy around one RGB wallet backend."""

from __future__ import annotations

import hashlib
import os
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

from .backend import BackendSendResult, ParsedInvoice, ReceiveIntent, RgbBackend
from .config import BillRole, RgbSettings


class AdapterError(RuntimeError):
    """The adapter rejected or could not complete an operation."""


class RoleViolation(AdapterError):
    """The active bill role is not allowed to perform this operation."""


class ConfirmationRequired(AdapterError):
    """A spend was attempted without its one-use confirmation."""


@dataclass(frozen=True)
class TransferPlan:
    plan_id: str
    asset_id: str
    recipient_id: str
    amount: int
    balance_before: int
    witness_amount_sat: int
    fee_rate: int
    min_confirmations: int
    expiration_timestamp: int


@dataclass(frozen=True)
class ConsignmentArtifact:
    txid: str
    batch_transfer_idx: int
    path: Path
    size: int
    sha256: str


@dataclass
class _PlanState:
    plan: TransferPlan
    confirmed: bool = False
    consumed: bool = False


class RgbBillAdapter:
    """One-process policy adapter; never owns a second wallet."""

    def __init__(
        self,
        settings: RgbSettings,
        backend: RgbBackend,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.settings = settings
        self._backend = backend
        self._clock = clock
        self._plans: dict[str, _PlanState] = {}
        self._lock = threading.RLock()

    def create_receive_intent(
        self,
        *,
        asset_id: str | None,
        expires_in_seconds: int = 900,
    ) -> ReceiveIntent:
        if self.settings.role is not BillRole.B:
            raise RoleViolation("only Bill B may create the tap receive invoice")
        if expires_in_seconds < 60:
            raise AdapterError("receive intent lifetime must be at least 60 seconds")
        expiration = int(self._clock()) + expires_in_seconds
        return self._backend.witness_receive(
            asset_id,
            expiration,
            self.settings.min_confirmations,
        )

    def plan_whole_balance_transfer(
        self,
        *,
        asset_id: str,
        recipient_id: str,
        expires_in_seconds: int = 900,
    ) -> TransferPlan:
        return self.plan_transfer(
            asset_id=asset_id,
            recipient_id=recipient_id,
            amount=None,
            expires_in_seconds=expires_in_seconds,
        )

    def spendable_balance(self, asset_id: str) -> int:
        """Return the active wallet's spendable balance for one exact asset."""
        if not asset_id:
            raise AdapterError("asset_id is required")
        return self._backend.spendable_balance(asset_id)

    def parse_tap_invoice(
        self, payload: bytes, *, expected_asset_id: str
    ) -> ParsedInvoice:
        """Validate exact BLE bytes as a transport-free Mutinynet invoice."""
        if self.settings.role is not BillRole.A:
            raise RoleViolation("only Bill A may consume the tap receive invoice")
        if not payload:
            raise AdapterError("empty invoice payload")
        try:
            invoice = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise AdapterError("invoice payload is not valid UTF-8") from exc
        if invoice != invoice.strip() or not invoice:
            raise AdapterError("invoice payload must contain one exact invoice string")
        parsed = self._backend.parse_invoice(invoice)
        if parsed.invoice != invoice:
            raise AdapterError("RGB invoice did not round-trip canonically")
        if parsed.transport_endpoints:
            raise AdapterError("tap invoice must have empty transport endpoints")
        if parsed.unknown_query_params:
            raise AdapterError("tap invoice contains unsupported query parameters")
        if parsed.asset_id != expected_asset_id:
            raise AdapterError("tap invoice asset does not match the selected asset")
        if (
            parsed.expiration_timestamp is None
            or parsed.expiration_timestamp <= int(self._clock())
        ):
            raise AdapterError("tap invoice is expired or has no expiration")
        return parsed

    def plan_transfer_from_tap_invoice(
        self,
        payload: bytes,
        *,
        expected_asset_id: str,
        amount: int | None,
        expires_in_seconds: int = 900,
    ) -> tuple[ParsedInvoice, TransferPlan]:
        parsed = self.parse_tap_invoice(
            payload, expected_asset_id=expected_asset_id
        )
        remaining = parsed.expiration_timestamp - int(self._clock())
        plan_lifetime = min(expires_in_seconds, remaining)
        if plan_lifetime < 60:
            raise AdapterError("tap invoice expires too soon for a confirmed send")
        plan = self.plan_transfer(
            asset_id=expected_asset_id,
            recipient_id=parsed.recipient_id,
            amount=amount,
            expires_in_seconds=plan_lifetime,
        )
        return parsed, plan

    def plan_transfer(
        self,
        *,
        asset_id: str,
        recipient_id: str,
        amount: int | None,
        expires_in_seconds: int = 900,
    ) -> TransferPlan:
        if self.settings.role is not BillRole.A:
            raise RoleViolation("only Bill A may plan a tap transfer")
        if not asset_id or not recipient_id:
            raise AdapterError("asset_id and recipient_id are required")
        if expires_in_seconds < 60:
            raise AdapterError("transfer lifetime must be at least 60 seconds")
        balance = self._backend.spendable_balance(asset_id)
        if balance <= 0:
            raise AdapterError("the active bill has no spendable balance for this asset")
        transfer_amount = balance if amount is None else amount
        if transfer_amount <= 0:
            raise AdapterError("transfer amount must be positive")
        if transfer_amount > balance:
            raise AdapterError("transfer amount exceeds the spendable balance")
        plan = TransferPlan(
            plan_id=str(uuid.uuid4()),
            asset_id=asset_id,
            recipient_id=recipient_id,
            amount=transfer_amount,
            balance_before=balance,
            witness_amount_sat=self.settings.witness_amount_sat,
            fee_rate=self.settings.fee_rate,
            min_confirmations=self.settings.min_confirmations,
            expiration_timestamp=int(self._clock()) + expires_in_seconds,
        )
        with self._lock:
            self._plans[plan.plan_id] = _PlanState(plan=plan)
        return plan

    def confirm_transfer(self, plan_id: str) -> TransferPlan:
        """Mark a displayed plan confirmed; this method itself never spends."""
        with self._lock:
            state = self._plans.get(plan_id)
            if state is None or state.consumed:
                raise ConfirmationRequired("unknown or already-consumed transfer plan")
            if state.plan.expiration_timestamp <= int(self._clock()):
                state.consumed = True
                raise ConfirmationRequired("transfer plan expired before confirmation")
            state.confirmed = True
            return state.plan

    def execute_confirmed_transfer(self, plan_id: str) -> ConsignmentArtifact:
        """Consume one confirmation and perform a donation send exactly once."""
        with self._lock:
            state = self._plans.get(plan_id)
            if state is None or not state.confirmed or state.consumed:
                raise ConfirmationRequired("a fresh explicit confirmation is required")
            if state.plan.expiration_timestamp <= int(self._clock()):
                state.consumed = True
                raise ConfirmationRequired("confirmed transfer plan has expired")
            state.consumed = True
            plan = state.plan

        current_balance = self._backend.spendable_balance(plan.asset_id)
        if current_balance != plan.balance_before:
            raise ConfirmationRequired(
                "spendable balance changed; review and confirm a new transfer plan"
            )
        result = self._backend.send_donation(
            asset_id=plan.asset_id,
            recipient_id=plan.recipient_id,
            amount=plan.amount,
            witness_amount_sat=plan.witness_amount_sat,
            fee_rate=plan.fee_rate,
            min_confirmations=plan.min_confirmations,
            expiration_timestamp=plan.expiration_timestamp,
        )
        return self._artifact(result)

    def import_consignment(self, payload: bytes) -> Mapping[int, str]:
        """Persist bytes received over BLE and validate them with Bill B's wallet."""
        if self.settings.role is not BillRole.B:
            raise RoleViolation("only Bill B may import the tap consignment")
        if not payload:
            raise AdapterError("empty consignment payload")
        if len(payload) > self.settings.max_consignment_bytes:
            raise AdapterError("consignment payload exceeds configured limit")
        digest = hashlib.sha256(payload).hexdigest()
        self.settings.inbox_dir.mkdir(parents=True, exist_ok=True)
        destination = self.settings.inbox_dir / f"{digest}.rgbc"
        if destination.exists():
            try:
                existing = destination.read_bytes()
            except OSError as exc:
                raise AdapterError("cannot verify existing consignment artifact") from exc
            if existing != payload:
                raise AdapterError("content-addressed consignment artifact was modified")
        else:
            fd, temporary = tempfile.mkstemp(
                dir=self.settings.inbox_dir,
                prefix=".incoming-",
                suffix=".rgbc",
            )
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, destination)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        return self._backend.import_consignment(destination)

    def refresh_transfers(self) -> Mapping[int, str]:
        """Refresh this process's wallet without opening a second owner."""
        return self._backend.refresh()

    def close(self) -> None:
        self._backend.close()

    def _artifact(self, result: BackendSendResult) -> ConsignmentArtifact:
        path = result.consignment_path.resolve()
        try:
            payload = path.read_bytes()
        except OSError as exc:
            raise AdapterError("rgb-lib did not expose a readable consignment") from exc
        if not payload:
            raise AdapterError("rgb-lib produced an empty consignment")
        if len(payload) > self.settings.max_consignment_bytes:
            raise AdapterError("generated consignment exceeds configured limit")
        return ConsignmentArtifact(
            txid=result.txid,
            batch_transfer_idx=result.batch_transfer_idx,
            path=path,
            size=len(payload),
            sha256=hashlib.sha256(payload).hexdigest(),
        )
