# Live isolated-wallet RGB tap acceptance

This is the controlled acceptance run for the real wallet-to-BLE bridge. It
replaces the 520-byte inert fixture with a native rgb-lib witness invoice and
the exact out-of-band consignment produced by the confirmed Mutinynet send.

It does **not** remove the confirmation gate. The only command that can spend
stops on an immutable plan and requires the exact generated
`CONFIRM <plan_id>` phrase.

## Fixed roles for the two-board bench

| Role | Wallet | Physical bill | BLE address |
| --- | --- | --- | --- |
| A | Funded sender | LilyGO TTGO LoRa32 V1.3 | `30:AE:A4:4C:B1:6A` |
| B | Empty receiver | WEMOS LOLIN32 | `30:AE:A4:07:2D:2E` |

Use one terminal/process per role. Never source both role files into one
process and never open one wallet datadir from two processes.

## Prerequisite checks

Both ignored role files must set:

```dotenv
ELECTRUM_URL=https://esplora.signet.kaleidoswap.com
RGB_OOB_CONSIGNMENT=1
RGB_MAX_CONSIGNMENT_BYTES=655360
```

The 640 KiB limit is the shared maximum of the wallet bridge and BLE chunk
protocol. A larger wallet limit is rejected before either wallet is opened.

Run status sequentially so the public indexer is not hit by both wallets at
once:

```bash
set -a; source .env.a; set +a
.venv/bin/python -m scripts.rgb_wallet status

set -a; source .env.b; set +a
.venv/bin/python -m scripts.rgb_wallet status
```

Record the exact USDT `asset_id`, its `precision`, Bill A's spendable asset
balance, and both BTC balances. The dedicated KaleidoSwap Esplora endpoint is
the default because the public `https://mutinynet.com/api` endpoint can return
HTTP 429 under shared traffic. Do not replace Mutinynet with generic Signet and
do not bypass the wallet consistency check.

`--amount` is always an integer in asset base units. For 20 USDT, use
`20 * 10^precision`. Omitting `--amount` intentionally plans Bill A's entire
spendable balance.

## 1. Bill B creates and stages the real invoice

In the Bill B environment:

```bash
set -a; source .env.b; set +a
.venv/bin/python -m scripts.rgb_tap stage-invoice \
  --address 30:AE:A4:07:2D:2E \
  --asset-id '<USDT_ASSET_ID>' \
  --expires-seconds 3600
```

Evidence required before continuing:

- `phase` is `invoice-created`, followed by `invoice-staged`;
- `transport_endpoints` is exactly `[]`;
- the artifact path, byte count, SHA-256, and BLE session ID are present.

Press the TTGO touch button once. The rising edge arms its 15-second receive
window; release immediately. The invoice moves WEMOS to TTGO without a phone,
QR code, proxy, or dock-to-dock network path.

## 2. Bill A retrieves the invoice and plans the send

In the Bill A environment:

```bash
set -a; source .env.a; set +a
.venv/bin/python -m scripts.rgb_tap send-from-tap \
  --address 30:AE:A4:4C:B1:6A \
  --asset-id '<USDT_ASSET_ID>' \
  --amount '<20_USDT_IN_BASE_UNITS>'
```

The command retrieves the invoice from the TTGO, parses it with rgb-lib, and
rejects it unless it is canonical, unexpired, for the expected asset, and has
empty transport endpoints. Review the printed recipient, amount, balance,
fees, expiry, invoice hash, and plan ID.

Only after that review, type the exact generated phrase:

```text
CONFIRM <plan_id>
```

That confirmation is one-use. A failed or ambiguous send is never retried
automatically. After `broadcast-complete`, the command stages the exact native
consignment into the TTGO and reports its SHA-256 and BLE session ID.

If BLE staging fails after `broadcast-complete`, **do not run
`send-from-tap` again**. Use only the printed recovery `chunk-send` command for
the retained consignment file.

## 3. Bill B receives and imports the consignment

Press the WEMOS touch button once, then run this in the Bill B environment:

```bash
set -a; source .env.b; set +a
.venv/bin/python -m scripts.rgb_tap import-from-tap \
  --address 30:AE:A4:07:2D:2E
```

The command first persists and hashes the exact bytes received from the WEMOS,
then passes that file to `provide_out_of_band_consignment`. If import fails,
use the printed `scripts.rgb_wallet import-consignment` recovery command; the
content-addressed file is retained.

## 4. Settlement evidence

Refresh roles sequentially, then inspect status:

```bash
set -a; source .env.a; set +a
.venv/bin/python -m scripts.rgb_wallet refresh
.venv/bin/python -m scripts.rgb_wallet status

set -a; source .env.b; set +a
.venv/bin/python -m scripts.rgb_wallet refresh
.venv/bin/python -m scripts.rgb_wallet status
```

Acceptance requires all of the following:

- one confirmed Mutinynet txid, with no second send attempt;
- the invoice and consignment BLE sessions visible in both bill monitors;
- the staged and received consignment SHA-256 values match;
- Bill A decreases by the planned base-unit amount;
- Bill B reaches the corresponding confirmed/settled balance after the
  configured confirmation gate;
- both bills resume advertising without reset.

## Accepted run — 2026-10-11

The first real-wallet run passed every acceptance condition:

| Evidence | Accepted value |
| --- | --- |
| Mutinynet txid | `97885ddffc2305aabf1574d78be8cf102d0afb1f104529c817fc4dcff541a1fb` |
| Invoice session | `0x9dd99696`, 210 bytes |
| Invoice SHA-256 | `d1f27eb119ec49996acc9c51e565de4473b5ceeef7ec9080c75fce49edb25ffa` |
| Consignment session | `0x9e4eff88`, 12,496 bytes, 70 tap frames |
| Consignment SHA-256 | `e84c8499e53988981b187feafb9ae8de4d6c13e94fdc36508ec0794cb4dd2ee1` |
| Bill A transfer | batch `5`, `SETTLED`, 80 → 60 USDT |
| Bill B transfer | batch `3`, `SETTLED`, 20 → 40 USDT |
| Tap RSSI | invoice `-44 dBm`; consignment `-51 dBm` |
| Transport endpoints | `[]` |

The invoice crossed WEMOS → TTGO and the exact consignment crossed TTGO →
WEMOS. Both bills resumed advertising without reset. An initial pre-transfer
read and the first receiver import open encountered recoverable public-indexer
timeouts; neither caused a second send. The one confirmed broadcast produced
the txid above, and both isolated wallets independently refreshed to
`SETTLED` with the expected balances.
