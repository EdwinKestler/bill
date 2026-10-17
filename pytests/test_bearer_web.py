import hashlib
import json
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from web import bearer_web
from web.bearer_web import BearerWebError, BearerWebService
from web.rgb.bearer_capsule import BearerCapsule, encode_bearer_capsule
from web.rgb.config import BillRole, RgbSettings


class FakeGateway:
    def __init__(self, payload: bytes = b"") -> None:
        self.payload = payload
        self.staged = []

    def stage(self, kind, path, denomination_cents=0):
        self.staged.append((kind, Path(path), denomination_cents))
        return 0x01020304

    def receive(self, kind, output):
        Path(output).write_bytes(self.payload)
        return 0x05060708, len(self.payload)


class FakeWallet:
    def __init__(self, settings: RgbSettings, gateway: FakeGateway) -> None:
        self.role = settings.role
        self.settings = settings
        self.flow = SimpleNamespace(gateway=gateway)
        self.borrow_calls = 0

    def with_borrowed_backend(self, operation):
        self.borrow_calls += 1

        class Borrowed:
            def close(self):
                raise AssertionError("test operation must not close the fake owner")

        return operation(self.settings, lambda _settings: Borrowed())


def settings(tmp_path: Path, role: BillRole) -> RgbSettings:
    return RgbSettings(
        role=role,
        data_dir=tmp_path / f"wallet-{role.value.lower()}",
        peer_data_dir=tmp_path / "peer",
        inbox_dir=tmp_path / "inbox",
        electrum_url="https://mutinynet.com/api",
        master_fingerprint="fingerprint",
        mnemonic_file=tmp_path / "secret",
    )


def capsule_bytes() -> bytes:
    return encode_bearer_capsule(
        BearerCapsule(
            network="mutinynet",
            vault_key_id="local-demo-vault-v1",
            note_id="11111111-1111-4111-8111-111111111111",
            claim_secret=b"s" * 32,
            asset_id="rgb:asset",
            amount_base_units=5_000_000,
            denomination_cents=500,
            funding_txid="a" * 64,
            funding_consignment_sha256="b" * 64,
            issued_timestamp=1_800_000_000,
        )
    )


def test_load_stages_only_the_existing_active_capsule(monkeypatch, tmp_path):
    vault = tmp_path / "vault"
    note_id = "11111111-1111-4111-8111-111111111111"
    manifest = vault / "notes" / note_id / "manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        json.dumps(
            {
                "note_id": note_id,
                "state": "ACTIVE",
                "issuer_master_fingerprint": "fingerprint",
            }
        )
    )
    artifact = manifest.parent / "artifacts" / "bearer-note.rgbn"
    artifact.parent.mkdir()
    artifact.write_bytes(capsule_bytes())
    gateway = FakeGateway()
    wallet = FakeWallet(settings(tmp_path, BillRole.B), gateway)
    service = BearerWebService(wallet, vault_root=vault)

    monkeypatch.setattr(
        bearer_web,
        "prepare_live_bearer_capsule",
        lambda *_args, **_kwargs: {
            "capsule_path": str(artifact),
            "denomination_cents": 500,
            "artifact_bytes": artifact.stat().st_size,
            "artifact_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
        },
    )

    result = service.load_note()

    assert result["note_id"] == note_id
    assert result["broadcast"] is False
    assert gateway.staged == [(bearer_web.FrameKind.BEARER_NOTE, artifact, 500)]


def test_load_rejects_active_note_owned_by_another_wallet(tmp_path):
    vault = tmp_path / "vault"
    note_id = "11111111-1111-4111-8111-111111111111"
    manifest = vault / "notes" / note_id / "manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        json.dumps(
            {
                "note_id": note_id,
                "state": "ACTIVE",
                "issuer_master_fingerprint": "other-fingerprint",
            }
        )
    )
    wallet = FakeWallet(settings(tmp_path, BillRole.A), FakeGateway())
    service = BearerWebService(wallet, vault_root=vault)

    with pytest.raises(BearerWebError, match="not an active, settled"):
        service.select_load_note(note_id)


