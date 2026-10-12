from pathlib import Path
from types import SimpleNamespace

from web.rgb.native import RgbLibBackend


class FakeLock:
    def __init__(self):
        self.released = False

    def release(self):
        self.released = True


class Assignment:
    @staticmethod
    def ANY():
        return "any"

    @staticmethod
    def FUNGIBLE(amount):
        return ("fungible", amount)


class Recipient:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class WitnessData:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class Invoice:
    def __init__(self, invoice_string):
        self._invoice_string = invoice_string

    def invoice_string(self):
        return self._invoice_string

    def invoice_data(self):
        return SimpleNamespace(
            recipient_id="recipient",
            asset_id="rgb:usdt",
            expiration_timestamp=1900,
            transport_endpoints=[],
            unknown_query_params={},
            network="signet-custom",
        )


class FakeWallet:
    def __init__(self, consignment_path: Path):
        self.consignment_path = consignment_path
        self.witness_args = None
        self.send_args = None
        self.import_args = None

    def get_asset_balance(self, _asset_id):
        return SimpleNamespace(spendable=500)

    def witness_receive(self, *args):
        self.witness_args = args
        return SimpleNamespace(
            invoice="invoice",
            recipient_id="recipient",
            expiration_timestamp=1900,
            batch_transfer_idx=4,
        )

    def send(self, *args):
        self.send_args = args
        return SimpleNamespace(txid="txid", batch_transfer_idx=7)

    def list_transfers(self, asset_id):
        assert asset_id == "rgb:usdt"
        return [
            SimpleNamespace(
                kind="Send",
                txid="txid",
                consignment_path=str(self.consignment_path),
            )
        ]

    def provide_out_of_band_consignment(self, *args):
        self.import_args = args
        return {4: SimpleNamespace(updated_status="WaitingConfirmations")}


def backend(tmp_path):
    rgb = SimpleNamespace(
        Assignment=Assignment,
        Recipient=Recipient,
        WitnessData=WitnessData,
        Invoice=Invoice,
        BitcoinNetwork=SimpleNamespace(SIGNET_CUSTOM="signet-custom"),
    )
    wallet = FakeWallet(tmp_path / "consignment_out")
    return RgbLibBackend(
        rgb_lib=rgb,
        wallet=wallet,
        online="online",
        process_lock=FakeLock(),
    ), wallet


def test_native_witness_receive_has_no_transport_endpoints(tmp_path):
    native, wallet = backend(tmp_path)

    native.witness_receive("rgb:usdt", 1900, 1)

    assert wallet.witness_args == ("rgb:usdt", "any", 1900, [], 1)


def test_native_parses_mutinynet_invoice_for_tap_sender(tmp_path):
    native, _wallet = backend(tmp_path)

    parsed = native.parse_invoice("invoice")

    assert parsed.invoice == "invoice"
    assert parsed.recipient_id == "recipient"
    assert parsed.asset_id == "rgb:usdt"
    assert parsed.expiration_timestamp == 1900
    assert parsed.transport_endpoints == ()


def test_native_send_is_donation_whole_amount_and_has_no_transport_endpoints(tmp_path):
    native, wallet = backend(tmp_path)

    result = native.send_donation(
        asset_id="rgb:usdt",
        recipient_id="recipient",
        amount=500,
        witness_amount_sat=1000,
        fee_rate=2,
        min_confirmations=1,
        expiration_timestamp=1900,
    )

    recipient = wallet.send_args[1]["rgb:usdt"][0]
    assert recipient.transport_endpoints == []
    assert recipient.assignment == ("fungible", 500)
    assert recipient.witness_data.amount_sat == 1000
    assert recipient.witness_data.blinding is None
    assert wallet.send_args[2] is True
    assert result.consignment_path == tmp_path / "consignment_out"


def test_native_receiver_import_uses_no_media_or_proxy(tmp_path):
    native, wallet = backend(tmp_path)
    path = tmp_path / "received.rgbc"

    result = native.import_consignment(path)

    assert wallet.import_args == ("online", str(path), [])
    assert result == {4: "waitingconfirmations"}
