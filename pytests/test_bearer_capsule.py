from __future__ import annotations

import json

import pytest

from web.rgb.bearer_capsule import (
    CAPSULE_HEADER,
    BearerCapsule,
    BearerCapsuleError,
    decode_bearer_capsule,
    encode_bearer_capsule,
    redacted_capsule,
)


SECRET = bytes.fromhex("11" * 32)


def _capsule(**changes) -> BearerCapsule:
    values = {
        "network": "mutinynet",
        "vault_key_id": "local-demo-vault-v1",
        "note_id": "758186be-791d-4c8c-92f5-a8c4194ac856",
        "claim_secret": SECRET,
        "asset_id": "rgb:synthetic-usdt",
        "amount_base_units": 5_000_000,
        "denomination_cents": 500,
        "funding_txid": "aa" * 32,
        "funding_consignment_sha256": "bb" * 32,
        "issued_timestamp": 1_792_085_194,
    }
    values.update(changes)
    return BearerCapsule(**values)


def test_capsule_round_trip_is_canonical_and_bounded():
    encoded = encode_bearer_capsule(_capsule())
    decoded = decode_bearer_capsule(encoded)

    assert decoded == _capsule()
    assert encode_bearer_capsule(decoded) == encoded
    assert len(encoded) < 1_024


def test_capsule_rejects_truncation_unknown_version_and_bit_flip():
    encoded = encode_bearer_capsule(_capsule())
    with pytest.raises(BearerCapsuleError, match="truncated"):
        decode_bearer_capsule(encoded[:-1])

    unknown = bytearray(encoded)
    unknown[4] = 2
    with pytest.raises(BearerCapsuleError, match="version"):
        decode_bearer_capsule(bytes(unknown))

    damaged = bytearray(encoded)
    damaged[CAPSULE_HEADER.size + 10] ^= 1
    with pytest.raises(BearerCapsuleError, match="integrity"):
        decode_bearer_capsule(bytes(damaged))


def test_capsule_rejects_wrong_network_bounds_and_amount_mismatch():
    with pytest.raises(BearerCapsuleError, match="network"):
        encode_bearer_capsule(_capsule(network="bitcoin"))
    with pytest.raises(BearerCapsuleError, match="too long"):
        encode_bearer_capsule(_capsule(vault_key_id="v" * 65))
    with pytest.raises(BearerCapsuleError, match="do not match"):
        encode_bearer_capsule(_capsule(amount_base_units=4_999_999))


def test_capsule_redaction_never_formats_the_synthetic_secret():
    capsule = _capsule()
    encoded = encode_bearer_capsule(capsule)
    public = redacted_capsule(capsule, encoded)

    assert SECRET.hex() not in repr(capsule)
    assert SECRET.hex() not in json.dumps(public)
    assert public["claim_secret_redacted"] is True
    assert public["contains_wallet_backup"] is False
