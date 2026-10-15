"""Local web dock for the accepted isolated-wallet RGB-over-BLE flow."""

from __future__ import annotations

import json
import os
import re
import sys
import threading
from collections.abc import Callable
from functools import wraps
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, ParamSpec, TypeVar
from urllib.parse import urlparse

from web.rgb.config import BillRole
from dock.chunk_protocol import FrameKind
from web.device_registry import (
    DeviceRegistry,
    DeviceRegistryError,
    RegisteredBillGateway,
)
from web.rgb_web import RgbWebError, RgbWebService

STATIC = Path(__file__).resolve().parent / "static"
HOST = os.environ.get("DOCK_HTTP_HOST", "127.0.0.1")
PORT = int(os.environ.get("DOCK_HTTP_PORT", "8788"))
ROLE = os.environ.get("BILL_ROLE", "A").upper()
MODE = "live-rgb-tap"

_state_lock = threading.RLock()
_confirm_lock = threading.Lock()
_workflow_lock = threading.RLock()
_rgb_service: RgbWebService | None = None
_device_registry: DeviceRegistry | None = None

P = ParamSpec("P")
R = TypeVar("R")

_state: dict[str, Any] = {
    "role": ROLE,
    "identity": "bill-unprovisioned",
    "status": "starting",
    "cents": 0,
    "pending": None,
    "receipts": [],
    "recovery": None,
    "mode": MODE,
    "settlement": "not-broadcast",
    "asset_id": os.environ.get("RGB_ASSET_ID") or None,
    "asset_precision": os.environ.get("RGB_ASSET_PRECISION") or None,
    "expected_receive_cents": None,
}


def _serialized_workflow(function: Callable[P, R]) -> Callable[P, R]:
    """Keep device registration and transfer state changes in one order."""

    @wraps(function)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
        with _workflow_lock:
            return function(*args, **kwargs)

    return wrapped


def _bill() -> dict[str, Any]:
    device = _device_registry.snapshot() if _device_registry is not None else None
    with _state_lock:
        pending = _state["pending"]
        recovery = _state["recovery"]
        return {
            "role": _state["role"],
            "identity": _state["identity"],
            "status": _state["status"],
            "cents": _state["cents"],
            "pending": dict(pending) if pending is not None else None,
            "receipts": [dict(receipt) for receipt in _state["receipts"]],
            "recovery": dict(recovery) if recovery is not None else None,
            "mode": _state["mode"],
            "settlement": _state["settlement"],
            "asset_id": _state["asset_id"],
            "asset_precision": _state["asset_precision"],
            "device": device,
        }


def _service(selected: RgbWebService | None) -> RgbWebService:
    service = selected or _rgb_service
    if service is None:
        raise RgbWebError(
            "live RGB wallet service is not initialized",
            retryable=True,
            broadcast=False,
        )
    return service


def _error(exc: Exception, *, retryable: bool = True) -> dict[str, Any]:
    if isinstance(exc, RgbWebError):
        return {
            "ok": False,
            "error": str(exc),
            "retryable": exc.retryable,
            "broadcast": exc.broadcast,
            "recovery_path": (
                str(exc.recovery_path) if exc.recovery_path is not None else None
            ),
            "mode": MODE,
        }
    return {
        "ok": False,
        "error": f"{type(exc).__name__}: {exc}",
        "retryable": retryable,
        "broadcast": False,
        "mode": MODE,
    }


def _registry(selected: DeviceRegistry | None = None) -> DeviceRegistry:
    registry = selected or _device_registry
    if registry is None:
        raise DeviceRegistryError("physical bill registry is not initialized")
    return registry


def _device_error(exc: Exception) -> dict[str, Any]:
    return {
        "ok": False,
        "error": f"{type(exc).__name__}: {exc}",
        "retryable": (
            exc.retryable if isinstance(exc, DeviceRegistryError) else True
        ),
        "broadcast": False,
    }


