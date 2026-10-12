"""Binary frame codec and reliable stop-and-wait BLE chunk transport."""

from __future__ import annotations

import asyncio
import secrets
import struct
import zlib
from dataclasses import dataclass
from enum import IntEnum

VERSION = 0x01
MAX_PAYLOAD_BYTES = 200
DEFAULT_PAYLOAD_BYTES = 180
MAX_TRANSFER_BYTES = 640 * 1024
HEADER = struct.Struct("<BBIHHH")
CRC = struct.Struct("<I")
MAX_FRAME_BYTES = HEADER.size + MAX_PAYLOAD_BYTES + CRC.size


class FrameKind(IntEnum):
    INVOICE = 0x01
    CONSIGNMENT = 0x02
    ACK = 0x03


class AckStatus(IntEnum):
    OK = 0x00
    MALFORMED = 0x01
    UNSUPPORTED = 0x02
    CRC_MISMATCH = 0x03
    SESSION_MISMATCH = 0x04
    SEQUENCE_MISMATCH = 0x05
    TOTAL_MISMATCH = 0x06
    TOO_LARGE = 0x07
    STORAGE_FAILURE = 0x08
    BUSY = 0x09


class ChunkProtocolError(RuntimeError):
    """A frame or transfer violated the frozen chunk-v1 contract."""

    def __init__(self, message: str, status: AckStatus = AckStatus.MALFORMED):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class ChunkFrame:
    kind: FrameKind
    session_id: int
    sequence: int
    total: int
    payload: bytes
    version: int = VERSION


def encode_frame(frame: ChunkFrame) -> bytes:
    if frame.version != VERSION:
        raise ChunkProtocolError("unsupported frame version", AckStatus.UNSUPPORTED)
    if not 0 <= frame.session_id <= 0xFFFFFFFF:
        raise ChunkProtocolError("session id is outside uint32")
    if not 0 <= frame.sequence <= 0xFFFF or not 0 <= frame.total <= 0xFFFF:
        raise ChunkProtocolError("sequence or total is outside uint16")
    if len(frame.payload) > MAX_PAYLOAD_BYTES:
        raise ChunkProtocolError("frame payload exceeds 200 bytes")
    header = HEADER.pack(
        frame.version,
        int(frame.kind),
        frame.session_id,
        frame.sequence,
        frame.total,
        len(frame.payload),
    )
    body = header + frame.payload
    return body + CRC.pack(zlib.crc32(body) & 0xFFFFFFFF)


def decode_frame(encoded: bytes | bytearray | memoryview) -> ChunkFrame:
    raw = bytes(encoded)
    if len(raw) < HEADER.size + CRC.size:
        raise ChunkProtocolError("frame is shorter than the fixed envelope")
    version, raw_kind, session_id, sequence, total, payload_length = HEADER.unpack_from(
        raw
    )
    if payload_length > MAX_PAYLOAD_BYTES:
        raise ChunkProtocolError("declared payload exceeds 200 bytes")
    expected_length = HEADER.size + payload_length + CRC.size
    if len(raw) != expected_length:
        raise ChunkProtocolError("frame length does not match payload_length")
    expected_crc = CRC.unpack_from(raw, HEADER.size + payload_length)[0]
    actual_crc = zlib.crc32(raw[: HEADER.size + payload_length]) & 0xFFFFFFFF
    if actual_crc != expected_crc:
        raise ChunkProtocolError("frame CRC32 mismatch", AckStatus.CRC_MISMATCH)
    if version != VERSION:
        raise ChunkProtocolError("unsupported frame version", AckStatus.UNSUPPORTED)
    try:
        kind = FrameKind(raw_kind)
    except ValueError as exc:
        raise ChunkProtocolError(
            f"unsupported frame kind {raw_kind}", AckStatus.UNSUPPORTED
        ) from exc
    return ChunkFrame(kind, session_id, sequence, total, raw[HEADER.size : -CRC.size])


def make_ack(frame: ChunkFrame, status: AckStatus = AckStatus.OK) -> ChunkFrame:
    return ChunkFrame(
        kind=FrameKind.ACK,
        session_id=frame.session_id,
        sequence=frame.sequence,
        total=frame.total,
        payload=bytes([int(status)]),
    )


