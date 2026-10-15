"""Discover, verify, and persist one physical bill for a dock role."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import threading
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterator

from dock.bill_dock import (
    DOCK_SERVICE,
    BillCandidate,
    BillState,
    discover_bill_candidates,
    read_bill_state,
)
from dock.chunk_protocol import FrameKind
from web.rgb.config import BillRole
from web.rgb.tap_flow import BillChunkGateway, TapFlowError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REGISTRATION_VERSION = 1


class DeviceRegistryError(RuntimeError):
    """A device picker operation failed without touching a wallet."""

    def __init__(self, message: str, *, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable


@dataclass(frozen=True)
class RegisteredBill:
    address: str
    name: str
    identity: str
    service_uuid: str
    role: str
    registered_at: str


class DeviceRegistry:
    """Own one saved physical bill and serialize access to the BLE adapter."""

    def __init__(
        self,
        role: BillRole,
        path: Path,
        *,
        fallback_address: str = "",
        timeout: float = 8.0,
        discoverer: Callable[[float], Awaitable[list[BillCandidate]]] = (
            discover_bill_candidates
        ),
        reader: Callable[[float, str | None], Awaitable[BillState]] = read_bill_state,
    ) -> None:
        self.role = role
        self.path = path.resolve()
        self.fallback_address = fallback_address.strip()
        self.timeout = timeout
        self._discoverer = discoverer
        self._reader = reader
        self._state_lock = threading.RLock()
        self._ble_lock = threading.RLock()
        self._candidates: dict[str, BillCandidate] = {}
        self._registered = self._load()
        self._connection: dict[str, Any] | None = None

    @classmethod
    def from_env(cls, role: BillRole) -> DeviceRegistry:
        configured_path = os.environ.get("BLE_REGISTRATION_FILE", "").strip()
        path = (
            Path(configured_path).expanduser()
            if configured_path
            else PROJECT_ROOT / f".dock-registration-{role.value.lower()}.json"
        )
        try:
            timeout = float(os.environ.get("BLE_TIMEOUT_SECONDS", "8"))
        except ValueError as exc:
            raise DeviceRegistryError("BLE_TIMEOUT_SECONDS must be numeric") from exc
        if timeout <= 0:
            raise DeviceRegistryError("BLE_TIMEOUT_SECONDS must be positive")
        return cls(
            role,
            path,
            fallback_address=os.environ.get("BLE_DEVICE_ADDRESS", ""),
            timeout=timeout,
        )

    def _load(self) -> RegisteredBill | None:
        if not self.path.exists():
            return None
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if payload.get("version") != REGISTRATION_VERSION:
                raise ValueError("unsupported registration version")
            record = RegisteredBill(
                address=str(payload["address"]),
                name=str(payload["name"]),
                identity=str(payload["identity"]),
                service_uuid=str(payload["service_uuid"]).lower(),
                role=str(payload["role"]),
                registered_at=str(payload["registered_at"]),
            )
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise DeviceRegistryError(
                "saved bill registration is invalid; remove it and register again",
                retryable=False,
            ) from exc
        if record.role != self.role.value or record.service_uuid != DOCK_SERVICE:
            raise DeviceRegistryError(
                "saved bill registration does not match this dock role or service",
                retryable=False,
            )
        return record

    def active_address(self) -> str | None:
        with self._state_lock:
            if self._registered is not None:
                return self._registered.address
            return self.fallback_address or None

    def require_address(self) -> str:
        address = self.active_address()
        if address is None:
            raise TapFlowError(
                "no physical bill is registered; scan and register one in the dock"
            )
        return address

    @contextmanager
    def address_lease(self) -> Iterator[str]:
        """Serialize a complete scan/read/chunk operation on the BLE adapter."""
        with self._ble_lock:
            yield self.require_address()

    def scan(self, timeout: float) -> list[dict[str, Any]]:
        if not 1 <= timeout <= 15:
            raise DeviceRegistryError("scan timeout must be between 1 and 15 seconds")
        try:
            with self._ble_lock:
                candidates = asyncio.run(self._discoverer(timeout))
        except Exception as exc:
            raise DeviceRegistryError(
                f"BLE scan failed: {type(exc).__name__}: {exc}"
            ) from exc
        with self._state_lock:
            self._candidates = {candidate.address: candidate for candidate in candidates}
            registered_address = (
                self._registered.address if self._registered is not None else None
            )
        return [
            {
                **asdict(candidate),
                "registered": candidate.address == registered_address,
            }
            for candidate in candidates
        ]

    def _allowed_address(self, address: str | None) -> tuple[str, BillCandidate | None]:
        selected = (address or self.active_address() or "").strip()
        if not selected:
            raise DeviceRegistryError("select a discovered bill first")
        with self._state_lock:
            candidate = self._candidates.get(selected)
            active = self.active_address()
        if candidate is None and selected != active:
            raise DeviceRegistryError(
                "selected bill was not found in the latest authorized scan",
                retryable=False,
            )
        return selected, candidate

    def connect(self, address: str | None = None) -> dict[str, Any]:
        with self._ble_lock:
            selected, candidate = self._allowed_address(address)
            return self._connect_unlocked(selected, candidate)

    def _connect_unlocked(
        self, selected: str, candidate: BillCandidate | None
    ) -> dict[str, Any]:
        try:
            bill = asyncio.run(self._reader(self.timeout, selected))
        except Exception as exc:
            connection = {
                "connected": False,
                "address": selected,
                "error": f"{type(exc).__name__}: {exc}",
            }
            with self._state_lock:
                self._connection = connection
            raise DeviceRegistryError(
                f"unable to verify bill: {type(exc).__name__}: {exc}"
            ) from exc
        connection = {
            "connected": True,
            "address": bill.address,
            "name": candidate.name if candidate is not None else self._active_name(),
            "identity": bill.identity,
            "status": bill.status,
            "denomination": bill.denomination,
            "artifact": asdict(bill.artifact) if bill.artifact is not None else None,
            "service_uuid": DOCK_SERVICE,
            "connection_mode": "on-demand",
            "verified_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        with self._state_lock:
            self._connection = connection
        return dict(connection)

    def _active_name(self) -> str:
        with self._state_lock:
            if self._registered is not None:
                return self._registered.name
        return os.environ.get("BLE_DEVICE_NAME", "RgbBill")

    def register(
        self,
        address: str,
        *,
        guard: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        with self._ble_lock:
            if guard is not None and not guard():
                raise DeviceRegistryError(
                    "finish or recover the current transfer before changing bills",
                    retryable=False,
                )
            selected, candidate = self._allowed_address(address)
            if candidate is None:
                raise DeviceRegistryError(
                    "scan and select the bill before registering it",
                    retryable=False,
                )
            connection = self._connect_unlocked(selected, candidate)
            record = RegisteredBill(
                address=selected,
                name=candidate.name,
                identity=str(connection["identity"]),
                service_uuid=DOCK_SERVICE,
                role=self.role.value,
                registered_at=datetime.now(timezone.utc).isoformat(
                    timespec="seconds"
                ),
            )
            self._save(record)
            with self._state_lock:
                self._registered = record
                self._connection = {**connection, "registered": True}
        return self.snapshot()

    def _save(self, record: RegisteredBill) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": REGISTRATION_VERSION, **asdict(record)}
        descriptor, temporary = tempfile.mkstemp(
            dir=self.path.parent,
            prefix=f".{self.path.name}.",
            suffix=".tmp",
            text=True,
        )
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            os.chmod(self.path, 0o600)
        finally:
            Path(temporary).unlink(missing_ok=True)

    def snapshot(self) -> dict[str, Any]:
        with self._state_lock:
            registered = asdict(self._registered) if self._registered else None
            connection = dict(self._connection) if self._connection else None
            active = self.active_address()
        return {
            "role": self.role.value,
            "registered": registered is not None,
            "source": "registered" if registered else "environment" if active else None,
            "active_address": active,
            "device": registered,
            "connection": connection,
            "service_uuid": DOCK_SERVICE,
            "connection_mode": "on-demand",
        }


class RegisteredBillGateway:
    """Resolve the current saved bill immediately before every BLE transfer."""

    def __init__(self, registry: DeviceRegistry, *, timeout: float) -> None:
        self.registry = registry
        self.timeout = timeout

    def stage(
        self, kind: FrameKind, path: Path, denomination_cents: int = 0
    ) -> int:
        with self.registry.address_lease() as address:
            return BillChunkGateway(address, timeout=self.timeout).stage(
                kind, path, denomination_cents
            )

    def receive(self, kind: FrameKind, output: Path) -> tuple[int, int]:
        with self.registry.address_lease() as address:
            return BillChunkGateway(address, timeout=self.timeout).receive(kind, output)