def handle_device_scan(
    timeout: float, registry: DeviceRegistry | None = None
) -> dict[str, Any]:
    try:
        selected = _registry(registry)
        devices = selected.scan(timeout)
    except Exception as exc:
        return _device_error(exc)
    return {
        "ok": True,
        "devices": devices,
        "count": len(devices),
        "device": selected.snapshot(),
        "broadcast": False,
    }


def handle_device_connect(
    address: str | None, registry: DeviceRegistry | None = None
) -> dict[str, Any]:
    try:
        selected = _registry(registry)
        connection = selected.connect(address or None)
    except Exception as exc:
        return _device_error(exc)
    if connection["address"] == selected.active_address():
        with _state_lock:
            _state["identity"] = connection["identity"]
    return {
        "ok": True,
        "connection": connection,
        "device": selected.snapshot(),
        "broadcast": False,
    }


@_serialized_workflow
def handle_device_register(
    address: str, registry: DeviceRegistry | None = None
) -> dict[str, Any]:
    def registration_allowed() -> bool:
        with _state_lock:
            return (
                _state["pending"] is None
                and _state["recovery"] is None
                and _state["status"] in {"idle", "settled"}
            )

    try:
        selected = _registry(registry)
        snapshot = selected.register(address, guard=registration_allowed)
    except Exception as exc:
        return _device_error(exc)
    with _state_lock:
        _state["identity"] = snapshot["device"]["identity"]
    return {
        "ok": True,
        "reply": "Physical bill registered. Future BLE operations will reconnect automatically.",
        "device": snapshot,
        "broadcast": False,
    }


def _requested_cents(text: str) -> int:
    match = re.search(r"\$?\s*(\d+(?:\.\d{1,2})?)", text)
    return 500 if match is None else int(round(float(match.group(1)) * 100))


def _require_five(cents: int) -> dict[str, Any] | None:
    if cents == 500:
        return None
    return {
        "ok": False,
        "reply": "The cash-bill web flow currently supports exactly $5.00.",
        "pending": None,
        "retryable": False,
        "broadcast": False,
    }


