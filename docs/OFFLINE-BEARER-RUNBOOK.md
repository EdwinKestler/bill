# Offline bearer-note live demo runbook

Accepted path: Wallet A → disposable note N → offline WEMOS/TTGO relay →
Wallet B. Network: Mutinynet only. The direct invoice-first browser flow remains
the fallback in [`WEB-RGB-TEST.md`](WEB-RGB-TEST.md).

This runbook contains spend-capable commands. Every `confirm-*` operation must
stop at its own freshly printed immutable plan and receive a separate exact
human `CONFIRM <plan-id>` authorization. Never reuse a phrase copied from this
repository or an earlier run.

## 0. Safety and process isolation

- Stop `web.server`, `scripts.rgb_wallet`, and other rgb-lib processes using
  the same role datadir.
- Keep `.env.a`, `.env.b`, `.note-vault/`, capsule files, and consignments out
  of Git and screenshots.
- Keep both TTP223 inputs released/LOW during boot/reset because GPIO12 is an
  ESP32 strapping pin.
- A read/indexer timeout may be retried. A send with unknown outcome may not.

```bash
ps -eo pid,args | rg 'web\.server|rgb_wallet|rgb_tap|note_wallet_live'
.venv/bin/python -m pytest -q
```

## 1. Prepare and fund a disposable note

Load Wallet A's isolated environment and create a fresh no-broadcast plan:

```bash
set -a; source .env.a; set +a
.venv/bin/python -m scripts.note_wallet_live prepare-funding-plan \
  --asset-id "$RGB_ASSET_ID"
```

Review the note ID, exact 5,000,000-unit amount, Wallet A balance, recipient,
fee, expiry, transport endpoints, and Bitcoin fee inventory. In a separate
operation, and only after explicit approval:

```bash
.venv/bin/python -m scripts.note_wallet_live confirm-funding \
  --note-id NOTE_ID \
  --plan-id PLAN_ID
```

Wait for confirmation and activate only after exact settlement proof:

```bash
.venv/bin/python -m scripts.note_wallet_live refresh-funding \
  --note-id NOTE_ID
```

Do not continue until `settled=true`, note state `ACTIVE`, transfer kind
`receive_witness`, and settled/future/spendable all equal 5,000,000.

## 2. Create and load the bearer capsule

```bash
.venv/bin/python -m scripts.note_wallet_live prepare-capsule \
  --note-id NOTE_ID

.venv/bin/python -m dock.bill_dock chunk-send \
  --address STARTING_BILL_ADDRESS \
  --kind bearer-note \
  --input .note-vault/notes/NOTE_ID/artifacts/bearer-note.rgbn
```

Record the capsule byte count and SHA-256 from redacted output. Do not print or
decode the claim secret. Inventory must become `bearer-held`; the onboard
display may show `$5.00 / NOTE` only after the complete file is durable.

## 3. Prove the offline physical handoff

Disconnect or gate the docks' network. Keep both laptop docks out of the tap
path. Place the bills close together, press the empty receiver once, and
release immediately. Expected receiver milestones:

```text
receiver armed for 15s
qualifying peer ... RSSI >= -60
receiving kind=4
bearer note promoted for offline relay
receive complete
```

The sender must report `sender complete`. Reboot the receiver and require a
boot line restoring the same kind/session/size. Repeat additional bill-to-bill
hops if desired; each hop moves the same bearer capability, not a new RGB
transition.

## 4. Extract and verify at the destination dock

After reconnecting the destination dock, pull the note from the final bill:

```bash
.venv/bin/python -m dock.bill_dock chunk-receive \
  --address DESTINATION_BILL_ADDRESS \
  --kind bearer-note \
  --output .note-vault/incoming/received.rgbn

sha256sum .note-vault/incoming/received.rgbn
```

The full digest must equal the source digest before the capsule is parsed or a
Wallet B invoice is created. An interrupted extraction does not consume the
bill copy; retry extraction, not funding.

## 5. Prepare the Wallet B redemption plan

```bash
set -a; source .env.b; set +a
.venv/bin/python -m scripts.note_wallet_live prepare-redemption-plan \
  --capsule .note-vault/incoming/received.rgbn \
  --expected-sha256 EXPECTED_CAPSULE_SHA256
```

This creates Wallet B's fresh transport-free invoice only after capsule and
vault validation. Review note ID, recipient, invoice hash, amount, fee, expiry,
and empty endpoints.

If the note lacks a free colorable UTXO, do not reuse the redemption
confirmation. Reconcile the known pre-broadcast rejection, then prepare,
confirm, and settle a separate capacity transaction:

```bash
.venv/bin/python -m scripts.note_wallet_live reconcile-redemption \
  --note-id NOTE_ID
.venv/bin/python -m scripts.note_wallet_live prepare-redemption-capacity \
  --note-id NOTE_ID
.venv/bin/python -m scripts.note_wallet_live confirm-redemption-capacity \
  --note-id NOTE_ID --plan-id CAPACITY_PLAN_ID
.venv/bin/python -m scripts.note_wallet_live refresh-redemption-capacity \
  --note-id NOTE_ID
.venv/bin/python -m scripts.note_wallet_live prepare-redemption-after-capacity \
  --capsule .note-vault/incoming/received.rgbn \
  --expected-sha256 EXPECTED_CAPSULE_SHA256
```

## 6. Confirm once, import, and settle

Only after reviewing the fresh plan and obtaining explicit authorization:

```bash
.venv/bin/python -m scripts.note_wallet_live confirm-redemption \
  --note-id NOTE_ID \
  --plan-id REDEMPTION_PLAN_ID
```

This consumes the confirmation before the send, records the broadcast and
exact consignment, and imports that retained consignment into Wallet B. If
import alone failed after a recorded broadcast, use `recover-redemption`; do
not confirm or send again.

```bash
.venv/bin/python -m scripts.note_wallet_live recover-redemption \
  --note-id NOTE_ID
```

Wait for one Mutinynet confirmation and run the read-only settlement gate:

```bash
.venv/bin/python -m scripts.note_wallet_live refresh-redemption \
  --note-id NOTE_ID
```

Acceptance requires exactly one matching txid, `receive_witness`, one
5,000,000-unit assignment, and Wallet B's settled/future/spendable balance at
the recorded pre-balance plus 5,000,000. Terminal state must be `REDEEMED`
with claim `SPENT`. Repeating this command returns the recorded evidence
without reopening the wallet.

## 7. Demo closeout and evidence

- Show both RGB txids, not only the Bitcoin capacity txid.
- Show source/extracted capsule hashes and redemption consignment hash.
- State plainly: the offline segment relayed a bearer capability; settlement
  required the vault and Mutinynet later.
- State the trusted-vault, copy, ESP32 extraction, QVAC, and WDK limitations.
- Never run another live spend merely to improve a screenshot.

The accepted reference values are in [`LIVE-EVIDENCE.md`](LIVE-EVIDENCE.md),
and recovery rationale is in [`THREAT-MODEL.md`](THREAT-MODEL.md).
