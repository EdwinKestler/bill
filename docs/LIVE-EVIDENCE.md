# Live evidence ledger

Updated: 2026-10-15 22:30 CEST
Network: Mutinynet/custom signet only

This is the canonical public index of real RGB and physical-transport evidence
for the project. It contains no mnemonic, claim secret, private key, capsule
bytes, or wallet datadir. Historical test records remain in their dedicated
documents; when summary copy disagrees with this ledger, this ledger and the
wallet journals are authoritative.

## Offline bearer-note vertical slice

The selected demo makes exactly two RGB state transitions. Between them, the
ESP32 bills relay a bearer capability over BLE; that relay is not itself an
RGB transition.

| Stage | Accepted evidence |
| --- | --- |
| Disposable note | note ID `758186be-791d-4c8c-92f5-a8c4194ac856`; isolated ignored wallet N |
| Wallet A → note N | txid [`b325cbe40c282e661c40ff8555cb6cb0fc9867a32855feb8b17d7756c9a83963`](https://mutinynet.com/tx/b325cbe40c282e661c40ff8555cb6cb0fc9867a32855feb8b17d7756c9a83963); exactly 5,000,000 units; funding consignment 14,347 bytes; SHA-256 `dc44a8cf9754c5469e55d38de7e49fc61b01ba28279975d615660f81cd2f03a9` |
| Funding settlement | note transfer `receive_witness`, batch `1`, `settled`; block `3508184`; note settled/future/spendable all 5,000,000 |
| Bearer capsule | canonical v1; 603 bytes; SHA-256 `a38775213ac972dae871906e37b09750e25e4fe71a2d28a9bd4bd3fca4615144`; no mnemonic or wallet backup |
| Offline physical relay | WEMOS → TTGO; kind `0x04`; session `0x3de6f5e7`; 4 BLE frames; TTGO restored the same artifact after reboot |
| Destination extraction | 603 bytes; SHA-256 exactly matched the source capsule before parsing or planning |
| Redemption capacity | txid [`089a8231b4c8916d9b1aac3cfd445b11dc9ec87583f15cd8eeec072b4f0734bb`](https://mutinynet.com/tx/089a8231b4c8916d9b1aac3cfd445b11dc9ec87583f15cd8eeec072b4f0734bb); one 8,000-sat free colorable UTXO created by its own confirmation gate |
| Note N → Wallet B | plan `95c33df6-d74a-496d-9867-aab341c6be87`; txid [`dfe138b0983f6238103d2e5c57bf0848fdd5b7fd733162299fb4c6e5e9f427bf`](https://mutinynet.com/tx/dfe138b0983f6238103d2e5c57bf0848fdd5b7fd733162299fb4c6e5e9f427bf); consignment 15,057 bytes; SHA-256 `7f3915724cffed5aee99ad93a10b97bd2b895595ca4c473783672a6d13fad704` |
| Wallet B settlement | exact txid match; batch `10`; `receive_witness`; one 5,000,000-unit assignment; balance 50,000,000 → 55,000,000; settled/future/spendable all 55,000,000 |
| Chain check | redemption included at block `3508531`, block time 2026-10-15 22:24:53 CEST; 11 confirmations at verification tip `3508541` |
| Durable terminal state | plan `REDEEMED`; manifest `REDEEMED`; claim `SPENT`; journal order `BROADCAST_RECORDED` → `REDEMPTION_IMPORTED` → `REDEEMED` |

The final settlement refresh is idempotent: replay returned the recorded result
without reopening Wallet B or creating another send. The private plan,
manifest, and journal files were mode `0600` at acceptance.

## Accepted direct-mode fallback

The original human-first invoice/consignment path remains a working fallback.
It creates Wallet B's invoice first, relays that invoice to the sender bill,
broadcasts once after exact confirmation, then relays the exact consignment
back to Wallet B.

| Date | Amount | Txid | Result |
| --- | ---: | --- | --- |
| 2026-10-11 | 20 USDT | [`97885ddffc2305aabf1574d78be8cf102d0afb1f104529c817fc4dcff541a1fb`](https://mutinynet.com/tx/97885ddffc2305aabf1574d78be8cf102d0afb1f104529c817fc4dcff541a1fb) | 12,496-byte consignment crossed BLE in 70 frames; Wallet A 80→60, Wallet B 20→40; settled |
| 2026-10-15 | 5 USDT | [`1f8953866f24f5b64ec02875aa51507fc6c76777646680eddfb573247cf5d45f`](https://mutinynet.com/tx/1f8953866f24f5b64ec02875aa51507fc6c76777646680eddfb573247cf5d45f) | browser-driven inventory-v2 flow; both wallets reached 50 USDT; settled |

Additional historical settled rows are listed in
[`spikes/M0-BASELINE.md`](spikes/M0-BASELINE.md). They are regression history,
not separate claims about the bearer-note architecture.

## What this proves

- real RGB funding and redemption using rgb-lib on Mutinynet;
- empty RGB transport endpoints and exact out-of-band consignments;
- byte-exact BLE transport and reboot persistence on two ESP32 profiles;
- an unknown-at-issuance final wallet chosen only at redemption;
- one-use confirmation, durable recovery records, and no automatic resend;
- exact Wallet B assignment and settled-balance verification.

## What this does not prove

- Mainnet safety or real-dollar value;
- trustless custody: the note vault retains each disposable wallet key;
- offline double-spend prevention: a copied capsule is first-redemption-wins;
- offline issuer authentication: capsule v1 has integrity hashing but no
  device-verifiable signature;
- a completed QVAC action integration or WDK integration;
- production web authentication, secure-element resistance, or network-level
  anonymity.

## Local validation at acceptance

- Python: `125 passed`;
- focused settlement tests: `21 passed`;
- `git diff --check`: passed;
- Palimnex parent index: incremental, fresh, deep validation passed;
- public evidence intentionally excludes ignored `.note-vault/` contents.