def _inspect_registered_bill(
    registry: DeviceRegistry | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    selected = _registry(registry)
    connection = selected.connect()
    artifact = connection.get("artifact")
    if artifact is None:
        raise DeviceRegistryError(
            "bill firmware does not expose artifact inventory; flash the new protocol firmware",
            retryable=False,
        )
    return connection, artifact


def _blocked_inventory_error(artifact: dict[str, Any]) -> RgbWebError:
    kind = artifact.get("kind")
    label = "artifact"
    if kind == int(FrameKind.INVOICE):
        label = "invoice"
    elif kind == int(FrameKind.CONSIGNMENT):
        label = "consignment"
    elif kind == int(FrameKind.BEARER_NOTE):
        label = "bearer note"
    return RgbWebError(
        f"Bill storage recovery is required: a retained {label} could not be handed to the tap service. "
        "Do not create or send another artifact. Use the explicit chunk-discard recovery, then retry the retained dock action.",
        retryable=False,
        broadcast=False,
    )


@_serialized_workflow
def handle_send_usdt(
    cents: int = 500,
    service: RgbWebService | None = None,
    registry: DeviceRegistry | None = None,
) -> dict[str, Any]:
    """Inspect Bill A, then read exactly one invoice and prepare confirmation."""
    rejected = _require_five(cents)
    if rejected is not None:
        return rejected
    try:
        selected = _service(service)
        if selected.role is not BillRole.A:
            raise RgbWebError(
                "this dock is the receiver; use Receive USDT",
                retryable=False,
                broadcast=False,
            )
        _connection, artifact = _inspect_registered_bill(registry)
        if artifact["direction"] == "blocked":
            raise _blocked_inventory_error(artifact)
        if artifact["direction"] != "to-dock" or artifact["kind"] != int(
            FrameKind.INVOICE
        ):
            raise RgbWebError(
                "Bill A has no received invoice. On Bill A press once near Bill B, then try Send USDT again.",
                retryable=True,
                broadcast=False,
            )
        if artifact["denomination_cents"] != cents:
            raise RgbWebError(
                "the invoice amount on Bill A does not match $5.00",
                retryable=False,
                broadcast=False,
            )
    except Exception as exc:
        result = _error(exc)
        result["reply"] = result["error"]
        result["pending"] = None
        return result
    return handle_plan(cents, selected)


@_serialized_workflow
def handle_receive_usdt(
    cents: int = 500,
    service: RgbWebService | None = None,
    registry: DeviceRegistry | None = None,
) -> dict[str, Any]:
    """Inspect Bill B, then either stage its invoice or import its proof."""
    rejected = _require_five(cents)
    if rejected is not None:
        return rejected
    try:
        selected = _service(service)
        if selected.role is not BillRole.B:
            raise RgbWebError(
                "this dock is the sender; use Send USDT",
                retryable=False,
                broadcast=False,
            )
        _connection, artifact = _inspect_registered_bill(registry)
    except Exception as exc:
        result = _error(exc)
        result["reply"] = result["error"]
        result["pending"] = None
        return result

    direction = artifact["direction"]
    kind = artifact["kind"]
    if direction == "blocked":
        result = _error(_blocked_inventory_error(artifact))
        result["reply"] = result["error"]
        result["pending"] = None
        return result
    if direction == "empty":
        return handle_stage_invoice(cents, selected)
    if direction == "to-dock" and kind == int(FrameKind.CONSIGNMENT):
        return handle_import(selected)
    if direction == "to-peer" and kind == int(FrameKind.INVOICE):
        return {
            "ok": True,
            "reply": "Invoice is loaded on Bill B. Press Bill A once near Bill B, then use Send USDT on Dock A.",
            "pending": None,
            "broadcast": False,
            "bill": _bill(),
        }
    if direction == "to-peer" and kind == int(FrameKind.CONSIGNMENT):
        return {
            "ok": True,
            "reply": "Consignment is loaded on Bill B. Press the empty receiving bill once near it.",
            "pending": None,
            "broadcast": True,
            "bill": _bill(),
        }
    result = _error(
        RgbWebError(
            "Bill B contains an unexpected artifact; do not discard it automatically",
            retryable=False,
            broadcast=False,
        )
    )
    result["reply"] = result["error"]
    result["pending"] = None
    return result


@_serialized_workflow
def handle_stage_invoice(
    cents: int, service: RgbWebService | None = None
) -> dict[str, Any]:
    rejected = _require_five(cents)
    if rejected is not None:
        return rejected
    try:
        outcome = _service(service).stage_invoice(cents)
    except Exception as exc:
        result = _error(exc)
        result["reply"] = result["error"]
        result["pending"] = None
        return result

    receipt = {
        "action": "invoice-stage",
        "cents": cents,
        "source": MODE,
        "settlement": "not-broadcast",
        "batch_transfer_idx": outcome.batch_transfer_idx,
        "expiration_timestamp": outcome.expiration_timestamp,
        "artifact_path": str(outcome.artifact.path),
        "artifact_bytes": outcome.artifact.size,
        "artifact_sha256": outcome.artifact.sha256,
        "transport_endpoints": [],
    }
    if outcome.staged is None:
        receipt.update(
            {
                "status": "invoice-stage-recovery-required",
                "error": outcome.error,
            }
        )
        recovery = {
            "action": "retry-invoice-stage",
            "artifact_path": str(outcome.artifact.path),
            "artifact_sha256": outcome.artifact.sha256,
            "broadcast": False,
        }
        with _state_lock:
            _state["status"] = "invoice-stage-recovery-required"
            _state["recovery"] = recovery
            _state["receipts"].insert(0, receipt)
        return {
            "ok": False,
            "reply": "Invoice retained, but BLE staging failed. Retry this step.",
            "pending": None,
            "retryable": True,
            "broadcast": False,
            "recovery": recovery,
            "receipt": receipt,
        }

    receipt.update(
        {
            "status": "invoice-staged",
            "ble_session_id": f"0x{outcome.staged.session_id:08x}",
        }
    )
    with _state_lock:
        _state["status"] = "invoice-staged"
        _state["settlement"] = "not-broadcast"
        _state["recovery"] = None
        _state["expected_receive_cents"] = cents
        _state["receipts"].insert(0, receipt)
    return {
        "ok": True,
        "reply": "Real transport-free invoice staged. Tap Bill A once.",
        "pending": None,
        "broadcast": False,
        "receipt": receipt,
        "bill": _bill(),
    }


@_serialized_workflow
def handle_plan(cents: int, service: RgbWebService | None = None) -> dict[str, Any]:
    rejected = _require_five(cents)
    if rejected is not None:
        return rejected
    try:
        selected = _service(service)
        prepared = selected.plan_transfer(cents)
        balance_cents = selected.cents_from_base_units(
            prepared.plan.balance_before
        )
    except Exception as exc:
        result = _error(exc)
        result["reply"] = result["error"]
        result["pending"] = None
        return result

    plan = prepared.plan
    pending = {
        "id": plan.plan_id,
        "action": "rgb-send",
        "cents": cents,
        "ticker": "USDT",
        "asset_id": plan.asset_id,
        "recipient_id": plan.recipient_id,
        "amount_base_units": plan.amount,
        "balance_before_base_units": plan.balance_before,
        "balance_before_cents": balance_cents,
        "witness_amount_sat": plan.witness_amount_sat,
        "fee_rate_sat_vb": plan.fee_rate,
        "min_confirmations": plan.min_confirmations,
        "expiration_timestamp": plan.expiration_timestamp,
        "invoice_path": str(prepared.artifact.path),
        "invoice_sha256": prepared.artifact.sha256,
        "invoice_session_id": (
            f"0x{prepared.received_session_id:08x}"
            if prepared.received_session_id is not None
            else None
        ),
        "confirmation_phrase": f"CONFIRM {plan.plan_id}",
        "donation": True,
        "transport_endpoints": [],
        "note": (
            f"Send ${cents / 100:.2f} USDT on Mutinynet to the tapped invoice. "
            "Review the immutable plan and type its exact confirmation phrase."
        ),
    }
    with _state_lock:
        _state["pending"] = pending
        _state["status"] = "confirmation-required"
        _state["settlement"] = "not-broadcast"
        _state["recovery"] = None
    return {
        "ok": True,
        "reply": pending["note"],
        "pending": pending,
        "broadcast": False,
        "bill": _bill(),
    }


@_serialized_workflow
def handle_confirm(
    confirm_id: str,
    phrase: str,
    service: RgbWebService | None = None,
) -> dict[str, Any]:
    try:
        selected = _service(service)
    except Exception as exc:
        return _error(exc)
    with _confirm_lock:
        with _state_lock:
            pending = _state["pending"]
            if (
                pending is None
                or pending.get("action") != "rgb-send"
                or pending.get("id") != confirm_id
            ):
                return {
                    "ok": False,
                    "error": "no matching pending RGB transfer plan",
                    "retryable": False,
                    "broadcast": False,
                }
            pending = dict(pending)

        try:
            outcome = selected.confirm_and_stage(confirm_id, phrase)
        except Exception as exc:
            result = _error(exc)
            if not result["retryable"]:
                receipt = {
                    "id": confirm_id,
                    "action": "rgb-send",
                    "source": MODE,
                    "status": "send-outcome-unknown",
                    "settlement": "unknown",
                    "broadcast": result["broadcast"],
                    "error": result["error"],
                }
                with _state_lock:
                    _state["pending"] = None
                    _state["status"] = "send-outcome-unknown"
                    _state["settlement"] = "unknown"
                    _state["recovery"] = {
                        "action": "inspect-wallet-before-any-new-plan",
                        "retry_send": False,
                    }
                    _state["receipts"].insert(0, receipt)
                result["receipt"] = receipt
            return result

        artifact = outcome.consignment
        receipt = {
            "id": confirm_id,
            "action": "rgb-send",
            "cents": pending["cents"],
            "source": MODE,
            "settlement": "broadcast",
            "broadcast": True,
            "txid": artifact.txid,
            "batch_transfer_idx": artifact.batch_transfer_idx,
            "consignment_path": str(artifact.path),
            "consignment_bytes": artifact.size,
            "consignment_sha256": artifact.sha256,
            "retry_send": False,
        }
        remaining_cents = pending["balance_before_cents"] - pending["cents"]
        if outcome.staged is None:
            receipt.update(
                {
                    "status": "consignment-stage-recovery-required",
                    "error": outcome.error,
                }
            )
            recovery = {
                "action": "retry-consignment-stage",
                "endpoint": "/api/rgb/retry-stage",
                "txid": artifact.txid,
                "artifact_path": str(artifact.path),
                "artifact_sha256": artifact.sha256,
                "retry_send": False,
            }
            with _state_lock:
                _state["pending"] = None
                _state["cents"] = remaining_cents
                _state["status"] = "consignment-stage-recovery-required"
                _state["settlement"] = "broadcast"
                _state["recovery"] = recovery
                _state["receipts"].insert(0, receipt)
            return {
                "ok": True,
                "completed": False,
                "broadcast": True,
                "recovery_required": True,
                "retry_send": False,
                "receipt": receipt,
                "recovery": recovery,
                "bill": _bill(),
            }

        receipt.update(
            {
                "status": "consignment-staged",
                "ble_session_id": f"0x{outcome.staged.session_id:08x}",
            }
        )
        with _state_lock:
            _state["pending"] = None
            _state["cents"] = remaining_cents
            _state["status"] = "consignment-staged"
            _state["settlement"] = "broadcast"
            _state["recovery"] = None
            _state["receipts"].insert(0, receipt)
        return {
            "ok": True,
            "completed": True,
            "broadcast": True,
            "recovery_required": False,
            "receipt": receipt,
            "bill": _bill(),
        }


@_serialized_workflow
def handle_retry_stage(service: RgbWebService | None = None) -> dict[str, Any]:
    try:
        selected = _service(service)
        outcome = selected.retry_consignment_stage()
    except Exception as exc:
        return _error(exc)
    receipt = {
        "action": "consignment-stage-retry",
        "source": MODE,
        "settlement": "broadcast",
        "broadcast": True,
        "txid": outcome.consignment.txid,
        "consignment_path": str(outcome.consignment.path),
        "consignment_bytes": outcome.consignment.size,
        "consignment_sha256": outcome.consignment.sha256,
        "retry_send": False,
    }
    if outcome.staged is None:
        receipt.update(
            {
                "status": "consignment-stage-recovery-required",
                "error": outcome.error,
            }
        )
        return {
            "ok": False,
            "retryable": True,
            "broadcast": True,
            "retry_send": False,
            "receipt": receipt,
            "recovery": _bill()["recovery"],
        }
    receipt.update(
        {
            "status": "consignment-staged",
            "ble_session_id": f"0x{outcome.staged.session_id:08x}",
        }
    )
    with _state_lock:
        _state["status"] = "consignment-staged"
        _state["recovery"] = None
        _state["receipts"].insert(0, receipt)
    return {
        "ok": True,
        "completed": True,
        "broadcast": True,
        "retry_send": False,
        "receipt": receipt,
        "bill": _bill(),
    }


@_serialized_workflow
def handle_import(service: RgbWebService | None = None) -> dict[str, Any]:
    try:
        selected = _service(service)
        outcome = selected.receive_and_import()
    except Exception as exc:
        return _error(exc)
    receipt = {
        "action": "consignment-import",
        "source": MODE,
        "session_id": f"0x{outcome.received.session_id:08x}",
        "artifact_path": str(outcome.received.artifact.path),
        "artifact_bytes": outcome.received.artifact.size,
        "artifact_sha256": outcome.received.artifact.sha256,
    }
    if outcome.updated_transfers is None:
        receipt.update(
            {
                "status": "consignment-import-recovery-required",
                "settlement": "waiting-import",
                "error": outcome.error,
            }
        )
        recovery = {
            "action": "retry-consignment-import",
            "endpoint": "/api/rgb/import",
            "artifact_path": str(outcome.received.artifact.path),
            "artifact_sha256": outcome.received.artifact.sha256,
            "retry_send": False,
        }
        with _state_lock:
            _state["status"] = "consignment-import-recovery-required"
            _state["settlement"] = "waiting-import"
            _state["recovery"] = recovery
            _state["receipts"].insert(0, receipt)
        return {
            "ok": False,
            "retryable": True,
            "broadcast": True,
            "retry_send": False,
            "recovery": recovery,
            "receipt": receipt,
            "bill": _bill(),
        }

    updated = {str(key): value for key, value in outcome.updated_transfers.items()}
    statuses = set(updated.values())
    settlement = (
        "settled"
        if statuses and statuses <= {"settled"}
        else "waiting-confirmations"
    )
    receipt.update(
        {
            "status": "consignment-imported",
            "settlement": settlement,
            "updated_transfers": updated,
        }
    )
    with _state_lock:
        expected = _state["expected_receive_cents"]
        if expected is not None:
            _state["cents"] += expected
        _state["expected_receive_cents"] = None
        _state["status"] = "consignment-imported"
        _state["settlement"] = settlement
        _state["recovery"] = None
        _state["receipts"].insert(0, receipt)
    return {
        "ok": True,
        "broadcast": True,
        "receipt": receipt,
        "bill": _bill(),
    }


def handle_refresh(service: RgbWebService | None = None) -> dict[str, Any]:
    try:
        cents, updated_transfers = _service(service).refresh_settlement()
    except Exception as exc:
        return _error(exc)
    updated = {str(key): value for key, value in updated_transfers.items()}
    statuses = set(updated.values())
    with _state_lock:
        _state["cents"] = cents
        if any(status == "settled" for status in statuses):
            _state["status"] = "settled"
            _state["settlement"] = "settled"
        elif statuses:
            _state["status"] = "waiting-confirmations"
            _state["settlement"] = "waiting-confirmations"
        _state["receipts"].insert(
            0,
            {
                "action": "wallet-refresh",
                "source": MODE,
                "status": _state["status"],
                "settlement": _state["settlement"],
                "updated_transfers": updated,
                "cents": cents,
            },
        )
    return {
        "ok": True,
        "broadcast": False,
        "updated_transfers": updated,
        "bill": _bill(),
    }


def handle_chat(
    text: str, service: RgbWebService | None = None
) -> dict[str, Any]:
    lowered = text.strip().lower()
    try:
        selected = _service(service)
    except Exception as exc:
        result = _error(exc)
        return {"reply": result["error"], "pending": None, **result}

    if selected.role is BillRole.B and any(
        word in lowered for word in ("import", "consignment", "settle")
    ):
        result = handle_import(selected)
        result.setdefault(
            "reply",
            (
                "Consignment imported; waiting for Mutinynet confirmation."
                if result["ok"]
                else result.get("error", "Consignment import needs recovery.")
            ),
        )
        result.setdefault("pending", None)
        return result
    if selected.role is BillRole.A and "retry" in lowered and "stage" in lowered:
        result = handle_retry_stage(selected)
        result.setdefault(
            "reply",
            (
                "Retained consignment staged without another send."
                if result["ok"]
                else "Consignment remains retained; BLE staging still failed."
            ),
        )
        result.setdefault("pending", None)
        return result
    if any(word in lowered for word in ("bill", "print", "dollar", "receive")):
        cents = _requested_cents(lowered)
        if selected.role is BillRole.B:
            return handle_stage_invoice(cents, selected)
        return handle_plan(cents, selected)
    if any(word in lowered for word in ("status", "worth", "balance")):
        refreshed = handle_refresh(selected)
        if not refreshed["ok"]:
            refreshed.setdefault("reply", refreshed["error"])
            refreshed.setdefault("pending", None)
            return refreshed
        bill = refreshed["bill"]
        return {
            "ok": True,
            "reply": (
                f"Bill {bill['role']} shows ${bill['cents'] / 100:.2f} "
                f"({bill['status']}, {bill['settlement']})."
            ),
            "pending": None,
        }
    instruction = (
        "Say ‘prepare bill for $5’ or ‘import consignment’."
        if selected.role is BillRole.B
        else "Tap the prepared bill, then say ‘bill for $5’."
    )
    return {"ok": True, "reply": instruction, "pending": _bill()["pending"]}


@_serialized_workflow
def handle_cancel(confirm_id: str) -> dict[str, Any]:
    with _state_lock:
        pending = _state["pending"]
        if pending is None or pending.get("id") != confirm_id:
            return {
                "ok": False,
                "error": "no matching pending RGB transfer plan",
                "broadcast": False,
                "retryable": False,
            }
        _state["pending"] = None
        _state["status"] = "idle"
        _state["settlement"] = "not-broadcast"
    return {"ok": True, "broadcast": False, "bill": _bill()}


def _status_code(result: dict[str, Any]) -> int:
    if result.get("ok"):
        return 202 if result.get("recovery_required") else 200
    if result.get("retryable"):
        return 503
    return 409


def _startup_error_message(exc: Exception) -> str:
    detail = f"{type(exc).__name__}: {exc}"
    lowered = detail.lower()
    if "429" in lowered or "too many requests" in lowered:
        return (
            "Mutinynet indexer rate limit (HTTP 429); stop both dock startup "
            "attempts, wait, then start the roles sequentially"
        )
    if "timedout" in lowered or "timed out" in lowered:
        return "Mutinynet indexer timed out; wait and retry this dock"
    return detail


class DockHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(STATIC), **kwargs)

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stdout.write("[dock] " + (fmt % args) + "\n")

    def _json(self, code: int, payload: dict[str, Any]) -> None:
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/api/health":
            self._json(
                200,
                {
                    "ok": _rgb_service is not None,
                    "role": _state["role"],
                    "bind": f"{HOST}:{PORT}",
                    "mode": MODE,
                    "settlement": _state["settlement"],
                    "device": (
                        _device_registry.snapshot()
                        if _device_registry is not None
                        else None
                    ),
                },
            )
            return
        if path == "/api/device":
            try:
                self._json(200, {"ok": True, "device": _registry().snapshot()})
            except Exception as exc:
                result = _device_error(exc)
                self._json(_status_code(result), result)
            return
        if path == "/api/bill":
            self._json(200, _bill())
            return
        if path == "/":
            self.path = "/index.html"
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            body = self._read_json()
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
            self._json(400, {"ok": False, "error": "invalid json"})
            return
        if path == "/api/chat":
            result = handle_chat(str(body.get("text") or ""))
            self._json(_status_code(result), result)
            return
        if path == "/api/workflow/send":
            try:
                cents = int(body.get("cents", 500))
            except (TypeError, ValueError):
                self._json(400, {"ok": False, "error": "cents must be an integer"})
                return
            result = handle_send_usdt(cents)
            self._json(_status_code(result), result)
            return
        if path == "/api/workflow/receive":
            try:
                cents = int(body.get("cents", 500))
            except (TypeError, ValueError):
                self._json(400, {"ok": False, "error": "cents must be an integer"})
                return
            result = handle_receive_usdt(cents)
            self._json(_status_code(result), result)
            return
        if path == "/api/device/scan":
            try:
                timeout = float(body.get("timeout", 5))
            except (TypeError, ValueError):
                self._json(400, {"ok": False, "error": "timeout must be numeric"})
                return
            result = handle_device_scan(timeout)
            self._json(_status_code(result), result)
            return
        if path == "/api/device/connect":
            result = handle_device_connect(str(body.get("address") or "") or None)
            self._json(_status_code(result), result)
            return
        if path == "/api/device/register":
            result = handle_device_register(str(body.get("address") or ""))
            self._json(_status_code(result), result)
            return
        if path in {"/api/confirm", "/api/rgb/confirm"}:
            result = handle_confirm(
                str(body.get("id") or ""),
                str(body.get("phrase") or ""),
            )
            self._json(_status_code(result), result)
            return
        if path == "/api/cancel":
            result = handle_cancel(str(body.get("id") or ""))
            self._json(_status_code(result), result)
            return
        if path == "/api/rgb/invoice":
            try:
                cents = int(body.get("cents", 500))
            except (TypeError, ValueError):
                self._json(400, {"ok": False, "error": "cents must be an integer"})
                return
            result = handle_stage_invoice(cents)
            self._json(_status_code(result), result)
            return
        if path == "/api/rgb/plan":
            try:
                cents = int(body.get("cents", 500))
            except (TypeError, ValueError):
                self._json(400, {"ok": False, "error": "cents must be an integer"})
                return
            result = handle_plan(cents)
            self._json(_status_code(result), result)
            return
        if path == "/api/rgb/import":
            result = handle_import()
            self._json(_status_code(result), result)
            return
        if path == "/api/rgb/refresh":
            result = handle_refresh()
            self._json(_status_code(result), result)
            return
        if path == "/api/rgb/retry-stage":
            result = handle_retry_stage()
            self._json(_status_code(result), result)
            return
        self._json(404, {"ok": False, "error": "not found"})