def test_prepare_funding_turns_missing_note_sats_into_dock_topup_plan(
    monkeypatch, tmp_path
):
    wallet = FakeWallet(settings(tmp_path, BillRole.B), FakeGateway())
    wallet.asset_id = "rgb:asset"
    service = BearerWebService(wallet, vault_root=tmp_path / "vault")
    funding = {
        "plan_id": "funding-1",
        "note_id": "11111111-1111-4111-8111-111111111111",
        "note_btc_address": "tb1qnote",
        "note_vanilla_spendable_before": 0,
        "recommended_redemption_vanilla_sat": 2_000,
    }
    topup = {
        "plan_id": "topup-1",
        "note_id": funding["note_id"],
        "destination_address": "tb1qnote",
        "topup_amount_sat": 2_000,
        "target_note_vanilla_sat": 2_000,
        "note_vanilla_spendable_before": 0,
        "source_vanilla_spendable_before": 50_000,
        "fee_rate_sat_vb": 2,
        "expiration_timestamp": 1_900_000_000,
    }

    monkeypatch.setattr(
        bearer_web,
        "prepare_live_funding_plan",
        lambda *_args, **_kwargs: (
            funding,
            {"state": "AWAITING_FUNDING"},
        ),
    )
    monkeypatch.setattr(
        bearer_web,
        "prepare_live_funding_btc_topup_plan",
        lambda *_args, **_kwargs: (
            SimpleNamespace(**topup),
            {"state": "BTC_TOPUP_PLANNED"},
        ),
    )
    monkeypatch.setattr(
        bearer_web,
        "redacted_plan",
        lambda plan: dict(vars(plan)),
    )

    result = service.prepare_funding()

    assert result["phase"] == "bearer-note-btc-topup-plan-ready"
    assert result["plan"]["topup_amount_sat"] == 2_000
    assert wallet.borrow_calls == 2


def test_inspect_ambiguous_funding_prepares_separate_capacity_plan(
    monkeypatch, tmp_path
):
    vault = tmp_path / "vault"
    note_id = "11111111-1111-4111-8111-111111111111"
    manifest_path = vault / "notes" / note_id / "manifest.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        json.dumps(
            {
                "version": 1,
                "network": "mutinynet",
                "note_id": note_id,
                "state": "AMBIGUOUS",
                "issuer_master_fingerprint": "fingerprint",
            }
        )
    )
    wallet = FakeWallet(settings(tmp_path, BillRole.B), FakeGateway())
    service = BearerWebService(wallet, vault_root=vault)
    public_plan = {
        "plan_id": "capacity-1",
        "note_id": note_id,
        "utxo_count": 1,
        "utxo_size_sat": 8_000,
        "vanilla_spendable_before": 20_000,
        "free_colorable_utxo_count_before": 0,
        "fee_rate_sat_vb": 2,
        "expiration_timestamp": 1_900_000_000,
    }

    monkeypatch.setattr(
        bearer_web,
        "prepare_live_funding_capacity_plan",
        lambda *_args, **_kwargs: (
            object(),
            {"state": "FUNDING_CAPACITY_PLANNED"},
        ),
    )
    monkeypatch.setattr(bearer_web, "redacted_plan", lambda _plan: public_plan)

    result = service.inspect_funding()

    assert result["phase"] == "bearer-funding-capacity-plan-ready"
    assert result["plan"] == public_plan
    assert wallet.borrow_calls == 1


def test_redemption_extracts_private_content_addressed_capsule_before_plan(
    monkeypatch, tmp_path
):
    payload = capsule_bytes()
    gateway = FakeGateway(payload)
    wallet = FakeWallet(settings(tmp_path, BillRole.A), gateway)
    service = BearerWebService(wallet, vault_root=tmp_path / "vault")
    public_plan = {
        "plan_id": "plan-1",
        "note_id": "11111111-1111-4111-8111-111111111111",
        "denomination_cents": 500,
        "asset_id": "rgb:asset",
        "amount_base_units": 5_000_000,
        "recipient_id": "recipient",
        "witness_amount_sat": 1000,
        "fee_rate_sat_vb": 2,
        "min_confirmations": 1,
        "expiration_timestamp": 1_900_000_000,
        "recipient_invoice_sha256": "c" * 64,
        "capsule_sha256": hashlib.sha256(payload).hexdigest(),
    }
    observed = {}

    def prepare(_settings, **kwargs):
        path = kwargs["capsule_path"]
        observed["path"] = path
        observed["digest"] = kwargs["expected_capsule_sha256"]
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert path.read_bytes() == payload
        return object(), {"state": "CLAIM_PLANNED"}

    monkeypatch.setattr(bearer_web, "prepare_live_redemption_plan", prepare)
    monkeypatch.setattr(bearer_web, "redacted_plan", lambda _plan: public_plan)

    result = service.prepare_redemption(receive_from_bill=True)

    digest = hashlib.sha256(payload).hexdigest()
    assert observed["digest"] == digest
    assert observed["path"].name == f"{digest}.rgbn"
    assert result["capsule_sha256"] == digest
    assert result["ble_session_id"] == "0x05060708"
    assert result["broadcast"] is False
    assert wallet.borrow_calls == 1
