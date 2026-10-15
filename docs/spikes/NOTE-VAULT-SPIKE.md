# M1 disposable-wallet RGB spike

Started: 2026-10-15
Network target: Mutinynet/custom signet
Current mode: live disposable-wallet bearer round trip accepted

## Current result

M0 is closed. The isolated fake slice first froze the disposable-wallet
ordering and confirmation contract; the live path then funded the disposable
note, relayed its bearer capsule over the two physical bills without docks or
network service, redeemed it once, and settled the exact allocation into
Wallet B. The canonical current evidence is in
[../LIVE-EVIDENCE.md](../LIVE-EVIDENCE.md).

The fake round trip proves the following software behavior:

1. Create a fresh synthetic note wallet and a transport-free $5 invoice.
2. Display an immutable Wallet A -> note funding plan.
3. Require and consume its exact one-use confirmation before the fake backend.
4. Import the exact fake OOB consignment and mark the note active.
5. Create Wallet B's invoice only after activation.
6. Display and confirm the note -> Wallet B redemption plan.
7. Import the exact fake redemption consignment.
8. Replay returns `BOUNCED` with the winning fake txid and causes no third send.
9. An injected ambiguous backend outcome consumes the plan and cannot retry.

All output is labelled `fake-no-wallet-no-network-no-broadcast`. Fake txids and
consignments are deterministic hashes of synthetic data and are not Bitcoin or
RGB evidence.

## Local acceptance evidence

Validated on 2026-10-15 against commit `303134c8ff153baf509a4f9cdff67d40231a727c`
plus the uncommitted M1 spike:

- focused spike tests: `4 passed`;
- complete Python suite: `92 passed`;
- Ruff checks: passed;
- browser JavaScript syntax check: passed;
- `git diff --check`: passed;
- fake round trip: two transitions, Wallet A `50 -> 45`, Wallet B `50 -> 55`,
  disposable note `5 -> 0`;
- replay: `BOUNCED`, retained winning fake txid, `new_send=false`.

This evidence accepts only the fake-backend domain and confirmation slice. It
does not satisfy the live M1 gate below.

## Run the fake slice

```bash
.venv/bin/python -m scripts.note_wallet_spike fake-roundtrip
```

The command displays two separate immutable plans and asks for each exact
`CONFIRM <plan-id>` phrase. It never accepts a general yes/no response.

## First live preparation

One fresh disposable Mutinynet wallet was created on 2026-10-15 without
printing its mnemonic. Its wallet, 0600 mnemonic file, invoice, manifest, and
plan live under ignored `.note-vault/` state. The selected note is:

- note ID: `758186be-791d-4c8c-92f5-a8c4194ac856`;
- state: `ACTIVE` (`settled`);
- invoice SHA-256:
  `4b11af2a12972f58288b154c95d64ac57afaf9dd52d4b7d7eb6da8d82d50e4f0`;
- original funding plan ID: `60ff9b5f-e10e-4a35-94ae-b0f5fe5bf6b8`
  (`SUPERSEDED`, never confirmed);
- current funding plan ID: `4bed5c40-9292-4fec-a033-cb8bdb487c07`;
- current plan validity: 2026-10-15 19:01:53–20:01:53 CEST;
- Wallet A balance bound by the plan: `50,000,000` base units;
- exact funding amount: `5,000,000` base units (5 USDT);
- transport endpoints: empty;
- donation: true;
- exact confirmation consumed: 2026-10-15 19:14:26 CEST;
- funding txid:
  `b325cbe40c282e661c40ff8555cb6cb0fc9867a32855feb8b17d7756c9a83963`;
- retained consignment: 14,347 bytes, SHA-256
  `dc44a8cf9754c5469e55d38de7e49fc61b01ba28279975d615660f81cd2f03a9`;
- sender rgb-lib batch transfer index: `8`;
- note rgb-lib batch transfer index: `1`, `receive_witness`, `settled`;
- Mutinynet confirmation: block `3508184`, block hash
  `00000138a4bbdc898a41a5294c7de13a3910d43f545b135913d8391a297d29d7`,
  block time 2026-10-15 19:15:27 CEST;
- settlement verified: 2026-10-15 19:26:34 CEST, with exactly `5,000,000`
  settled, future, and spendable units;
- broadcast: true, exactly once; the plan is consumed and cannot be replayed.

The first preparation attempt received an Esplora HTTP 429. Recovery retained
the exact same wallet and later the exact same invoice; it did not create a
second disposable wallet. Loading and parsing the note wallet is now offline,
while Wallet A uses one online check to bind its current spendable balance.