def main() -> None:
    global _device_registry, _rgb_service
    service: RgbWebService | None = None
    try:
        role = BillRole.parse(ROLE)
        registry = DeviceRegistry.from_env(role)
        gateway = RegisteredBillGateway(registry, timeout=registry.timeout)
        service = RgbWebService.from_env(gateway=gateway)
        balance_cents = service.spendable_cents()
    except KeyboardInterrupt:
        if service is not None:
            service.close()
        print("bill web dock startup cancelled", file=sys.stderr)
        return
    except Exception as exc:
        if service is not None:
            service.close()
        print(
            "live RGB web dock failed to initialize: "
            f"{_startup_error_message(exc)}",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc
    _device_registry = registry
    _rgb_service = service
    registered_device = registry.snapshot()["device"]
    with _state_lock:
        _state.update(
            {
                "role": service.role.value,
                "status": "idle",
                "cents": balance_cents,
                "mode": MODE,
                "settlement": "settled",
                "asset_id": service.asset_id,
                "asset_precision": service.asset_precision,
                "identity": (
                    registered_device["identity"]
                    if registered_device is not None
                    else "bill-unregistered"
                ),
            }
        )
    try:
        server = ThreadingHTTPServer((HOST, PORT), DockHandler)
    except Exception:
        service.close()
        _rgb_service = None
        _device_registry = None
        raise
    print(
        f"bill web dock on http://{HOST}:{PORT}/  "
        f"role={service.role.value} mode={MODE}"
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("bill web dock stopped")
    finally:
        server.server_close()
        service.close()
        _rgb_service = None
        _device_registry = None


if __name__ == "__main__":
    main()
