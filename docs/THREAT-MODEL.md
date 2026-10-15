# Threat model — offline RGB bearer-note prototype

Updated: 2026-10-15
Scope: Mutinynet hackathon prototype, not production custody

## Security objective

Move a compact capability between ESP32 bills while offline, then allow one
later RGB redemption into a newly selected wallet. Prevent accidental duplicate
sends and misleading UI states. Expose trust and copy risk instead of claiming
that the prototype solves offline double spending.

## Assets

| Asset | Location | Required protection |
| --- | --- | --- |
| Wallet A/B mnemonics and datadirs | role-scoped laptop environments | mode `0600`, one process per datadir, never in BLE or Git |
| Disposable note mnemonic/datadir | ignored `.note-vault/notes/<id>/` | vault-only, one open process, never placed on a bill |
| Bearer claim secret | canonical capsule on one or more physical bills | never log, advertise, put in URLs, or commit |
| RGB invoice/consignment | private dock storage and opaque BLE chunks | byte-exact hashing, bounded size, retained recovery copy |
| Confirmation authority | human-entered `CONFIRM <plan-id>` | fresh, exact, one-use, amount/recipient/expiry-bound |
| Public evidence | docs and website | txids/hashes/status only; no secret material |

## Trust boundaries

- **Human:** chooses the physical bill and independently authorizes every
  spend-capable plan.
- **Dock:** trusted to protect wallet state, validate inventory, and enforce
  recovery/no-resend rules.
- **Note vault:** trusted custodian of disposable wallet N. It can steal or
  censor every active note; this is the largest deliberate prototype trust.
- **ESP32 bill:** non-custodial transport/display device. It stores an opaque
  bearer capability but cannot validate RGB or protect against physical key
  extraction.
- **BLE proximity:** convenience gate, not identity. RSSI ≥ −60 dBm and one
  press reduce accidental pairing; they do not authenticate a person.
- **Mutinynet/Esplora:** external settlement/indexing dependency. Read errors
  may be retried; ambiguous sends may not.

## Threats and current controls

| Threat | Current control | Residual risk |
| --- | --- | --- |
| Copied capsule redeemed twice | salted claim hash, atomic reservation, first recorded send wins, durable `SPENT` state | Fastest valid copy wins; offline holders cannot detect the copy |
| Ambiguous send repeated | confirmation consumed before send; `AMBIGUOUS` blocks automatic retry; broadcast/journal persisted before success | Manual reconciliation may be required |
| Import or BLE staging failure causes resend | exact consignment retained; stage/import-only recovery paths cannot call send | Operator must follow the recovery instruction |
| Wrong/duplicate Wallet B transfer marked settled | exact txid, `receive_witness`, one 5,000,000-unit assignment, and recorded balance delta are all required | Relies on pinned rgb-lib semantics and indexer correctness |
| Malformed or oversized BLE payload | strict frame version/kind/session/order/CRC; 640 KiB limit; atomic promotion | CRC32 is corruption detection, not adversarial authentication |
| Stale/orphaned device file overwritten | inventory v3 `recovery-blocked`; explicit discard only | Physical attacker can still alter flash |
| Fake capsule amount shown as authentic | vault revalidates canonical capsule and claim hash at redemption | Firmware cannot authenticate issuer offline; display is provisional |
| Remote use of LAN dock UI | loopback default; explicit `0.0.0.0` warning; no port forwarding | No web authentication; any trusted-LAN client can operate it |
| Secret leaked through logs/docs | redacted capsule view, private files, public allowlist build | Host compromise remains fatal |
| Vault unavailable or malicious | honest UI and direct-mode fallback | Redemption can be censored; vault can spend active notes |

## Fail-closed rules

1. No valid inventory metadata means no new artifact.
2. No exact fresh confirmation means no spend.
3. A consumed confirmation cannot authorize a replacement plan.
4. Unknown send outcome means no automatic resend.
5. A retained artifact is recovery state, never `empty`.
6. Wallet B becomes `REDEEMED` only after exact settlement evidence.
7. Clearing a bill never rewrites the vault's claim or wallet history.

## Production gaps

Before any Mainnet or real-value claim: remove single-vault custody or harden it
with threshold/HSM controls; add offline issuer signatures; add authenticated
device pairing and web access; protect claim material with a secure element;
define revocation/expiry/privacy policy; complete adversarial and restart fault
testing; and obtain independent RGB/security review.