The note initially had zero vanilla sats. It now has one confirmed, unspent
20,000-sat vanilla UTXO. Accepted prior transfers measured a 1,000-sat witness
output plus a 395-sat fee, so one redemption needs at least 1,395 spendable
vanilla sats. The 2,000-sat safety target therefore passes. The renewed plan
reused the same invoice and rechecked Wallet A's 50,000,000-unit balance before
the exact confirmation. The resulting consignment was retained and imported
into the disposable wallet. Mutinynet confirmed the transaction, and the
bounded note refresh verified the matching `receive_witness` row as `settled`
with exactly `5,000,000` settled, future, and spendable units. The durable note
state is now `ACTIVE`.

## Offline bearer capsule preparation

At 2026-10-15 19:31:29 CEST the active note produced exactly one bearer
capsule v1. This operation opened no wallet, created no Wallet B invoice, and
broadcast no transaction. Its redacted evidence is:

- artifact: ignored private `bearer-note.rgbn`, mode `0600`, 603 bytes;
- artifact SHA-256:
  `a38775213ac972dae871906e37b09750e25e4fe71a2d28a9bd4bd3fca4615144`;
- canonical-envelope integrity digest:
  `98f6892130ca183c6fc83b3e3cdedb730a228f6c143b85b199a24f1e5e5b377e`;
- network: `mutinynet`; amount: `5,000,000` base units / 500 cents;
- funding evidence: the exact txid and funding-consignment SHA-256 above;
- claim authority: one random 256-bit secret carried only inside the ignored
  capsule; the vault manifest stores a random salt and domain-separated
  SHA-256 hash, never the plaintext secret;
- wallet material: no mnemonic, private key, wallet database, invoice, or
  funding consignment is embedded;
- issuer authentication: `vault-online-only`.

Running capsule preparation a second time returned the same 603-byte artifact
and digest with `created=false`; it did not mint a second claim capability.
The SHA-256 envelope detects corruption but does not authenticate the issuer.
Ed25519 is intentionally deferred because no suitable dependency is currently
installed. Until a signature is added, a future bill display must treat the
amount as unverified offline and the vault must authenticate the capability at
redemption. The capsule was later loaded onto WEMOS, relayed offline to TTGO,
and extracted at the destination dock with the same 603-byte size and exact
SHA-256.

## Live redemption acceptance

The separately confirmed live redemption completed on 2026-10-15. Its exact
evidence is:

- destination extraction: 603 bytes, SHA-256
  `a38775213ac972dae871906e37b09750e25e4fe71a2d28a9bd4bd3fca4615144`;
- capacity txid:
  `089a8231b4c8916d9b1aac3cfd445b11dc9ec87583f15cd8eeec072b4f0734bb`,
  confirmed before the final plan and creating one free colorable UTXO;
- immutable redemption plan ID: `95c33df6-d74a-496d-9867-aab341c6be87`;
- redemption txid:
  `dfe138b0983f6238103d2e5c57bf0848fdd5b7fd733162299fb4c6e5e9f427bf`;
- exact redemption consignment: 15,057 bytes, SHA-256
  `7f3915724cffed5aee99ad93a10b97bd2b895595ca4c473783672a6d13fad704`;
- Wallet B transfer: batch index `10`, `receive_witness`, exactly one
  5,000,000-unit assignment, `settled`;
- Wallet B balance delta: `50,000,000 -> 55,000,000` base units, with
  settled/future/spendable all equal to `55,000,000`;
- Mutinynet inclusion: block `3508531`, block time 2026-10-15 22:24:53 CEST;
  at verification tip `3508541` the transaction had 11 confirmations;
- settlement verified: 2026-10-15 22:30:20 CEST;
- durable terminal state: plan `REDEEMED`, manifest `REDEEMED`, bearer claim
  `SPENT`, with journal order `BROADCAST_RECORDED`,
  `REDEMPTION_IMPORTED`, `REDEEMED`.

The settlement refresh is read-only with respect to spending: it can refresh
Wallet B and persist proof, but cannot call send or create another RGB
transition. Replaying it after `REDEEMED` returns the recorded settlement
without reopening a wallet. The consumed funding, capacity, and redemption
confirmations must never be reused.

## Fresh-wallet invoice discovery

The first live preparation attempt established that a brand-new rgb-lib wallet
does not know the selected USDT contract and rejects an asset-specific witness
invoice with `AssetNotFound`. The recovery path therefore uses a transport-free
`ANY` witness invoice for initial funding. Wallet A still binds the immutable
send plan to the exact USDT asset ID and exactly `5,000,000` base units. This is
the same bootstrap distinction used when a wallet first receives an unknown
RGB asset; it does not add an online transport endpoint.
