"""Discover an RgbBill and read its dock GATT identity."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from bleak import BleakClient, BleakScanner

from .chunk_protocol import (
    DEFAULT_PAYLOAD_BYTES,
    MAX_TRANSFER_BYTES,
    ChunkProtocolError,
    ChunkTransport,
    FrameKind,
)

DEFAULT_NAME = "RgbBill"
DOCK_SERVICE = "7c3e9a10-4b1e-4c8f-9d2a-00b111d0c001"
IDENTITY = "7c3e9a10-4b1e-4c8f-9d2a-00b111d0c002"
STATUS = "7c3e9a10-4b1e-4c8f-9d2a-00b111d0c003"
DENOMINATION = "7c3e9a10-4b1e-4c8f-9d2a-00b111d0c004"
CMD = "7c3e9a10-4b1e-4c8f-9d2a-00b111d0c005"
CHUNK_IN = "7c3e9a10-4b1e-4c8f-9d2a-00b111d0c006"
CHUNK_OUT = "7c3e9a10-4b1e-4c8f-9d2a-00b111d0c007"
DIAGNOSTIC_COMMAND = b"diag:display:500:pending"
CHUNK_ECHO_COMMAND = b"diag:chunk:echo"
CHUNK_DISCARD_COMMAND = b"chunk:discard"
VALID_STATUSES = {"idle", "tap", "pending", "settled", "error"}


def _emit(message: str) -> None:
    """Print one dock event with a timezone-aware wall-clock timestamp."""
    timestamp = datetime.now().astimezone().isoformat(timespec="milliseconds")
    print(f"[{timestamp}] {message}")


class BillNotFoundError(RuntimeError):
    """Raised when the requested physical bill is not advertising."""


@dataclass(frozen=True)
class BillState:
    address: str
    identity: str
    status: str
    denomination: int


async def _discover(timeout: float):
    """Return Bleak 3.x ``(device, advertisement)`` sightings."""
    adapter = os.environ.get("BLE_ADAPTER") or None
    sightings = await BleakScanner.discover(
        timeout=timeout,
        service_uuids=[DOCK_SERVICE],
        adapter=adapter,
        return_adv=True,
    )
    if not sightings:
        sightings = await BleakScanner.discover(
            timeout=timeout, adapter=adapter, return_adv=True
        )
    return list(sightings.values())


def _matches(device, advertisement, name: str) -> bool:
    advertised = advertisement.local_name or device.name or ""
    services = {uuid.lower() for uuid in (advertisement.service_uuids or [])}
    return advertised == name or DOCK_SERVICE.lower() in services


async def _find_target(timeout: float, address: str | None = None):
    adapter = os.environ.get("BLE_ADAPTER") or None
    if address:
        return await BleakScanner.find_device_by_address(
            address, timeout=timeout, adapter=adapter
        )

    name = os.environ.get("BLE_DEVICE_NAME", DEFAULT_NAME)
    for device, advertisement in await _discover(timeout):
        if _matches(device, advertisement, name):
            return device
    return None


async def _read_text(client, uuid: str, timeout: float) -> str:
    raw = bytes(await asyncio.wait_for(client.read_gatt_char(uuid), timeout=timeout))
    return raw.decode("utf-8", errors="replace")


async def _read_state(client, timeout: float) -> tuple[str, str, str]:
    identity_value = await _read_text(client, IDENTITY, timeout)
    status_value = await _read_text(client, STATUS, timeout)
    denomination_value = await _read_text(client, DENOMINATION, timeout)
    return identity_value, status_value, denomination_value


def _validated_state(
    address: str, identity_value: str, status_value: str, denomination_value: str
) -> BillState:
    if status_value not in VALID_STATUSES:
        raise ValueError(f"bill returned invalid status {status_value!r}")
    try:
        denomination = int(denomination_value)
    except ValueError as exc:
        raise ValueError(
            f"bill returned invalid denomination {denomination_value!r}"
        ) from exc
    if denomination < 0:
        raise ValueError("bill returned a negative denomination")
    return BillState(address, identity_value, status_value, denomination)


async def read_bill_state(
    timeout: float, address: str | None = None
) -> BillState:
    """Read and validate the physical bill's frozen dock-core state."""
    target = await _find_target(timeout, address)
    if target is None:
        qualifier = f" at {address}" if address else ""
        raise BillNotFoundError(f"no RgbBill advertisement{qualifier}")
    async with BleakClient(target, timeout=timeout) as client:
        values = await _read_state(client, timeout)
    return _validated_state(target.address, *values)


