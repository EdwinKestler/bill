"""Cross-platform codec and stop-and-wait chunk transport coverage."""

import asyncio
import zlib

import pytest

from dock.chunk_protocol import (
    AckStatus,
    ChunkFrame,
    ChunkProtocolError,
    ChunkReceiver,
    ChunkTransport,
    FrameKind,
    decode_frame,
    encode_frame,
    iter_frames,
    make_ack,
)

CHUNK_IN = "chunk-in"
CHUNK_OUT = "chunk-out"


def test_frame_round_trip_uses_little_endian_and_standard_crc32():
    frame = ChunkFrame(
        FrameKind.CONSIGNMENT,
        session_id=0x78563412,
        sequence=2,
        total=4,
        payload=b"\x00\x11\xfe\xff",
    )
    encoded = encode_frame(frame)

    assert encoded[:12] == bytes.fromhex("010212345678020004000400")
    assert int.from_bytes(encoded[-4:], "little") == zlib.crc32(encoded[:-4])
    assert decode_frame(encoded) == frame


def test_corrupt_frame_is_rejected_before_reassembly():
    encoded = bytearray(
        encode_frame(ChunkFrame(FrameKind.INVOICE, 7, 0, 1, b"invoice"))
    )
    encoded[12] ^= 0x01

    with pytest.raises(ChunkProtocolError, match="CRC32") as caught:
        decode_frame(encoded)
    assert caught.value.status is AckStatus.CRC_MISMATCH


def test_bearer_note_round_trip_is_supported_data():
    frames = list(
        iter_frames(b"RGBN bearer capsule", FrameKind.BEARER_NOTE, 0xAABBCCDD, 7)
    )
    receiver = ChunkReceiver()

    for frame in frames:
        receiver.accept(decode_frame(encode_frame(frame)))

    assert receiver.complete
    assert receiver.kind is FrameKind.BEARER_NOTE
    assert receiver.payload == b"RGBN bearer capsule"


def test_receiver_reassembles_ordered_frames_and_deduplicates_previous_frame():
    frames = list(iter_frames(b"abcdefgh", FrameKind.INVOICE, 99, payload_bytes=3))
    receiver = ChunkReceiver()

    assert receiver.accept(frames[0]) is True
    assert receiver.accept(frames[0]) is False
    assert receiver.accept(frames[1]) is True
    assert receiver.accept(frames[2]) is True
    assert receiver.complete
    assert receiver.payload == b"abcdefgh"


def test_receiver_rejects_out_of_order_frame():
    frames = list(iter_frames(b"abcdef", FrameKind.INVOICE, 99, payload_bytes=3))
    receiver = ChunkReceiver()

    with pytest.raises(ChunkProtocolError) as caught:
        receiver.accept(frames[1])
    assert caught.value.status is AckStatus.SEQUENCE_MISMATCH


class FakeClient:
    def __init__(self, *, acknowledge_data: bool = False):
        self.acknowledge_data = acknowledge_data
        self.callback = None
        self.writes = []
        self.stopped = False

    async def start_notify(self, uuid, callback):
        assert uuid == CHUNK_OUT
        self.callback = callback

    async def stop_notify(self, uuid):
        assert uuid == CHUNK_OUT
        self.stopped = True

    async def write_gatt_char(self, uuid, encoded, response):
        assert uuid == CHUNK_IN
        assert response is True
        frame = decode_frame(encoded)
        self.writes.append(frame)
        if self.acknowledge_data and frame.kind is not FrameKind.ACK:
            assert self.callback is not None
            self.callback(None, bytearray(encode_frame(make_ack(frame))))

    def emit(self, frame):
        assert self.callback is not None
        self.callback(None, bytearray(encode_frame(frame)))


def test_transport_sends_each_frame_with_response_and_waits_for_ack():
    async def run():
        client = FakeClient(acknowledge_data=True)
        transport = ChunkTransport(
            client, CHUNK_IN, CHUNK_OUT, timeout=0.1
        )
        await transport.start()
        session = await transport.send(
            FrameKind.CONSIGNMENT,
            b"0123456789",
            session_id=0x12345678,
            payload_bytes=4,
        )
        await transport.stop()
        return client, session

    client, session = asyncio.run(run())
    assert session == 0x12345678
    assert [frame.sequence for frame in client.writes] == [0, 1, 2]
    assert all(frame.total == 3 for frame in client.writes)
    assert client.stopped


def test_transport_receives_and_acks_every_notification():
    async def run():
        client = FakeClient()
        transport = ChunkTransport(
            client, CHUNK_IN, CHUNK_OUT, timeout=0.1
        )
        await transport.start()
        frames = list(
            iter_frames(b"rgb-consignment", FrameKind.CONSIGNMENT, 41, 5)
        )
        receive_task = asyncio.create_task(
            transport.receive(
                expected_kind=FrameKind.CONSIGNMENT,
                expected_session_id=41,
            )
        )
        for frame in frames:
            client.emit(frame)
            await asyncio.sleep(0)
        result = await receive_task
        await transport.stop()
        return client, result

    client, result = asyncio.run(run())
    assert result == (FrameKind.CONSIGNMENT, 41, b"rgb-consignment")
    assert len(client.writes) == 3
    assert all(frame.kind is FrameKind.ACK for frame in client.writes)
    assert all(frame.payload == bytes([AckStatus.OK]) for frame in client.writes)


def test_transport_multiplexes_final_ack_and_echo_data_without_loss():
    class LoopbackClient(FakeClient):
        def __init__(self):
            super().__init__()
            self.receiver = ChunkReceiver()
            self.host_acks = []

        async def write_gatt_char(self, uuid, encoded, response):
            assert uuid == CHUNK_IN
            assert response is True
            frame = decode_frame(encoded)
            if frame.kind is FrameKind.ACK:
                self.host_acks.append(frame)
                return
            self.receiver.accept(frame)
            assert self.callback is not None
            self.callback(None, bytearray(encode_frame(make_ack(frame))))
            if self.receiver.complete:
                for echoed in iter_frames(
                    self.receiver.payload,
                    frame.kind,
                    frame.session_id,
                    payload_bytes=4,
                ):
                    self.callback(None, bytearray(encode_frame(echoed)))

    async def run():
        client = LoopbackClient()
        transport = ChunkTransport(
            client, CHUNK_IN, CHUNK_OUT, timeout=0.1
        )
        await transport.start()
        payload = b"invoice-over-both-characteristics"
        session = await transport.send(
            FrameKind.INVOICE,
            payload,
            session_id=0xAABBCCDD,
            payload_bytes=6,
        )
        result = await transport.receive(
            expected_kind=FrameKind.INVOICE,
            expected_session_id=session,
        )
        await transport.stop()
        return client, result

    client, result = asyncio.run(run())
    assert result == (
        FrameKind.INVOICE,
        0xAABBCCDD,
        b"invoice-over-both-characteristics",
    )
    assert client.host_acks
    assert all(frame.payload == bytes([AckStatus.OK]) for frame in client.host_acks)