def iter_frames(
    payload: bytes,
    kind: FrameKind,
    session_id: int,
    payload_bytes: int = DEFAULT_PAYLOAD_BYTES,
):
    if kind not in (FrameKind.INVOICE, FrameKind.CONSIGNMENT):
        raise ChunkProtocolError("only invoice or consignment payloads can be chunked")
    if not payload:
        raise ChunkProtocolError("empty transfers are forbidden")
    if len(payload) > MAX_TRANSFER_BYTES:
        raise ChunkProtocolError(
            "transfer exceeds the ESP32 staging limit", AckStatus.TOO_LARGE
        )
    if not 1 <= payload_bytes <= MAX_PAYLOAD_BYTES:
        raise ChunkProtocolError("chunk payload size must be between 1 and 200")
    total = (len(payload) + payload_bytes - 1) // payload_bytes
    if total > 0xFFFF:
        raise ChunkProtocolError("transfer requires more than 65535 frames")
    for sequence in range(total):
        start = sequence * payload_bytes
        yield ChunkFrame(
            kind=kind,
            session_id=session_id,
            sequence=sequence,
            total=total,
            payload=payload[start : start + payload_bytes],
        )


class ChunkReceiver:
    """Ordered, bounded reassembly with exact previous-frame deduplication."""

    def __init__(self, max_transfer_bytes: int = MAX_TRANSFER_BYTES) -> None:
        self.max_transfer_bytes = max_transfer_bytes
        self._kind: FrameKind | None = None
        self._session_id: int | None = None
        self._total: int | None = None
        self._next_sequence = 0
        self._payload = bytearray()
        self._last_signature: tuple[FrameKind, int, int, int, bytes] | None = None

    @property
    def complete(self) -> bool:
        return self._total is not None and self._next_sequence == self._total

    @property
    def kind(self) -> FrameKind | None:
        return self._kind

    @property
    def session_id(self) -> int | None:
        return self._session_id

    @property
    def payload(self) -> bytes:
        if not self.complete:
            raise ChunkProtocolError("transfer is not complete")
        return bytes(self._payload)

    def accept(self, frame: ChunkFrame) -> bool:
        if frame.kind not in (FrameKind.INVOICE, FrameKind.CONSIGNMENT):
            raise ChunkProtocolError("receiver expected a data frame", AckStatus.UNSUPPORTED)
        if frame.total == 0 or frame.sequence >= frame.total or not frame.payload:
            raise ChunkProtocolError("invalid data frame counters or empty payload")

        signature = (
            frame.kind,
            frame.session_id,
            frame.sequence,
            frame.total,
            frame.payload,
        )
        if self._last_signature == signature and frame.sequence + 1 == self._next_sequence:
            return False
        if self.complete:
            raise ChunkProtocolError("receiver already holds a transfer", AckStatus.BUSY)

        if self._kind is None:
            if frame.sequence != 0:
                raise ChunkProtocolError(
                    "first frame must have sequence zero", AckStatus.SEQUENCE_MISMATCH
                )
            self._kind = frame.kind
            self._session_id = frame.session_id
            self._total = frame.total
        else:
            if frame.kind != self._kind or frame.session_id != self._session_id:
                raise ChunkProtocolError(
                    "frame does not match active session", AckStatus.SESSION_MISMATCH
                )
            if frame.total != self._total:
                raise ChunkProtocolError(
                    "frame total changed within session", AckStatus.TOTAL_MISMATCH
                )

        if frame.sequence != self._next_sequence:
            raise ChunkProtocolError(
                "frame arrived out of order", AckStatus.SEQUENCE_MISMATCH
            )
        if len(self._payload) + len(frame.payload) > self.max_transfer_bytes:
            raise ChunkProtocolError(
                "transfer exceeds receiver limit", AckStatus.TOO_LARGE
            )
        self._payload.extend(frame.payload)
        self._next_sequence += 1
        self._last_signature = signature
        return True


