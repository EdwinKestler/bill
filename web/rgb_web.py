"""Long-lived, role-scoped RGB wallet service for the local web dock."""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from dock.chunk_protocol import MAX_TRANSFER_BYTES
from web.rgb.adapter import ConsignmentArtifact
from web.rgb.backend import ReceiveIntent
from web.rgb.config import BillRole, RgbSettings, SettingsError
from web.rgb.runtime import open_adapter
from web.rgb.tap_flow import (
    BillChunkGateway,
    InvoiceTransferPlan,
    ReceivedArtifact,
    StagedArtifact,
    StoredArtifact,
    TapWalletFlow,
)


class RgbWebError(RuntimeError):
    """A web operation stopped at a known broadcast/retry boundary."""

    def __init__(
        self,
        message: str,
        *,
        retryable: bool,
        broadcast: bool | None,
        recovery_path: Path | None = None,
    ) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.broadcast = broadcast
        self.recovery_path = recovery_path


@dataclass(frozen=True)
class InvoiceStageOutcome:
    cents: int
    artifact: StoredArtifact
    expiration_timestamp: int
    batch_transfer_idx: int
    staged: StagedArtifact | None
    error: str | None = None


@dataclass(frozen=True)
class SendStageOutcome:
    consignment: ConsignmentArtifact
    staged: StagedArtifact | None
    error: str | None = None


@dataclass(frozen=True)
class ImportOutcome:
    received: ReceivedArtifact
    updated_transfers: Mapping[int, str] | None
    error: str | None = None


