"""Strict, canonical bearer-capsule v1 codec for the offline note demo."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import struct
import uuid
from dataclasses import dataclass, field
from typing import Any


CAPSULE_MAGIC = b"RGBN"
CAPSULE_VERSION = 1
CAPSULE_NETWORK = "mutinynet"
CAPSULE_ISSUER_AUTHENTICATION = "vault-online-only"
CAPSULE_HEADER = struct.Struct("<4sBI")
CAPSULE_DIGEST_BYTES = 32
CAPSULE_MAX_PAYLOAD_BYTES = 2_048
CAPSULE_MAX_BYTES = CAPSULE_HEADER.size + CAPSULE_MAX_PAYLOAD_BYTES + 32
CLAIM_SECRET_BYTES = 32
CLAIM_SALT_BYTES = 32
CLAIM_HASH_SCHEME = "sha256-domain-separated-v1"
_CLAIM_HASH_DOMAIN = b"rgb-bill-claim-v1\x00"
_VAULT_KEY_ID = re.compile(r"[A-Za-z0-9._-]{1,64}\Z")
_HEX_64 = re.compile(r"[0-9a-f]{64}\Z")
_PAYLOAD_KEYS = {
    "amount_base_units",
    "asset_id",
    "claim_secret",
    "denomination_cents",
    "funding_consignment_sha256",
    "funding_txid",
    "issued_timestamp",
    "issuer_authentication",
    "network",
    "note_id",
    "vault_key_id",
}


class BearerCapsuleError(ValueError):
    """A bearer capsule failed a strict format or integrity check."""


@dataclass(frozen=True)
class BearerCapsule:
    network: str
    vault_key_id: str
    note_id: str
    claim_secret: bytes = field(repr=False)
    asset_id: str
    amount_base_units: int
    denomination_cents: int
    funding_txid: str
    funding_consignment_sha256: str
    issued_timestamp: int
    issuer_authentication: str = CAPSULE_ISSUER_AUTHENTICATION


def claim_secret_hash(secret: bytes, salt: bytes) -> str:
    """Return the registry-safe hash; the random secret itself stays in the capsule."""

    if len(secret) != CLAIM_SECRET_BYTES or len(salt) != CLAIM_SALT_BYTES:
        raise BearerCapsuleError("claim secret and salt must each be exactly 32 bytes")
    return hashlib.sha256(_CLAIM_HASH_DOMAIN + salt + secret).hexdigest()


def _validate(capsule: BearerCapsule) -> None:
    if capsule.network != CAPSULE_NETWORK:
        raise BearerCapsuleError("capsule network must be mutinynet")
    if not _VAULT_KEY_ID.fullmatch(capsule.vault_key_id):
        raise BearerCapsuleError("vault key ID is invalid or too long")
    try:
        parsed_note_id = uuid.UUID(capsule.note_id)
    except (ValueError, AttributeError) as exc:
        raise BearerCapsuleError("note ID is not a UUID") from exc
    if str(parsed_note_id) != capsule.note_id:
        raise BearerCapsuleError("note ID is not in canonical UUID form")
    if len(capsule.claim_secret) != CLAIM_SECRET_BYTES:
        raise BearerCapsuleError("claim secret must be exactly 32 bytes")
    try:
        encoded_asset_id = capsule.asset_id.encode("ascii")
    except (AttributeError, UnicodeEncodeError) as exc:
        raise BearerCapsuleError("asset ID must be ASCII") from exc
    if not 1 <= len(encoded_asset_id) <= 192:
        raise BearerCapsuleError("asset ID is empty or too long")
    if type(capsule.amount_base_units) is not int or capsule.amount_base_units <= 0:
        raise BearerCapsuleError("amount must be a positive integer")
    if type(capsule.denomination_cents) is not int or capsule.denomination_cents <= 0:
        raise BearerCapsuleError("denomination must be a positive integer")
    if capsule.amount_base_units != capsule.denomination_cents * 10_000:
        raise BearerCapsuleError("base units do not match the six-decimal denomination")
    if not _HEX_64.fullmatch(capsule.funding_txid):
        raise BearerCapsuleError("funding txid must be 32-byte lowercase hex")
    if not _HEX_64.fullmatch(capsule.funding_consignment_sha256):
        raise BearerCapsuleError("funding consignment digest must be lowercase SHA-256")
    if type(capsule.issued_timestamp) is not int or not (
        1 <= capsule.issued_timestamp < 2**63
    ):
        raise BearerCapsuleError("issued timestamp is invalid")
    if capsule.issuer_authentication != CAPSULE_ISSUER_AUTHENTICATION:
        raise BearerCapsuleError("unsupported capsule issuer-authentication mode")


def _canonical_payload(capsule: BearerCapsule) -> bytes:
    _validate(capsule)
    payload = {
        "amount_base_units": capsule.amount_base_units,
        "asset_id": capsule.asset_id,
        "claim_secret": capsule.claim_secret.hex(),
        "denomination_cents": capsule.denomination_cents,
        "funding_consignment_sha256": capsule.funding_consignment_sha256,
        "funding_txid": capsule.funding_txid,
        "issued_timestamp": capsule.issued_timestamp,
        "issuer_authentication": capsule.issuer_authentication,
        "network": capsule.network,
        "note_id": capsule.note_id,
        "vault_key_id": capsule.vault_key_id,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    if len(encoded) > CAPSULE_MAX_PAYLOAD_BYTES:
        raise BearerCapsuleError("capsule payload exceeds the v1 bound")
    return encoded


def encode_bearer_capsule(capsule: BearerCapsule) -> bytes:
    payload = _canonical_payload(capsule)
    header = CAPSULE_HEADER.pack(CAPSULE_MAGIC, CAPSULE_VERSION, len(payload))
    digest = hashlib.sha256(header + payload).digest()
    return header + payload + digest


def decode_bearer_capsule(encoded: bytes) -> BearerCapsule:
    minimum = CAPSULE_HEADER.size + 2 + CAPSULE_DIGEST_BYTES
    if not minimum <= len(encoded) <= CAPSULE_MAX_BYTES:
        raise BearerCapsuleError("capsule length is outside the v1 bounds")
    magic, version, payload_size = CAPSULE_HEADER.unpack_from(encoded)
    if magic != CAPSULE_MAGIC:
        raise BearerCapsuleError("capsule magic is invalid")
    if version != CAPSULE_VERSION:
        raise BearerCapsuleError("capsule version is unsupported")
    if not 1 <= payload_size <= CAPSULE_MAX_PAYLOAD_BYTES:
        raise BearerCapsuleError("capsule payload length is invalid")
    expected_size = CAPSULE_HEADER.size + payload_size + CAPSULE_DIGEST_BYTES
    if len(encoded) != expected_size:
        raise BearerCapsuleError("capsule is truncated or has trailing bytes")
    signed = encoded[: CAPSULE_HEADER.size + payload_size]
    supplied_digest = encoded[-CAPSULE_DIGEST_BYTES:]
    if not hmac.compare_digest(hashlib.sha256(signed).digest(), supplied_digest):
        raise BearerCapsuleError("capsule integrity digest does not match")
    payload_bytes = encoded[CAPSULE_HEADER.size : -CAPSULE_DIGEST_BYTES]
    try:
        payload: Any = json.loads(payload_bytes.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BearerCapsuleError("capsule payload is not canonical JSON") from exc
    if not isinstance(payload, dict) or set(payload) != _PAYLOAD_KEYS:
        raise BearerCapsuleError("capsule payload fields are invalid")
    try:
        claim_secret = bytes.fromhex(payload["claim_secret"])
        capsule = BearerCapsule(
            network=payload["network"],
            vault_key_id=payload["vault_key_id"],
            note_id=payload["note_id"],
            claim_secret=claim_secret,
            asset_id=payload["asset_id"],
            amount_base_units=payload["amount_base_units"],
            denomination_cents=payload["denomination_cents"],
            funding_txid=payload["funding_txid"],
            funding_consignment_sha256=payload["funding_consignment_sha256"],
            issued_timestamp=payload["issued_timestamp"],
            issuer_authentication=payload["issuer_authentication"],
        )
    except (TypeError, ValueError, KeyError) as exc:
        raise BearerCapsuleError("capsule payload types are invalid") from exc
    if _canonical_payload(capsule) != payload_bytes:
        raise BearerCapsuleError("capsule payload is not canonically encoded")
    return capsule


def redacted_capsule(capsule: BearerCapsule, encoded: bytes) -> dict[str, object]:
    """Return demonstrable capsule evidence without the bearer capability."""

    digest = encoded[-CAPSULE_DIGEST_BYTES:].hex()
    return {
        "version": CAPSULE_VERSION,
        "network": capsule.network,
        "vault_key_id": capsule.vault_key_id,
        "note_id": capsule.note_id,
        "asset_id": capsule.asset_id,
        "amount_base_units": capsule.amount_base_units,
        "denomination_cents": capsule.denomination_cents,
        "funding_txid": capsule.funding_txid,
        "funding_consignment_sha256": capsule.funding_consignment_sha256,
        "issued_timestamp": capsule.issued_timestamp,
        "issuer_authentication": capsule.issuer_authentication,
        "integrity_digest": digest,
        "artifact_sha256": hashlib.sha256(encoded).hexdigest(),
        "artifact_bytes": len(encoded),
        "claim_secret_redacted": True,
        "contains_wallet_backup": False,
        "contains_funding_consignment": False,
    }