async def run_display_diagnostic(
    timeout: float, address: str | None = None
) -> BillState:
    """Write the one frozen no-wallet diagnostic and verify bill state."""
    target = await _find_target(timeout, address)
    if target is None:
        qualifier = f" at {address}" if address else ""
        raise BillNotFoundError(f"no RgbBill advertisement{qualifier}")
    async with BleakClient(target, timeout=timeout) as client:
        await asyncio.wait_for(
            client.write_gatt_char(CMD, DIAGNOSTIC_COMMAND, response=True),
            timeout=timeout,
        )
        values = await _read_state(client, timeout)
    bill_state = _validated_state(target.address, *values)
    if bill_state.status != "pending" or bill_state.denomination != 500:
        raise ValueError(
            "diagnostic verification failed: "
            f"status={bill_state.status!r} denomination={bill_state.denomination!r}"
        )
    return bill_state


def _read_transfer_file(path: Path) -> bytes:
    payload = path.read_bytes()
    if not payload:
        raise ChunkProtocolError("transfer file is empty")
    if len(payload) > MAX_TRANSFER_BYTES:
        raise ChunkProtocolError(
            f"transfer exceeds the {MAX_TRANSFER_BYTES}-byte ESP32 staging limit"
        )
    return payload


async def send_chunk_file(
    timeout: float,
    address: str,
    kind: FrameKind,
    path: Path,
    *,
    payload_bytes: int = DEFAULT_PAYLOAD_BYTES,
    echo: bool = False,
) -> tuple[int, bytes | None]:
    """Send one opaque RGB artifact and optionally verify a byte-exact echo."""
    target = await _find_target(timeout, address)
    if target is None:
        raise BillNotFoundError(f"no RgbBill advertisement at {address}")
    payload = _read_transfer_file(path)
    async with BleakClient(target, timeout=timeout) as client:
        transport = ChunkTransport(
            client, CHUNK_IN, CHUNK_OUT, timeout=timeout
        )
        await transport.start()
        try:
            if echo:
                await asyncio.wait_for(
                    client.write_gatt_char(
                        CMD, CHUNK_ECHO_COMMAND, response=True
                    ),
                    timeout=timeout,
                )
            session_id = await transport.send(
                kind, payload, payload_bytes=payload_bytes
            )
            echoed = None
            if echo:
                returned_kind, returned_session, echoed = await transport.receive(
                    expected_kind=kind,
                    expected_session_id=session_id,
                )
                if returned_kind != kind or returned_session != session_id:
                    raise ChunkProtocolError("echo metadata did not match transfer")
                if echoed != payload:
                    raise ChunkProtocolError("echo payload was not byte-exact")
            return session_id, echoed
        finally:
            await transport.stop()