class RgbWebService:
    """Own one wallet process and preserve exact-artifact recovery state."""

    def __init__(
        self,
        flow: TapWalletFlow,
        *,
        asset_id: str,
        asset_precision: int,
    ) -> None:
        if not asset_id.strip():
            raise SettingsError("RGB_ASSET_ID is required for the live web dock")
        if not 0 <= asset_precision <= 18:
            raise SettingsError("RGB_ASSET_PRECISION must be between 0 and 18")
        self.flow = flow
        self.asset_id = asset_id
        self.asset_precision = asset_precision
        self.role = flow.adapter.settings.role
        self._lock = threading.RLock()
        self._pending_invoice: tuple[int, ReceiveIntent, StoredArtifact] | None = None
        self._pending_consignment: ConsignmentArtifact | None = None
        self._pending_import: ReceivedArtifact | None = None

    @classmethod
    def from_env(cls) -> RgbWebService:
        settings = RgbSettings.from_env(require_credentials=True)
        if settings.max_consignment_bytes > MAX_TRANSFER_BYTES:
            raise SettingsError(
                "RGB_MAX_CONSIGNMENT_BYTES must be at most "
                f"{MAX_TRANSFER_BYTES} for the physical BLE path"
            )
        asset_id = os.environ.get("RGB_ASSET_ID", "").strip()
        try:
            precision = int(os.environ.get("RGB_ASSET_PRECISION", ""))
        except ValueError as exc:
            raise SettingsError("RGB_ASSET_PRECISION must be an integer") from exc
        address = os.environ.get("BLE_DEVICE_ADDRESS", "").strip()
        if not address:
            raise SettingsError("BLE_DEVICE_ADDRESS is required for the live web dock")
        try:
            timeout = float(os.environ.get("BLE_TIMEOUT_SECONDS", "8"))
        except ValueError as exc:
            raise SettingsError("BLE_TIMEOUT_SECONDS must be numeric") from exc
        if timeout <= 0:
            raise SettingsError("BLE_TIMEOUT_SECONDS must be positive")
        gateway = BillChunkGateway(address, timeout=timeout)
        adapter = open_adapter(settings)
        try:
            return cls(
                TapWalletFlow(adapter, gateway),
                asset_id=asset_id,
                asset_precision=precision,
            )
        except Exception:
            adapter.close()
            raise

    def amount_base_units(self, cents: int) -> int:
        if cents <= 0:
            raise RgbWebError(
                "amount must be positive",
                retryable=True,
                broadcast=False,
            )
        numerator = cents * (10**self.asset_precision)
        amount, remainder = divmod(numerator, 100)
        if remainder:
            raise RgbWebError(
                "amount cannot be represented at the configured asset precision",
                retryable=True,
                broadcast=False,
            )
        return amount

    def cents_from_base_units(self, amount: int) -> int:
        cents, remainder = divmod(amount * 100, 10**self.asset_precision)
        if remainder:
            raise RgbWebError(
                "wallet balance cannot be represented as whole cents",
                retryable=False,
                broadcast=False,
            )
        return cents

    def spendable_cents(self) -> int:
        with self._lock:
            balance = self.flow.adapter.spendable_balance(self.asset_id)
        return self.cents_from_base_units(balance)

    def stage_invoice(
        self, cents: int, *, expires_in_seconds: int = 3600
    ) -> InvoiceStageOutcome:
        if self.role is not BillRole.B:
            raise RgbWebError(
                "only Bill B may stage a receive invoice",
                retryable=False,
                broadcast=False,
            )
        self.amount_base_units(cents)
        with self._lock:
            if self._pending_invoice is None:
                intent, artifact = self.flow.create_invoice_artifact(
                    asset_id=self.asset_id,
                    expires_in_seconds=expires_in_seconds,
                )
                self._pending_invoice = (cents, intent, artifact)
            pending_cents, intent, artifact = self._pending_invoice
            if pending_cents != cents:
                raise RgbWebError(
                    "a different receive invoice is already awaiting BLE staging",
                    retryable=False,
                    broadcast=False,
                    recovery_path=artifact.path,
                )
            try:
                staged = self.flow.stage_artifact(artifact)
            except Exception as exc:
                return InvoiceStageOutcome(
                    cents,
                    artifact,
                    intent.expiration_timestamp,
                    intent.batch_transfer_idx,
                    None,
                    f"{type(exc).__name__}: {exc}",
                )
            self._pending_invoice = None
            return InvoiceStageOutcome(
                cents,
                artifact,
                intent.expiration_timestamp,
                intent.batch_transfer_idx,
                staged,
            )

    def plan_transfer(
        self, cents: int, *, expires_in_seconds: int = 900
    ) -> InvoiceTransferPlan:
        if self.role is not BillRole.A:
            raise RgbWebError(
                "only Bill A may prepare a send plan",
                retryable=False,
                broadcast=False,
            )
        amount = self.amount_base_units(cents)
        with self._lock:
            return self.flow.receive_and_plan_invoice(
                expected_asset_id=self.asset_id,
                amount=amount,
                expires_in_seconds=expires_in_seconds,
            )

    def confirm_and_stage(self, plan_id: str, phrase: str) -> SendStageOutcome:
        if self.role is not BillRole.A:
            raise RgbWebError(
                "only Bill A may confirm a send",
                retryable=False,
                broadcast=False,
            )
        expected = f"CONFIRM {plan_id}"
        if phrase != expected:
            raise RgbWebError(
                "confirmation phrase did not match; nothing was sent",
                retryable=True,
                broadcast=False,
            )
        with self._lock:
            try:
                self.flow.adapter.confirm_transfer(plan_id)
                consignment = self.flow.execute_confirmed_transfer(plan_id)
            except Exception as exc:
                raise RgbWebError(
                    "send failed or has an unknown broadcast outcome; "
                    "do not confirm or send this plan again: "
                    f"{type(exc).__name__}: {exc}",
                    retryable=False,
                    broadcast=None,
                ) from exc
            self._pending_consignment = consignment
            return self._stage_pending_consignment()

    def retry_consignment_stage(self) -> SendStageOutcome:
        if self.role is not BillRole.A:
            raise RgbWebError(
                "only Bill A may stage a retained consignment",
                retryable=False,
                broadcast=False,
            )
        with self._lock:
            if self._pending_consignment is None:
                raise RgbWebError(
                    "there is no retained consignment to stage",
                    retryable=False,
                    broadcast=False,
                )
            return self._stage_pending_consignment()

    def _stage_pending_consignment(self) -> SendStageOutcome:
        consignment = self._pending_consignment
        if consignment is None:
            raise RgbWebError(
                "there is no retained consignment to stage",
                retryable=False,
                broadcast=False,
            )
        try:
            staged = self.flow.stage_consignment(consignment)
        except Exception as exc:
            return SendStageOutcome(
                consignment,
                None,
                f"{type(exc).__name__}: {exc}",
            )
        self._pending_consignment = None
        return SendStageOutcome(consignment, staged)

    def receive_and_import(self) -> ImportOutcome:
        if self.role is not BillRole.B:
            raise RgbWebError(
                "only Bill B may receive a consignment",
                retryable=False,
                broadcast=False,
            )
        with self._lock:
            if self._pending_import is None:
                self._pending_import = self.flow.receive_consignment()
            received = self._pending_import
            try:
                updated = self.flow.import_consignment(received)
            except Exception as exc:
                return ImportOutcome(
                    received,
                    None,
                    f"{type(exc).__name__}: {exc}",
                )
            self._pending_import = None
            return ImportOutcome(received, updated)

    def refresh_settlement(self) -> tuple[int, Mapping[int, str]]:
        with self._lock:
            updated = self.flow.adapter.refresh_transfers()
            balance = self.flow.adapter.spendable_balance(self.asset_id)
        return self.cents_from_base_units(balance), updated

    def close(self) -> None:
        self.flow.adapter.close()