class ChunkTransport:
    """Bleak-compatible stop-and-wait transport over CHUNK_IN/CHUNK_OUT."""

    def __init__(
        self,
        client,
        chunk_in_uuid: str,
        chunk_out_uuid: str,
        *,
        timeout: float,
    ) -> None:
        self.client = client
        self.chunk_in_uuid = chunk_in_uuid
        self.chunk_out_uuid = chunk_out_uuid
        self.timeout = timeout
        self._ack_queue: asyncio.Queue[ChunkFrame] = asyncio.Queue()
        self._data_queue: asyncio.Queue[ChunkFrame] = asyncio.Queue()
        self._decode_errors: asyncio.Queue[ChunkProtocolError] = asyncio.Queue()
        self._started = False

    async def start(self) -> None:
        if not self._started:
            await self.client.start_notify(self.chunk_out_uuid, self._on_notification)
            self._started = True

    async def stop(self) -> None:
        if self._started:
            await self.client.stop_notify(self.chunk_out_uuid)
            self._started = False

    def _on_notification(self, _characteristic, data: bytearray) -> None:
        try:
            frame = decode_frame(data)
        except ChunkProtocolError as exc:
            self._decode_errors.put_nowait(exc)
            return
        if frame.kind is FrameKind.ACK:
            self._ack_queue.put_nowait(frame)
        else:
            self._data_queue.put_nowait(frame)

    async def _next_frame(self, queue: asyncio.Queue[ChunkFrame]) -> ChunkFrame:
        if not self._decode_errors.empty():
            raise self._decode_errors.get_nowait()
        frame_task = asyncio.create_task(queue.get())
        error_task = asyncio.create_task(self._decode_errors.get())
        done, pending = await asyncio.wait(
            {frame_task, error_task},
            timeout=self.timeout,
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        if not done:
            raise asyncio.TimeoutError
        if error_task in done:
            raise error_task.result()
        return frame_task.result()

    async def send(
        self,
        kind: FrameKind,
        payload: bytes,
        *,
        session_id: int | None = None,
        payload_bytes: int = DEFAULT_PAYLOAD_BYTES,
    ) -> int:
        if not self._started:
            raise ChunkProtocolError("chunk notifications must be started first")
        selected_session = (
            session_id if session_id is not None else secrets.randbits(32)
        )
        frames = iter_frames(payload, kind, selected_session, payload_bytes)
        for frame in frames:
            try:
                await asyncio.wait_for(
                    self.client.write_gatt_char(
                        self.chunk_in_uuid, encode_frame(frame), response=True
                    ),
                    timeout=self.timeout,
                )
            except asyncio.TimeoutError as exc:
                raise ChunkProtocolError(
                    f"timed out writing frame {frame.sequence}/{frame.total}"
                ) from exc
            while True:
                try:
                    ack = await self._next_frame(self._ack_queue)
                except asyncio.TimeoutError as exc:
                    raise ChunkProtocolError(
                        "timed out waiting for ACK for "
                        f"frame {frame.sequence}/{frame.total}"
                    ) from exc
                if (
                    ack.session_id == frame.session_id
                    and ack.sequence == frame.sequence
                    and ack.total == frame.total
                ):
                    break
            if len(ack.payload) != 1:
                raise ChunkProtocolError("ACK must carry one status byte")
            try:
                status = AckStatus(ack.payload[0])
            except ValueError as exc:
                raise ChunkProtocolError(
                    f"unknown ACK status {ack.payload[0]}"
                ) from exc
            if status is not AckStatus.OK:
                raise ChunkProtocolError(
                    f"bill rejected frame {frame.sequence}: {status.name}", status
                )
        return selected_session

    async def receive(
        self,
        *,
        expected_kind: FrameKind | None = None,
        expected_session_id: int | None = None,
    ) -> tuple[FrameKind, int, bytes]:
        if not self._started:
            raise ChunkProtocolError("chunk notifications must be started first")
        receiver = ChunkReceiver()
        while not receiver.complete:
            try:
                frame = await self._next_frame(self._data_queue)
            except asyncio.TimeoutError as exc:
                raise ChunkProtocolError(
                    "timed out waiting for a CHUNK_OUT data frame"
                ) from exc
            status = AckStatus.OK
            try:
                if expected_kind is not None and frame.kind is not expected_kind:
                    raise ChunkProtocolError(
                        "received an unexpected transfer kind",
                        AckStatus.SESSION_MISMATCH,
                    )
                if (
                    expected_session_id is not None
                    and frame.session_id != expected_session_id
                ):
                    raise ChunkProtocolError(
                        "received an unexpected session id",
                        AckStatus.SESSION_MISMATCH,
                    )
                receiver.accept(frame)
            except ChunkProtocolError as exc:
                status = exc.status
                await asyncio.wait_for(
                    self.client.write_gatt_char(
                        self.chunk_in_uuid,
                        encode_frame(make_ack(frame, status)),
                        response=True,
                    ),
                    timeout=self.timeout,
                )
                raise
            await asyncio.wait_for(
                self.client.write_gatt_char(
                    self.chunk_in_uuid,
                    encode_frame(make_ack(frame, status)),
                    response=True,
                ),
                timeout=self.timeout,
            )
        assert receiver.kind is not None
        assert receiver.session_id is not None
        return receiver.kind, receiver.session_id, receiver.payload