async def receive_chunk_file(
    timeout: float,
    address: str,
    output: Path,
    *,
    expected_kind: FrameKind | None = None,
    expected_session_id: int | None = None,
) -> tuple[FrameKind, int, int]:
    """Receive a bill-originated artifact and atomically persist it."""
    target = await _find_target(timeout, address)
    if target is None:
        raise BillNotFoundError(f"no RgbBill advertisement at {address}")
    async with BleakClient(target, timeout=timeout) as client:
        transport = ChunkTransport(
            client, CHUNK_IN, CHUNK_OUT, timeout=timeout
        )
        await transport.start()
        try:
            kind, session_id, payload = await transport.receive(
                expected_kind=expected_kind,
                expected_session_id=expected_session_id,
            )
        finally:
            await transport.stop()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.part")
    try:
        with temporary.open("wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output)
    finally:
        if temporary.exists():
            temporary.unlink()
    return kind, session_id, len(payload)


async def discard_staged_chunk(timeout: float, address: str) -> None:
    target = await _find_target(timeout, address)
    if target is None:
        raise BillNotFoundError(f"no RgbBill advertisement at {address}")
    async with BleakClient(target, timeout=timeout) as client:
        await asyncio.wait_for(
            client.write_gatt_char(CMD, CHUNK_DISCARD_COMMAND, response=True),
            timeout=timeout,
        )


async def scan(timeout: float) -> int:
    name = os.environ.get("BLE_DEVICE_NAME", DEFAULT_NAME)
    _emit(f"scanning {timeout:.0f}s for name={name!r} service={DOCK_SERVICE}")
    found = 0
    for device, advertisement in await _discover(timeout):
        if _matches(device, advertisement, name):
            found += 1
            advertised = advertisement.local_name or device.name or ""
            _emit(
                f"{device.address}  rssi={advertisement.rssi}  "
                f"name={advertised!r}"
            )
    if found == 0:
        _emit("no RgbBill advertisements")
        return 1
    return 0


async def identity(timeout: float, address: str | None = None) -> int:
    """Connect to one bill and read, but never write, its identity."""
    name = os.environ.get("BLE_DEVICE_NAME", DEFAULT_NAME)
    _emit(f"scanning {timeout:.0f}s for identity from name={name!r}")
    target = await _find_target(timeout, address)
    if target is None:
        qualifier = f" at {address}" if address else ""
        _emit(f"no RgbBill advertisement{qualifier}")
        return 1

    async with BleakClient(target, timeout=timeout) as client:
        identity_value = await _read_text(client, IDENTITY, timeout)
    _emit(f"{target.address}  identity={identity_value}")
    return 0


async def state(timeout: float, address: str | None = None) -> int:
    """Read the frozen dock core state without subscribing or writing."""
    try:
        bill_state = await read_bill_state(timeout, address)
    except (BillNotFoundError, ValueError) as exc:
        _emit(str(exc))
        return 1
    _emit(
        f"{bill_state.address}  identity={bill_state.identity}  "
        f"status={bill_state.status}  denomination={bill_state.denomination}"
    )
    return 0


async def diagnostic(timeout: float, address: str | None = None) -> int:
    """Run the fixed no-wallet $5/PENDING display diagnostic."""
    try:
        bill_state = await run_display_diagnostic(timeout, address)
    except (BillNotFoundError, ValueError) as exc:
        _emit(str(exc))
        return 1
    _emit(
        f"{bill_state.address}  diagnostic=ok  identity={bill_state.identity}  "
        f"status={bill_state.status}  denomination={bill_state.denomination}"
    )
    return 0


async def chunk_send(
    timeout: float,
    address: str,
    kind: FrameKind,
    path: Path,
    payload_bytes: int,
    *,
    echo: bool,
) -> int:
    try:
        session_id, echoed = await send_chunk_file(
            timeout,
            address,
            kind,
            path,
            payload_bytes=payload_bytes,
            echo=echo,
        )
    except (BillNotFoundError, ChunkProtocolError, OSError, asyncio.TimeoutError) as exc:
        _emit(f"chunk transfer failed: {exc}")
        return 1
    payload = path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    mode = "loopback=ok" if echoed is not None else "staged=ok"
    _emit(
        f"{address}  {mode}  kind={kind.name.lower()}  "
        f"session=0x{session_id:08x}  bytes={len(payload)}  sha256={digest}"
    )
    return 0


async def chunk_receive(
    timeout: float,
    address: str,
    output: Path,
    kind: FrameKind | None,
    session_id: int | None,
) -> int:
    try:
        actual_kind, actual_session, size = await receive_chunk_file(
            timeout,
            address,
            output,
            expected_kind=kind,
            expected_session_id=session_id,
        )
    except (BillNotFoundError, ChunkProtocolError, OSError, asyncio.TimeoutError) as exc:
        _emit(f"chunk receive failed: {exc}")
        return 1
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    _emit(
        f"{address}  received=ok  kind={actual_kind.name.lower()}  "
        f"session=0x{actual_session:08x}  bytes={size}  sha256={digest}  "
        f"output={output}"
    )
    return 0


async def chunk_discard(timeout: float, address: str) -> int:
    try:
        await discard_staged_chunk(timeout, address)
    except (BillNotFoundError, OSError, asyncio.TimeoutError) as exc:
        _emit(f"chunk discard failed: {exc}")
        return 1
    _emit(f"{address}  staged chunk discarded")
    return 0


def _frame_kind(value: str) -> FrameKind:
    try:
        return FrameKind[value.upper()]
    except KeyError as exc:
        raise argparse.ArgumentTypeError(
            "kind must be invoice or consignment"
        ) from exc


def _session_id(value: str) -> int:
    parsed = int(value, 0)
    if not 0 <= parsed <= 0xFFFFFFFF:
        raise argparse.ArgumentTypeError("session id must fit uint32")
    return parsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="RGB cash bill dock")
    sub = parser.add_subparsers(dest="cmd", required=True)
    scan_p = sub.add_parser("scan", help="list nearby RgbBill advertisements")
    scan_p.add_argument("--timeout", type=float, default=5.0)
    identity_p = sub.add_parser("identity", help="read one RgbBill identity")
    identity_p.add_argument("--timeout", type=float, default=5.0)
    identity_p.add_argument("--address", help="read only this BLE address")
    state_p = sub.add_parser("state", help="read identity, status, and denomination")
    state_p.add_argument("--timeout", type=float, default=5.0)
    state_p.add_argument("--address", help="read only this BLE address")
    diagnostic_p = sub.add_parser(
        "diagnostic", help="show the fixed $5.00 / PENDING hardware diagnostic"
    )
    diagnostic_p.add_argument("--timeout", type=float, default=5.0)
    diagnostic_p.add_argument("--address", help="target this BLE address")
    chunk_send_p = sub.add_parser(
        "chunk-send", help="stage one invoice or consignment on a bill"
    )
    chunk_send_p.add_argument("--timeout", type=float, default=8.0)
    chunk_send_p.add_argument("--address", required=True)
    chunk_send_p.add_argument(
        "--kind", choices=("invoice", "consignment"), required=True
    )
    chunk_send_p.add_argument("--input", type=Path, required=True)
    chunk_send_p.add_argument("--payload-bytes", type=int, default=DEFAULT_PAYLOAD_BYTES)
    chunk_loopback_p = sub.add_parser(
        "chunk-loopback", help="send and byte-verify the safe firmware echo"
    )
    chunk_loopback_p.add_argument("--timeout", type=float, default=8.0)
    chunk_loopback_p.add_argument("--address", required=True)
    chunk_loopback_p.add_argument(
        "--kind", choices=("invoice", "consignment"), required=True
    )
    chunk_loopback_p.add_argument("--input", type=Path, required=True)
    chunk_loopback_p.add_argument("--payload-bytes", type=int, default=DEFAULT_PAYLOAD_BYTES)
    chunk_receive_p = sub.add_parser(
        "chunk-receive", help="receive a bill-originated invoice or consignment"
    )
    chunk_receive_p.add_argument("--timeout", type=float, default=8.0)
    chunk_receive_p.add_argument("--address", required=True)
    chunk_receive_p.add_argument("--kind", choices=("invoice", "consignment"))
    chunk_receive_p.add_argument("--session", type=_session_id)
    chunk_receive_p.add_argument("--output", type=Path, required=True)
    chunk_discard_p = sub.add_parser(
        "chunk-discard", help="discard the bill's staged transport artifact"
    )
    chunk_discard_p.add_argument("--timeout", type=float, default=8.0)
    chunk_discard_p.add_argument("--address", required=True)
    args = parser.parse_args(argv)
    if args.cmd == "scan":
        return asyncio.run(scan(args.timeout))
    if args.cmd == "identity":
        return asyncio.run(identity(args.timeout, args.address))
    if args.cmd == "state":
        return asyncio.run(state(args.timeout, args.address))
    if args.cmd == "diagnostic":
        return asyncio.run(diagnostic(args.timeout, args.address))
    if args.cmd == "chunk-send":
        return asyncio.run(
            chunk_send(
                args.timeout,
                args.address,
                _frame_kind(args.kind),
                args.input,
                args.payload_bytes,
                echo=False,
            )
        )
    if args.cmd == "chunk-loopback":
        return asyncio.run(
            chunk_send(
                args.timeout,
                args.address,
                _frame_kind(args.kind),
                args.input,
                args.payload_bytes,
                echo=True,
            )
        )
    if args.cmd == "chunk-receive":
        return asyncio.run(
            chunk_receive(
                args.timeout,
                args.address,
                args.output,
                _frame_kind(args.kind) if args.kind else None,
                args.session,
            )
        )
    if args.cmd == "chunk-discard":
        return asyncio.run(chunk_discard(args.timeout, args.address))
    return 2


if __name__ == "__main__":
    sys.exit(main())
