"""Role-scoped wallet-to-BLE artifact handoff for the live tap flow."""

from __future__ import annotations

import asyncio
import hashlib
import os
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Protocol

from dock.bill_dock import receive_chunk_file, send_chunk_file
from dock.chunk_protocol import FrameKind, MAX_TRANSFER_BYTES

from .adapter import ConsignmentArtifact, RgbBillAdapter, TransferPlan
from .backend import ParsedInvoice, ReceiveIntent


class TapFlowError(RuntimeError):
    """The live wallet-to-BLE handoff could not safely continue."""


@dataclass(frozen=True)
class StoredArtifact:
    kind: FrameKind
    path: Path
    size: int
    sha256: str


@dataclass(frozen=True)
class StagedArtifact:
    artifact: StoredArtifact
    session_id: int


@dataclass(frozen=True)
class ReceivedArtifact:
    artifact: StoredArtifact
    session_id: int


@dataclass(frozen=True)
class StagedInvoice:
    intent: ReceiveIntent
    staged: StagedArtifact


@dataclass(frozen=True)
class InvoiceTransferPlan:
    invoice: ParsedInvoice
    artifact: StoredArtifact
    received_session_id: int | None
    plan: TransferPlan


class ChunkGateway(Protocol):
    def stage(self, kind: FrameKind, path: Path) -> int: ...

    def receive(self, kind: FrameKind, output: Path) -> tuple[int, int]: ...


class BillChunkGateway:
    """Synchronous boundary around the accepted Bleak chunk transport."""

    def __init__(self, address: str, *, timeout: float = 8.0) -> None:
        if not address.strip():
            raise TapFlowError("a physical bill BLE address is required")
        self.address = address
        self.timeout = timeout

    def stage(self, kind: FrameKind, path: Path) -> int:
        session_id, _echoed = asyncio.run(
            send_chunk_file(
                self.timeout,
                self.address,
                kind,
                path,
                echo=False,
            )
        )
        return session_id

    def receive(self, kind: FrameKind, output: Path) -> tuple[int, int]:
        actual_kind, session_id, size = asyncio.run(
            receive_chunk_file(
                self.timeout,
                self.address,
                output,
                expected_kind=kind,
            )
        )
        if actual_kind != kind:
            raise TapFlowError("received BLE artifact kind changed unexpectedly")
        return session_id, size


class TapArtifactStore:
    """Content-addressed, crash-safe storage outside either wallet datadir."""

    _SUFFIX = {
        FrameKind.INVOICE: ".rgb-invoice",
        FrameKind.CONSIGNMENT: ".rgbc",
    }

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def persist(self, kind: FrameKind, payload: bytes) -> StoredArtifact:
        if kind not in self._SUFFIX:
            raise TapFlowError("only invoice and consignment artifacts are supported")
        if not payload:
            raise TapFlowError("cannot persist an empty tap artifact")
        if len(payload) > MAX_TRANSFER_BYTES:
            raise TapFlowError(
                f"tap artifact exceeds the {MAX_TRANSFER_BYTES}-byte BLE limit"
            )
        digest = hashlib.sha256(payload).hexdigest()
        directory = self.root / kind.name.lower()
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(directory, 0o700)
        destination = directory / f"{digest}{self._SUFFIX[kind]}"
        if destination.exists():
            if destination.read_bytes() != payload:
                raise TapFlowError("content-addressed tap artifact was modified")
        else:
            descriptor, temporary = tempfile.mkstemp(
                dir=directory,
                prefix=".incoming-",
                suffix=self._SUFFIX[kind],
            )
            try:
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, destination)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        return StoredArtifact(kind, destination, len(payload), digest)

    def load(self, kind: FrameKind, path: Path) -> StoredArtifact:
        try:
            payload = path.resolve().read_bytes()
        except OSError as exc:
            raise TapFlowError("unable to read tap artifact") from exc
        return self.persist(kind, payload)

    def incoming_path(self, kind: FrameKind) -> Path:
        directory = self.root / ".received"
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(directory, 0o700)
        return directory / f"{uuid.uuid4()}{self._SUFFIX[kind]}"


class TapWalletFlow:
    """Compose one role's wallet policy with one attached physical bill."""

    def __init__(
        self,
        adapter: RgbBillAdapter,
        gateway: ChunkGateway,
        *,
        store: TapArtifactStore | None = None,
    ) -> None:
        self.adapter = adapter
        self.gateway = gateway
        self.store = store or TapArtifactStore(
            adapter.settings.inbox_dir / "tap-artifacts"
        )

    def create_invoice_artifact(
        self, *, asset_id: str, expires_in_seconds: int
    ) -> tuple[ReceiveIntent, StoredArtifact]:
        intent = self.adapter.create_receive_intent(
            asset_id=asset_id,
            expires_in_seconds=expires_in_seconds,
        )
        artifact = self.store.persist(
            FrameKind.INVOICE, intent.invoice.encode("utf-8")
        )
        return intent, artifact

    def stage_artifact(self, artifact: StoredArtifact) -> StagedArtifact:
        session_id = self.gateway.stage(artifact.kind, artifact.path)
        return StagedArtifact(artifact, session_id)

    def create_and_stage_invoice(
        self, *, asset_id: str, expires_in_seconds: int
    ) -> StagedInvoice:
        intent, artifact = self.create_invoice_artifact(
            asset_id=asset_id,
            expires_in_seconds=expires_in_seconds,
        )
        staged = self.stage_artifact(artifact)
        return StagedInvoice(intent, staged)

    def receive_and_plan_invoice(
        self,
        *,
        expected_asset_id: str,
        amount: int | None,
        expires_in_seconds: int,
        invoice_path: Path | None = None,
    ) -> InvoiceTransferPlan:
        received_session_id: int | None = None
        if invoice_path is None:
            incoming = self.store.incoming_path(FrameKind.INVOICE)
            received_session_id, _size = self.gateway.receive(
                FrameKind.INVOICE, incoming
            )
            try:
                artifact = self.store.load(FrameKind.INVOICE, incoming)
            finally:
                incoming.unlink(missing_ok=True)
        else:
            artifact = self.store.load(FrameKind.INVOICE, invoice_path)
        parsed, plan = self.adapter.plan_transfer_from_tap_invoice(
            artifact.path.read_bytes(),
            expected_asset_id=expected_asset_id,
            amount=amount,
            expires_in_seconds=expires_in_seconds,
        )
        return InvoiceTransferPlan(
            parsed,
            artifact,
            received_session_id,
            plan,
        )

    def execute_confirmed_transfer(self, plan_id: str) -> ConsignmentArtifact:
        return self.adapter.execute_confirmed_transfer(plan_id)

    def stage_consignment(self, artifact: ConsignmentArtifact) -> StagedArtifact:
        stored = self.store.load(FrameKind.CONSIGNMENT, artifact.path)
        if stored.size != artifact.size or stored.sha256 != artifact.sha256:
            raise TapFlowError("generated consignment changed before BLE staging")
        return self.stage_artifact(stored)

    def receive_consignment(self) -> ReceivedArtifact:
        incoming = self.store.incoming_path(FrameKind.CONSIGNMENT)
        session_id, _size = self.gateway.receive(FrameKind.CONSIGNMENT, incoming)
        try:
            artifact = self.store.load(FrameKind.CONSIGNMENT, incoming)
        finally:
            incoming.unlink(missing_ok=True)
        return ReceivedArtifact(artifact, session_id)

    def import_consignment(self, received: ReceivedArtifact) -> Mapping[int, str]:
        return self.adapter.import_consignment(received.artifact.path.read_bytes())
